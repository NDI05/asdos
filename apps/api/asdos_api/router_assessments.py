from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .database import get_db
from .dependencies import require_actor, require_owner_scope, require_writer
from .models import (
    Assessment,
    AssessmentRevision,
    AuditEvent,
    QuestionRevision,
    RubricCriterion,
    Submission,
    now_utc,
)
from .schemas import AssessmentCreate, QuestionSet, RevisionCreate, RevisionExpectation, GenerateRubricRequest
from .services import canonical_hash, question_json, validate_question_payload

router = APIRouter(prefix="/api/v1", tags=["assessments"])


@router.get("/assessments")
def list_assessments(db: Session = Depends(get_db), actor=Depends(require_actor)):
    rows = db.scalars(select(Assessment).where(Assessment.owner_id == actor.id).order_by(Assessment.created_at.desc())).all()
    items = []
    for assessment in rows:
        revision = db.get(AssessmentRevision, assessment.active_revision_id) if assessment.active_revision_id else None
        count = db.scalar(select(func.count(Submission.id)).where(Submission.assessment_id == assessment.id)) or 0
        items.append({
            "id": assessment.id,
            "title": assessment.title,
            "course_label": assessment.course_label,
            "language": assessment.language,
            "status": assessment.lifecycle_status,
            "revision": ({"id": revision.id, "sequence": revision.sequence, "version": revision.version, "status": revision.status} if revision else None),
            "submission_count": count,
            "created_at": assessment.created_at.isoformat(),
        })
    return {"items": items}


@router.post("/assessments", status_code=201)
def create_assessment(body: AssessmentCreate, db: Session = Depends(get_db), actor=Depends(require_writer)):
    assessment = Assessment(
        owner_id=actor.id,
        title=body.title,
        course_label=body.course_label,
        language=body.language,
        lifecycle_status="draft",
    )
    db.add(assessment)
    db.flush()
    revision = AssessmentRevision(assessment_id=assessment.id, sequence=1, status="draft", created_by=actor.id)
    db.add(revision)
    db.flush()
    assessment.active_revision_id = revision.id
    db.add(AuditEvent(
        assessment_id=assessment.id,
        actor_id=actor.id,
        action="assessment.created",
        resource_id=assessment.id,
        new_revision=revision.id,
        metadata_json={"revision_sequence": 1},
    ))
    db.commit()
    return {"id": assessment.id, "title": assessment.title, "status": assessment.lifecycle_status,
            "revision": {"id": revision.id, "sequence": revision.sequence, "version": revision.version, "status": revision.status}}


@router.post("/assessments/{assessment_id}/revisions", status_code=201)
def create_revision(assessment_id: str, body: RevisionCreate, db: Session = Depends(get_db), actor=Depends(require_writer)):
    assessment = db.scalar(select(Assessment).where(Assessment.id == assessment_id).with_for_update())
    if not assessment:
        raise HTTPException(status_code=404, detail={"code": "RESOURCE_NOT_FOUND"})
    require_owner_scope(db, actor, assessment.id)
    base = db.get(AssessmentRevision, body.base_revision_id)
    if not base or base.assessment_id != assessment.id or base.status != "approved":
        raise HTTPException(status_code=409, detail={"code": "BASE_REVISION_NOT_APPROVED"})
    sequence = (db.scalar(select(func.max(AssessmentRevision.sequence)).where(AssessmentRevision.assessment_id == assessment.id)) or 0) + 1
    revision = AssessmentRevision(
        assessment_id=assessment.id,
        sequence=sequence,
        status="draft",
        scoring_policy_version=base.scoring_policy_version,
        created_by=actor.id,
    )
    db.add(revision)
    db.flush()
    for question in db.scalars(select(QuestionRevision).where(QuestionRevision.assessment_revision_id == base.id).order_by(QuestionRevision.order_index)).all():
        copy = QuestionRevision(
            assessment_revision_id=revision.id,
            stable_question_id=question.stable_question_id,
            label=question.label,
            order_index=question.order_index,
            text=question.text,
            answer_type=question.answer_type,
            weight=question.weight,
            reference_answer=question.reference_answer,
            alternatives=question.alternatives,
        )
        db.add(copy)
        db.flush()
        for criterion in db.scalars(select(RubricCriterion).where(RubricCriterion.question_revision_id == question.id)).all():
            db.add(RubricCriterion(
                question_revision_id=copy.id,
                criterion_id=criterion.criterion_id,
                description=criterion.description,
                max_points=criterion.max_points,
                credit_levels=criterion.credit_levels,
                anchors=criterion.anchors,
            ))
    assessment.active_revision_id = revision.id
    assessment.lifecycle_status = "draft"
    db.add(AuditEvent(
        assessment_id=assessment.id,
        actor_id=actor.id,
        action="assessment_revision.created",
        resource_id=revision.id,
        previous_revision=base.id,
        new_revision=revision.id,
    ))
    db.commit()
    return {"id": revision.id, "sequence": sequence, "version": revision.version, "status": revision.status}


