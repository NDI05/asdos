from __future__ import annotations

import io
import json
import logging
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .dependencies import require_actor, require_owner_scope, require_writer
from .models import (
    Answer,
    AnswerMappingRevision,
    AnswerRegionLink,
    Artifact,
    Assessment,
    AssessmentRevision,
    AuditEvent,
    Document,
    DocumentLayoutRevision,
    GradeProposal,
    IdentityConfirmation,
    ModelRun,
    Page,
    PageImageRevision,
    PipelineJob,
    QuestionRevision,
    Region,
    ReviewItem,
    ReviewRevision,
    Submission,
    TranscriptionRevision,
    now_utc,
)
from .schemas import (
    IdentityConfirmationInput,
    MappingInput,
    PageRotationInput,
    RegionInput,
    RetryRequest,
    SubmissionCreate,
    TranscriptionInput,
)
from .services import add_job, canonical_hash, publish_job_outbox
from .storage import artifact_store
from .model_adapters import GRADER_PROMPT_VERSION, GRADING_EVIDENCE_VERSION, MODEL_REVISION, model_status, transcription_flags, transcriber_fingerprint
from apps.worker.render_pdf import RENDER_POLICY_VERSION

router = APIRouter(prefix="/api/v1", tags=["submissions"])
PENDING_ID_PREFIX = "__asdos_pending__"
logger = logging.getLogger(__name__)


def _submission_scope(db: Session, actor, submission_id: str, *, lock: bool = False) -> tuple[Submission, Assessment]:
    submission = (db.scalar(select(Submission).where(Submission.id == submission_id).with_for_update())
                  if lock else db.get(Submission, submission_id))
    if not submission:
        raise HTTPException(status_code=404, detail={"code": "RESOURCE_NOT_FOUND"})
    assessment = require_owner_scope(db, actor, submission.assessment_id)
    return submission, assessment


async def _store_pdf(upload: UploadFile) -> tuple[str, str, int]:
    content_length = upload.headers.get("content-length")
    if content_length and int(content_length) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail={"code": "PDF_TOO_LARGE"})
    prefix = await upload.read(5)
    await upload.seek(0)
    if prefix != b"%PDF-":
        raise HTTPException(status_code=415, detail={"code": "NOT_A_PDF"})
    try:
        return artifact_store.put_stream(upload.file, max_bytes=settings.max_upload_bytes)
    except ValueError as exc:
        if str(exc) == "UPLOAD_TOO_LARGE":
            raise HTTPException(status_code=413, detail={"code": "PDF_TOO_LARGE"}) from exc
        raise
    finally:
        await upload.close()


def _job_fingerprint(document_id: str, sha256: str, *, scope_revision_id: str | None = None) -> str:
    return canonical_hash({"document_id": document_id, "scope_revision_id": scope_revision_id,
                           "sha256": sha256, "stage": "pdfium-render", "dpi": settings.render_dpi,
                           "max_pixels": settings.max_render_pixels, "renderer": "pypdfium2",
                           "render_policy": RENDER_POLICY_VERSION})


def _job_summary(job: PipelineJob) -> dict:
    return {"id": job.id, "kind": job.kind, "stage": job.stage, "status": job.status,
            "answer_id": job.answer_id, "document_id": job.document_id, "attempt": job.attempt,
            "progress": {"completed": job.progress_current, "total": job.progress_total,
                         "unit": ("pages" if job.kind in {"document_render", "question_import"} or
                                  (job.kind == "analyze_answers" and job.stage == "locate_answers")
                                  else "regions" if job.kind == "analyze_answers" else "answers")},
            "error_code": job.error_code, "retryable": job.status == "failed" and job.attempt < 3,
            "cancel_requested": job.cancel_requested, "created_at": job.created_at.isoformat(),
            "finished_at": job.finished_at.isoformat() if job.finished_at else None}


@router.get("/assessments/{assessment_id}/submissions")
def list_submissions(assessment_id: str, db: Session = Depends(get_db), actor=Depends(require_actor)):
    assessment = require_owner_scope(db, actor, assessment_id)
    rows = db.scalars(select(Submission).where(Submission.assessment_id == assessment.id).order_by(Submission.created_at.desc())).all()
    submission_ids = [row.id for row in rows]
    answer_counts = dict(db.execute(select(Answer.submission_id,func.count(Answer.id)).where(
        Answer.submission_id.in_(submission_ids)).group_by(Answer.submission_id)).all()) if submission_ids else {}
    document_ids = [row.active_document_id for row in rows if row.active_document_id]
    latest_jobs = {}
    if document_ids:
        for job in db.scalars(select(PipelineJob).where(PipelineJob.document_id.in_(document_ids),
                PipelineJob.kind.in_(['document_render','analyze_answers','grade_answer'])).order_by(PipelineJob.created_at.desc(),PipelineJob.attempt.desc())):
            latest_jobs.setdefault((job.document_id,job.kind,job.answer_id),job)
    result = []
    for submission in rows:
        document = db.get(Document, submission.active_document_id) if submission.active_document_id else None
        from .models import GradeSnapshot
        final_snapshot = db.scalar(select(GradeSnapshot).where(GradeSnapshot.submission_id == submission.id).order_by(GradeSnapshot.approved_at.desc()).limit(1))
        grades = [job for (doc_id,kind,_),job in latest_jobs.items() if document and doc_id == document.id and kind == 'grade_answer']
        analysis = latest_jobs.get((document.id,'analyze_answers',None)) if document else None
        active_grade = next((job for job in grades if job.status in ('queued','running')),None)
        processing = (analysis if analysis and analysis.status in ('queued','running','failed') else active_grade or analysis
                      or (latest_jobs.get((document.id,'document_render',None)) if document else None))
        result.append({
            "id": submission.id,
            "external_student_id": submission.external_student_id if submission.identity_status == "confirmed" else "",
            "display_name": submission.display_name if submission.identity_status == "confirmed" else "Belum dikonfirmasi",
            "attempt_no": submission.attempt_no,
            "identity_status": submission.identity_status,
            "identity_candidate": ((document.analysis_result or {}).get('identity_candidate') if document and submission.identity_status != 'confirmed' else None),
            "status": submission.status,
            "document_id": document.id if document else None,
            "page_count": document.page_count if document else 0,
            "document_status": document.validation_status if document else "missing",
            "document_filename": document.original_filename if document else None,
            "processing": _job_summary(processing) if processing else None,
            "grade_progress": {"succeeded":sum(job.status=='succeeded' for job in grades),"failed":sum(job.status=='failed' for job in grades),
                               "scheduled":len(grades),"total":answer_counts.get(submission.id,0)},
            "final_score": str(final_snapshot.final_score) if final_snapshot else None,
            "created_at": submission.created_at.isoformat(),
        })
    return {"assessment_id": assessment.id, "items": result}


