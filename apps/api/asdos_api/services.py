from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.asdos_domain.scoring import CriterionSpec, QuestionSpec

from .models import (
    Assessment,
    AssessmentRevision,
    OutboxEvent,
    PipelineJob,
    QuestionRevision,
    RubricCriterion,
    now_utc,
)


def canonical_hash(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def assessment_for_owner(db: Session, assessment_id: str, owner_id: str) -> Assessment:
    assessment = db.scalar(select(Assessment).where(Assessment.id == assessment_id, Assessment.owner_id == owner_id))
    if not assessment:
        raise HTTPException(status_code=404, detail={"code": "RESOURCE_NOT_FOUND"})
    return assessment


def load_question_specs(db: Session, revision_id: str) -> list[QuestionSpec]:
    question_rows = db.scalars(
        select(QuestionRevision).where(QuestionRevision.assessment_revision_id == revision_id).order_by(QuestionRevision.order_index)
    ).all()
    result = []
    for row in question_rows:
        criteria = db.scalars(select(RubricCriterion).where(RubricCriterion.question_revision_id == row.id)).all()
        result.append(QuestionSpec(
            question_id=row.stable_question_id,
            label=row.label,
            order=row.order_index,
            weight=Decimal(str(row.weight)),
            criteria=tuple(CriterionSpec(
                criterion_id=item.criterion_id,
                description=item.description,
                max_points=Decimal(str(item.max_points)),
                credit_levels=tuple(Decimal(str(value)) for value in item.credit_levels),
                anchors={str(key): value for key, value in item.anchors.items()},
            ) for item in criteria),
        ))
    return result


def question_json(db: Session, revision_id: str) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(QuestionRevision).where(QuestionRevision.assessment_revision_id == revision_id).order_by(QuestionRevision.order_index)
    ).all()
    payload = []
    for row in rows:
        criteria = db.scalars(select(RubricCriterion).where(RubricCriterion.question_revision_id == row.id)).all()
        payload.append({
            "stable_question_id": row.stable_question_id,
            "label": row.label,
            "order": row.order_index,
            "text": row.text,
            "answer_type": row.answer_type,
            "weight": str(row.weight),
            "reference_answer": row.reference_answer,
            "alternatives": row.alternatives,
            "criteria": [{
                "id": item.criterion_id,
                "description": item.description,
                "max_points": str(item.max_points),
                "credit_levels": [str(value) for value in item.credit_levels],
                "anchors": item.anchors,
            } for item in criteria],
        })
    return payload


def validate_question_payload(questions) -> list[QuestionSpec]:
    specs = []
    ids: set[str] = set()
    labels: set[str] = set()
    orders: set[int] = set()
    for item in questions:
        if item.stable_question_id in ids or item.label in labels or item.order in orders:
            raise HTTPException(status_code=422, detail={"code": "DUPLICATE_QUESTION_ID_LABEL_OR_ORDER"})
        ids.add(item.stable_question_id)
        labels.add(item.label)
        orders.add(item.order)
        try:
            criteria = tuple(CriterionSpec(
                criterion_id=criterion.id,
                description=criterion.description,
                max_points=Decimal(criterion.max_points),
                credit_levels=tuple(Decimal(value) for value in criterion.credit_levels),
                anchors=criterion.anchors,
            ) for criterion in item.criteria)
            if any(Decimal("0") not in c.credit_levels or Decimal("1") not in c.credit_levels for c in criteria):
                raise ValueError("rubric credit levels must include 0 and 1")
            specs.append(QuestionSpec(
                question_id=item.stable_question_id,
                label=item.label,
                order=item.order,
                weight=Decimal(item.weight),
                criteria=criteria,
            ))
        except Exception as exc:
            raise HTTPException(status_code=422, detail={"code": "INVALID_RUBRIC", "message": str(exc)}) from exc
    return sorted(specs, key=lambda question: question.order)


def add_job(
    db: Session,
    *,
    assessment_id: str,
    document_id: str | None,
    kind: str,
    input_fingerprint: str,
    submission_id: str | None = None,
    answer_id: str | None = None,
    draft_assessment_revision_id: str | None = None,
) -> PipelineJob:
    if kind == "rubric_generate":
        if not draft_assessment_revision_id or document_id or submission_id or answer_id:
            raise ValueError("rubric generation must be assessment-revision scoped")
    elif not document_id:
        raise ValueError("document-scoped pipeline job requires a document")
    previous = db.scalar(select(PipelineJob).where(
        PipelineJob.input_fingerprint == input_fingerprint,
        PipelineJob.kind == kind,
    ).order_by(PipelineJob.attempt.desc()).limit(1))
    if previous and previous.status in {"queued", "running", "succeeded"}:
        return previous
    attempt = (previous.attempt + 1) if previous else 1
    if attempt > 3:
        raise HTTPException(status_code=409, detail={"code": "RETRY_LIMIT_REACHED"})
    job = PipelineJob(
        assessment_id=assessment_id,
        submission_id=submission_id,
        answer_id=answer_id,
        document_id=document_id,
        draft_assessment_revision_id=draft_assessment_revision_id,
        kind=kind,
        stage=kind,
        input_fingerprint=input_fingerprint,
        attempt=attempt,
        status="queued",
    )
    db.add(job)
    db.flush()
    event_type = {
        "document_render": "document.process",
        "question_import": "document.process",
        "transcribe_answer": "answer.transcribe",
        "grade_answer": "answer.grade",
        "rubric_generate": "rubric.generate",
        "analyze_answers": "document.analyze_answers",
    }[kind]
    db.add(OutboxEvent(event_type=event_type, job_id=job.id, payload={"job_id": job.id}))
    return job


def publish_job_outbox(db: Session, job_id: str) -> None:
    """Publish after the caller committed; failures leave the DB outbox pending."""
    from apps.worker.tasks import grade_answer, process_document, transcribe_answer, generate_rubric
    from apps.worker.auto_answers import analyze_answers

    task_map = {
        "document_render": process_document,
        "question_import": process_document,
        "transcribe_answer": transcribe_answer,
        "grade_answer": grade_answer,
        "rubric_generate": generate_rubric,
        "analyze_answers": analyze_answers,
    }
    events = db.scalars(select(OutboxEvent).where(OutboxEvent.job_id == job_id, OutboxEvent.published_at.is_(None))).all()
    for event in events:
        job = db.get(PipelineJob, event.job_id)
        if not job:
            event.published_at = now_utc()
            continue
        task_map[job.kind].apply_async(args=[job.id], task_id=event.id)
        event.published_at = now_utc()
    db.commit()
