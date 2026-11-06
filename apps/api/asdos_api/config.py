from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    environment: str = os.getenv("ASDOS_ENV", "development")
    database_url: str = os.getenv("ASDOS_DATABASE_URL", "sqlite:///./data/asdos-dev.sqlite3")
    redis_url: str = os.getenv("ASDOS_REDIS_URL", "redis://127.0.0.1:6379/0")
    artifact_dir: Path = Path(os.getenv("ASDOS_ARTIFACT_DIR", "./data/private")).resolve()
    model_dir: Path = Path(os.getenv("ASDOS_MODEL_DIR", "./models/Qwen3-VL-4B-Instruct")).resolve()
    model_revision: str = os.getenv("ASDOS_MODEL_REVISION", "ebb281ec70b05090aa6165b016eac8ec08e71b17")
    session_secret: str = os.getenv("ASDOS_SESSION_SECRET", "")
    cookie_secure: bool = os.getenv("ASDOS_COOKIE_SECURE", "false").lower() == "true"
    celery_eager: bool = os.getenv("ASDOS_CELERY_EAGER", "false").lower() == "true"
    auto_create: bool = os.getenv("ASDOS_AUTO_CREATE", "true").lower() == "true"
    max_upload_bytes: int = int(os.getenv("ASDOS_MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))
    max_pdf_pages: int = int(os.getenv("ASDOS_MAX_PDF_PAGES", "100"))
    max_render_pixels: int = int(os.getenv("ASDOS_MAX_RENDER_PIXELS", "25000000"))
    render_dpi: int = int(os.getenv("ASDOS_RENDER_DPI", "250"))
    max_request_bytes: int = int(os.getenv("ASDOS_MAX_REQUEST_BYTES", str(52 * 1024 * 1024)))
    model_allow_cpu: bool = os.getenv("ASDOS_MODEL_ALLOW_CPU", "false").lower() == "true"
    export_retention_days: int = int(os.getenv("ASDOS_EXPORT_RETENTION_DAYS", "0"))

    def validate(self) -> None:
        if self.environment == "production" and len(self.session_secret) < 32:
            raise RuntimeError("ASDOS_SESSION_SECRET must be configured with at least 32 characters")
        if self.max_upload_bytes <= 0 or self.max_pdf_pages <= 0 or self.max_render_pixels <= 0:
            raise RuntimeError("PDF limits must be positive")
        if self.export_retention_days < 0:
            raise RuntimeError("ASDOS_EXPORT_RETENTION_DAYS must be zero or positive")


settings = Settings()
if not settings.session_secret and settings.environment != "production":
    settings = Settings(session_secret=secrets.token_urlsafe(48))
