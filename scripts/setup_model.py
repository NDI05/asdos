"""Provision the real Qwen runtime/checkpoint and verify local inference."""
import os
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parents[1]
    uv = shutil.which("uv")
    if not uv:
        print("uv belum tersedia. Pasang uv lalu ulangi make setup-model.", file=sys.stderr)
        return 2
    env = dict(os.environ)
    env.setdefault("UV_CACHE_DIR", str(root / "data" / "cache" / "uv"))
    commands = [
        [uv, "sync", "--locked", "--extra", "model", "--extra", "test"],
        [uv, "run", "--locked", "--extra", "model", "--extra", "test", "python", "-m", "scripts.provision_model"],
        [uv, "run", "--locked", "--extra", "model", "--extra", "test", "python", "-m", "scripts.model_smoke",
         "--output", str(root / "data" / "model-smoke.json")],
    ]
    for stage, command in zip(("runtime", "checkpoint", "inference"), commands, strict=True):
        print(f"Penyiapan Qwen: {stage}", flush=True)
        code = subprocess.run(command, cwd=root, env=env).returncode
        if code:
            print(f"Tahap {stage} gagal. Periksa izin, DNS/jaringan, ruang disk dan backend perangkat; model belum dinyatakan siap.", file=sys.stderr)
            return code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
