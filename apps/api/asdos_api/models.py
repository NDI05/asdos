from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def new_id() -> str:
    return str(uuid4())


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(512))
    role: Mapped[str] = mapped_column(String(24), default="owner")
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class LoginSession(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Assessment(Base):
    __tablename__ = "assessments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(240))
    course_label: Mapped[str] = mapped_column(String(240), default="")
    language: Mapped[str] = mapped_column(String(8), default="id")
    lifecycle_status: Mapped[str] = mapped_column(String(24), default="draft")
    active_revision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class AssessmentRevision(Base):
    __tablename__ = "assessment_revisions"
    __table_args__ = (UniqueConstraint("assessment_id", "sequence", name="uq_assessment_revision_sequence"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(24), default="draft")
    scoring_policy_version: Mapped[str] = mapped_column(String(32), default="asdos-weighted.v1")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_document_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class QuestionRevision(Base):
    __tablename__ = "question_revisions"
    __table_args__ = (
        UniqueConstraint("assessment_revision_id", "stable_question_id", name="uq_question_revision_stable_id"),
        UniqueConstraint("assessment_revision_id", "label", name="uq_question_revision_label"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    assessment_revision_id: Mapped[str] = mapped_column(ForeignKey("assessment_revisions.id", ondelete="CASCADE"), index=True)
    stable_question_id: Mapped[str] = mapped_column(String(80))
    label: Mapped[str] = mapped_column(String(32))
    order_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    answer_type: Mapped[str] = mapped_column(String(24), default="essay")
    weight: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    reference_answer: Mapped[str] = mapped_column(Text)
    alternatives: Mapped[list] = mapped_column(JSON, default=list)


class RubricCriterion(Base):
    __tablename__ = "rubric_criteria"
    __table_args__ = (UniqueConstraint("question_revision_id", "criterion_id", name="uq_rubric_criterion_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    question_revision_id: Mapped[str] = mapped_column(ForeignKey("question_revisions.id", ondelete="CASCADE"), index=True)
    criterion_id: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text)
    max_points: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    credit_levels: Mapped[list] = mapped_column(JSON)
    anchors: Mapped[dict] = mapped_column(JSON)


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (UniqueConstraint("assessment_id", "external_student_id", "attempt_no", name="uq_submission_student_attempt"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"), index=True)
    assessment_revision_id: Mapped[str] = mapped_column(ForeignKey("assessment_revisions.id"))
    external_student_id: Mapped[str] = mapped_column(String(80))
    display_name: Mapped[str] = mapped_column(String(200))
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)
    identity_status: Mapped[str] = mapped_column(String(24), default="pending")
    active_document_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    active_identity_confirmation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    active_review_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="created")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"), index=True)
    submission_id: Mapped[str | None] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"), index=True, nullable=True)
    draft_assessment_revision_id: Mapped[str | None] = mapped_column(ForeignKey("assessment_revisions.id"), nullable=True)
    active_layout_revision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    kind: Mapped[str] = mapped_column(String(24))
    storage_key: Mapped[str] = mapped_column(String(180), unique=True)
    original_filename: Mapped[str] = mapped_column(String(255), default="")
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    byte_size: Mapped[int] = mapped_column(Integer)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    validation_status: Mapped[str] = mapped_column(String(24), default="pending")
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    auto_process: Mapped[bool] = mapped_column(Boolean, default=False)
    analysis_result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class IdentityConfirmation(Base):
    __tablename__ = "identity_confirmations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"))
    document_hash: Mapped[str] = mapped_column(String(64))
    identity_snapshot: Mapped[dict] = mapped_column(JSON)
    confirmed_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Page(Base):
    __tablename__ = "pages"
    __table_args__ = (UniqueConstraint("document_id", "page_index", name="uq_document_page_index"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    page_index: Mapped[int] = mapped_column(Integer)
    original_rotation: Mapped[int] = mapped_column(Integer, default=0)
    pdf_width_points: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    pdf_height_points: Mapped[Decimal] = mapped_column(Numeric(12, 3))


class PageImageRevision(Base):
    __tablename__ = "page_image_revisions"
    __table_args__ = (UniqueConstraint("page_id", "sequence", name="uq_page_image_revision_sequence"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    page_id: Mapped[str] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    parent_revision_id: Mapped[str | None] = mapped_column(ForeignKey("page_image_revisions.id"), nullable=True)
    image_storage_key: Mapped[str] = mapped_column(String(180), unique=True)
    width_px: Mapped[int] = mapped_column(Integer)
    height_px: Mapped[int] = mapped_column(Integer)
    rotation: Mapped[int] = mapped_column(Integer, default=0)
    transform: Mapped[dict] = mapped_column(JSON)
    inverse_transform: Mapped[dict] = mapped_column(JSON)
    image_sha256: Mapped[str] = mapped_column(String(64))
    preprocessing_version: Mapped[str] = mapped_column(String(80), default="render.v1")


class DocumentLayoutRevision(Base):
    __tablename__ = "document_layout_revisions"
    __table_args__ = (UniqueConstraint("document_id", "sequence", name="uq_layout_revision_sequence"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    parent_revision_id: Mapped[str | None] = mapped_column(ForeignKey("document_layout_revisions.id"), nullable=True)
    ordered_page_image_revision_ids: Mapped[list] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Region(Base):
    __tablename__ = "regions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    page_image_revision_id: Mapped[str] = mapped_column(ForeignKey("page_image_revisions.id", ondelete="CASCADE"), index=True)
    parent_region_id: Mapped[str | None] = mapped_column(ForeignKey("regions.id"), nullable=True)
    polygon: Mapped[list] = mapped_column(JSON)
    region_type: Mapped[str] = mapped_column(String(24), default="answer")
    analysis: Mapped[dict] = mapped_column(JSON, default=dict)
    excluded_from_mapping: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Answer(Base):
    __tablename__ = "answers"
    __table_args__ = (UniqueConstraint("submission_id", "stable_question_id", name="uq_submission_answer_question"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"), index=True)
    stable_question_id: Mapped[str] = mapped_column(String(80))
    mapping_status: Mapped[str] = mapped_column(String(24), default="unmapped")
    active_mapping_revision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    transcript_status: Mapped[str] = mapped_column(String(24), default="pending")
    literal_text: Mapped[str] = mapped_column(Text, default="")
    transcript_revision: Mapped[int] = mapped_column(Integer, default=0)
    active_transcription_revision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    active_proposal_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class ModelRun(Base):
    __tablename__ = "model_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_type: Mapped[str] = mapped_column(String(24))
    checkpoint: Mapped[str] = mapped_column(String(180))
    checkpoint_revision: Mapped[str] = mapped_column(String(80))
    checkpoint_sha256: Mapped[str] = mapped_column(String(64), default="")
    runtime: Mapped[str] = mapped_column(String(120))
    prompt_version: Mapped[str] = mapped_column(String(40))
    schema_version: Mapped[str] = mapped_column(String(40))
    preprocessing_version: Mapped[str] = mapped_column(String(80), default="none")
    input_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    device: Mapped[str] = mapped_column(String(80), default="unknown")
    status: Mapped[str] = mapped_column(String(24))
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class TranscriptionRevision(Base):
    __tablename__ = "transcription_revisions"
    __table_args__ = (UniqueConstraint("answer_id", "revision_no", name="uq_transcription_revision"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    answer_id: Mapped[str] = mapped_column(ForeignKey("answers.id", ondelete="CASCADE"), index=True)
    mapping_revision_id: Mapped[str | None] = mapped_column(ForeignKey("answer_mapping_revisions.id"), nullable=True)
    revision_no: Mapped[int] = mapped_column(Integer)
    parent_revision_id: Mapped[str | None] = mapped_column(ForeignKey("transcription_revisions.id"), nullable=True)
    literal_text: Mapped[str] = mapped_column(Text, default="")
    segments: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(24))
    flags: Mapped[list] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(16))
    model_run_id: Mapped[str | None] = mapped_column(ForeignKey("model_runs.id"), nullable=True)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class GradeProposal(Base):
    __tablename__ = "grade_proposals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    answer_id: Mapped[str] = mapped_column(ForeignKey("answers.id", ondelete="CASCADE"), index=True)
    transcription_revision_id: Mapped[str] = mapped_column(ForeignKey("transcription_revisions.id"))
    assessment_revision_id: Mapped[str] = mapped_column(ForeignKey("assessment_revisions.id"))
    model_run_id: Mapped[str] = mapped_column(ForeignKey("model_runs.id"))
    status: Mapped[str] = mapped_column(String(24))
    proposal_payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class CriterionProposalResult(Base):
    __tablename__ = "criterion_results"
    __table_args__ = (UniqueConstraint("proposal_id", "criterion_id", name="uq_proposal_criterion"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    proposal_id: Mapped[str] = mapped_column(ForeignKey("grade_proposals.id", ondelete="CASCADE"), index=True)
    criterion_id: Mapped[str] = mapped_column(String(80))
    credit: Mapped[Decimal] = mapped_column(Numeric(8, 6))
    points: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    evidence_refs: Mapped[list] = mapped_column(JSON, default=list)
    rationale: Mapped[str] = mapped_column(Text, default="")


class AnswerRegionLink(Base):
    __tablename__ = "answer_region_links"
    __table_args__ = (UniqueConstraint("mapping_revision_id", "region_id", name="uq_answer_region"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    answer_id: Mapped[str] = mapped_column(ForeignKey("answers.id", ondelete="CASCADE"), index=True)
    mapping_revision_id: Mapped[str] = mapped_column(ForeignKey("answer_mapping_revisions.id", ondelete="CASCADE"), index=True)
    region_id: Mapped[str] = mapped_column(ForeignKey("regions.id"))
    order_index: Mapped[int] = mapped_column(Integer)


class AnswerMappingRevision(Base):
    __tablename__ = "answer_mapping_revisions"
    __table_args__ = (UniqueConstraint("answer_id", "sequence", name="uq_answer_mapping_revision"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    answer_id: Mapped[str] = mapped_column(ForeignKey("answers.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    parent_revision_id: Mapped[str | None] = mapped_column(ForeignKey("answer_mapping_revisions.id"), nullable=True)
    layout_revision_id: Mapped[str] = mapped_column(ForeignKey("document_layout_revisions.id"))
    ordered_region_ids: Mapped[list] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ReviewRevision(Base):
    __tablename__ = "review_revisions"
    __table_args__ = (UniqueConstraint("submission_id", "sequence", name="uq_review_revision_sequence"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"), index=True)
    assessment_revision_id: Mapped[str] = mapped_column(ForeignKey("assessment_revisions.id"))
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"))
    identity_confirmation_id: Mapped[str] = mapped_column(ForeignKey("identity_confirmations.id"))
    sequence: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="draft")
    version: Mapped[int] = mapped_column(Integer, default=1)
    based_on_revision_id: Mapped[str | None] = mapped_column(ForeignKey("review_revisions.id"), nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class ReviewItem(Base):
    __tablename__ = "review_items"
    __table_args__ = (UniqueConstraint("review_revision_id", "stable_question_id", name="uq_review_item_question"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    review_revision_id: Mapped[str] = mapped_column(ForeignKey("review_revisions.id", ondelete="CASCADE"), index=True)
    stable_question_id: Mapped[str] = mapped_column(String(80))
    answer_status: Mapped[str] = mapped_column(String(24))
    transcription_revision_id: Mapped[str | None] = mapped_column(ForeignKey("transcription_revisions.id"), nullable=True)
    mapping_revision_id: Mapped[str | None] = mapped_column(ForeignKey("answer_mapping_revisions.id"), nullable=True)
    proposal_id: Mapped[str | None] = mapped_column(ForeignKey("grade_proposals.id"), nullable=True)
    accepted_criteria: Mapped[list | None] = mapped_column(JSON, nullable=True)
    override_raw: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class ReviewCriterionResult(Base):
    __tablename__ = "review_criterion_results"
    __table_args__ = (UniqueConstraint("review_item_id", "criterion_id", name="uq_review_criterion"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    review_item_id: Mapped[str] = mapped_column(ForeignKey("review_items.id", ondelete="CASCADE"), index=True)
    criterion_id: Mapped[str] = mapped_column(String(80))
    accepted_credit: Mapped[Decimal] = mapped_column(Numeric(8, 6))
    points: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    evidence_refs: Mapped[list] = mapped_column(JSON, default=list)
    rationale: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(24))
    base_proposal_result_id: Mapped[str | None] = mapped_column(ForeignKey("criterion_results.id"), nullable=True)


class GradeSnapshot(Base):
    __tablename__ = "grade_snapshots"
    __table_args__ = (UniqueConstraint("review_revision_id", name="uq_grade_snapshot_review_revision"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"), index=True)
    review_revision_id: Mapped[str] = mapped_column(ForeignKey("review_revisions.id"))
    assessment_revision_id: Mapped[str] = mapped_column(ForeignKey("assessment_revisions.id"))
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"))
    document_hash: Mapped[str] = mapped_column(String(64))
    identity_snapshot: Mapped[dict] = mapped_column(JSON)
    total_unrounded: Mapped[Decimal] = mapped_column(Numeric(32, 18))
    final_score: Mapped[Decimal] = mapped_column(Numeric(7, 2))
    content_hash: Mapped[str] = mapped_column(String(64))
    approved_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class GradeSnapshotItem(Base):
    __tablename__ = "grade_snapshot_items"
    __table_args__ = (UniqueConstraint("snapshot_id", "stable_question_id", name="uq_grade_snapshot_item"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("grade_snapshots.id", ondelete="CASCADE"), index=True)
    stable_question_id: Mapped[str] = mapped_column(String(80))
    raw_points: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    max_raw: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    weight: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    contribution: Mapped[Decimal] = mapped_column(Numeric(32, 18))
    answer_status: Mapped[str] = mapped_column(String(24))
    decision_payload: Mapped[dict] = mapped_column(JSON)


class GradeSnapshotCriterion(Base):
    __tablename__ = "grade_snapshot_criteria"
    __table_args__ = (UniqueConstraint("snapshot_item_id", "criterion_id", name="uq_snapshot_criterion"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    snapshot_item_id: Mapped[str] = mapped_column(ForeignKey("grade_snapshot_items.id", ondelete="CASCADE"), index=True)
    criterion_id: Mapped[str] = mapped_column(String(80))
    accepted_credit: Mapped[Decimal] = mapped_column(Numeric(8, 6))
    max_points: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    points: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    evidence_refs: Mapped[list] = mapped_column(JSON, default=list)
    rationale: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(24))


class PipelineJob(Base):
    __tablename__ = "pipeline_jobs"
    __table_args__ = (UniqueConstraint("input_fingerprint", "kind", "attempt", name="uq_job_fingerprint_attempt"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"), index=True)
    submission_id: Mapped[str | None] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"), index=True, nullable=True)
    answer_id: Mapped[str | None] = mapped_column(ForeignKey("answers.id", ondelete="CASCADE"), index=True, nullable=True)
    document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=True)
    draft_assessment_revision_id: Mapped[str | None] = mapped_column(ForeignKey("assessment_revisions.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(40))
    stage: Mapped[str] = mapped_column(String(32))
    input_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(24), default="queued")
    progress_current: Mapped[int] = mapped_column(Integer, default=0)
    progress_total: Mapped[int] = mapped_column(Integer, default=0)
    lease_owner: Mapped[str | None] = mapped_column(String(80), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[str] = mapped_column(String(36))
    previous_revision: Mapped[str | None] = mapped_column(String(36), nullable=True)
    new_revision: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ExportSnapshot(Base):
    __tablename__ = "export_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"), index=True)
    assessment_revision_id: Mapped[str] = mapped_column(ForeignKey("assessment_revisions.id"))
    mode: Mapped[str] = mapped_column(String(12))
    payload: Mapped[dict] = mapped_column(JSON)
    manifest_hash: Mapped[str] = mapped_column(String(64))
    artifact_key: Mapped[str] = mapped_column(String(180), unique=True)
    artifact_hash: Mapped[str] = mapped_column(String(64), default="")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Artifact(Base):
    __tablename__ = "artifacts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=True)
    storage_key: Mapped[str] = mapped_column(String(180), unique=True)
    kind: Mapped[str] = mapped_column(String(32))
    sha256: Mapped[str] = mapped_column(String(64))
    byte_size: Mapped[int] = mapped_column(Integer)
    parent_ids: Mapped[list] = mapped_column(JSON, default=list)
    retention_class: Mapped[str] = mapped_column(String(32), default="assessment_data")
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_type: Mapped[str] = mapped_column(String(80))
    job_id: Mapped[str] = mapped_column(ForeignKey("pipeline_jobs.id", ondelete="CASCADE"), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