@router.post("/assessments/{assessment_id}/submissions", status_code=201)
def create_submission(assessment_id: str, body: SubmissionCreate, db: Session = Depends(get_db), actor=Depends(require_writer)):
    assessment = db.scalar(select(Assessment).where(Assessment.id == assessment_id).with_for_update())
    if not assessment:
        raise HTTPException(status_code=404, detail={"code": "RESOURCE_NOT_FOUND"})
    require_owner_scope(db, actor, assessment.id)
    revision = db.get(AssessmentRevision, assessment.active_revision_id) if assessment.active_revision_id else None
    if not revision or revision.status != "approved":
        raise HTTPException(status_code=409, detail={"code": "APPROVED_ASSESSMENT_REQUIRED"})
    duplicate = db.scalar(select(Submission).where(
        Submission.assessment_id == assessment.id,
        Submission.external_student_id == body.external_student_id,
        Submission.attempt_no == body.attempt_no,
    ))
    if duplicate:
        raise HTTPException(status_code=409, detail={"code": "DUPLICATE_STUDENT_ATTEMPT"})
    submission = Submission(
        assessment_id=assessment.id,
        assessment_revision_id=revision.id,
        external_student_id=body.external_student_id,
        display_name=body.display_name,
        attempt_no=body.attempt_no,
        identity_status="pending",
        status="awaiting_document",
    )
    db.add(submission)
    db.flush()
    from .models import QuestionRevision
    for question in db.scalars(select(QuestionRevision).where(QuestionRevision.assessment_revision_id == revision.id)).all():
        db.add(Answer(submission_id=submission.id, stable_question_id=question.stable_question_id))
    db.add(AuditEvent(
        assessment_id=assessment.id,
        actor_id=actor.id,
        action="submission.created",
        resource_id=submission.id,
        new_revision=revision.id,
        metadata_json={"attempt_no": submission.attempt_no},
    ))
    db.commit()
    return {"id": submission.id, "assessment_revision_id": revision.id, "identity_status": submission.identity_status,
            "status": submission.status, "version": submission.version}


@router.post("/assessments/{assessment_id}/submissions/unidentified", status_code=201)
def create_unidentified_submission(assessment_id: str, db: Session = Depends(get_db), actor=Depends(require_writer)):
    """Reserve a distinct submission without claiming a student's identity."""
    return create_submission(assessment_id, SubmissionCreate(
        external_student_id=PENDING_ID_PREFIX + uuid4().hex, display_name="Belum dikonfirmasi"), db, actor)


@router.post("/submissions/{submission_id}/documents", status_code=202)
async def upload_submission_pdf(
    submission_id: str,
    file: UploadFile = File(...),
    auto_process: bool = Form(True),
    auto_grade: bool = Form(False),
    db: Session = Depends(get_db),
    actor=Depends(require_writer),
):
    submission, assessment = _submission_scope(db, actor, submission_id, lock=True)
    key, digest, size = await _store_pdf(file)
    document = Document(
        assessment_id=assessment.id,
        submission_id=submission.id,
        kind="student_answer",
        storage_key=key,
        original_filename=(file.filename or "jawaban.pdf")[:255],
        sha256=digest,
        byte_size=size,
        validation_status="pending",
        auto_process=auto_process,
        analysis_result={"auto_grade_requested": bool(auto_grade and auto_process)},
    )
    db.add(document)
    db.flush()
    db.add(Artifact(
        assessment_id=assessment.id,
        document_id=document.id,
        storage_key=key,
        kind="original_pdf",
        sha256=digest,
        byte_size=size,
        parent_ids=[],
    ))
    prior_document = submission.active_document_id
    submission.active_document_id = document.id
    submission.active_identity_confirmation_id = None
    submission.identity_status = "pending"
    submission.active_review_id = None
    submission.status = "validating_pdf"
    submission.version += 1
    job = add_job(
        db,
        assessment_id=assessment.id,
        document_id=document.id,
        submission_id=submission.id,
        kind="document_render",
        input_fingerprint=_job_fingerprint(document.id, digest),
    )
    db.add(AuditEvent(
        assessment_id=assessment.id,
        actor_id=actor.id,
        action="submission.document_replaced" if prior_document else "submission.document_uploaded",
        resource_id=submission.id,
        previous_revision=prior_document,
        new_revision=document.id,
        metadata_json={"sha256": digest, "bytes": size},
    ))
    db.commit()
    publish_job_outbox(db, job.id)
    db.refresh(document)
    db.refresh(job)
    return {
        "document_id": document.id,
        "sha256": document.sha256,
        "bytes": document.byte_size,
        "page_count": document.page_count,
        "validation_status": document.validation_status,
        "job": {"id": job.id, "status": job.status, "error_code": job.error_code},
    }


