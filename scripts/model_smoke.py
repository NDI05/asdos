from __future__ import annotations

import json
from pathlib import Path

from apps.api.asdos_api.model_adapters import hardware_summary, qwen_adapter


def main() -> int:
    report = {"hardware": hardware_summary()}
    image = Path("tests/fixtures/synthetic_region.png")
    if not image.exists():
        report["status"] = "blocked_fixture_missing"
    else:
        segments, provenance = qwen_adapter.transcribe([image.read_bytes()], "id")
        report.update({"status": "inference_succeeded", "segment_count": len(segments), "provenance": provenance.__dict__})
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "inference_succeeded" else 2


if __name__ == "__main__":
    raise SystemExit(main())
