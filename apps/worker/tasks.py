from __future__ import annotations

import json
import shutil
import threading
import time
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from sqlalchemy import select

from apps.api.asdos_api.config import settings
from apps.api.asdos_api.database import SessionLocal
from apps.api.asdos_api.model_adapters import ModelUnavailable, qwen_adapter
from apps.api.asdos_api.models import (
    Answer,
    AnswerMappingRevision,
    AnswerRegionLink,
    Artifact,
    Assessment,
    AssessmentRevision,
    CriterionProposalResult,
    Document,
    DocumentLayoutRevision,
    GradeProposal,
    ModelRun,
    Page,
    PageImageRevision,
    PipelineJob,
    QuestionRevision,
    Region,
    RubricCriterion,
    Submission,
    TranscriptionRevision,
    now_utc,
)
from packages.asdos_domain.scoring import CriterionSpec
from apps.api.asdos_api.storage import ArtifactStore
from apps.api.asdos_api.services import canonical_hash
from apps.worker.celery_app import celery_app
from apps.worker.pdfium_runner import PdfPipelineError, render_in_isolated_process

store = ArtifactStore()
LEASE_SECONDS = 1800
MAX_AUTO_ATTEMPTS = 3
RECOVERY_DISPATCH_COOLDOWN_SECONDS = 60


def _lease_is_live(value) -> bool:
    if value is None:
        return False
    if value.tzinfo is None:
        value = value.replace(tzinfo=now_utc().tzinfo)
    return value > now_utc()


def _begin(job_id: str) -> tuple[str, str] | None:
    worker_id = f"{uuid4()}"
    with SessionLocal.begin() as db:
        job = db.get(PipelineJob, job_id)
        if not job or job.status in {"succeeded", "cancelled"}:
            return None
        if job.cancel_requested:
            job.status = "cancelled"
            job.finished_at = now_utc()
            return None
        if job.status == "running" and _lease_is_live(job.lease_until):
            return None
        job.status = "running"
        job.lease_owner = worker_id
        job.lease_until = now_utc() + timedelta(seconds=LEASE_SECONDS)
        job.heartbeat_at = now_utc()
        job.error_code = None
    return job_id, worker_id