@router.post("/assessments/{assessment_id}/question-imports", status_code=202)
async def import_question_pdf(
    assessment_id: str,
    file: UploadFile = File(...),
    assessment_revision_id: str = Form(...),
    db: Session = Depends(get_db),
    actor=Depends(require_writer),
):
    assessment = require_owner_scope(db, actor, assessment_id)
    revision = db.get(AssessmentRevision, assessment_revision_id)
    if not revision or revision.assessment_id != assessment.id or revision.status != "draft":
        raise HTTPException(status_code=409, detail={"code": "DRAFT_REVISION_SCOPE_REQUIRED"})
    key, digest, size = await _store_pdf(file)
    document = Document(
        assessment_id=assessment.id,
        draft_assessment_revision_id=revision.id,
        kind="question_source",
        storage_key=key,
        original_filename=(file.filename or "soal.pdf")[:255],
        sha256=digest,
        byte_size=size,
        validation_status="pending",
    )
    db.add(document)
    db.flush()
    db.add(Artifact(
        assessment_id=assessment.id,
        document_id=document.id,
        storage_key=key,
        kind="question_source_pdf",
        sha256=digest,
        byte_size=size,
        parent_ids=[revision.id],
    ))
    job = add_job(
        db,
        assessment_id=assessment.id,
        document_id=document.id,
        draft_assessment_revision_id=revision.id,
        kind="question_import",
        input_fingerprint=_job_fingerprint(document.id, digest, scope_revision_id=revision.id),
    )
    db.add(AuditEvent(
        assessment_id=assessment.id,
        actor_id=actor.id,
        action="assessment.question_pdf_imported",
        resource_id=document.id,
        new_revision=revision.id,
        metadata_json={"sha256": digest, "bytes": size, "scope": "assessment_draft"},
    ))
    db.commit()
    publish_job_outbox(db, job.id)
    db.refresh(document)
    db.refresh(job)
    return {"document_id": document.id, "revision_id": revision.id, "status": document.validation_status,
            "job": {"id": job.id, "status": job.status, "error_code": job.error_code},
            "extracted_text": document.extracted_text}


@router.get("/documents/{document_id}")
def get_document(document_id: str, db: Session = Depends(get_db), actor=Depends(require_actor)):
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail={"code": "RESOURCE_NOT_FOUND"})
    require_owner_scope(db, actor, document.assessment_id)
    return {
        "id": document.id,
        "kind": document.kind,
        "sha256": document.sha256,
        "bytes": document.byte_size,
        "page_count": document.page_count,
        "validation_status": document.validation_status,
        "extracted_text": document.extracted_text if document.kind == "question_source" else None,
        "active_layout_revision_id": document.active_layout_revision_id,
        "original_url": f"/api/v1/documents/{document.id}/content",
    }


@router.get("/documents/{document_id}/content")
def get_document_content(document_id: str, db: Session = Depends(get_db), actor=Depends(require_actor)):
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail={"code": "RESOURCE_NOT_FOUND"})
    require_owner_scope(db, actor, document.assessment_id)
    data = artifact_store.read(document.storage_key)
    return StreamingResponse(io.BytesIO(data), media_type="application/pdf", headers={"Content-Disposition": "inline; filename=source.pdf", "Cache-Control": "private, no-store"})


@router.post("/submissions/{submission_id}/confirm-identity")
def confirm_identity(submission_id: str, body: IdentityConfirmationInput, db: Session = Depends(get_db), actor=Depends(require_writer)):
    if body.external_student_id.startswith(PENDING_ID_PREFIX):
        raise HTTPException(status_code=422, detail={"code":"INVALID_STUDENT_ID"})
    submission, assessment = _submission_scope(db, actor, submission_id, lock=True)
    if submission.version != body.expected_submission_version:
        raise HTTPException(status_code=409, detail={"code": "STALE_SUBMISSION", "current_version": submission.version})
    document = db.get(Document, body.document_id)
    if not document or document.id != submission.active_document_id or document.submission_id != submission.id or document.sha256 != body.document_hash:
        raise HTTPException(status_code=409, detail={"code": "IDENTITY_DOCUMENT_MISMATCH"})
    duplicate = db.scalar(select(Submission).where(
        Submission.assessment_id == assessment.id,
        Submission.external_student_id == body.external_student_id,
        Submission.attempt_no == submission.attempt_no,
        Submission.id != submission.id,
    ))
    if duplicate:
        raise HTTPException(status_code=409, detail={"code": "DUPLICATE_STUDENT_ATTEMPT"})
    confirmation = IdentityConfirmation(
        submission_id=submission.id,
        document_id=document.id,
        document_hash=document.sha256,
        identity_snapshot={"external_student_id": body.external_student_id, "display_name": body.display_name},
        confirmed_by=actor.id,
    )
    db.add(confirmation)
    db.flush()
    prior = submission.external_student_id
    submission.external_student_id = body.external_student_id
    submission.display_name = body.display_name
    submission.active_identity_confirmation_id = confirmation.id
    submission.identity_status = "confirmed"
    submission.status = "needs_mapping" if document.validation_status == "valid" else "validating_pdf"
    submission.version += 1
    db.add(AuditEvent(
        assessment_id=assessment.id,
        actor_id=actor.id,
        action="submission.identity_confirmed",
        resource_id=submission.id,
        previous_revision=prior,
        new_revision=confirmation.id,
        metadata_json={"document_id": document.id, "document_hash": document.sha256},
    ))
    db.commit()
    _enqueue_automatic_grades(db, submission.id, actor)
    return {"identity_status": submission.identity_status, "external_student_id": submission.external_student_id,
            "display_name": submission.display_name, "document_id": document.id,
            "document_hash": document.sha256, "version": submission.version}


