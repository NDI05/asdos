from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

MODEL_ID = "Qwen/Qwen3-VL-4B-Instruct"
REVISION = "ebb281ec70b05090aa6165b016eac8ec08e71b17"


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    target = Path(os.getenv("ASDOS_MODEL_DIR", "models/Qwen3-VL-4B-Instruct")).resolve()
    target.mkdir(parents=True, exist_ok=True)
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        sys.stderr.write("Pasang extra model terlebih dahulu: uv sync --extra model\n")
        return 2
    print(f"Mengunduh {MODEL_ID} pada revision tetap {REVISION} ke {target}", flush=True)
    snapshot_download(
        repo_id=MODEL_ID,
        revision=REVISION,
        local_dir=str(target),
        allow_patterns=[
            "*.json", "*.safetensors", "*.model", "*.tiktoken", "*.txt", "*.jinja", "LICENSE", "README.md"
        ],
    )
    if not (target / "config.json").is_file():
        raise RuntimeError("Download selesai tanpa config.json; checkpoint tidak valid.")
    hashes = {
        path.relative_to(target).as_posix(): file_hash(path)
        for path in sorted(target.rglob("*"))
        if path.is_file() and ".cache" not in path.parts and path.name != "asdos-model-manifest.json"
    }
    manifest = {
        "schema_version": "asdos-model-manifest.v1",
        "model_id": MODEL_ID,
        "revision": REVISION,
        "license": "Apache-2.0",
        "runtime": {"torch": "2.15.0", "transformers": "5.22.1", "trust_remote_code": False},
        "files": hashes,
    }
    encoded = json.dumps(manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    manifest["manifest_sha256"] = hashlib.sha256(encoded).hexdigest()
    (target / "asdos-model-manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Checkpoint diprovisikan. File terhash: {len(hashes)}. Manifest: {target / 'asdos-model-manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
