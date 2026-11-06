"""Auditable Decimal scoring and strict model-output validation."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from typing import Any, Iterable, Mapping, Sequence


class DomainError(ValueError):
    """Input violates an ASDOS domain invariant."""


def decimal_key(value: Decimal) -> str:
    normalized = value.normalize()
    return format(normalized, "f") if normalized else "0"


def decimal_value(value: Any, field: str = "value") -> Decimal:
    if isinstance(value, bool) or value is None:
        raise DomainError(f"{field} must be a finite decimal")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise DomainError(f"{field} must be a finite decimal") from exc
    if not result.is_finite():
        raise DomainError(f"{field} must be finite")
    return result


@dataclass(frozen=True)
class CriterionSpec:
    criterion_id: str
    description: str
    max_points: Decimal
    credit_levels: tuple[Decimal, ...]
    anchors: Mapping[str, str]

    def __post_init__(self) -> None:
        maximum = decimal_value(self.max_points, "max_points")
        levels = tuple(decimal_value(v, "credit_level") for v in self.credit_levels)
        if not self.criterion_id or not self.description.strip():
            raise DomainError("criterion ID and description are required")
        if maximum <= 0:
            raise DomainError("criterion max_points must be positive")
        if not levels or len(set(levels)) != len(levels):
            raise DomainError("credit levels must be nonempty and unique")
        if any(v < 0 or v > 1 for v in levels):
            raise DomainError("credit levels must be between 0 and 1")
        if set(self.anchors) != {decimal_key(v) for v in levels}:
            raise DomainError("every allowed credit level needs exactly one anchor")
        if any(not str(text).strip() for text in self.anchors.values()):
            raise DomainError("credit anchors cannot be empty")
        object.__setattr__(self, "max_points", maximum)
        object.__setattr__(self, "credit_levels", levels)


@dataclass(frozen=True)
class QuestionSpec:
    question_id: str
    label: str
    order: int
    weight: Decimal
    criteria: tuple[CriterionSpec, ...]

    def __post_init__(self) -> None:
        weight = decimal_value(self.weight, "weight")
        if not self.question_id or not self.label or self.order < 1:
            raise DomainError("question ID, label, and positive order are required")
        if weight <= 0:
            raise DomainError("question weight must be positive")
        if not self.criteria:
            raise DomainError("each question needs at least one criterion")
        ids = [c.criterion_id for c in self.criteria]
        if len(set(ids)) != len(ids):
            raise DomainError("criterion IDs must be unique within a question")
        object.__setattr__(self, "weight", weight)

    @property
    def max_raw(self) -> Decimal:
        return sum((c.max_points for c in self.criteria), Decimal("0"))


@dataclass(frozen=True)
class AnswerGrade:
    question_id: str
    status: str
    criteria: Mapping[str, Decimal] | None = None
    override_raw: Decimal | None = None
    override_reason: str | None = None


@dataclass(frozen=True)
class GradeResult:
    total_unrounded: Decimal | None
    final_score: Decimal | None
    total_weight: Decimal
    contributions: Mapping[str, Decimal | None]
    raw_points: Mapping[str, Decimal | None]
    blockers: tuple[str, ...]


REVIEWABLE_STATUSES = {"correct", "partially_correct", "incorrect", "verified_blank", "reviewed"}
NULL_STATUSES = {"unreadable", "unsupported", "unmapped", "model_failed", "needs_review"}


def validate_review(question: QuestionSpec, answer: AnswerGrade, *, final: bool = False) -> Decimal | None:
    if answer.question_id != question.question_id:
        raise DomainError("answer question ID does not match question")
    if answer.status in NULL_STATUSES:
        if final:
            raise DomainError(f"{question.label} is unresolved ({answer.status})")
        return None
    if answer.status not in REVIEWABLE_STATUSES:
        raise DomainError(f"unsupported answer status: {answer.status}")
    if answer.override_raw is not None:
        raw = decimal_value(answer.override_raw, "override_raw")
        if raw < 0 or raw > question.max_raw:
            raise DomainError("override_raw must be within the question's raw score range")
        if not answer.override_reason or not answer.override_reason.strip():
            raise DomainError("a raw score override requires a reason")
        if answer.status == "correct" and raw != question.max_raw:
            raise DomainError("correct status requires a full raw score")
        if answer.status == "incorrect" and raw != 0:
            raise DomainError("incorrect status requires a zero raw score")
        if answer.status == "partially_correct" and not (0 < raw < question.max_raw):
            raise DomainError("partially_correct status requires a partial raw score")
        return raw
    if answer.status == "verified_blank":
        if not answer.override_reason or not answer.override_reason.strip():
            raise DomainError("verified_blank requires a human verification reason")
        if answer.criteria is None:
            if final:
                raise DomainError("verified_blank final review needs an explicit zero decision for every criterion")
            return Decimal("0")
    if answer.criteria is None:
        if final:
            raise DomainError(f"{question.label} has no accepted criterion decisions")
        return None
    expected = {c.criterion_id for c in question.criteria}
    actual = set(answer.criteria)
    if expected != actual:
        raise DomainError(f"{question.label} criteria mismatch; missing={sorted(expected-actual)}, unknown={sorted(actual-expected)}")
    raw = Decimal("0")
    for criterion in question.criteria:
        credit = decimal_value(answer.criteria[criterion.criterion_id], f"{criterion.criterion_id}.credit")
        if credit not in criterion.credit_levels:
            raise DomainError(f"credit {credit} is not allowed for criterion {criterion.criterion_id}")
        raw += credit * criterion.max_points
    if raw > question.max_raw:
        raise DomainError("accepted raw score exceeds question maximum")
    if answer.status == "verified_blank" and raw != 0:
        raise DomainError("verified_blank must award zero on all criteria")
    if answer.status == "correct" and raw != question.max_raw:
        raise DomainError("correct status requires full raw credit")
    if answer.status == "incorrect" and raw != 0:
        raise DomainError("incorrect status requires zero raw credit")
    if answer.status == "partially_correct" and not (0 < raw < question.max_raw):
        raise DomainError("partially_correct status requires partial raw credit")
    return raw


def calculate_grade(
    questions: Sequence[QuestionSpec],
    answers: Mapping[str, AnswerGrade],
    *,
    final: bool = False,
) -> GradeResult:
    if not questions:
        raise DomainError("an assessment must contain at least one required question")
    question_ids = [q.question_id for q in questions]
    if len(question_ids) != len(set(question_ids)):
        raise DomainError("question IDs must be unique")
    expected = set(question_ids)
    if set(answers) - expected:
        raise DomainError("answer contains an unknown question ID")
    total_weight = sum((q.weight for q in questions), Decimal("0"))
    if total_weight <= 0:
        raise DomainError("total question weight must be positive")
    contributions: dict[str, Decimal | None] = {}
    raw_points: dict[str, Decimal | None] = {}
    blockers: list[str] = []
    with localcontext() as ctx:
        ctx.prec = 28
        weighted_total = Decimal("0")
        for question in questions:
            answer = answers.get(question.question_id)
            if answer is None:
                raw = None
                blockers.append(f"{question.label}:missing_answer")
            else:
                try:
                    raw = validate_review(question, answer, final=final)
                except DomainError as exc:
                    if final:
                        blockers.append(f"{question.label}:{exc}")
                        raw = None
                    else:
                        raise
                if raw is None and f"{question.label}:missing_answer" not in blockers:
                    blockers.append(f"{question.label}:{answer.status}")
            raw_points[question.question_id] = raw
            if raw is None:
                contributions[question.question_id] = None
            else:
                contribution = (raw / question.max_raw) * question.weight
                contributions[question.question_id] = contribution
                weighted_total += contribution
        if blockers:
            return GradeResult(None, None, total_weight, contributions, raw_points, tuple(blockers))
        unrounded_score = Decimal("100") * weighted_total / total_weight
        score = unrounded_score.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return GradeResult(unrounded_score, score, total_weight, contributions, raw_points, ())


def validate_criterion_proposal(
    payload: Mapping[str, Any],
    *,
    question_id: str,
    criteria: Sequence[CriterionSpec],
    segments: Mapping[str, str],
    valid_region_ids: Iterable[str],
) -> list[dict[str, Any]]:
    """Validate a grader response; model output never supplies a total score."""
    if set(payload) != {"schema_version", "question_id", "status", "criteria", "flags"}:
        raise DomainError("proposal schema has missing or unknown fields")
    if payload["schema_version"] != "grade-proposal.v1" or payload["question_id"] != question_id:
        raise DomainError("proposal schema or question reference mismatch")
    if payload["status"] != "proposed" or not isinstance(payload["criteria"], list):
        raise DomainError("proposal must contain criterion decisions")
    if not isinstance(payload["flags"], list) or any(not isinstance(x, str) for x in payload["flags"]):
        raise DomainError("proposal flags must be a list of strings")
    expected = {criterion.criterion_id: criterion for criterion in criteria}
    seen: set[str] = set()
    valid_regions = set(valid_region_ids)
    cleaned: list[dict[str, Any]] = []
    for item in payload["criteria"]:
        required = {"criterion_id", "credit", "label", "evidence_refs", "rationale"}
        if not isinstance(item, Mapping) or set(item) != required:
            raise DomainError("criterion proposal has missing or unknown fields")
        criterion_id = item["criterion_id"]
        if criterion_id not in expected or criterion_id in seen:
            raise DomainError("unknown or duplicate criterion ID")
        seen.add(criterion_id)
        criterion = expected[criterion_id]
        credit = decimal_value(item["credit"], "credit")
        if credit not in criterion.credit_levels:
            raise DomainError(f"invalid credit for {criterion_id}")
        label = "met" if credit == 1 else "not_met" if credit == 0 else "partial"
        if item["label"] != label:
            raise DomainError(f"label contradicts credit for {criterion_id}")
        rationale = item["rationale"]
        if not isinstance(rationale, str) or len(rationale) > 1000:
            raise DomainError("rationale must be a short string")
        refs = item["evidence_refs"]
        if not isinstance(refs, list):
            raise DomainError("evidence_refs must be a list")
        validated_refs: list[dict[str, Any]] = []
        for ref in refs:
            if not isinstance(ref, Mapping) or set(ref) != {"segment_id", "start", "end", "region_id"}:
                raise DomainError("invalid evidence reference shape")
            segment_id, region_id = ref["segment_id"], ref["region_id"]
            start, end = ref["start"], ref["end"]
            if segment_id not in segments or region_id not in valid_regions:
                raise DomainError("evidence reference is not from the active answer")
            if isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, int) or not isinstance(end, int):
                raise DomainError("evidence offsets must be integers")
            if start < 0 or end <= start or end > len(segments[segment_id]):
                raise DomainError("evidence span is out of range")
            validated_refs.append(dict(ref))
        if credit > 0 and not validated_refs:
            raise DomainError("positive credit requires visible evidence references")
        cleaned.append({**dict(item), "credit": str(credit), "evidence_refs": validated_refs})
    if seen != set(expected):
        raise DomainError("proposal must include every criterion exactly once")
    return cleaned
