"""Write an integrity manifest for a locally trained, private TrOCR checkpoint."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--training-report", type=Path, required=True)
    args = parser.parse_args()
    checkpoint = args.checkpoint.resolve()
    report_path = args.training_report.resolve()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if (report.get("status") != "completed" or report.get("samples_trained") != 2348
            or report.get("human_accuracy_measured") is not False
            or report.get("held_out_evaluation") is not False):
        parser.error("laporan bukan run eksperimen 2.348 sampel AI yang selesai dengan evaluasi training-only")

    required = {"config.json", "generation_config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json"}
    found = {path.name for path in checkpoint.iterdir() if path.is_file()}
    processor_config = "processor_config.json" if "processor_config.json" in found else "preprocessor_config.json"
    if not required <= found or processor_config not in found:
        parser.error("berkas checkpoint tidak lengkap")
    required.add(processor_config)
    files = {name: sha256(checkpoint / name) for name in sorted(required)}
    weights_hash = files["model.safetensors"]
    if weights_hash != report.get("final_weights_sha256"):
        parser.error("hash bobot tidak sama dengan laporan training")

    manifest = {
        "manifest_version": 1,
        "model_id": "asdos/trocr-handwriting-ai-experiment-v1",
        "revision": f"sha256:{weights_hash}",
        "experimental": True,
        "base_model_id": "microsoft/trocr-base-handwritten",
        "base_model_revision": "eaacaf452b06415df8f10bb6fad3a4c11e609406",
        "training_report_sha256": sha256(report_path),
        "dataset_manifest_sha256": report.get("manifest_sha256"),
        "training_samples": report["samples_trained"],
        "training_label_source": "ai_ocr_unverified",
        "human_accuracy_measured": False,
        "held_out_evaluation": False,
        "files": files,
        "weights_sha256": weights_hash,
    }
    output = checkpoint / "asdos-trocr-manifest.json"
    temporary = output.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, output)
    print(json.dumps({"manifest": str(output), "model_id": manifest["model_id"],
                      "revision": manifest["revision"], "files": len(files)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