@contextmanager
def _heartbeat(job_id: str, worker_id: str) -> Iterator[None]:
    stopped = threading.Event()

    def pulse() -> None:
        while not stopped.wait(30):
            try:
                with SessionLocal.begin() as db:
                    job = db.get(PipelineJob, job_id)
                    if job and job.status == "running" and job.lease_owner == worker_id:
                        job.heartbeat_at = now_utc()
                        job.lease_until = now_utc() + timedelta(seconds=LEASE_SECONDS)
            except Exception:
                continue

    thread = threading.Thread(target=pulse, name=f"asdos-heartbeat-{job_id[:8]}", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stopped.set()
        thread.join(timeout=2)


def _finish(job_id: str, worker_id: str, *, status: str, error_code: str | None = None) -> None:
    with SessionLocal.begin() as db:
        job = db.get(PipelineJob, job_id)
        if not job or job.lease_owner != worker_id:
            return
        job.status = status
        job.error_code = error_code
        job.finished_at = now_utc() if status in {"succeeded", "failed", "cancelled"} else None
        job.lease_owner = None
        job.lease_until = None
        job.heartbeat_at = now_utc()


def _failed(job_id: str, worker_id: str, code: str) -> dict:
    _finish(job_id, worker_id, status="failed", error_code=code)
    return {"job_id": job_id, "status": "failed", "error_code": code}


@celery_app.task(name="asdos.process_document", bind=True, max_retries=0)
def process_document(self, job_id: str) -> dict:
    lease = _begin(job_id)
    if not lease:
        return {"job_id": job_id, "status": "skipped"}
    _, worker_id = lease
    temp_root: Path | None = None
    created_storage_keys: list[str] = []
    committed = False
    with _heartbeat(job_id, worker_id):
        try:
            with SessionLocal() as db:
                job = db.get(PipelineJob, job_id)
                document = db.get(Document, job.document_id) if job else None
                if not job or not document:
                    return _failed(job_id, worker_id, "DOCUMENT_SCOPE_MISSING")
                assessment = db.get(Assessment, document.assessment_id)
                if not assessment:
                    return _failed(job_id, worker_id, "ASSESSMENT_SCOPE_MISSING")
                source_path = store.path(document.storage_key)
                question_import = document.kind == "question_source"
                original_sha = document.sha256
            manifest, temp_root = render_in_isolated_process(source_path, extract_text=question_import)
            created_pages: list[tuple[dict, str, str]] = []
            page_text: list[str] = []
            for info in manifest["pages"]:
                if info.get("text"):
                    page_text.append(str(info["text"]))
                key, digest, size = store.put((temp_root / info["file"]).read_bytes())
                created_storage_keys.append(key)
                if digest != info["sha256"]:
                    raise PdfPipelineError("RENDER_ARTIFACT_HASH_MISMATCH")
                created_pages.append((info, key, digest))
            with SessionLocal.begin() as db:
                job = db.get(PipelineJob, job_id)
                document = db.get(Document, job.document_id) if job else None
                if (not job or not document or document.sha256 != original_sha
                        or job.status != "running" or job.lease_owner != worker_id or job.cancel_requested):
                    if job and job.lease_owner == worker_id:
                        cancelled = job.cancel_requested
                        job.status = "cancelled" if cancelled else "failed"
                        job.error_code = None if cancelled else "STALE_DOCUMENT_INPUT"
                        job.finished_at = now_utc()
                        job.lease_owner = None
                        job.lease_until = None
                    return {"job_id": job_id, "status": "cancelled_or_stale"}
                revision_ids: list[str] = []
                for info, key, digest in created_pages:
                    page = Page(
                        document_id=document.id,
                        page_index=info["page_index"],
                        original_rotation=info["original_rotation"],
                        pdf_width_points=info["pdf_width_points"],
                        pdf_height_points=info["pdf_height_points"],
                    )
                    db.add(page)
                    db.flush()
                    transform = {"type": "affine", "matrix": [1, 0, 0, 1, 0, 0], "coordinate_space": "canonical_render"}
                    inverse = {**transform, "inverse_of": "identity"}
                    image_revision = PageImageRevision(
                        page_id=page.id,
                        sequence=1,
                        image_storage_key=key,
                        width_px=info["width_px"],
                        height_px=info["height_px"],
                        rotation=0,
                        transform=transform,
                        inverse_transform=inverse,
                        image_sha256=digest,
                        preprocessing_version=f"pdfium-{manifest['dpi']}dpi.v1",
                    )
                    db.add(image_revision)
                    db.flush()
                    revision_ids.append(image_revision.id)
                    db.add(Artifact(
                        assessment_id=document.assessment_id,
                        document_id=document.id,
                        storage_key=key,
                        kind="page_render",
                        sha256=digest,
                        byte_size=store.path(key).stat().st_size,
                        parent_ids=[document.id],
                    ))
                max_layout = db.scalar(
                    select(DocumentLayoutRevision.sequence)
                    .where(DocumentLayoutRevision.document_id == document.id)
                    .order_by(DocumentLayoutRevision.sequence.desc())
                    .limit(1)
                ) or 0
                layout = DocumentLayoutRevision(
                    document_id=document.id,
                    sequence=max_layout + 1,
                    ordered_page_image_revision_ids=revision_ids,
                    created_by=assessment.owner_id,
                )
                db.add(layout)
                db.flush()
                document.active_layout_revision_id = layout.id
                document.page_count = len(created_pages)
                document.validation_status = "needs_review" if question_import else "valid"
                if question_import:
                    document.extracted_text = "\n\n".join(page_text)
                job.status = "succeeded"
                job.progress_current = job.progress_total = len(created_pages)
                job.finished_at = now_utc()
                job.lease_owner = None
                job.lease_until = None
                job.heartbeat_at = now_utc()
                if document.submission_id:
                    submission = db.get(Submission, document.submission_id)
                    if submission:
                        submission.status = "needs_mapping" if submission.identity_status == "confirmed" else "awaiting_identity"
            committed = True
            return {"job_id": job_id, "status": "succeeded", "pages": len(created_pages)}
        except PdfPipelineError as exc:
            return _failed(job_id, worker_id, exc.code)
        except Exception as exc:
            code = getattr(exc, "code", None) or "PIPELINE_STAGE_FAILED"
            return _failed(job_id, worker_id, code)
        finally:
            if not committed:
                for key in created_storage_keys:
                    store.delete(key)
            if temp_root:
                shutil.rmtree(temp_root.parent, ignore_errors=True)


@celery_app.task(name="asdos.transcribe_answer", bind=True, max_retries=0)
def transcribe_answer(self, job_id: str) -> dict:
    lease = _begin(job_id)
    if not lease:
        return {"job_id": job_id, "status": "skipped"}
    _, worker_id = lease
    try:
        with _heartbeat(job_id, worker_id), SessionLocal() as db:
            job = db.get(PipelineJob, job_id)
            answer = db.get(Answer, job.answer_id) if job and job.answer_id else None
            if not job or not answer:
                return _failed(job_id, worker_id, "ANSWER_SCOPE_MISSING")
            submission = db.get(Submission, answer.submission_id)
            assessment = db.get(Assessment, job.assessment_id)
            if not submission or not assessment or submission.active_document_id != job.document_id:
                return _failed(job_id, worker_id, "STALE_DOCUMENT_INPUT")
            if submission.identity_status != "confirmed":
                return _failed(job_id, worker_id, "IDENTITY_CONFIRMATION_REQUIRED")
            mapping = db.get(AnswerMappingRevision, answer.active_mapping_revision_id) if answer.active_mapping_revision_id else None
            if not mapping:
                return _failed(job_id, worker_id, "UNMAPPED_ANSWER")
            links = db.scalars(
                select(AnswerRegionLink).where(
                    AnswerRegionLink.answer_id == answer.id,
                    AnswerRegionLink.mapping_revision_id == answer.active_mapping_revision_id,
                ).order_by(AnswerRegionLink.order_index)
            ).all()
            if not links:
                return _failed(job_id, worker_id, "UNMAPPED_ANSWER")
            regions, images, region_fingerprint = _read_region_images(db, links)
            input_fingerprint = canonical_hash({"document": job.document_id, "answer": answer.id,
                                                "regions": region_fingerprint, "language": assessment.language})
            if input_fingerprint != job.input_fingerprint:
                return _failed(job_id, worker_id, "STALE_MODEL_INPUT")
            run = ModelRun(
                task_type="transcription",
                checkpoint="Qwen/Qwen3-VL-4B-Instruct",
                checkpoint_revision=settings.model_revision,
                runtime=qwen_adapter.runtime,
                prompt_version="literal-transcription.v1",
                schema_version="transcript.v1",
                preprocessing_version="region-crop.v1",
                input_fingerprint=input_fingerprint,
                device="pending",
                status="running",
            )
            db.add(run)
            db.commit()
            try:
                segments, provenance = qwen_adapter.transcribe(images, assessment.language)
            except ModelUnavailable as exc:
                run.status = "failed"
                run.error_code = exc.code
                db.commit()
                return _failed(job_id, worker_id, exc.code)
            run.status = "succeeded"
            run.device = provenance.device
            run.checkpoint_sha256 = provenance.checkpoint_sha256
            current_job = db.scalar(select(PipelineJob).where(PipelineJob.id == job_id)
                                     .with_for_update().execution_options(populate_existing=True))
            if (not current_job or current_job.status != "running" or current_job.lease_owner != worker_id):
                run.status = "stale"
                db.commit()
                return {"job_id": job_id, "status": "stale_lease"}
            if current_job.cancel_requested:
                run.status = "cancelled"
                current_job.status = "cancelled"
                current_job.finished_at = now_utc()
                current_job.lease_owner = None
                current_job.lease_until = None
                db.commit()
                return {"job_id": job_id, "status": "cancelled"}
            revision_data = []
            for index, (region, segment) in enumerate(zip(regions, segments, strict=True), start=1):
                revision_data.append({
                    "segment_id": f"seg-{index}",
                    "region_id": region["id"],
                    "page_index": region["page_index"],
                    "order": index,
                    "text": segment.text,
                    "confidence": None,
                    "flags": list(segment.flags),
                })
            current_submission = db.scalar(select(Submission).where(
                Submission.id == submission.id).with_for_update().execution_options(populate_existing=True))
            current_answer = db.scalar(select(Answer).where(
                Answer.id == answer.id).with_for_update().execution_options(populate_existing=True))
            current_links = db.scalars(select(AnswerRegionLink).where(
                AnswerRegionLink.answer_id == answer.id,
                AnswerRegionLink.mapping_revision_id == (current_answer.active_mapping_revision_id if current_answer else None),
            ).order_by(AnswerRegionLink.order_index)).all()
            if (not current_answer or not current_submission or current_submission.active_document_id != job.document_id
                    or current_submission.identity_status != "confirmed" or current_answer.active_mapping_revision_id != mapping.id
                    or [item.region_id for item in current_links] != [r["id"] for r in regions]):
                run.status = "stale"
                db.commit()
                return _failed(job_id, worker_id, "STALE_MODEL_INPUT")
            revision_no = current_answer.transcript_revision + 1
            transcript = TranscriptionRevision(
                answer_id=current_answer.id,
                mapping_revision_id=mapping.id,
                revision_no=revision_no,
                parent_revision_id=current_answer.active_transcription_revision_id,
                literal_text="\n".join(item["text"] for item in revision_data),
                segments=revision_data,
                status="transcribed",
                flags=[],
                source="model",
                model_run_id=run.id,
            )
            db.add(transcript)
            db.flush()
            current_answer.active_transcription_revision_id = transcript.id
            current_answer.transcript_revision = revision_no
            current_answer.transcript_status = "transcribed"
            current_answer.literal_text = transcript.literal_text
            current_answer.active_proposal_id = None
            current_job.status = "succeeded"
            current_job.finished_at = now_utc()
            current_job.error_code = None
            current_job.lease_owner = None
            current_job.lease_until = None
            current_job.heartbeat_at = now_utc()
            db.commit()
            return {"job_id": job_id, "status": "succeeded", "segments": len(revision_data)}
    except Exception as exc:
        return _failed(job_id, worker_id, getattr(exc, "code", None) or "TRANSCRIPTION_FAILED")


@celery_app.task(name="asdos.grade_answer", bind=True, max_retries=0)
def grade_answer(self, job_id: str) -> dict:
    lease = _begin(job_id)
    if not lease:
        return {"job_id": job_id, "status": "skipped"}
    _, worker_id = lease
    try:
        with _heartbeat(job_id, worker_id), SessionLocal() as db:
            job = db.get(PipelineJob, job_id)
            answer = db.get(Answer, job.answer_id) if job and job.answer_id else None
            submission = db.get(Submission, answer.submission_id) if answer else None
            assessment = db.get(Assessment, job.assessment_id) if job else None
            revision = db.get(AssessmentRevision, submission.assessment_revision_id) if submission else None
            if not job or not answer or not submission or not assessment or not revision or revision.status != "approved":
                return _failed(job_id, worker_id, "APPROVED_RUBRIC_REQUIRED")
            if submission.identity_status != "confirmed" or submission.active_document_id != job.document_id:
                return _failed(job_id, worker_id, "IDENTITY_OR_DOCUMENT_STALE")
            transcript = db.get(TranscriptionRevision, answer.active_transcription_revision_id) if answer.active_transcription_revision_id else None
            if (not transcript or transcript.status not in {"transcribed", "corrected"}
                    or transcript.mapping_revision_id != answer.active_mapping_revision_id):
                return _failed(job_id, worker_id, "ACTIVE_TRANSCRIPTION_REQUIRED")
            question = db.scalar(select(QuestionRevision).where(
                QuestionRevision.assessment_revision_id == revision.id,
                QuestionRevision.stable_question_id == answer.stable_question_id,
            ))
            if not question:
                return _failed(job_id, worker_id, "QUESTION_REVISION_MISSING")
            criterion_rows = db.scalars(select(RubricCriterion).where(RubricCriterion.question_revision_id == question.id)).all()
            rubric = {
                "reference_answer": question.reference_answer,
                "alternatives": question.alternatives,
                "criteria": [{
                    "criterion_id": item.criterion_id,
                    "description": item.description,
                    "max_points": str(item.max_points),
                    "credit_levels": item.credit_levels,
                    "anchors": item.anchors,
                } for item in criterion_rows],
            }
            question_payload = {"question_id": question.stable_question_id, "label": question.label, "text": question.text}
            segments = {item["segment_id"]: item["text"] for item in transcript.segments}
            catalog = []
            region_ids = []
            for segment in transcript.segments:
                region_ids.append(segment["region_id"])
                catalog.append({key: segment[key] for key in ("segment_id", "region_id", "page_index", "order", "text")})
            expected_fingerprint = canonical_hash({
                "answer_id": answer.id,
                "transcript_revision": transcript.id,
                "assessment_revision": revision.id,
                "question_id": question.id,
            })
            if expected_fingerprint != job.input_fingerprint:
                return _failed(job_id, worker_id, "STALE_MODEL_INPUT")
            run = ModelRun(
                task_type="grading",
                checkpoint="Qwen/Qwen3-VL-4B-Instruct",
                checkpoint_revision=settings.model_revision,
                runtime=qwen_adapter.runtime,
                prompt_version="criterion-grading.v1",
                schema_version="grade-proposal.v1",
                preprocessing_version="none",
                input_fingerprint=expected_fingerprint,
                device="pending",
                status="running",
            )
            db.add(run)
            db.commit()
            try:
                proposal, provenance = qwen_adapter.grade(
                    question_id=question.stable_question_id,
                    question=question_payload,
                    rubric=rubric,
                    transcript=transcript.literal_text,
                    segments=segments,
                    evidence_catalog=catalog,
                    valid_region_ids=region_ids,
                )
            except (ModelUnavailable, ValueError) as exc:
                run.status = "failed"
                run.error_code = getattr(exc, "code", None) or "MODEL_OUTPUT_INVALID"
                db.commit()
                return _failed(job_id, worker_id, run.error_code)
            run.status = "succeeded"
            run.device = provenance.device
            run.checkpoint_sha256 = provenance.checkpoint_sha256
            current_job = db.scalar(select(PipelineJob).where(PipelineJob.id == job_id)
                                     .with_for_update().execution_options(populate_existing=True))
            if (not current_job or current_job.status != "running" or current_job.lease_owner != worker_id):
                run.status = "stale"
                db.commit()
                return {"job_id": job_id, "status": "stale_lease"}
            if current_job.cancel_requested:
                run.status = "cancelled"
                current_job.status = "cancelled"
                current_job.finished_at = now_utc()
                current_job.lease_owner = None
                current_job.lease_until = None
                db.commit()
                return {"job_id": job_id, "status": "cancelled"}
            current_submission = db.scalar(select(Submission).where(
                Submission.id == submission.id).with_for_update().execution_options(populate_existing=True))
            current_answer = db.scalar(select(Answer).where(
                Answer.id == answer.id).with_for_update().execution_options(populate_existing=True))
            current_transcript = db.get(TranscriptionRevision, current_answer.active_transcription_revision_id) if current_answer and current_answer.active_transcription_revision_id else None
            if (not current_answer or not current_submission or current_submission.active_document_id != job.document_id
                    or current_submission.identity_status != "confirmed" or current_answer.active_transcription_revision_id != transcript.id
                    or not current_transcript or current_transcript.mapping_revision_id != current_answer.active_mapping_revision_id):
                run.status = "stale"
                db.commit()
                return _failed(job_id, worker_id, "STALE_MODEL_INPUT")
            proposal_row = GradeProposal(
                answer_id=answer.id,
                transcription_revision_id=transcript.id,
                assessment_revision_id=revision.id,
                model_run_id=run.id,
                status="proposed",
                proposal_payload=proposal,
            )
            db.add(proposal_row)
            db.flush()
            criterion_map = {item.criterion_id: item for item in criterion_rows}
            for item in proposal["criteria"]:
                criterion = criterion_map[item["criterion_id"]]
                credit = __import__("decimal").Decimal(item["credit"])
                db.add(CriterionProposalResult(
                    proposal_id=proposal_row.id,
                    criterion_id=item["criterion_id"],
                    credit=credit,
                    points=credit * criterion.max_points,
                    evidence_refs=item["evidence_refs"],
                    rationale=item["rationale"],
                ))
            answer.active_proposal_id = proposal_row.id
            current_job.status = "succeeded"
            current_job.finished_at = now_utc()
            current_job.error_code = None
            current_job.lease_owner = None
            current_job.lease_until = None
            current_job.heartbeat_at = now_utc()
            db.commit()
            return {"job_id": job_id, "status": "succeeded", "proposal_id": proposal_row.id}
    except Exception as exc:
        return _failed(job_id, worker_id, getattr(exc, "code", None) or "GRADING_FAILED")


def _read_region_images(db, links) -> tuple[list[dict], list[bytes], list[str]]:
    from io import BytesIO
    from PIL import Image

    regions, images, fingerprints = [], [], []
    for link in links:
        region = db.get(Region, link.region_id)
        image_revision = db.get(PageImageRevision, region.page_image_revision_id) if region else None
        page = db.get(Page, image_revision.page_id) if image_revision else None
        if not region or not image_revision or not page:
            raise PdfPipelineError("REGION_IMAGE_REFERENCE_MISSING")
        png = store.read(image_revision.image_storage_key)
        image = Image.open(BytesIO(png)).convert("RGB")
        polygon = region.polygon
        x_values, y_values = [point[0] for point in polygon], [point[1] for point in polygon]
        left = max(0, int(min(x_values) * image.width))
        top = max(0, int(min(y_values) * image.height))
        right = min(image.width, int(max(x_values) * image.width + 0.999))
        bottom = min(image.height, int(max(y_values) * image.height + 0.999))
        if right <= left or bottom <= top:
            raise PdfPipelineError("REGION_EMPTY")
        crop = image.crop((left, top, right, bottom))
        output = BytesIO()
        crop.save(output, format="PNG")
        images.append(output.getvalue())
        regions.append({
            "id": region.id,
            "page_index": page.page_index,
            "polygon": polygon,
            "order": link.order_index,
        })
        fingerprints.append({"region_id": region.id, "page_image_hash": image_revision.image_sha256, "polygon": polygon})
    return regions, images, [json.dumps(item, sort_keys=True) for item in fingerprints]


@celery_app.task(name="asdos.dispatch_outbox")
def dispatch_outbox() -> dict:
    with SessionLocal() as db:
        from apps.api.asdos_api.models import OutboxEvent

        events = db.scalars(
            select(OutboxEvent).where(OutboxEvent.published_at.is_(None)).order_by(OutboxEvent.created_at).limit(100)
        ).all()
        published = 0
        for event in events:
            task_name = {
                "document.process": "asdos.process_document",
                "answer.transcribe": "asdos.transcribe_answer",
                "answer.grade": "asdos.grade_answer",
            }.get(event.event_type)
            if not task_name:
                event.published_at = now_utc()
                continue
            celery_app.send_task(task_name, args=[event.job_id], task_id=event.id)
            event.published_at = now_utc()
            published += 1
        db.commit()
        return {"published": published}


@celery_app.task(name="asdos.recover_expired_jobs")
def recover_expired_jobs() -> dict:
    from apps.api.asdos_api.models import OutboxEvent

    recovered = 0
    now = now_utc()
    cooldown_start = now - timedelta(seconds=RECOVERY_DISPATCH_COOLDOWN_SECONDS)
    with SessionLocal.begin() as db:
        queued = db.scalars(select(PipelineJob).where(
            PipelineJob.status == "queued",
        ).order_by(PipelineJob.created_at).limit(500).with_for_update(skip_locked=True)).all()
        running = db.scalars(select(PipelineJob).where(
            PipelineJob.status == "running",
        ).order_by(PipelineJob.lease_until, PipelineJob.created_at).limit(500).with_for_update(skip_locked=True)).all()
        for job in [*queued, *(item for item in running if not _lease_is_live(item.lease_until))]:
            if job.cancel_requested:
                if job.status == "running" and _lease_is_live(job.lease_until):
                    continue
                job.status = "cancelled"
                job.finished_at = now
                job.lease_owner = None
                job.lease_until = None
                continue
            if job.status == "running" and _lease_is_live(job.lease_until):
                continue
            if job.status == "running":
                if job.attempt >= MAX_AUTO_ATTEMPTS:
                    job.status = "failed"
                    job.error_code = "WORKER_RESTART_RETRY_EXHAUSTED"
                    job.finished_at = now
                    job.lease_owner = None
                    job.lease_until = None
                    continue
                job.attempt += 1
                job.status = "queued"
                job.lease_owner = None
                job.lease_until = None
            event_type = {
                "document_render": "document.process",
                "question_import": "document.process",
                "transcribe_answer": "answer.transcribe",
                "grade_answer": "answer.grade",
            }.get(job.kind)
            if not event_type:
                continue
            has_unpublished = db.scalar(select(OutboxEvent.id).where(
                OutboxEvent.job_id == job.id,
                OutboxEvent.published_at.is_(None),
            ).limit(1))
            latest_event = db.scalar(select(OutboxEvent.created_at).where(
                OutboxEvent.job_id == job.id,
            ).order_by(OutboxEvent.created_at.desc()).limit(1))
            if latest_event and latest_event.tzinfo is None:
                latest_event = latest_event.replace(tzinfo=now.tzinfo)
            if has_unpublished or (latest_event and latest_event >= cooldown_start):
                continue
            if event_type:
                db.add(OutboxEvent(event_type=event_type, job_id=job.id, payload={"attempt": job.attempt}))
                recovered += 1
    return {"requeued": recovered}
