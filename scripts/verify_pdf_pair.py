"""Local functional diagnostic on explicitly supplied PDFs and reviewed regions.

Outputs contain private document text: keep the output directory outside Git.
This does not approve identities, rubrics, mappings, or grades in the application.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import time
from io import BytesIO
from pathlib import Path

from PIL import Image

from apps.api.asdos_api.config import settings
from apps.api.asdos_api.model_adapters import qwen_adapter
from apps.worker.pdfium_runner import render_in_isolated_process


def render_private(source: Path, destination: Path, *, extract_text: bool) -> dict:
    manifest, temporary = render_in_isolated_process(source, extract_text=extract_text)
    try:
        shutil.copytree(temporary, destination)
    finally:
        shutil.rmtree(temporary.parent)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question-pdf", required=True, type=Path)
    parser.add_argument("--answer-pdf", required=True, type=Path)
    parser.add_argument("--regions", required=True, type=Path,
                        help="Reviewed JSON array: {label,page_index,bbox:[left,top,right,bottom]} (normalized).")
    parser.add_argument("--output", required=True, type=Path, help="New private output directory.")
    parser.add_argument("--language", choices=["id", "en"], default="id")
    args = parser.parse_args()
    regions = json.loads(args.regions.read_text(encoding="utf-8"))
    if not isinstance(regions, list) or not regions:
        parser.error("At least one reviewed answer region is required.")
    for region in regions:
        box = region["bbox"]
        if (len(box) != 4 or any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in box)
                or not 0 <= box[0] < box[2] <= 1 or not 0 <= box[1] < box[3] <= 1
                or not isinstance(region["page_index"], int) or region["page_index"] < 0):
            parser.error("Invalid normalized region bounds.")
    args.output.mkdir(parents=True, exist_ok=False, mode=0o700)
    settings.artifact_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    started = time.monotonic()
    report = {"schema_version": "asdos-pdf-diagnostic.v1", "status": "running",
              "gate_decision": "not_assessed", "scores": None, "transcripts": [],
              "purpose": "functional_diagnostic_not_accuracy_benchmark",
              "sources": {"question_sha256": hashlib.sha256(args.question_pdf.read_bytes()).hexdigest(),
                          "answer_sha256": hashlib.sha256(args.answer_pdf.read_bytes()).hexdigest()}}
    try:
        print("Rendering question and answer PDFs locally.", flush=True)
        questions = render_private(args.question_pdf, args.output / "questions", extract_text=True)
        answers = render_private(args.answer_pdf, args.output / "answers", extract_text=False)
        report.update({"question_render": questions, "answer_render": answers})
        (args.output / "questions.txt").write_text("\n\n".join(p["text"] for p in questions["pages"]), encoding="utf-8")
        for index, region in enumerate(regions):
            print(f"Transcribing reviewed region {index + 1}/{len(regions)} (no question/rubric context).", flush=True)
            page = answers["pages"][region["page_index"]]
            with Image.open(args.output / "answers" / page["file"]) as image:
                left, top, right, bottom = region["bbox"]
                crop = image.crop((int(left * image.width), int(top * image.height),
                                   math.ceil(right * image.width), math.ceil(bottom * image.height)))
                buffer = BytesIO()
                crop.save(buffer, format="PNG")
                crop.close()
            data = buffer.getvalue()
            crop_name = f"region-{index + 1:02d}.png"
            (args.output / crop_name).write_bytes(data)
            segment_start = time.monotonic()
            segments, provenance = qwen_adapter.transcribe([data], args.language)
            report["transcripts"].append({**region, "crop": crop_name,
                "crop_sha256": hashlib.sha256(data).hexdigest(),
                "segments": [s.__dict__ for s in segments], "provenance": provenance.__dict__,
                "duration_seconds": round(time.monotonic() - segment_start, 2)})
            (args.output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        report["status"] = "completed_needs_human_review"
    except Exception as exc:
        report.update({"status": "failed", "error_code": getattr(exc, "code", type(exc).__name__)})
    report["duration_seconds"] = round(time.monotonic() - started, 2)
    (args.output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    draft = ["DRAF TRANSKRIPSI LITERAL — PERLU DIPERIKSA TERHADAP GAMBAR", ""]
    for region in report["transcripts"]:
        draft.extend([f"Bagian {region['label']} (halaman {region['page_index'] + 1})",
                      "\n".join(segment["text"] for segment in region["segments"]), ""])
    (args.output / "transcripts.txt").write_text("\n".join(draft), encoding="utf-8")
    print(f"Diagnostic status: {report['status']}. Private report saved in output directory.", flush=True)
    return 0 if report["status"] == "completed_needs_human_review" else 2


if __name__ == "__main__":
    raise SystemExit(main())
