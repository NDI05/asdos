from __future__ import annotations

import unittest

from packages.asdos_domain.evaluation import EvaluationInputError, evaluate_manifest


def sample_manifest() -> dict:
    return {
        "schema_version": "asdos-evaluation.v1",
        "dataset": {
            "manifest_id": "synthetic-eval-1",
            "consent_status": "synthetic",
            "retention_policy": "fixture-only",
            "split_manifest_sha256": "b" * 64,
        },
        "provenance": {
            "model_id": "synthetic-baseline",
            "model_revision": "test-only",
            "checkpoint_sha256": "a" * 64,
            "prompt_version": "literal.v1",
            "preprocessing_version": "none",
            "runtime": "synthetic",
            "device": "cpu-test",
            "code_revision": "synthetic-test-revision",
            "dependency_lock_sha256": "c" * 64,
        },
        "samples": [
            {
                "sample_id": "s1", "writer_id": "w1", "split": "development",
                "source_sha256": "1" * 64, "gold_text": "RAM baik", "predicted_text": "RAM baik",
                "gold_question_id": "q1", "predicted_question_id": "q1",
                "gold_score": "8", "predicted_score": "8.5", "status": "proposed",
            },
            {
                "sample_id": "s2", "writer_id": "w2", "split": "development",
                "source_sha256": "2" * 64, "gold_text": "SSD", "predicted_text": "SDD",
                "gold_question_id": "q2", "predicted_question_id": "q3",
                "gold_score": "6", "predicted_score": "5", "critical_error": True,
            },
            {
                "sample_id": "s3", "writer_id": "w3", "split": "locked_test",
                "source_sha256": "3" * 64, "gold_text": "uji", "predicted_text": "uji",
            },
        ],
    }


class TestEvaluation(unittest.TestCase):
    def test_aggregates_only_the_requested_split_and_hides_raw_text(self):
        report = evaluate_manifest(sample_manifest(), split="development")
        self.assertEqual(report["counts"]["samples"], 2)
        self.assertEqual(report["counts"]["writers"], 2)
        self.assertEqual(report["transcription"]["char_errors"], 1)
        self.assertEqual(report["mapping"]["accuracy"], 0.5)
        self.assertEqual(report["scoring"]["mae"], "0.75")
        self.assertEqual(report["gate_decision"], "not_assessed")
        self.assertNotIn("gold_text", str(report))

    def test_rejects_writer_leakage_before_selecting_a_split(self):
        manifest = sample_manifest()
        manifest["samples"][2]["writer_id"] = "w1"
        with self.assertRaisesRegex(EvaluationInputError, "writer leakage"):
            evaluate_manifest(manifest, split="development")

    def test_rejects_document_hash_leakage_across_splits(self):
        manifest = sample_manifest()
        manifest["samples"][2]["source_sha256"] = "1" * 64
        with self.assertRaisesRegex(EvaluationInputError, "document leakage"):
            evaluate_manifest(manifest, split="development")

    def test_reports_empty_gold_separately_and_excludes_it_from_cer(self):
        manifest = sample_manifest()
        manifest["samples"] = manifest["samples"][:1]
        manifest["samples"][0]["gold_text"] = ""
        manifest["samples"][0]["predicted_text"] = "ink"
        report = evaluate_manifest(manifest, split="development")
        self.assertEqual(report["counts"]["empty_gold"], 1)
        self.assertIsNone(report["transcription"]["cer"])


if __name__ == "__main__":
    unittest.main()