@router.get("/submissions/{submission_id}")
def get_submission(submission_id: str, db: Session = Depends(get_db), actor=Depends(require_actor)):
    submission, assessment = _submission_scope(db, actor, submission_id)
    revision = db.get(AssessmentRevision, submission.assessment_revision_id)
    document = db.get(Document, submission.active_document_id) if submission.active_document_id else None
    pages = []
    if document and document.active_layout_revision_id:
        layout = db.get(DocumentLayoutRevision, document.active_layout_revision_id)
        for image_id in layout.ordered_page_image_revision_ids if layout else []:
            image_revision = db.get(PageImageRevision, image_id)
            page = db.get(Page, image_revision.page_id) if image_revision else None
            if not image_revision or not page:
                continue
            regions = db.scalars(select(Region).where(Region.page_image_revision_id == image_revision.id)).all()
            pages.append({
                "id": page.id,
                "page_index": page.page_index,
                "page_image_revision_id": image_revision.id,
                "width_px": image_revision.width_px,
                "height_px": image_revision.height_px,
                "rotation": image_revision.rotation,
                "transform": image_revision.transform,
                "inverse_transform": image_revision.inverse_transform,
                "image_url": f"/api/v1/page-image-revisions/{image_revision.id}/content",
                "regions": [{"id": region.id, "polygon": region.polygon, "region_type": region.region_type,
                             "analysis":region.analysis,"excluded_from_mapping":region.excluded_from_mapping} for region in regions],
            })
    from .services import question_json
    questions = {item["stable_question_id"]: item for item in question_json(db, revision.id)} if revision else {}
    answers = db.scalars(select(Answer).where(Answer.submission_id == submission.id)).all()
    items = []
    for answer in answers:
        question = questions.get(answer.stable_question_id, {})
        mapping = db.get(AnswerMappingRevision, answer.active_mapping_revision_id) if answer.active_mapping_revision_id else None
        links = db.scalars(select(AnswerRegionLink).where(
            AnswerRegionLink.answer_id == answer.id,
            AnswerRegionLink.mapping_revision_id == mapping.id if mapping else False,
        ).order_by(AnswerRegionLink.order_index)).all() if mapping else []
        transcript = db.get(TranscriptionRevision, answer.active_transcription_revision_id) if answer.active_transcription_revision_id else None
        mapping_is_current = bool(mapping and document and mapping.layout_revision_id == document.active_layout_revision_id)
        transcript_is_current = bool(transcript and mapping_is_current and transcript.mapping_revision_id == mapping.id)
        proposal = db.get(GradeProposal, answer.active_proposal_id) if answer.active_proposal_id else None
        proposal_is_current = bool(proposal and transcript_is_current and proposal.transcription_revision_id == transcript.id and revision and proposal.assessment_revision_id == revision.id)
        review = db.get(ReviewRevision, submission.active_review_id) if submission.active_review_id else None
        review_item = db.scalar(select(ReviewItem).where(
            ReviewItem.review_revision_id == review.id,
            ReviewItem.stable_question_id == answer.stable_question_id,
        )) if review else None
        items.append({
            "id": answer.id,
            "question_id": answer.stable_question_id,
            "label": question.get("label", answer.stable_question_id),
            "text": question.get("text", ""),
            "weight": question.get("weight"),
            "rubric": question.get("criteria", []),
            "mapping_status": answer.mapping_status if mapping_is_current else "unmapped",
            "mapping_revision_id": mapping.id if mapping_is_current else None,
            "region_ids": [link.region_id for link in links] if mapping_is_current else [],
            "transcript_status": answer.transcript_status,
            "transcript": transcript.literal_text if transcript and transcript_is_current else "",
            "transcript_flags": transcript.flags if transcript and transcript_is_current else [],
            "transcript_revision_id": transcript.id if transcript else None,
            "transcript_revision_no": transcript.revision_no if transcript else 0,
            "transcript_stale": bool(transcript and not transcript_is_current),
            "segments": transcript.segments if transcript and transcript_is_current else [],
            "proposal": proposal.proposal_payload if proposal else None,
            "proposal_id": proposal.id if proposal else None,
            "proposal_stale": bool(proposal and not proposal_is_current),
            "review": ({
                "status": review_item.answer_status,
                "criteria": review_item.accepted_criteria,
                "override_raw": str(review_item.override_raw) if review_item.override_raw is not None else None,
                "reason": review_item.override_reason,
            } if review_item else None),
        })
    from .models import GradeSnapshot
    final = db.scalar(select(GradeSnapshot).where(GradeSnapshot.submission_id == submission.id).order_by(GradeSnapshot.approved_at.desc()).limit(1))
    confirmation = db.get(IdentityConfirmation, submission.active_identity_confirmation_id) if submission.active_identity_confirmation_id else None
    latest_jobs = {}
    if document:
        jobs = db.scalars(select(PipelineJob).where(
            PipelineJob.submission_id == submission.id, PipelineJob.document_id == document.id,
        ).order_by(PipelineJob.created_at.desc(), PipelineJob.attempt.desc())).all()
        for item in jobs:
            latest_jobs.setdefault((item.kind, item.answer_id), _job_summary(item))
    return {
        "id": submission.id,
        "assessment_id": assessment.id,
        "assessment_revision_id": revision.id if revision else None,
        "assessment_revision_status": revision.status if revision else None,
        "external_student_id": submission.external_student_id if submission.identity_status == "confirmed" else "",
        "display_name": submission.display_name if submission.identity_status == "confirmed" else "",
        "claimed_identity": ({"external_student_id":((document.analysis_result or {}).get('identity_candidate') or {}).get('student_id') or "", "display_name":((document.analysis_result or {}).get('identity_candidate') or {}).get('name') or ""}
            if document and submission.external_student_id.startswith(PENDING_ID_PREFIX)
            else {"external_student_id":"", "display_name":""}
            if submission.external_student_id.startswith(PENDING_ID_PREFIX)
            else {"external_student_id": submission.external_student_id, "display_name": submission.display_name}),
        "attempt_no": submission.attempt_no,
        "identity_status": submission.identity_status,
        "identity_confirmation_id": confirmation.id if confirmation else None,
        "document": ({"id": document.id, "sha256": document.sha256, "status": document.validation_status,
                      "page_count": document.page_count, "layout_revision_id": document.active_layout_revision_id,
                      "auto_process":document.auto_process,"analysis_result":document.analysis_result,
                      "original_url": f"/api/v1/documents/{document.id}/content"} if document else None),
        "pages": pages,
        "answers": items,
        "pipeline_jobs": list(latest_jobs.values()),
        "unassigned_region_ids": [r["id"] for p in pages for r in p["regions"]
            if r["region_type"] in {"answer","unassigned"} and not r["excluded_from_mapping"]
            and r["id"] not in {rid for item in items for rid in item["region_ids"]}],
        "review_revision": ({"id": review.id, "sequence": review.sequence, "version": review.version, "status": review.status} if review else None),
        "final_snapshot": ({"id": final.id, "score": str(final.final_score), "revision_id": final.assessment_revision_id,
                            "approved_at": final.approved_at.isoformat()} if final else None),
        "status": submission.status,
        "version": submission.version,
    }


