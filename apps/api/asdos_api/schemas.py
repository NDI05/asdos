from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LoginRequest(StrictModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=256)


class AssessmentCreate(StrictModel):
    title: str = Field(min_length=1, max_length=240)
    course_label: str = Field(default="", max_length=240)
    language: str = Field(default="id", pattern="^(id|en)$")


class CriterionInput(StrictModel):
    id: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=1000)
    max_points: str = Field(min_length=1, max_length=32)
    credit_levels: list[str] = Field(min_length=1, max_length=11)
    anchors: dict[str, str]


class QuestionInput(StrictModel):
    stable_question_id: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=32)
    order: int = Field(ge=1, le=500)
    text: str = Field(min_length=1, max_length=12000)
    answer_type: str = Field(default="essay", pattern="^(essay|short_text|list|simple_table)$")
    weight: str = Field(min_length=1, max_length=32)
    reference_answer: str = Field(min_length=1, max_length=12000)
    alternatives: list[str] = Field(default_factory=list, max_length=100)
    criteria: list[CriterionInput] = Field(min_length=1, max_length=100)


class QuestionSet(StrictModel):
    expected_version: int = Field(ge=1)
    questions: list[QuestionInput] = Field(min_length=1, max_length=100)


class RevisionExpectation(StrictModel):
    expected_version: int = Field(ge=1)
    confirmation: bool = True


class RevisionCreate(StrictModel):
    base_revision_id: str = Field(min_length=36, max_length=36)


class SubmissionCreate(StrictModel):
    external_student_id: str = Field(min_length=1, max_length=80)
    display_name: str = Field(min_length=1, max_length=200)
    attempt_no: int = Field(default=1, ge=1, le=10)


class IdentityConfirmationInput(StrictModel):
    document_id: str = Field(min_length=36, max_length=36)
    document_hash: str = Field(pattern="^[a-f0-9]{64}$")
    external_student_id: str = Field(min_length=1, max_length=80)
    display_name: str = Field(min_length=1, max_length=200)
    expected_submission_version: int = Field(ge=1)


class RegionInput(StrictModel):
    polygon: list[tuple[float, float]] = Field(min_length=3, max_length=50)
    region_type: str = Field(default="answer", pattern="^(answer|identity|header|unassigned)$")


class PageRotationInput(StrictModel):
    degrees_clockwise: Literal[90, 180, 270]
    expected_layout_revision_id: str = Field(min_length=36, max_length=36)


class MappingInput(StrictModel):
    region_ids: list[str] = Field(min_length=1, max_length=100)
    expected_transcript_revision: int = Field(ge=0)
    expected_mapping_revision_id: str | None = Field(default=None, min_length=36, max_length=36)


class TranscriptionInput(StrictModel):
    literal_text: str = Field(default="", max_length=100000)
    status: str = Field(pattern="^(transcribed|verified_blank|unreadable|unsupported)$")
    flags: list[str] = Field(default_factory=list, max_length=50)
    expected_revision: int = Field(ge=0)
    reason: str | None = Field(default=None, max_length=1000)


class AcceptedCriterion(StrictModel):
    criterion_id: str = Field(min_length=1, max_length=80)
    credit: str = Field(min_length=1, max_length=32)
    evidence_refs: list[dict] = Field(default_factory=list, max_length=100)
    rationale: str = Field(default="", max_length=1000)
    source: str = Field(default="human", pattern="^(human|model_accepted)$")


class ReviewItemInput(StrictModel):
    expected_review_id: str | None = None
    expected_version: int = Field(ge=1)
    answer_status: str = Field(pattern="^(correct|partially_correct|incorrect|verified_blank|reviewed|unreadable|unsupported|unmapped|needs_review)$")
    accepted_criteria: list[AcceptedCriterion] | None = Field(default=None, max_length=100)
    override_raw: str | None = Field(default=None, max_length=32)
    reason: str | None = Field(default=None, max_length=1000)


class FinalizeRequest(StrictModel):
    expected_review_id: str = Field(min_length=36, max_length=36)
    expected_version: int = Field(ge=1)


class ExportRequest(StrictModel):
    mode: str = Field(pattern="^(draft|final)$")
    submission_ids: list[str] = Field(min_length=1, max_length=10000)


class RetryRequest(StrictModel):
    reason: str = Field(min_length=1, max_length=500)
    expected_attempt: int = Field(ge=1)
