from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from packages.asdos_domain.scoring import AnswerGrade, DomainError, calculate_grade, validate_criterion_proposal

from .database import get_db
from .dependencies import require_actor, require_owner_scope, require_writer
from .models import (
    Answer, AnswerMappingRevision, AnswerRegionLink, AssessmentRevision, AuditEvent,
    CriterionProposalResult, Document, DocumentLayoutRevision, GradeProposal,
    GradeSnapshot, GradeSnapshotCriterion, GradeSnapshotItem, IdentityConfirmation,
    PipelineJob, QuestionRevision, Region, ReviewCriterionResult, ReviewItem,
    ReviewRevision, Submission, TranscriptionRevision, now_utc,
)
from .schemas import FinalizeRequest, ReviewItemInput
from .services import canonical_hash, load_question_specs

router = APIRouter(prefix="/api/v1", tags=["review"])


def _scope(db: Session, actor, submission_id: str, *, lock: bool = False):
    submission = (db.scalar(select(Submission).where(Submission.id == submission_id).with_for_update())
                  if lock else db.get(Submission, submission_id))
    if not submission:
        raise HTTPException(status_code=404, detail={"code": "RESOURCE_NOT_FOUND"})
    assessment = require_owner_scope(db, actor, submission.assessment_id)
    return submission, assessment


def _current_review(db: Session, submission: Submission) -> ReviewRevision | None:
    return db.get(ReviewRevision, submission.active_review_id) if submission.active_review_id else None


def _new_review(db: Session, submission: Submission, actor, previous: ReviewRevision | None) -> ReviewRevision:
    sequence = (db.scalar(select(func.max(ReviewRevision.sequence)).where(ReviewRevision.submission_id == submission.id)) or 0) + 1
    review = ReviewRevision(
        submission_id=submission.id,
        assessment_revision_id=submission.assessment_revision_id,
        document_id=submission.active_document_id,
        identity_confirmation_id=submission.active_identity_confirmation_id,
        sequence=sequence,
        status="draft",
        version=1,
        based_on_revision_id=previous.id if previous else None,
        created_by=actor.id,
    )
    db.add(review)
    db.flush()
    questions = db.scalars(select(QuestionRevision).where(
        QuestionRevision.assessment_revision_id == submission.assessment_revision_id
    ).order_by(QuestionRevision.order_index)).all()
    old_items = {}
    if previous:
        old_items = {item.stable_question_id: item for item in db.scalars(select(ReviewItem).where(ReviewItem.review_revision_id == previous.id)).all()}
    for question in questions:
        answer = db.scalar(select(Answer).where(Answer.submission_id == submission.id, Answer.stable_question_id == question.stable_question_id))
        prior = old_items.get(question.stable_question_id)
        item = ReviewItem(
            review_revision_id=review.id,
            stable_question_id=question.stable_question_id,
            answer_status=prior.answer_status if prior else (answer.transcript_status if answer and answer.transcript_status in {"verified_blank", "unreadable", "unsupported"} else "needs_review"),
            transcription_revision_id=answer.active_transcription_revision_id if answer else None,
            mapping_revision_id=answer.active_mapping_revision_id if answer else None,
            proposal_id=answer.active_proposal_id if answer else None,
            accepted_criteria=prior.accepted_criteria if prior else None,
            override_raw=prior.override_raw if prior else None,
            override_reason=prior.override_reason if prior else None,
            updated_by=actor.id,
        )
        db.add(item)
        db.flush()
        if prior:
            previous_results = db.scalars(select(ReviewCriterionResult).where(ReviewCriterionResult.review_item_id == prior.id)).all()
            for result in previous_results:
                db.add(ReviewCriterionResult(
                    review_item_id=item.id,
                    criterion_id=result.criterion_id,
                    accepted_credit=result.accepted_credit,
                    points=result.points,
                    evidence_refs=result.evidence_refs,
                    rationale=result.rationale,
                    source=result.source,
                    base_proposal_result_id=result.base_proposal_result_id,
                ))
    submission.active_review_id = review.id
    return review