@router.post("/page-image-revisions/{image_revision_id}/regions", status_code=201)
def create_region(image_revision_id: str, body: RegionInput, db: Session = Depends(get_db), actor=Depends(require_writer)):
    image_revision = db.get(PageImageRevision, image_revision_id)
    page = db.get(Page, image_revision.page_id) if image_revision else None
    document = db.get(Document, page.document_id) if page else None
    if not document:
        raise HTTPException(status_code=404, detail={"code": "RESOURCE_NOT_FOUND"})
    require_owner_scope(db, actor, document.assessment_id)
    if document.kind != "student_answer":
        raise HTTPException(status_code=409, detail={"code": "ANSWER_REGION_REQUIRES_SUBMISSION_DOCUMENT"})
    if not document.active_layout_revision_id:
        raise HTTPException(status_code=409, detail={"code": "DOCUMENT_LAYOUT_PENDING"})
    layout = db.get(DocumentLayoutRevision, document.active_layout_revision_id)
    if not layout or image_revision.id not in layout.ordered_page_image_revision_ids:
        raise HTTPException(status_code=409, detail={"code": "STALE_PAGE_IMAGE_REVISION"})
    if any(not (0 <= x <= 1 and 0 <= y <= 1) for x, y in body.polygon):
        raise HTTPException(status_code=422, detail={"code": "POLYGON_OUT_OF_BOUNDS"})
    if len(set(body.polygon)) < 3:
        raise HTTPException(status_code=422, detail={"code": "POLYGON_DEGENERATE"})
    region = Region(
        page_image_revision_id=image_revision.id,
        polygon=[[float(x), float(y)] for x, y in body.polygon],
        region_type=body.region_type,
        created_by=actor.id,
    )
    db.add(region)
    db.commit()
    return {"id": region.id, "page_image_revision_id": region.page_image_revision_id, "polygon": region.polygon,
            "region_type": region.region_type}


@router.post("/regions/{region_id}/revisions", status_code=201)
def revise_region(region_id: str, body: RegionInput, db: Session = Depends(get_db), actor=Depends(require_writer)):
    original = db.get(Region, region_id)
    image_revision = db.get(PageImageRevision, original.page_image_revision_id) if original else None
    page = db.get(Page, image_revision.page_id) if image_revision else None
    document = db.get(Document, page.document_id) if page else None
    if not original or not document:
        raise HTTPException(status_code=404, detail={"code": "RESOURCE_NOT_FOUND"})
    require_owner_scope(db, actor, document.assessment_id)
    if any(not (0 <= x <= 1 and 0 <= y <= 1) for x, y in body.polygon):
        raise HTTPException(status_code=422, detail={"code": "POLYGON_OUT_OF_BOUNDS"})
    revised = Region(
        page_image_revision_id=original.page_image_revision_id,
        parent_region_id=original.id,
        polygon=[[float(x), float(y)] for x, y in body.polygon],
        region_type=body.region_type,
        created_by=actor.id,
    )
    db.add(revised)
    db.commit()
    return {"id": revised.id, "parent_region_id": original.id, "polygon": revised.polygon, "status": "mapping_requires_revision"}


@router.post("/page-image-revisions/{image_revision_id}/rotate")
def rotate_page(image_revision_id: str, body: PageRotationInput, db: Session = Depends(get_db), actor=Depends(require_writer)):
    from PIL import Image
    image_revision = db.get(PageImageRevision, image_revision_id)
    page = db.get(Page, image_revision.page_id) if image_revision else None
    document = db.get(Document, page.document_id) if page else None
    if not image_revision or not document:
        raise HTTPException(status_code=404, detail={"code": "RESOURCE_NOT_FOUND"})
    require_owner_scope(db, actor, document.assessment_id)
    layout = db.get(DocumentLayoutRevision, document.active_layout_revision_id) if document.active_layout_revision_id else None
    if not layout or layout.id != body.expected_layout_revision_id or image_revision.id not in layout.ordered_page_image_revision_ids:
        raise HTTPException(status_code=409, detail={"code": "STALE_LAYOUT_REVISION"})
    source = Image.open(io.BytesIO(artifact_store.read(image_revision.image_storage_key))).convert("RGB")
    rotated = source.rotate(-body.degrees_clockwise, expand=True)
    image_bytes = io.BytesIO()
    rotated.save(image_bytes, format="PNG")
    key, digest, size = artifact_store.put(image_bytes.getvalue())
    turns = (image_revision.rotation + body.degrees_clockwise) % 360
    matrices = {
        90: ([0, 1, -1, 0, 1, 0], [0, -1, 1, 0, 0, 1]),
        180: ([-1, 0, 0, -1, 1, 1], [-1, 0, 0, -1, 1, 1]),
        270: ([0, -1, 1, 0, 0, 1], [0, 1, -1, 0, 1, 0]),
        0: ([1, 0, 0, 1, 0, 0], [1, 0, 0, 1, 0, 0]),
    }
    matrix, inverse = matrices[body.degrees_clockwise]
    current_sequence = db.scalar(select(func.max(PageImageRevision.sequence)).where(PageImageRevision.page_id == page.id)) or 0
    new_image = PageImageRevision(
        page_id=page.id,
        sequence=current_sequence + 1,
        parent_revision_id=image_revision.id,
        image_storage_key=key,
        width_px=rotated.width,
        height_px=rotated.height,
        rotation=turns,
        transform={"type": "affine", "matrix": matrix, "from": image_revision.id},
        inverse_transform={"type": "affine", "matrix": inverse, "to": image_revision.id},
        image_sha256=digest,
        preprocessing_version="manual-rotation.v1",
    )
    db.add(new_image)
    db.flush()
    ordered = [new_image.id if item == image_revision.id else item for item in layout.ordered_page_image_revision_ids]
    next_layout = DocumentLayoutRevision(
        document_id=document.id,
        sequence=layout.sequence + 1,
        parent_revision_id=layout.id,
        ordered_page_image_revision_ids=ordered,
        created_by=actor.id,
    )
    db.add(next_layout)
    db.flush()
    document.active_layout_revision_id = next_layout.id
    db.add(Artifact(
        assessment_id=document.assessment_id,
        document_id=document.id,
        storage_key=key,
        kind="page_rotation",
        sha256=digest,
        byte_size=size,
        parent_ids=[image_revision.id],
    ))
    db.add(AuditEvent(
        assessment_id=document.assessment_id,
        actor_id=actor.id,
        action="page_image.rotated",
        resource_id=new_image.id,
        previous_revision=image_revision.id,
        new_revision=new_image.id,
        metadata_json={"layout_revision_id": next_layout.id, "degrees_clockwise": body.degrees_clockwise},
    ))
    db.commit()
    return {"page_image_revision_id": new_image.id, "layout_revision_id": next_layout.id,
            "rotation": turns, "width_px": rotated.width, "height_px": rotated.height,
            "mapping_requires_revision": True}


