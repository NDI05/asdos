from __future__ import annotations

import hashlib
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.asdos_domain.scoring import AnswerGrade, calculate_grade
from .database import get_db
from .dependencies import require_actor, require_owner_scope, require_writer
from .exporter import build_workbook, workbook_filename
from .config import settings
from .models import (
    Answer, Assessment, AssessmentRevision, AuditEvent, Document, ExportSnapshot,
    GradeProposal, GradeSnapshot, GradeSnapshotCriterion, GradeSnapshotItem, ModelRun,
    IdentityConfirmation, Page, PageImageRevision, QuestionRevision, Region,
    ReviewItem, ReviewRevision, RubricCriterion,
    Submission, TranscriptionRevision, User, Artifact, new_id, now_utc,
)
from .schemas import ExportRequest
from .services import canonical_hash, load_question_specs
from .storage import artifact_store

router = APIRouter(prefix="/api/v1", tags=["exports"])


def _json_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(v) for v in value]
    return value


def _build_payload(db: Session, assessment: Assessment, revision: AssessmentRevision, mode: str,
                   submission_ids: list[str], snapshot_id: str, actor_id: str) -> dict:
    specs = load_question_specs(db, revision.id)
    questions_by_id = {question.question_id: question for question in specs}
    question_rows = db.scalars(select(QuestionRevision).where(QuestionRevision.assessment_revision_id == revision.id).order_by(QuestionRevision.order_index)).all()
    question_json = []
    rubric_rows = []
    for row in question_rows:
        criteria = db.scalars(select(RubricCriterion).where(RubricCriterion.question_revision_id == row.id).order_by(RubricCriterion.criterion_id)).all()
        question_json.append({"id": row.stable_question_id, "label": row.label, "order": row.order_index,
            "text": row.text, "weight": str(row.weight), "reference_answer": row.reference_answer,
            "alternatives": row.alternatives, "max_raw": str(questions_by_id[row.stable_question_id].max_raw)})
        for criterion in criteria:
            rubric_rows.append([revision.id, row.stable_question_id, row.label, row.text, str(row.weight),
                str(questions_by_id[row.stable_question_id].max_raw), criterion.criterion_id, criterion.description,
                str(criterion.max_points), {str(k): v for k, v in criterion.anchors.items()}, row.reference_answer, row.alternatives])
    summary_rows = []
    question_details = []
    criterion_details = []
    transcription_rows = []
    manifest_submissions = []
    used_model_run_ids: set[str] = set()
    included_resource_ids = set(submission_ids)
    final_count = 0
    pending_count = 0
    for submission_id in submission_ids:
        submission = db.get(Submission, submission_id)
        review = db.get(ReviewRevision, submission.active_review_id) if submission.active_review_id else None
        snapshot = db.scalar(select(GradeSnapshot).where(GradeSnapshot.review_revision_id == review.id)) if review else None
        identity = db.get(IdentityConfirmation, submission.active_identity_confirmation_id) if submission.active_identity_confirmation_id else None
        document = db.get(Document, submission.active_document_id) if submission.active_document_id else None
        final = bool(review and review.status == "finalized" and snapshot and snapshot.assessment_revision_id == revision.id
                     and submission.assessment_revision_id == revision.id)
        if mode == "final" and not final:
            raise HTTPException(status_code=409, detail={"code": "FINAL_EXPORT_HAS_PENDING_SUBMISSION", "submission_id": submission_id})
        if mode == "final" and (not identity or not document or identity.document_id != document.id or identity.document_hash != document.sha256):
            raise HTTPException(status_code=409, detail={"code": "FINAL_EXPORT_IDENTITY_MISMATCH", "submission_id": submission_id})
        if final:
            final_count += 1
        else:
            pending_count += 1
        student_id = submission.external_student_id if submission.identity_status == "confirmed" and identity else ""
        student_name = submission.display_name if submission.identity_status == "confirmed" and identity else "Belum dikonfirmasi"
        answers = db.scalars(select(Answer).where(Answer.submission_id == submission.id)).all()
        answers_by_q = {answer.stable_question_id: answer for answer in answers}
        items = {item.stable_question_id: item for item in (db.scalars(select(ReviewItem).where(ReviewItem.review_revision_id == review.id)).all() if review else [])}
        snapshot_items = {item.stable_question_id: item for item in (db.scalars(select(GradeSnapshotItem).where(GradeSnapshotItem.snapshot_id == snapshot.id)).all() if snapshot else [])}
        review_answers = {}
        for question in specs:
            item = items.get(question.question_id)
            if not item:
                continue
            if item.override_raw is not None:
                review_answers[question.question_id] = AnswerGrade(question.question_id, item.answer_status,
                    override_raw=Decimal(item.override_raw), override_reason=item.override_reason)
            elif item.accepted_criteria:
                review_answers[question.question_id] = AnswerGrade(question.question_id, item.answer_status,
                    {entry["criterion_id"]: Decimal(entry["credit"]) for entry in item.accepted_criteria},
                    override_reason=item.override_reason)
        try:
            provisional = calculate_grade(specs, review_answers, final=False)
        except Exception:
            provisional = None
        q_contributions = []
        contribution_sum = Decimal("0")
        for question in specs:
            q_item = items.get(question.question_id)
            snap_item = snapshot_items.get(question.question_id)
            if snap_item:
                raw_value = Decimal(snap_item.raw_points)
                contribution = Decimal(snap_item.contribution)
                status = snap_item.answer_status
                source = "manual_question_override" if snap_item.decision_payload.get("override_raw") is not None else "reviewed_criteria"
                review_status = "finalized" if final else (review.status if review else "not_started")
                override_raw = snap_item.decision_payload.get("override_raw")
                reason = snap_item.decision_payload.get("override_reason")
                source_revision = review.id if review else ""
            else:
                raw_value = None
                contribution = provisional.contributions.get(question.question_id) if provisional else None
                status = q_item.answer_status if q_item else "needs_review"
                source = "manual_question_override" if q_item and q_item.override_raw is not None else "reviewed_criteria" if q_item and q_item.accepted_criteria else "model_proposal" if q_item and q_item.proposal_id else "unreviewed"
                review_status = review.status if review else "not_started"
                override_raw = str(q_item.override_raw) if q_item and q_item.override_raw is not None else None
                reason = q_item.override_reason if q_item else None
                source_revision = review.id if review else ""
                if q_item and q_item.accepted_criteria and q_item.override_raw is None:
                    raw_value = sum((Decimal(entry["credit"]) * next(c.max_points for c in question.criteria if c.criterion_id == entry["criterion_id"]) for entry in q_item.accepted_criteria), Decimal("0"))
                elif q_item and q_item.override_raw is not None:
                    raw_value = Decimal(q_item.override_raw)
            if contribution is not None:
                contribution_sum += Decimal(contribution)
            q_contributions.append(str(contribution) if contribution is not None else None)
            answer = answers_by_q.get(question.question_id)
            if answer:
                included_resource_ids.add(answer.id)
            question_details.append([submission.id, student_id, question.question_id, question.label,
                str(raw_value) if raw_value is not None else None, str(question.max_raw), str(question.weight),
                str(contribution) if contribution is not None else None, status, source, review_status, reason, source_revision])
            if snap_item:
                decision = snap_item.decision_payload
                if decision.get("proposal_id"):
                    proposal = db.get(GradeProposal, decision["proposal_id"])
                    if proposal:
                        used_model_run_ids.add(proposal.model_run_id)
                snap_criteria = db.scalars(select(GradeSnapshotCriterion).where(GradeSnapshotCriterion.snapshot_item_id == snap_item.id)).all()
                for criterion in snap_criteria:
                    criterion_details.append([submission.id, question.question_id, criterion.criterion_id,
                        str(criterion.accepted_credit), str(criterion.max_points), str(criterion.points),
                        criterion.evidence_refs, criterion.rationale, criterion.source])
                if not snap_criteria and decision.get("proposal_id"):
                    proposal = db.get(GradeProposal, decision["proposal_id"])
                    if proposal and proposal.assessment_revision_id == revision.id:
                        for entry in proposal.proposal_payload.get("criteria", []):
                            criterion = next((c for c in question.criteria if c.criterion_id == entry.get("criterion_id")), None)
                            if criterion:
                                credit = Decimal(str(entry["credit"]))
                                criterion_details.append([submission.id, question.question_id, criterion.criterion_id,
                                    str(credit), str(criterion.max_points), str(credit * criterion.max_points),
                                    entry.get("evidence_refs", []), entry.get("rationale", ""), "model_proposal"])
            elif q_item and q_item.accepted_criteria:
                if q_item.proposal_id:
                    proposal = db.get(GradeProposal, q_item.proposal_id)
                    if proposal:
                        used_model_run_ids.add(proposal.model_run_id)
                for entry in q_item.accepted_criteria:
                    criterion = next(c for c in question.criteria if c.criterion_id == entry["criterion_id"])
                    criterion_details.append([submission.id, question.question_id, criterion.criterion_id,
                        str(entry["credit"]), str(criterion.max_points), str(Decimal(entry["credit"]) * criterion.max_points),
                        entry["evidence_refs"], entry["rationale"], entry["source"]])
            elif q_item and q_item.proposal_id:
                proposal = db.get(GradeProposal, q_item.proposal_id)
                transcript = db.get(TranscriptionRevision, q_item.transcription_revision_id) if q_item.transcription_revision_id else None
                if proposal and transcript and proposal.transcription_revision_id == transcript.id and proposal.assessment_revision_id == revision.id:
                    used_model_run_ids.add(proposal.model_run_id)
                    for entry in proposal.proposal_payload.get("criteria", []):
                        criterion = next((c for c in question.criteria if c.criterion_id == entry.get("criterion_id")), None)
                        if criterion:
                            credit = Decimal(str(entry["credit"]))
                            criterion_details.append([submission.id, question.question_id, criterion.criterion_id,
                                str(credit), str(criterion.max_points), str(credit * criterion.max_points),
                                entry.get("evidence_refs", []), entry.get("rationale", ""), "model_proposal"])
            transcript = db.get(TranscriptionRevision, answer.active_transcription_revision_id) if answer and answer.active_transcription_revision_id else None
            if transcript and answer.active_mapping_revision_id == transcript.mapping_revision_id:
                included_resource_ids.add(transcript.id)
                if transcript.model_run_id:
                    used_model_run_ids.add(transcript.model_run_id)
                for segment in transcript.segments:
                    region = db.get(Region, segment.get("region_id")) if segment.get("region_id") else None
                    page_index = None
                    if region:
                        page_image = db.get(PageImageRevision, region.page_image_revision_id)
                        page = db.get(Page, page_image.page_id) if page_image else None
                        page_index = page.page_index + 1 if page else None
                    transcription_rows.append([submission.id, question.question_id, segment.get("segment_id", ""),
                        segment.get("region_id", ""), page_index, segment.get("order"), segment.get("text", ""),
                        transcript.flags, transcript.id])
        # Final value appears only from an immutable final snapshot.
        final_score = str(snapshot.final_score) if final and snapshot else None
        summary_rows.append([submission.id, student_id, student_name, submission.attempt_no, *q_contributions,
            str(contribution_sum) if any(value is not None for value in q_contributions) else None,
            final_score, "finalized" if final else (review.status if review else submission.status), snapshot.id if final and snapshot else ""])
        manifest_submissions.append({"submission_id": submission.id, "document_id": document.id if document else None,
            "document_hash": document.sha256 if document else None, "review_revision_id": review.id if review else None,
            "grade_snapshot_id": snapshot.id if final and snapshot else None, "identity_confirmation_id": identity.id if identity else None,
            "answer_ids": sorted(answer.id for answer in answers)})
        included_resource_ids.update(filter(None, [document.id if document else None, identity.id if identity else None,
            review.id if review else None, snapshot.id if snapshot else None]))
        included_resource_ids.update(item.id for item in items.values())
    history = []
    if included_resource_ids:
        events = db.scalars(select(AuditEvent).where(AuditEvent.assessment_id == assessment.id,
            AuditEvent.resource_id.in_(included_resource_ids)).order_by(AuditEvent.created_at)).all()
        for event in events:
            actor = db.get(User, event.actor_id)
            history.append([event.id, event.resource_id, event.action, actor.display_name if actor else "", event.created_at.isoformat(),
                event.previous_revision, event.new_revision, event.reason])
    total_weight = sum((question.weight for question in specs), Decimal("0"))
    selected_all_final = final_count == len(submission_ids)
    model_runs = []
    for run_id in sorted(used_model_run_ids):
        run = db.get(ModelRun, run_id)
        if run:
            model_runs.append({"task_type": run.task_type, "checkpoint": run.checkpoint,
                "revision": run.checkpoint_revision, "checkpoint_sha256": run.checkpoint_sha256,
                "runtime": run.runtime, "prompt_version": run.prompt_version, "schema_version": run.schema_version,
                "preprocessing_version": run.preprocessing_version, "device": run.device, "status": run.status})
    info = {
        "project": "ASDOS",
        "assessment": assessment.title,
        "kelas": assessment.course_label,
        "mode": "FINAL" if mode == "final" else "DRAFT — BELUM DISAHKAN",
        "assessment_revision_id": revision.id,
        "assessment_revision_sequence": str(revision.sequence),
        "w_total": str(total_weight),
        "skala": "0–100",
        "pembulatan": "ROUND_HALF_UP, 2 desimal",
        "cakupan": f"{len(submission_ids)} submission dipilih secara eksplisit",
        "final_count": str(final_count),
        "pending_count": str(pending_count),
        "nilai_akhir_draft": "Kosong sampai semua review disahkan",
        "catatan_kontribusi": "Kontribusi dihitung dengan presisi Decimal; tampilan dapat berbeda 0.01 jika dijumlahkan.",
        "dibuat_pada": now_utc().isoformat(),
    }
    payload = {
        "schema": "asdos-export.v1", "snapshot_id": snapshot_id, "mode": mode,
        "assessment": {"id": assessment.id, "title": assessment.title}, "revision_id": revision.id,
        "questions": question_json, "summary": summary_rows, "question_details": question_details,
        "criterion_details": criterion_details, "transcriptions": transcription_rows,
        "rubric": rubric_rows, "history": history, "info": info,
        "metadata": {"schema": "asdos-export.v1", "scoring_policy": revision.scoring_policy_version,
            "software_release": "0.1.0", "git_commit": "unavailable", "model_runs": model_runs,
            "runtime_mode": "local-only; model inference not rerun for export",
            "export_snapshot_id": snapshot_id, "assessment_revision_id": revision.id,
            "assessment_revision_hash": revision.content_hash, "mode": mode,
            "selected_submission_count": len(submission_ids), "final_submission_count": final_count,
            "pending_submission_count": pending_count, "submitted_by": actor_id,
            "created_at": now_utc().isoformat(), "manifest_submissions": manifest_submissions,
            "included_history_event_count": len(history), "all_selected_final": selected_all_final},
    }
    return _json_value(payload)