def _valid_evidence(db: Session, answer: Answer | None, criteria: list[dict]) -> list[str]:
    if not answer:
        return []
    transcript = db.get(TranscriptionRevision, answer.active_transcription_revision_id) if answer.active_transcription_revision_id else None
    mapping_id = answer.active_mapping_revision_id
    if not transcript or transcript.mapping_revision_id != mapping_id:
        if any(Decimal(str(value["credit"])) > 0 for criterion in criteria for value in [criterion]):
            raise HTTPException(status_code=409, detail={"code": "CURRENT_TRANSCRIPTION_REQUIRED"})
        return []
    segments = {segment["segment_id"]: segment.get("text", "") for segment in transcript.segments}
    links = db.scalars(select(AnswerRegionLink).where(
        AnswerRegionLink.answer_id == answer.id,
        AnswerRegionLink.mapping_revision_id == mapping_id,
    )).all()
    region_ids = {link.region_id for link in links}
    try:
        # Reuse the strict evidence validator with domain values already stored in this question.
        for criterion in criteria:
            for ref in criterion["evidence_refs"]:
                segment_id, region_id = ref.get("segment_id"), ref.get("region_id")
                if segment_id not in segments or region_id not in region_ids:
                    raise DomainError("evidence reference is not from current answer")
                start, end = ref.get("start"), ref.get("end")
                if isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start or end > len(segments[segment_id]):
                    raise DomainError("evidence span is out of range")
    except (DomainError, TypeError, KeyError) as exc:
        raise HTTPException(status_code=422, detail={"code": "INVALID_EVIDENCE_REFERENCE", "message": str(exc)}) from exc
    return sorted(region_ids)


@router.get("/submissions/{submission_id}/review")
def get_review(submission_id: str, db: Session = Depends(get_db), actor=Depends(require_actor)):
    submission, _ = _scope(db, actor, submission_id)
    review = _current_review(db, submission)
    if not review:
        return {"review": None, "version": 0, "items": []}
    items = db.scalars(select(ReviewItem).where(ReviewItem.review_revision_id == review.id).order_by(ReviewItem.stable_question_id)).all()
    return {"review": {"id": review.id, "sequence": review.sequence, "version": review.version, "status": review.status,
                        "based_on_revision_id": review.based_on_revision_id},
            "items": [{"question_id": item.stable_question_id, "status": item.answer_status,
                       "criteria": item.accepted_criteria, "override_raw": str(item.override_raw) if item.override_raw is not None else None,
                       "reason": item.override_reason, "transcription_revision_id": item.transcription_revision_id,
                       "mapping_revision_id": item.mapping_revision_id, "proposal_id": item.proposal_id}
                      for item in items]}