@router.get("/page-image-revisions/{image_revision_id}/content")
def page_image_content(image_revision_id: str, db: Session = Depends(get_db), actor=Depends(require_actor)):
    image_revision = db.get(PageImageRevision, image_revision_id)
    page = db.get(Page, image_revision.page_id) if image_revision else None
    document = db.get(Document, page.document_id) if page else None
    if not document:
        raise HTTPException(status_code=404, detail={"code": "RESOURCE_NOT_FOUND"})
    require_owner_scope(db, actor, document.assessment_id)
    return StreamingResponse(io.BytesIO(artifact_store.read(image_revision.image_storage_key)), media_type="image/png",
                             headers={"Cache-Control": "private, no-store"})


@router.post("/answers/{answer_id}/mapping-revisions", status_code=201)
def map_answer(answer_id: str, body: MappingInput, db: Session = Depends(get_db), actor=Depends(require_writer)):
    answer = db.get(Answer, answer_id)
    submission = db.get(Submission, answer.submission_id) if answer else None
    if not answer or not submission:
        raise HTTPException(status_code=404, detail={"code": "RESOURCE_NOT_FOUND"})
    submission, assessment = _submission_scope(db, actor, submission.id, lock=True)
    answer = db.scalar(select(Answer).where(Answer.id == answer_id, Answer.submission_id == submission.id).with_for_update())
    if not answer:
        raise HTTPException(status_code=404, detail={"code": "RESOURCE_NOT_FOUND"})
    if submission.identity_status != "confirmed" or not submission.active_document_id:
        raise HTTPException(status_code=409, detail={"code": "IDENTITY_AND_DOCUMENT_REQUIRED"})
    document = db.get(Document, submission.active_document_id)
    layout = db.get(DocumentLayoutRevision, document.active_layout_revision_id) if document and document.active_layout_revision_id else None
    if not layout:
        raise HTTPException(status_code=409, detail={"code": "DOCUMENT_LAYOUT_PENDING"})
    if answer.transcript_revision != body.expected_transcript_revision:
        raise HTTPException(status_code=409, detail={"code": "STALE_TRANSCRIPTION", "current_revision": answer.transcript_revision})
    from .auto_mapping import current_mapping
    existing_mapping = current_mapping(db,submission,answer)
    if (existing_mapping.id if existing_mapping else None) != body.expected_mapping_revision_id:
        raise HTTPException(status_code=409, detail={"code": "STALE_MAPPING", "current_mapping_revision_id": answer.active_mapping_revision_id})
    if len(set(body.region_ids)) != len(body.region_ids):
        raise HTTPException(status_code=422, detail={"code": "DUPLICATE_REGION_ID"})
    regions = [db.get(Region, region_id) for region_id in body.region_ids]
    if any(region is None or region.region_type != "answer" or region.excluded_from_mapping for region in regions):
        raise HTTPException(status_code=422, detail={"code": "INVALID_ANSWER_REGION"})
    for region in regions:
        page_revision = db.get(PageImageRevision, region.page_image_revision_id)
        page = db.get(Page, page_revision.page_id) if page_revision else None
        if not page or page.document_id != document.id or page_revision.id not in layout.ordered_page_image_revision_ids:
            raise HTTPException(status_code=409, detail={"code": "REGION_OUTSIDE_ACTIVE_DOCUMENT_LAYOUT"})
        linked_elsewhere = db.scalar(select(AnswerRegionLink).join(Answer, Answer.id == AnswerRegionLink.answer_id).where(
            AnswerRegionLink.region_id == region.id,
            Answer.submission_id == submission.id,
            Answer.id != answer.id,
            Answer.active_mapping_revision_id == AnswerRegionLink.mapping_revision_id,
        ))
        if linked_elsewhere:
            raise HTTPException(status_code=409, detail={"code": "REGION_ALREADY_MAPPED"})
    sequence = (db.scalar(select(func.max(AnswerMappingRevision.sequence)).where(AnswerMappingRevision.answer_id == answer.id)) or 0) + 1
    mapping = AnswerMappingRevision(
        answer_id=answer.id,
        sequence=sequence,
        parent_revision_id=answer.active_mapping_revision_id,
        layout_revision_id=layout.id,
        ordered_region_ids=list(body.region_ids),
        created_by=actor.id,
    )
    db.add(mapping)
    db.flush()
    for order, region_id in enumerate(body.region_ids, start=1):
        db.add(AnswerRegionLink(answer_id=answer.id, mapping_revision_id=mapping.id, region_id=region_id, order_index=order))
    previous = answer.active_mapping_revision_id
    answer.active_mapping_revision_id = mapping.id
    answer.mapping_status = "mapped" if regions else "unmapped"
    if answer.transcript_status == "transcribed":
        answer.transcript_status = "pending"
    from .auto_mapping import adopt_region_transcripts
    reused_ocr = adopt_region_transcripts(db,answer,mapping,regions)
    submission.status = "needs_review"
    db.add(AuditEvent(
        assessment_id=assessment.id,
        actor_id=actor.id,
        action="answer.mapping_revised",
        resource_id=answer.id,
        previous_revision=previous,
        new_revision=mapping.id,
        metadata_json={"regions": list(body.region_ids), "layout_revision_id": layout.id},
    ))
    db.commit()
    if reused_ocr:
        _enqueue_automatic_grades(db, submission.id, actor)
    return {"answer_id": answer.id, "mapping_revision_id": mapping.id, "sequence": mapping.sequence,
            "region_ids": body.region_ids, "status":answer.mapping_status,"reused_ocr":reused_ocr}