@router.get("/assessment-revisions/{revision_id}")
def get_revision(revision_id: str, db: Session = Depends(get_db), actor=Depends(require_actor)):
    revision = db.get(AssessmentRevision, revision_id)
    if not revision:
        raise HTTPException(status_code=404, detail={"code": "RESOURCE_NOT_FOUND"})
    assessment = require_owner_scope(db, actor, revision.assessment_id)
    return {
        "assessment_id": assessment.id,
        "id": revision.id,
        "sequence": revision.sequence,
        "version": revision.version,
        "status": revision.status,
        "scoring_policy_version": revision.scoring_policy_version,
        "questions": question_json(db, revision.id),
    }


@router.put("/assessment-revisions/{revision_id}/questions")
def save_questions(revision_id: str, body: QuestionSet, db: Session = Depends(get_db), actor=Depends(require_writer)):
    revision = db.scalar(select(AssessmentRevision).where(AssessmentRevision.id == revision_id).with_for_update())
    if not revision:
        raise HTTPException(status_code=404, detail={"code": "RESOURCE_NOT_FOUND"})
    assessment = require_owner_scope(db, actor, revision.assessment_id)
    if revision.status != "draft":
        raise HTTPException(status_code=409, detail={"code": "APPROVED_REVISION_IMMUTABLE"})
    if revision.version != body.expected_version:
        raise HTTPException(status_code=409, detail={"code": "STALE_REVISION", "current_version": revision.version})
    specs = validate_question_payload(body.questions)
    old_ids = select(QuestionRevision.id).where(QuestionRevision.assessment_revision_id == revision.id)
    db.execute(delete(RubricCriterion).where(RubricCriterion.question_revision_id.in_(old_ids)))
    db.execute(delete(QuestionRevision).where(QuestionRevision.assessment_revision_id == revision.id))
    for question in sorted(body.questions, key=lambda item: item.order):
        row = QuestionRevision(
            assessment_revision_id=revision.id,
            stable_question_id=question.stable_question_id,
            label=question.label,
            order_index=question.order,
            text=question.text,
            answer_type=question.answer_type,
            weight=Decimal(question.weight),
            reference_answer=question.reference_answer,
            alternatives=question.alternatives,
        )
        db.add(row)
        db.flush()
        for criterion in question.criteria:
            db.add(RubricCriterion(
                question_revision_id=row.id,
                criterion_id=criterion.id,
                description=criterion.description,
                max_points=Decimal(criterion.max_points),
                credit_levels=[str(Decimal(value).normalize()) for value in criterion.credit_levels],
                anchors=criterion.anchors,
            ))
    normalized = [question.model_dump(mode="json") for question in sorted(body.questions, key=lambda item: item.order)]
    revision.content_hash = canonical_hash(normalized)
    revision.version += 1
    db.add(AuditEvent(
        assessment_id=assessment.id,
        actor_id=actor.id,
        action="assessment_revision.questions_saved",
        resource_id=revision.id,
        new_revision=revision.id,
        metadata_json={"question_count": len(specs), "version": revision.version},
    ))
    db.commit()
    return {"id": revision.id, "version": revision.version, "status": revision.status, "questions": question_json(db, revision.id)}


@router.put("/assessment-revisions/{revision_id}/question-seeds")
def save_question_seeds(revision_id: str, body: "GenerateRubricRequest", db: Session = Depends(get_db), actor=Depends(require_writer)):
    from .rubric_generation import save_seeds
    revision = db.scalar(select(AssessmentRevision).where(AssessmentRevision.id == revision_id).with_for_update())
    if not revision:
        raise HTTPException(404, detail={"code": "RESOURCE_NOT_FOUND"})
    require_owner_scope(db, actor, revision.assessment_id)
    if revision.status != "draft" or revision.version != body.expected_version:
        raise HTTPException(409, detail={"code": "STALE_OR_APPROVED_REVISION"})
    save_seeds(db, revision, body.questions)
    db.add(AuditEvent(assessment_id=revision.assessment_id, actor_id=actor.id,
        action="assessment.questions_saved", resource_id=revision.id,
        metadata_json={"version": revision.version, "question_count": len(body.questions)}))
    db.commit()
    return {"id": revision.id, "version": revision.version, "status": revision.status,
            "questions": question_json(db, revision.id)}