@router.put("/submissions/{submission_id}/review/{question_id}")
def save_review_item(submission_id: str, question_id: str, body: ReviewItemInput,
                     db: Session = Depends(get_db), actor=Depends(require_writer)):
    # Serialize edits and finalization through the submission row.
    submission, assessment = _scope(db, actor, submission_id, lock=True)
    if submission.identity_status != "confirmed" or not submission.active_document_id or not submission.active_identity_confirmation_id:
        raise HTTPException(status_code=409, detail={"code": "IDENTITY_AND_DOCUMENT_REQUIRED"})
    revision = db.get(AssessmentRevision, submission.assessment_revision_id)
    if not revision or revision.status != "approved":
        raise HTTPException(status_code=409, detail={"code": "APPROVED_RUBRIC_REQUIRED"})
    specs = {question.question_id: question for question in load_question_specs(db, revision.id)}
    question = specs.get(question_id)
    if not question:
        raise HTTPException(status_code=404, detail={"code": "RESOURCE_NOT_FOUND"})
    answer = db.scalar(select(Answer).where(Answer.submission_id == submission.id,
        Answer.stable_question_id == question_id).with_for_update())
    if not answer:
        raise HTTPException(status_code=409, detail={"code": "ANSWER_RECORD_MISSING"})
    if body.answer_status == "verified_blank":
        blank_transcript = db.get(TranscriptionRevision, answer.active_transcription_revision_id) if answer.active_transcription_revision_id else None
        if not blank_transcript or blank_transcript.status != "verified_blank" or blank_transcript.literal_text.strip():
            raise HTTPException(status_code=409, detail={"code": "VERIFIED_BLANK_TRANSCRIPTION_REQUIRED"})
    active = (db.scalar(select(ReviewRevision).where(ReviewRevision.id == submission.active_review_id).with_for_update())
              if submission.active_review_id else None)
    if active and active.status == "draft":
        if body.expected_review_id != active.id or body.expected_version != active.version:
            raise HTTPException(status_code=409, detail={"code": "STALE_REVIEW", "current_review_id": active.id, "current_version": active.version})
        review = active
    else:
        if body.expected_review_id is not None or body.expected_version != 1:
            raise HTTPException(status_code=409, detail={"code": "STALE_REVIEW", "current_review_id": active.id if active else None, "current_version": active.version if active else 0})
        review = _new_review(db, submission, actor, active)
    item = db.scalar(select(ReviewItem).where(ReviewItem.review_revision_id == review.id,
        ReviewItem.stable_question_id == question_id).with_for_update())
    if not item:
        raise HTTPException(status_code=500, detail={"code": "REVIEW_ITEM_MISSING"})

    accepted = None
    if body.accepted_criteria is not None:
        accepted = [entry.model_dump() for entry in body.accepted_criteria]
        criteria_map = {criterion.criterion_id: criterion for criterion in question.criteria}
        if {entry["criterion_id"] for entry in accepted} != set(criteria_map) or len(accepted) != len(criteria_map):
            raise HTTPException(status_code=422, detail={"code": "CRITERIA_SET_MISMATCH"})
        payload = {"schema_version": "grade-proposal.v1", "question_id": question_id, "status": "proposed", "flags": [],
                   "criteria": [{"criterion_id": entry["criterion_id"], "credit": entry["credit"],
                                 "label": "met" if Decimal(entry["credit"]) == 1 else "not_met" if Decimal(entry["credit"]) == 0 else "partial",
                                 "evidence_refs": entry["evidence_refs"], "rationale": entry["rationale"]} for entry in accepted]}
        segments = {}
        transcript = db.get(TranscriptionRevision, answer.active_transcription_revision_id) if answer.active_transcription_revision_id else None
        if transcript and transcript.mapping_revision_id == answer.active_mapping_revision_id:
            segments = {segment["segment_id"]: segment.get("text", "") for segment in transcript.segments}
        try:
            normalized = validate_criterion_proposal(payload, question_id=question_id, criteria=question.criteria,
                segments=segments, valid_region_ids=_valid_evidence(db, answer, accepted))
        except DomainError as exc:
            raise HTTPException(status_code=422, detail={"code": "INVALID_CRITERION_DECISION", "message": str(exc)}) from exc
        for entry, result in zip(accepted, normalized):
            entry["credit"] = result["credit"]
        accepted.sort(key=lambda entry: entry["criterion_id"])
    if body.override_raw is not None:
        if accepted is not None:
            raise HTTPException(status_code=422, detail={"code": "OVERRIDE_CANNOT_BE_COMBINED_WITH_CRITERIA"})
        if body.answer_status != "reviewed":
            raise HTTPException(status_code=422, detail={"code": "OVERRIDE_STATUS_MUST_BE_REVIEWED"})
        if not body.reason or not body.reason.strip():
            raise HTTPException(status_code=422, detail={"code": "OVERRIDE_REASON_REQUIRED"})
        try:
            value = Decimal(body.override_raw)
        except Exception as exc:
            raise HTTPException(status_code=422, detail={"code": "INVALID_OVERRIDE_SCORE"}) from exc
        if not value.is_finite() or value < 0 or value > question.max_raw:
            raise HTTPException(status_code=422, detail={"code": "INVALID_OVERRIDE_SCORE"})
        if body.answer_status in {"verified_blank", "unreadable", "unsupported", "unmapped", "needs_review"}:
            raise HTTPException(status_code=422, detail={"code": "OVERRIDE_REQUIRES_REVIEWED_STATUS"})
    else:
        value = None
    if body.answer_status == "verified_blank":
        if not body.reason or not body.reason.strip() or accepted is None or any(Decimal(item["credit"]) != 0 for item in accepted):
            raise HTTPException(status_code=422, detail={"code": "VERIFIED_BLANK_REQUIRES_ZERO_CRITERIA_AND_REASON"})
    if body.answer_status in {"unreadable", "unsupported", "unmapped", "needs_review"} and not body.reason:
        raise HTTPException(status_code=422, detail={"code": "REVIEW_REASON_REQUIRED"})
    if body.answer_status in {"correct", "partially_correct", "incorrect", "reviewed"} and accepted is None and value is None:
        raise HTTPException(status_code=422, detail={"code": "REVIEW_DECISION_REQUIRED"})
    if accepted is not None and value is None:
        grade = AnswerGrade(question_id, body.answer_status, {entry["criterion_id"]: Decimal(entry["credit"]) for entry in accepted}, override_reason=body.reason)
        try:
            from packages.asdos_domain.scoring import validate_review
            validate_review(question, grade, final=False)
        except DomainError as exc:
            raise HTTPException(status_code=422, detail={"code": "INVALID_REVIEW_DECISION", "message": str(exc)}) from exc

    old_review_id = active.id if active else None
    item.answer_status = body.answer_status
    item.transcription_revision_id = answer.active_transcription_revision_id
    item.mapping_revision_id = answer.active_mapping_revision_id
    item.proposal_id = answer.active_proposal_id
    item.accepted_criteria = accepted
    item.override_raw = value
    item.override_reason = body.reason
    item.updated_by = actor.id
    item.updated_at = now_utc()
    db.query(ReviewCriterionResult).filter(ReviewCriterionResult.review_item_id == item.id).delete(synchronize_session=False)
    if accepted is not None:
        proposal_results = {}
        if item.proposal_id:
            proposal_results = {row.criterion_id: row for row in db.scalars(select(CriterionProposalResult).where(CriterionProposalResult.proposal_id == item.proposal_id)).all()}
        for entry in accepted:
            criterion = next(c for c in question.criteria if c.criterion_id == entry["criterion_id"])
            credit = Decimal(entry["credit"])
            db.add(ReviewCriterionResult(
                review_item_id=item.id,
                criterion_id=criterion.criterion_id,
                accepted_credit=credit,
                points=credit * criterion.max_points,
                evidence_refs=entry["evidence_refs"],
                rationale=entry["rationale"],
                source=entry["source"],
                base_proposal_result_id=proposal_results[criterion.criterion_id].id if criterion.criterion_id in proposal_results else None,
            ))
    review.version += 1
    review.updated_at = now_utc()
    submission.active_review_id = review.id
    submission.status = "reviewing"
    submission.version += 1
    db.add(AuditEvent(assessment_id=assessment.id, actor_id=actor.id, action="review.item_saved",
        resource_id=item.id, previous_revision=old_review_id, new_revision=review.id, reason=body.reason,
        metadata_json={"question_id": question_id, "answer_status": body.answer_status, "review_version": review.version}))
    db.commit()
    return {"review_id": review.id, "sequence": review.sequence, "version": review.version, "status": review.status,
            "question_id": question_id, "answer_status": item.answer_status}