@router.post("/assessments/{assessment_id}/exports", status_code=201)
def create_export(assessment_id: str, body: ExportRequest, db: Session = Depends(get_db), actor=Depends(require_writer)):
    if settings.database_url.startswith("postgresql"):
        db.connection(execution_options={"isolation_level": "REPEATABLE READ"})
    assessment = require_owner_scope(db, actor, assessment_id)
    if len(body.submission_ids) != len(set(body.submission_ids)):
        raise HTTPException(status_code=422, detail={"code": "DUPLICATE_SUBMISSION_ID"})
    if body.mode == "final" and not body.submission_ids:
        raise HTTPException(status_code=422, detail={"code": "EMPTY_EXPORT_SCOPE"})
    submissions = db.scalars(select(Submission).where(Submission.assessment_id == assessment.id, Submission.id.in_(body.submission_ids))).all()
    if len(submissions) != len(body.submission_ids):
        raise HTTPException(status_code=404, detail={"code": "EXPORT_SUBMISSION_SCOPE_INVALID"})
    revision_ids = {submission.assessment_revision_id for submission in submissions}
    if len(revision_ids) != 1:
        raise HTTPException(status_code=409, detail={"code": "MIXED_ASSESSMENT_REVISIONS"})
    revision = db.get(AssessmentRevision, next(iter(revision_ids)))
    if not revision or revision.status != "approved":
        raise HTTPException(status_code=409, detail={"code": "APPROVED_ASSESSMENT_REQUIRED"})
    snapshot_id = new_id()
    payload = _build_payload(db, assessment, revision, body.mode, body.submission_ids, snapshot_id, actor.id)
    filename = workbook_filename(assessment.title, body.mode)
    payload["metadata"]["filename"] = filename
    manifest_hash = canonical_hash(payload)
    payload["metadata"]["manifest_hash"] = manifest_hash
    storage_key = None
    try:
        workbook = build_workbook(payload)
        storage_key, file_hash, byte_size = artifact_store.put(workbook)
        export_row = ExportSnapshot(id=snapshot_id, assessment_id=assessment.id, assessment_revision_id=revision.id,
            mode=body.mode, payload=payload, manifest_hash=manifest_hash, artifact_key=storage_key,
            artifact_hash=file_hash, created_by=actor.id)
        db.add(export_row)
        db.add(Artifact(assessment_id=assessment.id, storage_key=storage_key, kind=f"export_{body.mode}",
            sha256=file_hash, byte_size=byte_size, parent_ids=body.submission_ids, retention_class="export"))
        db.add(AuditEvent(assessment_id=assessment.id, actor_id=actor.id, action="grade.export_created",
            resource_id=export_row.id, new_revision=revision.id, metadata_json={"mode": body.mode, "manifest_hash": manifest_hash,
            "submission_count": len(body.submission_ids), "sha256": file_hash, "filename": filename}))
        db.commit()
    except Exception:
        db.rollback()
        if storage_key:
            artifact_store.delete(storage_key)
        raise
    return {"id": snapshot_id, "mode": body.mode, "manifest_hash": manifest_hash, "sha256": file_hash,
        "bytes": byte_size, "filename": filename, "download_url": f"/api/v1/exports/{snapshot_id}/download"}


