"""Validated, teacher-reviewable rubrics generated without student answers."""
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import delete, select

from packages.asdos_domain.scoring import decimal_value
from .models import QuestionRevision, RubricCriterion
from .schemas import GeneratedRubric, QuestionInput
from .services import canonical_hash, question_json, validate_question_payload


def validate_seeds(questions):
    seen_ids, seen_labels, seen_order = set(), set(), set()
    for q in questions:
        if q.stable_question_id in seen_ids or q.label in seen_labels or q.order in seen_order:
            raise HTTPException(422, detail={"code": "DUPLICATE_QUESTION_ID_LABEL_OR_ORDER"})
        seen_ids.add(q.stable_question_id)
        seen_labels.add(q.label)
        seen_order.add(q.order)
        try:
            weight = decimal_value(q.weight)
            if weight <= 0 or weight >= Decimal("100000000") or weight.as_tuple().exponent < -4:
                raise ValueError("weight must fit NUMERIC(12,4)")
        except ValueError as exc:
            raise HTTPException(422, detail={"code": "INVALID_QUESTION_WEIGHT"}) from exc


def replace_questions(db, revision_id, questions):
    old_ids = select(QuestionRevision.id).where(QuestionRevision.assessment_revision_id == revision_id)
    db.execute(delete(RubricCriterion).where(RubricCriterion.question_revision_id.in_(old_ids)))
    db.execute(delete(QuestionRevision).where(QuestionRevision.assessment_revision_id == revision_id))
    for q in questions:
        row = QuestionRevision(assessment_revision_id=revision_id,
            **{k: q[k] for k in ("stable_question_id", "label", "text", "answer_type", "reference_answer", "alternatives")},
            order_index=q["order"], weight=Decimal(q["weight"]))
        db.add(row)
        db.flush()
        for c in q["criteria"]:
            db.add(RubricCriterion(question_revision_id=row.id, criterion_id=c["id"],
                description=c["description"], max_points=Decimal(c["max_points"]),
                credit_levels=c["credit_levels"], anchors=c["anchors"]))

    db.flush()

def save_seeds(db, revision, seeds):
    validate_seeds(seeds)
    old = {q["stable_question_id"]: q for q in question_json(db, revision.id)}
    questions = []
    for seed in sorted(seeds, key=lambda q: q.order):
        q = seed.model_dump()
        prior = old.get(seed.stable_question_id)
        retain = prior and prior["text"] == seed.text and prior["answer_type"] == seed.answer_type
        q.update({k: prior[k] if retain else default for k, default in
                  (("reference_answer", ""), ("alternatives", []), ("criteria", []))})
        questions.append(q)
    replace_questions(db, revision.id, questions)
    revision.version += 1
    revision.content_hash = canonical_hash(questions)


def generation_fingerprint(db, revision):
    return canonical_hash({"revision_id": revision.id, "version": revision.version,
                           "questions": question_json(db, revision.id)})


def merge_generated(seeds, output):
    """Model cannot change IDs, questions, order, weights or approve a rubric."""
    if not isinstance(output, list) or len(output) != len(seeds):
        raise ValueError("generated rubric count differs from questions")
    merged = []
    for seed, raw in zip(seeds, output, strict=True):
        rubric = GeneratedRubric.model_validate(raw)
        seed = {k: seed[k] for k in ("stable_question_id", "label", "order", "text", "answer_type", "weight")}
        q = QuestionInput.model_validate({**seed, **rubric.model_dump()})
        merged.append(q)
    validate_question_payload(merged)
    return [q.model_dump() for q in merged]