@router.post("/submissions/{submission_id}/finalize")
def finalize_submission(submission_id: str, body: FinalizeRequest,
                        db: Session = Depends(get_db), actor=Depends(require_writer)):
    submission = db.scalar(select(Submission).where(Submission.id == submission_id).with_for_update())
    if not submission:
        raise HTTPException(status_code=404, detail={"code": "RESOURCE_NOT_FOUND"})
    assessment = require_owner_scope(db, actor, submission.assessment_id)
    existing = db.scalar(select(GradeSnapshot).where(GradeSnapshot.review_revision_id == body.expected_review_id))
    if existing and existing.submission_id == submission.id:
        return {"snapshot_id": existing.id, "score": str(existing.final_score), "status": "finalized", "idempotent": True}
    review = db.scalar(select(ReviewRevision).where(ReviewRevision.id == submission.active_review_id).with_for_update()) if submission.active_review_id else None
    if not review or review.id != body.expected_review_id or review.version != body.expected_version or review.status != "draft":
        raise HTTPException(status_code=409, detail={"code": "STALE_REVIEW", "current_review_id": review.id if review else None,
                                                      "current_version": review.version if review else 0})
    document = db.get(Document, submission.active_document_id) if submission.active_document_id else None
    confirmation = db.get(IdentityConfirmation, submission.active_identity_confirmation_id) if submission.active_identity_confirmation_id else None
    layout = db.get(DocumentLayoutRevision, document.active_layout_revision_id) if document and document.active_layout_revision_id else None
    blockers = []
    if submission.identity_status != "confirmed" or not confirmation or not document or confirmation.document_id != document.id or confirmation.document_hash != document.sha256:
        blockers.append("identity_confirmation")
    if not document or document.validation_status != "valid" or not layout:
        blockers.append("document_layout")
    pending = db.scalars(select(PipelineJob).where(PipelineJob.submission_id == submission.id, PipelineJob.status.in_(["queued", "running"]))).all()
    if pending:
        blockers.extend(f"job:{job.id}:{job.kind}" for job in pending)
    specs = load_question_specs(db, submission.assessment_revision_id)
    items = {item.stable_question_id: item for item in db.scalars(select(ReviewItem)
        .where(ReviewItem.review_revision_id == review.id).order_by(ReviewItem.stable_question_id).with_for_update()).all()}
    answers = {answer.stable_question_id: answer for answer in db.scalars(select(Answer)
        .where(Answer.submission_id == submission.id).order_by(Answer.stable_question_id).with_for_update()).all()}
    grades = {}
    snapshot_details = []
    questions = {question.question_id: question for question in specs}
    for question in specs:
        item = items.get(question.question_id)
        answer = answers.get(question.question_id)
        if not item:
            blockers.append(f"{question.label}:missing_review_item")
            continue
        if item.transcription_revision_id != (answer.active_transcription_revision_id if answer else None) or item.mapping_revision_id != (answer.active_mapping_revision_id if answer else None):
            blockers.append(f"{question.label}:stale_inputs")
            continue
        if item.transcription_revision_id:
            transcript = db.get(TranscriptionRevision, item.transcription_revision_id)
            if not transcript or transcript.mapping_revision_id != item.mapping_revision_id:
                blockers.append(f"{question.label}:stale_transcription")
                continue
        if item.answer_status in {"unreadable", "unsupported", "unmapped", "needs_review"}:
            blockers.append(f"{question.label}:{item.answer_status}")
            continue
        if item.answer_status == "verified_blank":
            blank_transcript = db.get(TranscriptionRevision, item.transcription_revision_id) if item.transcription_revision_id else None
            if not blank_transcript or blank_transcript.status != "verified_blank" or blank_transcript.literal_text.strip():
                blockers.append(f"{question.label}:blank_not_verified")
                continue
        if item.override_raw is not None:
            grade = AnswerGrade(question.question_id, item.answer_status, override_raw=Decimal(item.override_raw), override_reason=item.override_reason)
            criterion_rows = []
        elif item.accepted_criteria:
            try:
                _valid_evidence(db, answer, item.accepted_criteria)
            except HTTPException as exc:
                blockers.append(f"{question.label}:invalid_evidence")
                continue
            grade = AnswerGrade(question.question_id, item.answer_status,
                {entry["criterion_id"]: Decimal(entry["credit"]) for entry in item.accepted_criteria}, override_reason=item.override_reason)
            criterion_rows = item.accepted_criteria
        else:
            blockers.append(f"{question.label}:missing_accepted_criteria")
            continue
        try:
            # Capture field-level errors with the same deterministic validator used by scoring.
            from packages.asdos_domain.scoring import validate_review
            raw = validate_review(question, grade, final=True)
            grades[question.question_id] = grade
            snapshot_details.append((question, item, raw, criterion_rows))
        except DomainError as exc:
            blockers.append(f"{question.label}:{str(exc)}")
    calculation = calculate_grade(specs, grades, final=True)
    blockers.extend(calculation.blockers)
    if blockers:
        raise HTTPException(status_code=409, detail={"code": "FINALIZATION_BLOCKED", "blockers": sorted(set(blockers))})
    if review.assessment_revision_id != submission.assessment_revision_id or review.document_id != document.id or review.identity_confirmation_id != confirmation.id:
        raise HTTPException(status_code=409, detail={"code": "STALE_REVIEW_INPUTS"})
    identity = dict(confirmation.identity_snapshot)
    identity["attempt_no"] = submission.attempt_no
    payload = {"submission_id": submission.id, "review_id": review.id, "assessment_revision_id": review.assessment_revision_id,
        "document_id": document.id, "document_hash": document.sha256, "identity": identity,
        "score": str(calculation.final_score), "total_unrounded": str(calculation.total_unrounded),
        "questions": [{"question_id": q.question_id, "raw": str(raw), "max_raw": str(q.max_raw), "weight": str(q.weight),
            "contribution": str(calculation.contributions[q.question_id]), "status": item.answer_status,
            "transcription_revision_id": item.transcription_revision_id, "mapping_revision_id": item.mapping_revision_id,
            "proposal_id": item.proposal_id, "criteria": criterion_rows, "override_raw": str(item.override_raw) if item.override_raw is not None else None,
            "override_reason": item.override_reason} for q, item, raw, criterion_rows in snapshot_details]}
    snapshot = GradeSnapshot(
        submission_id=submission.id,
        review_revision_id=review.id,
        assessment_revision_id=review.assessment_revision_id,
        document_id=document.id,
        document_hash=document.sha256,
        identity_snapshot=identity,
        total_unrounded=calculation.total_unrounded,
        final_score=calculation.final_score,
        content_hash=canonical_hash(payload),
        approved_by=actor.id,
    )
    db.add(snapshot)
    db.flush()
    for question, item, raw, criteria in snapshot_details:
        snapshot_item = GradeSnapshotItem(
            snapshot_id=snapshot.id, stable_question_id=question.question_id, raw_points=raw,
            max_raw=question.max_raw, weight=question.weight,
            contribution=calculation.contributions[question.question_id], answer_status=item.answer_status,
            decision_payload={"criteria": criteria, "override_raw": str(item.override_raw) if item.override_raw is not None else None,
                              "override_reason": item.override_reason, "transcription_revision_id": item.transcription_revision_id,
                              "mapping_revision_id": item.mapping_revision_id, "proposal_id": item.proposal_id},
        )
        db.add(snapshot_item)
        db.flush()
        if criteria:
            for entry in criteria:
                criterion = next(c for c in question.criteria if c.criterion_id == entry["criterion_id"])
                credit = Decimal(entry["credit"])
                db.add(GradeSnapshotCriterion(snapshot_item_id=snapshot_item.id, criterion_id=criterion.criterion_id,
                    accepted_credit=credit, max_points=criterion.max_points, points=credit * criterion.max_points,
                    evidence_refs=entry["evidence_refs"], rationale=entry["rationale"], source=entry["source"]))
    review.status = "finalized"
    review.version += 1
    review.updated_at = now_utc()
    submission.status = "finalized"
    submission.version += 1
    db.add(AuditEvent(assessment_id=assessment.id, actor_id=actor.id, action="submission.finalized",
        resource_id=submission.id, previous_revision=review.id, new_revision=snapshot.id,
        metadata_json={"score": str(calculation.final_score), "snapshot_hash": snapshot.content_hash}))
    db.commit()
    return {"snapshot_id": snapshot.id, "score": str(snapshot.final_score), "status": "finalized", "idempotent": False}