@router.post("/submissions/{submission_id}/answers/{question_id}/transcription-revisions", status_code=201)
def save_transcription(
    submission_id: str,
    question_id: str,
    body: TranscriptionInput,
    db: Session = Depends(get_db),
    actor=Depends(require_writer),
):
    submission, assessment = _submission_scope(db, actor, submission_id, lock=True)
    answer = db.scalar(select(Answer).where(Answer.submission_id == submission.id, Answer.stable_question_id == question_id).with_for_update())
    if not answer:
        raise HTTPException(status_code=404, detail={"code": "RESOURCE_NOT_FOUND"})
    if answer.transcript_revision != body.expected_revision:
        raise HTTPException(status_code=409, detail={"code": "STALE_TRANSCRIPTION", "current_revision": answer.transcript_revision})
    if submission.identity_status != "confirmed" or not submission.active_document_id:
        raise HTTPException(status_code=409, detail={"code": "IDENTITY_AND_DOCUMENT_REQUIRED"})
    if body.status == "verified_blank" and (body.literal_text or not body.reason or not body.reason.strip()):
        raise HTTPException(status_code=422, detail={"code": "VERIFIED_BLANK_REQUIRES_EMPTY_TEXT_AND_REASON"})
    from .auto_mapping import current_mapping
    mapping = current_mapping(db,submission,answer)
    if body.status in {"transcribed", "unreadable", "unsupported"} and (not mapping or answer.mapping_status == "unmapped"):
        raise HTTPException(status_code=409, detail={"code": "ANSWER_MAPPING_REQUIRED"})
    if body.status == "transcribed" and not body.literal_text.strip():
        raise HTTPException(status_code=422, detail={"code": "TRANSCRIPTION_TEXT_REQUIRED"})
    links = db.scalars(select(AnswerRegionLink).where(
        AnswerRegionLink.answer_id == answer.id,
        AnswerRegionLink.mapping_revision_id == mapping.id if mapping else False,
    ).order_by(AnswerRegionLink.order_index)).all() if mapping else []
    if body.status == "verified_blank":
        segments = []
    elif len(links) <= 1:
        segments = ([{"segment_id": "seg-1", "region_id": links[0].region_id, "order": 1, "text": body.literal_text, "confidence": None}] if links else [])
    else:
        lines = body.literal_text.splitlines()
        if len(lines) == len(links):
            parts = lines
        else:
            parts = [body.literal_text] + [""] * (len(links) - 1)
        segments = [{"segment_id": f"seg-{index}", "region_id": link.region_id, "order": index,
                     "text": parts[index - 1], "confidence": None} for index, link in enumerate(links, start=1)]
    next_revision = answer.transcript_revision + 1
    transcript = TranscriptionRevision(
        answer_id=answer.id,
        mapping_revision_id=mapping.id if mapping else None,
        revision_no=next_revision,
        parent_revision_id=answer.active_transcription_revision_id,
        literal_text=body.literal_text,
        segments=segments,
        status=body.status,
        flags=body.flags,
        source="human",
        created_by=actor.id,
    )
    db.add(transcript)
    db.flush()
    prior = answer.active_transcription_revision_id
    answer.active_transcription_revision_id = transcript.id
    answer.transcript_revision = next_revision
    answer.transcript_status = body.status
    answer.literal_text = body.literal_text
    submission.status = "needs_review"
    db.add(AuditEvent(
        assessment_id=assessment.id,
        actor_id=actor.id,
        action="answer.transcription_corrected",
        resource_id=answer.id,
        previous_revision=prior,
        new_revision=transcript.id,
        reason=body.reason,
        metadata_json={"status": body.status, "source": "human"},
    ))
    db.commit()
    if body.status == 'transcribed':
        _enqueue_automatic_grades(db, submission.id, actor)
    return {"id": transcript.id, "revision_no": transcript.revision_no, "status": transcript.status,
            "literal_text": transcript.literal_text, "segments": transcript.segments,
            "mapping_revision_id": transcript.mapping_revision_id}


@router.post("/submissions/{submission_id}/answers/{question_id}/transcribe", status_code=202)
def request_transcription(submission_id: str, question_id: str, db: Session = Depends(get_db), actor=Depends(require_writer)):
    submission, assessment = _submission_scope(db, actor, submission_id, lock=True)
    if submission.identity_status != "confirmed" or not submission.active_document_id:
        raise HTTPException(status_code=409, detail={"code": "IDENTITY_AND_DOCUMENT_REQUIRED"})
    answer = db.scalar(select(Answer).where(Answer.submission_id == submission.id, Answer.stable_question_id == question_id).with_for_update())
    if not answer or not answer.active_mapping_revision_id:
        raise HTTPException(status_code=409, detail={"code": "ANSWER_MAPPING_REQUIRED"})
    from .auto_mapping import current_mapping
    mapping = current_mapping(db,submission,answer)
    if not mapping:
        raise HTTPException(409,detail={"code":"ANSWER_MAPPING_REQUIRED"})
    links = db.scalars(select(AnswerRegionLink).where(
        AnswerRegionLink.answer_id == answer.id,
        AnswerRegionLink.mapping_revision_id == mapping.id,
    ).order_by(AnswerRegionLink.order_index)).all()
    if not links:
        raise HTTPException(409, detail={"code": "ANSWER_MAPPING_REQUIRED"})
    regions_fingerprint = []
    for link in links:
        region = db.get(Region, link.region_id)
        page_image = db.get(PageImageRevision, region.page_image_revision_id)
        regions_fingerprint.append(json.dumps({"region_id": region.id, "page_image_hash": page_image.image_sha256,
                                               "polygon": region.polygon}, sort_keys=True))
    fingerprint = canonical_hash({"document": submission.active_document_id, "answer": answer.id,
                                  "regions": regions_fingerprint, "language": assessment.language,
                                  "transcriber": transcriber_fingerprint()})
    job = add_job(
        db,
        assessment_id=assessment.id,
        document_id=submission.active_document_id,
        submission_id=submission.id,
        answer_id=answer.id,
        kind="transcribe_answer",
        input_fingerprint=fingerprint,
    )
    db.commit()
    publish_job_outbox(db, job.id)
    db.refresh(job)
    return {"job_id": job.id, "status": job.status, "error_code": job.error_code,
            "model": model_status()}


