from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from apps.api.asdos_api.model_adapters import hardware_summary, qwen_adapter
from packages.asdos_domain.scoring import DomainError


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify real local inference on synthetic input only.")
    parser.add_argument("--output", type=Path, help="Save a reproducible JSON smoke report.")
    args = parser.parse_args()
    started = time.monotonic()
    stage = "transcription"
    report = {"hardware": hardware_summary(), "fixture": "synthetic_only", "checks": {}}
    image = Path("tests/fixtures/synthetic_region.png")
    if not image.exists():
        report["status"] = "blocked_fixture_missing"
    else:
        try:
            segments, provenance = qwen_adapter.transcribe([image.read_bytes()], "id")
            report["checks"]["transcription"] = {"completed": True, "segment_count": len(segments),
                                                   "needs_review": any(s.flags for s in segments),
                                                   "text": [s.text for s in segments], "provenance": provenance.__dict__}
            stage = "rubric_generation"
            seed = {"stable_question_id": "smoke-q", "label": "1", "order": 1,
                    "text": "Jelaskan fungsi RAM dan sifat penyimpanannya.", "weight": "1", "answer_type": "essay"}
            generated, rubric_provenance = qwen_adapter.generate_rubrics([seed], "id")
            from apps.api.asdos_api.rubric_generation import merge_generated
            rubric = merge_generated([seed], generated)[0]
            report["checks"]["rubric_generation"] = {"completed": True, "criterion_count": len(rubric["criteria"]),
                                                      "provenance": rubric_provenance.__dict__}
            stage = "text_grading"
            text = "RAM menyimpan data kerja sementara. Isinya hilang ketika daya mati."
            proposal, grading_provenance = qwen_adapter.grade(question_id="smoke-q", question={"question_id": "smoke-q", "text": seed["text"]},
                rubric={"reference_answer": rubric["reference_answer"], "alternatives": rubric["alternatives"],
                    "criteria": [{"criterion_id": c["id"], **{k:v for k,v in c.items() if k != "id"}} for c in rubric["criteria"]]},
                transcript=text, segments={"seg-1": text}, valid_region_ids=["synthetic-region"],
                evidence_catalog=[{"segment_id":"seg-1", "region_id":"synthetic-region", "page_index":0, "order":1, "text":text}])
            report["checks"]["text_grading"] = {"completed": True, "criterion_count": len(proposal["criteria"]),
                                                 "proposal": proposal, "provenance": grading_provenance.__dict__}
            report.update({"status": "inference_succeeded", "provenance": provenance.__dict__})
        except Exception as exc:
            report.update({"status": "inference_not_verified", "failed_check": stage,
                           "error_code": getattr(exc, "code", None) or type(exc).__name__})
            if isinstance(exc, DomainError):
                report["validation_error"] = str(exc)
    report["duration_seconds"] = round(time.monotonic() - started, 2)
    encoded = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded)
    return 0 if report["status"] == "inference_succeeded" else 2


if __name__ == "__main__":
    raise SystemExit(main())