@router.post("/assessment-revisions/{revision_id}/generate-rubric", status_code=202)
def request_generated_rubric(revision_id: str, body: "GenerateRubricRequest", db: Session = Depends(get_db), actor=Depends(require_writer)):
    from .model_adapters import model_status
    from .rubric_generation import save_seeds, generation_fingerprint
    from .services import add_job, publish_job_outbox
    revision = db.scalar(select(AssessmentRevision).where(AssessmentRevision.id == revision_id).with_for_update())
    if not revision:
        raise HTTPException(404, detail={"code": "RESOURCE_NOT_FOUND"})
    require_owner_scope(db, actor, revision.assessment_id)
    if revision.status != "draft" or revision.version != body.expected_version:
        raise HTTPException(409, detail={"code": "STALE_OR_APPROVED_REVISION"})
    if not model_status()["available"]:
        raise HTTPException(503, detail={"code": "MODEL_UNAVAILABLE"})
    save_seeds(db, revision, body.questions)
    job = add_job(db, assessment_id=revision.assessment_id, document_id=None,
        draft_assessment_revision_id=revision.id, kind="rubric_generate",
        input_fingerprint=generation_fingerprint(db, revision))
    db.commit()
    publish_job_outbox(db, job.id)
    db.refresh(job)
    db.refresh(revision)
    return {"job_id": job.id, "status": job.status, "error_code": job.error_code,
            "revision_version": revision.version}


@router.post("/assessment-revisions/{revision_id}/approve")
def approve_revision(revision_id: str, body: RevisionExpectation, db: Session = Depends(get_db), actor=Depends(require_writer)):
    revision = db.scalar(select(AssessmentRevision).where(AssessmentRevision.id == revision_id).with_for_update())
    if not revision:
        raise HTTPException(status_code=404, detail={"code": "RESOURCE_NOT_FOUND"})
    assessment = require_owner_scope(db, actor, revision.assessment_id)
    if not body.confirmation:
        raise HTTPException(status_code=422, detail={"code": "APPROVAL_CONFIRMATION_REQUIRED"})
    if revision.status != "draft":
        raise HTTPException(status_code=409, detail={"code": "REVISION_NOT_DRAFT"})
    if revision.version != body.expected_version:
        raise HTTPException(status_code=409, detail={"code": "STALE_REVISION", "current_version": revision.version})
    rows = db.scalars(select(QuestionRevision).where(QuestionRevision.assessment_revision_id == revision.id).order_by(QuestionRevision.order_index)).all()
    if not rows:
        raise HTTPException(status_code=409, detail={"code": "QUESTIONS_REQUIRED"})
    if any(not row.reference_answer.strip() or not db.scalar(select(RubricCriterion.id).where(
            RubricCriterion.question_revision_id == row.id).limit(1)) for row in rows):
        raise HTTPException(status_code=409, detail={"code": "RUBRIC_INCOMPLETE"})
    specs = validate_question_payload(_as_input_questions(db, revision.id))
    if len(specs) != len(rows) or any(question.max_raw <= 0 for question in specs):
        raise HTTPException(status_code=409, detail={"code": "RUBRIC_INCOMPLETE"})
    revision.status = "approved"
    revision.approved_by = actor.id
    revision.approved_at = now_utc()
    if not revision.content_hash:
        revision.content_hash = canonical_hash(question_json(db, revision.id))
    assessment.active_revision_id = revision.id
    assessment.lifecycle_status = "approved"
    db.add(AuditEvent(
        assessment_id=assessment.id,
        actor_id=actor.id,
        action="assessment_revision.approved",
        resource_id=revision.id,
        new_revision=revision.id,
        metadata_json={"content_hash": revision.content_hash},
    ))
    db.commit()
    return {"id": revision.id, "sequence": revision.sequence, "version": revision.version, "status": revision.status, "approved_at": revision.approved_at.isoformat()}


def _as_input_questions(db: Session, revision_id: str):
    from .schemas import CriterionInput, QuestionInput

    result = []
    for question in db.scalars(select(QuestionRevision).where(QuestionRevision.assessment_revision_id == revision_id).order_by(QuestionRevision.order_index)).all():
        criteria = db.scalars(select(RubricCriterion).where(RubricCriterion.question_revision_id == question.id)).all()
        result.append(QuestionInput(
            stable_question_id=question.stable_question_id,
            label=question.label,
            order=question.order_index,
            text=question.text,
            answer_type=question.answer_type,
            weight=str(question.weight),
            reference_answer=question.reference_answer,
            alternatives=question.alternatives,
            criteria=[CriterionInput(
                id=item.criterion_id,
                description=item.description,
                max_points=str(item.max_points),
                credit_levels=[str(value) for value in item.credit_levels],
                anchors=item.anchors,
            ) for item in criteria],
        ))
    return result
