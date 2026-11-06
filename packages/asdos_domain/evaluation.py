"""Small, deterministic evaluators for ASDOS's locked handwriting experiments.

This module never reads source documents. It accepts an explicit metadata manifest
and compares already-produced predictions with adjudicated text.
"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from decimal import Decimal
from typing import Any


SPLITS = {"development", "calibration", "locked_test"}
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
PROVENANCE_FIELDS = (
    "model_id",
    "model_revision",
    "checkpoint_sha256",
    "prompt_version",
    "preprocessing_version",
    "runtime",
    "device",
    "code_revision",
    "dependency_lock_sha256",
)


class EvaluationInputError(ValueError):
    """Raised when a private evaluation manifest violates its contract."""


def _distance(left: list[str], right: list[str]) -> int:
    """Levenshtein distance with O(min(n, m)) memory."""
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for index, left_item in enumerate(left, start=1):
        current = [index]
        for offset, right_item in enumerate(right, start=1):
            current.append(min(
                current[-1] + 1,
                previous[offset] + 1,
                previous[offset - 1] + (left_item != right_item),
            ))
        previous = current
    return previous[-1]


def _text(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def validate_manifest(manifest: dict[str, Any]) -> None:
    """Validate provenance and prevent writer/document leakage between splits."""
    if manifest.get("schema_version") != "asdos-evaluation.v1":
        raise EvaluationInputError("schema_version must be asdos-evaluation.v1")
    dataset = manifest.get("dataset")
    if not isinstance(dataset, dict) or not dataset.get("manifest_id"):
        raise EvaluationInputError("dataset.manifest_id is required")
    if dataset.get("consent_status") not in {"approved", "synthetic"}:
        raise EvaluationInputError("dataset.consent_status must be approved or synthetic")
    if not dataset.get("retention_policy"):
        raise EvaluationInputError("dataset.retention_policy is required")
    if not isinstance(dataset.get("split_manifest_sha256"), str) or not SHA256_RE.fullmatch(
        dataset["split_manifest_sha256"].lower()
    ):
        raise EvaluationInputError("dataset.split_manifest_sha256 must be a SHA-256 digest")

    provenance = manifest.get("provenance")
    if not isinstance(provenance, dict):
        raise EvaluationInputError("provenance is required")
    for field in PROVENANCE_FIELDS:
        value = provenance.get(field)
        if not isinstance(value, str) or not value.strip():
            raise EvaluationInputError(f"provenance.{field} is required")
    if not SHA256_RE.fullmatch(provenance["checkpoint_sha256"].lower()):
        raise EvaluationInputError("provenance.checkpoint_sha256 must be a SHA-256 digest")
    if not SHA256_RE.fullmatch(provenance["dependency_lock_sha256"].lower()):
        raise EvaluationInputError("provenance.dependency_lock_sha256 must be a SHA-256 digest")

    samples = manifest.get("samples")
    if not isinstance(samples, list) or not samples:
        raise EvaluationInputError("samples must be a non-empty list")
    sample_ids: set[str] = set()
    writer_splits: dict[str, set[str]] = defaultdict(set)
    document_splits: dict[str, set[str]] = defaultdict(set)
    for sample in samples:
        if not isinstance(sample, dict):
            raise EvaluationInputError("every sample must be an object")
        sample_id = sample.get("sample_id")
        writer_id = sample.get("writer_id")
        split = sample.get("split")
        digest = sample.get("source_sha256")
        if not isinstance(sample_id, str) or not sample_id.strip() or sample_id in sample_ids:
            raise EvaluationInputError("sample_id must be non-empty and unique")
        if not isinstance(writer_id, str) or not writer_id.strip():
            raise EvaluationInputError(f"sample {sample_id}: writer_id is required")
        if split not in SPLITS:
            raise EvaluationInputError(f"sample {sample_id}: invalid split")
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest.lower()):
            raise EvaluationInputError(f"sample {sample_id}: source_sha256 must be a SHA-256 digest")
        if not isinstance(sample.get("gold_text"), str) or not isinstance(sample.get("predicted_text"), str):
            raise EvaluationInputError(f"sample {sample_id}: gold_text and predicted_text must be strings")
        if sample.get("status", "proposed") not in {"proposed", "abstained"}:
            raise EvaluationInputError(f"sample {sample_id}: status must be proposed or abstained")
        if "critical_error" in sample and not isinstance(sample["critical_error"], bool):
            raise EvaluationInputError(f"sample {sample_id}: critical_error must be boolean")
        if "identity_error" in sample and not isinstance(sample["identity_error"], bool):
            raise EvaluationInputError(f"sample {sample_id}: identity_error must be boolean")
        if "missing_page_count" in sample and (
            isinstance(sample["missing_page_count"], bool)
            or not isinstance(sample["missing_page_count"], int)
            or sample["missing_page_count"] < 0
        ):
            raise EvaluationInputError(f"sample {sample_id}: missing_page_count must be a non-negative integer")
        for score_field in ("gold_score", "predicted_score"):
            score = sample.get(score_field)
            if score is not None:
                try:
                    parsed = Decimal(str(score))
                except Exception as exc:
                    raise EvaluationInputError(f"sample {sample_id}: invalid {score_field}") from exc
                if not parsed.is_finite():
                    raise EvaluationInputError(f"sample {sample_id}: {score_field} must be finite")
        sample_ids.add(sample_id)
        writer_splits[writer_id].add(split)
        document_splits[digest.lower()].add(split)

    if any(len(splits) > 1 for splits in writer_splits.values()):
        raise EvaluationInputError("writer leakage: one writer appears in multiple splits")
    if any(len(splits) > 1 for splits in document_splits.values()):
        raise EvaluationInputError("document leakage: one source hash appears in multiple splits")


def evaluate_manifest(manifest: dict[str, Any], *, split: str) -> dict[str, Any]:
    """Return aggregate metrics for one explicit split; never include raw text."""
    validate_manifest(manifest)
    if split not in SPLITS:
        raise EvaluationInputError("split must be development, calibration, or locked_test")
    samples = [sample for sample in manifest["samples"] if sample["split"] == split]
    if not samples:
        raise EvaluationInputError(f"manifest has no samples in {split}")

    char_errors = char_total = word_errors = word_total = 0
    empty_gold = abstained = critical_errors = identity_errors = missing_pages = 0
    mapping_total = mapping_correct = 0
    score_errors: list[Decimal] = []
    for sample in samples:
        gold = _text(sample["gold_text"])
        predicted = _text(sample["predicted_text"])
        status = sample.get("status", "proposed")
        abstained += status == "abstained"
        critical_errors += sample.get("critical_error", False)
        identity_errors += sample.get("identity_error", False)
        missing_pages += sample.get("missing_page_count", 0)
        if not gold:
            empty_gold += 1
        else:
            gold_chars, predicted_chars = list(gold), list(predicted)
            char_errors += _distance(gold_chars, predicted_chars)
            char_total += len(gold_chars)
            gold_words, predicted_words = gold.split(), predicted.split()
            word_errors += _distance(gold_words, predicted_words)
            word_total += len(gold_words)
        if "gold_question_id" in sample or "predicted_question_id" in sample:
            if sample.get("gold_question_id") is None or sample.get("predicted_question_id") is None:
                raise EvaluationInputError(f"sample {sample['sample_id']}: both question IDs are required")
            mapping_total += 1
            mapping_correct += sample["gold_question_id"] == sample["predicted_question_id"]
        if sample.get("gold_score") is not None and sample.get("predicted_score") is not None:
            score_errors.append(abs(Decimal(str(sample["predicted_score"])) - Decimal(str(sample["gold_score"]))))

    score_errors.sort()
    report: dict[str, Any] = {
        "schema_version": "asdos-evaluation-report.v1",
        "dataset_manifest_id": manifest["dataset"]["manifest_id"],
        "split": split,
        "provenance": dict(manifest["provenance"]),
        "counts": {
            "samples": len(samples),
            "writers": len({sample["writer_id"] for sample in samples}),
            "empty_gold": empty_gold,
            "abstained": abstained,
            "critical_errors": critical_errors,
            "identity_errors": identity_errors,
            "missing_pages": missing_pages,
        },
        "transcription": {
            "char_errors": char_errors,
            "gold_characters": char_total,
            "cer": char_errors / char_total if char_total else None,
            "word_errors": word_errors,
            "gold_words": word_total,
            "wer": word_errors / word_total if word_total else None,
            "proposal_coverage": (len(samples) - abstained) / len(samples),
        },
        "mapping": {
            "samples": mapping_total,
            "correct": mapping_correct,
            "accuracy": mapping_correct / mapping_total if mapping_total else None,
        },
        "scoring": {
            "samples": len(score_errors),
            "mae": str(sum(score_errors, Decimal(0)) / len(score_errors)) if score_errors else None,
            "p95_absolute_error": str(score_errors[max(0, (95 * len(score_errors) + 99) // 100 - 1)]) if score_errors else None,
        },
        "gate_decision": "not_assessed",
    }
    return report