@router.get("/exports/{snapshot_id}/download")
def download_export(snapshot_id: str, db: Session = Depends(get_db), actor=Depends(require_actor)):
    export_row = db.get(ExportSnapshot, snapshot_id)
    if not export_row:
        raise HTTPException(status_code=404, detail={"code": "RESOURCE_NOT_FOUND"})
    require_owner_scope(db, actor, export_row.assessment_id)
    artifact = db.scalar(select(Artifact).where(Artifact.storage_key == export_row.artifact_key))
    if not artifact or artifact.purged_at is not None:
        raise HTTPException(status_code=410, detail={"code": "EXPORT_PURGED"})
    try:
        data = artifact_store.read(export_row.artifact_key)
    except FileNotFoundError as exc:
        # A concurrent purge may unlink the file after the tombstone lookup.
        raise HTTPException(status_code=410, detail={"code": "EXPORT_PURGED"}) from exc
    if hashlib.sha256(data).hexdigest() != export_row.artifact_hash:
        raise HTTPException(status_code=409, detail={"code": "EXPORT_ARTIFACT_HASH_MISMATCH"})
    if canonical_hash(export_row.payload) != export_row.manifest_hash:
        # manifest excludes its own duplicated display field; compare its canonical body without that display field.
        payload = dict(export_row.payload)
        payload["metadata"] = dict(payload.get("metadata", {}))
        payload["metadata"].pop("manifest_hash", None)
        if canonical_hash(payload) != export_row.manifest_hash:
            raise HTTPException(status_code=409, detail={"code": "EXPORT_SNAPSHOT_HASH_MISMATCH"})
    filename = export_row.payload.get("metadata", {}).get("filename") or workbook_filename(export_row.payload["assessment"]["title"], export_row.mode, export_row.created_at)
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "private, no-store",
                 "X-Content-Type-Options": "nosniff", "X-ASDOS-Manifest-SHA256": export_row.manifest_hash})
