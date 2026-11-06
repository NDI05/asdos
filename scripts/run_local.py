"""Run the private local website and a single native model worker (MPS/CUDA)."""
from __future__ import annotations

import os
from pathlib import Path
import signal
import secrets
import socket
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    if not os.environ.get("ASDOS_SESSION_SECRET"):
        secret_path = root / "data/local-session-secret"
        secret_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            with secret_path.open("x", opener=lambda path, flags: os.open(path, flags, 0o600)) as stream:
                stream.write(secrets.token_urlsafe(48))
        except FileExistsError:
            pass
        os.environ["ASDOS_SESSION_SECRET"] = secret_path.read_text().strip()
    env = {**os.environ, "ASDOS_CELERY_EAGER": "false",
           "ASDOS_REDIS_URL": "redis://127.0.0.1:6380/0", "ASDOS_AUTO_CREATE": "false",
           "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1"}
    os.environ.update(env)
    from sqlalchemy import func, select
    from sqlalchemy.engine import make_url
    from apps.api.asdos_api.config import settings
    from apps.api.asdos_api.database import SessionLocal
    from apps.api.asdos_api.model_adapters import model_status
    from apps.api.asdos_api.models import User

    if not (root / "apps/web/dist/index.html").is_file():
        print("Bangun UI dahulu: make install-web && make build-web", file=sys.stderr)
        return 2
    status = model_status()
    if not status["available"]:
        print(f"Model belum siap ({status['reason']}). Jalankan make setup-model.", file=sys.stderr)
        return 2
    # Fail before starting any services if the website address is already occupied.
    try:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 8000))
    except OSError:
        print("Port 8000 sudah dipakai. Hentikan server ASDOS sebelumnya dahulu.", file=sys.stderr)
        return 2
    database_url = make_url(settings.database_url)
    if database_url.get_backend_name() == "sqlite" and database_url.database:
        source = Path(database_url.database)
        if source.is_file():
            backup_dir = root / "data/backups"
            backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            with sqlite3.connect(source) as live, sqlite3.connect(backup_dir / f"before-start-{stamp}.sqlite3") as backup:
                live.backup(backup)
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], env=env, check=True)
    with SessionLocal() as db:
        needs_owner = not db.scalar(select(func.count()).select_from(User).where(User.role == "owner"))
    if needs_owner:
        subprocess.run([sys.executable, "-m", "scripts.create_owner"], env=env, check=True)
    compose = ["docker", "compose", "-f", str(root / "deploy/compose.native.yaml")]
    children: list[subprocess.Popen] = []

    def interrupted(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupted)
    try:
        subprocess.run([*compose, "up", "-d", "--wait"], env=env, check=True)
        commands = [
            [sys.executable, "-m", "celery", "-A", "apps.worker.celery_app:celery_app",
             "worker", "--pool=solo", "--concurrency=1", "--loglevel=WARNING", "--without-gossip", "--without-mingle"],
            [sys.executable, "-m", "celery", "-A", "apps.worker.celery_app:celery_app",
             "beat", "--loglevel=WARNING", "--schedule", str(root / "data/celerybeat-schedule")],
            [sys.executable, "-m", "uvicorn", "apps.api.asdos_api.main:app",
             "--host", "127.0.0.1", "--port", "8000"],
        ]
        for command in commands:
            children.append(subprocess.Popen(command, cwd=root, env=env, start_new_session=True))
        print("ASDOS: http://127.0.0.1:8000 · Ctrl+C untuk berhenti. Model berjalan pada worker native.", flush=True)
        while all(child.poll() is None for child in children):
            time.sleep(1)
        print("Salah satu proses berhenti; menghentikan proses ASDOS lainnya.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
        for child in reversed(children):
            try:
                child.wait(timeout=20)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        subprocess.run([*compose, "stop"], env=env, check=False)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"Startup gagal ({type(exc).__name__}). Periksa Docker Desktop dan dependency lokal.", file=sys.stderr)
        raise SystemExit(2)
