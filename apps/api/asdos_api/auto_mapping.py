"""Strict visual localization contracts and conservative number matching.

The locator never receives question text, reference answers, or rubric data.
"""
from collections import Counter
import re
from typing import Annotated

from pydantic import Field, model_validator

from .schemas import StrictModel

LOCATOR_PROMPT_VERSION = "answer-localization.v2"
AUTO_MAPPING_VERSION = "number-matching.v1"
LOCATOR_PREPROCESSING = "locator-fit-1600x2000.v1"
Coordinate = Annotated[int, Field(strict=True, ge=0, le=1000)]


class LocatedAnswer(StrictModel):
    label: str | None = Field(max_length=20)
    bbox: tuple[Coordinate, Coordinate, Coordinate, Coordinate]
    continuation: bool = Field(strict=True)
    flags: list[str] = Field(max_length=10)

    @model_validator(mode="after")
    def valid_box(self):
        left, top, right, bottom = self.bbox
        if left >= right or top >= bottom:
            raise ValueError("answer box must have positive area")
        return self


class LocatedPage(StrictModel):
    regions: list[LocatedAnswer] = Field(max_length=60)
    flags: list[str] = Field(max_length=10)


def normalize_label(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"[().\s]", "", value).lower()
    return normalized if re.fullmatch(r"[0-9]{1,3}[a-z]?", normalized) else None


def flag_number_disagreement(region: dict) -> dict:
    prefix = re.match(r"^\s*(\d{1,3}(?:\([a-zA-Z]\)|[a-zA-Z])?)\s*[.)]",region["text"])
    if prefix and normalize_label(prefix.group(1)) != normalize_label(region["label"]):
        return {**region,"flags":[*region["flags"],"number_ocr_disagreement"]}
    return region


def match_regions(regions: list[dict], questions: list[dict]) -> list[dict]:
    """Only match explicit unique labels; retain ambiguous/unknown regions."""
    labels = [normalize_label(q["label"]) for q in questions]
    counts = Counter(labels)
    question_ids = {normalize_label(q["label"]): q["stable_question_id"] for q in questions
                    if normalize_label(q["label"]) and counts[normalize_label(q["label"])] == 1}
    grouped: dict[str, list[dict]] = {}
    for region in regions:
        key = normalize_label(region["label"])
        if key:
            grouped.setdefault(key, []).append(region)
    duplicated = set()
    for label, items in grouped.items():
        # Continuations must show the same explicit number and start on a later page.
        if any(not item["continuation"] or item["page_index"] <= items[i - 1]["page_index"]
               for i, item in enumerate(items) if i):
            duplicated.add(label)
    output = []
    for region in regions:
        flags = list(region["flags"])
        label = normalize_label(region["label"])
        if label and any(item["flags"] for item in grouped[label]):
            flags.append("number_group_needs_review")
        if not label:
            flags.append("number_unreadable_or_missing")
        elif label in duplicated:
            flags.append("duplicate_number")
        elif label not in question_ids:
            flags.append("unknown_question_number")
        if region["continuation"] and (not label or grouped.get(label, [region])[0] is region):
            flags.append("continuation_without_start")
        for other in regions:
            if other is region or other["page_index"] != region["page_index"]:
                continue
            a, b = region["bbox"], other["bbox"]
            if min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1]):
                flags.append("overlapping_answer_regions")
                break
        output.append({**region, "mapping_flags": sorted(set(flags)),
                       "question_id": question_ids.get(label) if not flags else None})
    ambiguous = {normalize_label(item["label"]) for item in output if item["mapping_flags"]}
    for item in output:
        label = normalize_label(item["label"])
        if label in ambiguous and len(grouped.get(label, [])) > 1:
            item["mapping_flags"] = sorted(set(item["mapping_flags"] + ["number_group_needs_review"]))
            item["question_id"] = None
    return output


def analysis_fingerprint(submission, document):
    from .config import settings
    from .model_adapters import transcriber_fingerprint
    from .services import canonical_hash
    return canonical_hash({
            "document_id":document.id, "layout_id":document.active_layout_revision_id,
            "assessment_revision_id":submission.assessment_revision_id, "model":settings.model_revision,
            "locator_prompt":LOCATOR_PROMPT_VERSION, "locator_preprocessing":LOCATOR_PREPROCESSING,
            "matching":AUTO_MAPPING_VERSION, "transcriber":transcriber_fingerprint()})


def schedule_analysis(db, submission, document):
    from .services import add_job
    return add_job(db, assessment_id=submission.assessment_id, submission_id=submission.id,
        document_id=document.id, kind="analyze_answers", input_fingerprint=analysis_fingerprint(submission,document))


def current_mapping(db, submission, answer):
    from .models import AnswerMappingRevision, Document
    document = db.get(Document,submission.active_document_id) if submission.active_document_id else None
    mapping = db.get(AnswerMappingRevision,answer.active_mapping_revision_id) if answer and answer.active_mapping_revision_id else None
    return mapping if mapping and document and mapping.layout_revision_id == document.active_layout_revision_id else None


def adopt_region_transcripts(db, answer, mapping, regions):
    """Reuse literal crop OCR after a mapping correction, without another model call."""
    from .model_adapters import transcription_flags, transcription_status_for_flags
    from .models import ModelRun, TranscriptionRevision
    old = db.get(TranscriptionRevision,answer.active_transcription_revision_id) if answer.active_transcription_revision_id else None
    if old and old.source == "human":
        return False
    if not regions or any(not r.analysis or "text" not in r.analysis or not r.analysis.get("transcriber_run_id") for r in regions):
        return False
    segments = []
    for order,region in enumerate(regions,start=1):
        result = region.analysis
        run = db.get(ModelRun,result["transcriber_run_id"])
        if not run or run.status != "succeeded":
            return False
        segments.append({"segment_id":f"seg-{order}","region_id":region.id,"page_index":result["page_index"],
            "order":order,"text":result["text"],"confidence":None,
            "flags":sorted(set(result.get("transcription_flags",[])) | set(transcription_flags(result["text"]))),
            "model_run_id":run.id})
    flags = sorted({f for segment in segments for f in segment["flags"]})
    transcript = TranscriptionRevision(answer_id=answer.id,mapping_revision_id=mapping.id,
        revision_no=answer.transcript_revision+1,parent_revision_id=answer.active_transcription_revision_id,
        literal_text="\n".join(s["text"] for s in segments),segments=segments,status=transcription_status_for_flags(flags),
        flags=flags,source="model",model_run_id=segments[0]["model_run_id"])
    db.add(transcript); db.flush()
    answer.active_transcription_revision_id,answer.transcript_revision = transcript.id,transcript.revision_no
    answer.literal_text,answer.transcript_status = transcript.literal_text,transcript.status
    answer.active_proposal_id = None
    return True