@router.post("/submissions/{submission_id}/answers/{question_id}/propose", status_code=202)
def request_grade_proposal(submission_id: str, question_id: str, db: Session = Depends(get_db), actor=Depends(require_writer)):
    submission, assessment = _submission_scope(db, actor, submission_id, lock=True)
    revision = db.get(AssessmentRevision, submission.assessment_revision_id)
    if not revision or revision.status != "approved":
        raise HTTPException(status_code=409, detail={"code": "APPROVED_RUBRIC_REQUIRED"})
    if submission.identity_status != "confirmed" or not submission.active_document_id:
        raise HTTPException(status_code=409, detail={"code": "IDENTITY_AND_DOCUMENT_REQUIRED"})
    answer = db.scalar(select(Answer).where(Answer.submission_id == submission.id,
        Answer.stable_question_id == question_id).with_for_update())
    transcript = db.get(TranscriptionRevision, answer.active_transcription_revision_id) if answer and answer.active_transcription_revision_id else None
    if answer and answer.mapping_status == "auto_mapped":
        raise HTTPException(409,detail={"code":"AUTO_MAPPING_REVIEW_REQUIRED"})
    from .auto_mapping import current_mapping
    if not current_mapping(db,submission,answer) or answer.mapping_status == "unmapped":
        raise HTTPException(409,detail={"code":"ANSWER_MAPPING_REQUIRED"})
    if not answer or not transcript or transcript.status != "transcribed" or transcript.mapping_revision_id != answer.active_mapping_revision_id:
        raise HTTPException(status_code=409, detail={"code": "CURRENT_TRANSCRIPTION_REQUIRED"})
    if transcript.flags or transcription_flags(transcript.literal_text):
        raise HTTPException(status_code=409, detail={"code": "UNREADABLE_TRANSCRIPTION_REVIEW_REQUIRED"})
    question = db.scalar(select(QuestionRevision).where(
        QuestionRevision.assessment_revision_id == revision.id,
        QuestionRevision.stable_question_id == answer.stable_question_id,
    ))
    fingerprint = canonical_hash({"prompt_version": GRADER_PROMPT_VERSION, "model_revision": MODEL_REVISION,
                                  "evidence_version": GRADING_EVIDENCE_VERSION,
                                  "answer_id": answer.id, "transcript_revision": transcript.id,
                                  "assessment_revision": revision.id, "question_id": question.id})
    job = add_job(
        db,
        assessment_id=assessment.id,
        document_id=submission.active_document_id,
        submission_id=submission.id,
        answer_id=answer.id,
        kind="grade_answer",
        input_fingerprint=fingerprint,
    )
    db.commit()
    publish_job_outbox(db, job.id)
    db.refresh(job)
    return {"job_id": job.id, "status": job.status, "error_code": job.error_code, "model": model_status()}


def _enqueue_automatic_grades(db: Session, submission_id: str, actor) -> None:
    """Schedule draft proposals only after identity and per-answer mapping are reviewed."""
    submission = db.get(Submission, submission_id)
    document = db.get(Document, submission.active_document_id) if submission and submission.active_document_id else None
    if not document or submission.identity_status != 'confirmed' or not (document.analysis_result or {}).get('auto_grade_requested'):
        return
    question_ids = list(db.scalars(select(Answer.stable_question_id).where(Answer.submission_id == submission_id)))
    for question_id in question_ids:
        try:
            request_grade_proposal(submission_id, question_id, db, actor)
        except HTTPException:
            db.rollback()  # A missing/review-pending answer remains for the lecturer.
        except Exception:
            db.rollback()
            logger.warning('Automatic grading could not be scheduled; manual retry remains available.')


@router.get("/jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db), actor=Depends(require_actor)):
    job = db.get(PipelineJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail={"code": "RESOURCE_NOT_FOUND"})
    require_owner_scope(db, actor, job.assessment_id)
    return _job_summary(job)


@router.post("/jobs/{job_id}/cancel", status_code=202)
def cancel_job(job_id: str, db: Session = Depends(get_db), actor=Depends(require_writer)):
    job = db.get(PipelineJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail={"code": "RESOURCE_NOT_FOUND"})
    require_owner_scope(db, actor, job.assessment_id)
    if job.status in {"succeeded", "failed", "cancelled"}:
        raise HTTPException(status_code=409, detail={"code": "JOB_NOT_CANCELLABLE"})
    job.cancel_requested = True
    if job.status == "queued":
        job.status = "cancelled"
        job.finished_at = now_utc()
    db.commit()
    return {"id": job.id, "status": job.status, "cancel_requested": job.cancel_requested}


@router.post("/jobs/{job_id}/retry", status_code=202)
def retry_job(job_id: str, body: RetryRequest, db: Session = Depends(get_db), actor=Depends(require_writer)):
    previous = db.get(PipelineJob, job_id)
    if not previous:
        raise HTTPException(status_code=404, detail={"code": "RESOURCE_NOT_FOUND"})
    require_owner_scope(db, actor, previous.assessment_id)
    if previous.status != "failed" or previous.attempt != body.expected_attempt:
        raise HTTPException(status_code=409, detail={"code": "JOB_NOT_RETRYABLE_OR_STALE"})
    new_job = add_job(
        db,
        assessment_id=previous.assessment_id,
        document_id=previous.document_id,
        submission_id=previous.submission_id,
        answer_id=previous.answer_id,
        draft_assessment_revision_id=previous.draft_assessment_revision_id,
        kind=previous.kind,
        input_fingerprint=previous.input_fingerprint,
    )
    db.add(AuditEvent(
        assessment_id=previous.assessment_id,
        actor_id=actor.id,
        action="pipeline_job.retried",
        resource_id=previous.id,
        previous_revision=previous.id,
        new_revision=new_job.id,
        reason=body.reason,
    ))
    db.commit()
    publish_job_outbox(db, new_job.id)
    db.refresh(new_job)
    return {"id": new_job.id, "status": new_job.status, "attempt": new_job.attempt,
            "error_code": new_job.error_code}
