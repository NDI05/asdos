from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from .config import settings
from .database import Base, engine
from . import models  # noqa: F401 - registers metadata
from .model_adapters import model_status
from .router_assessments import router as assessments_router
from .router_auth import router as auth_router
from .router_review import router as review_router
from .router_submissions import router as submissions_router
from .router_exports import router as exports_router


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        settings.validate()
        settings.artifact_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        if settings.auto_create and settings.environment != "production":
            Base.metadata.create_all(bind=engine)
        yield

    application = FastAPI(
        title="ASDOS API",
        version="0.1.0",
        description="Local-first assistant for lecturer-reviewed written assessments.",
        docs_url="/api/docs" if settings.environment != "production" else None,
        redoc_url=None,
        lifespan=lifespan,
    )

    @application.middleware("http")
    async def security_headers(request: Request, call_next):
        request.state.request_id = str(uuid.uuid4())
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > settings.max_request_bytes:
                    return JSONResponse(status_code=413, content={"error": {
                        "code": "REQUEST_TOO_LARGE", "message": "Ukuran permintaan melebihi batas.",
                        "request_id": request.state.request_id,
                    }})
            except ValueError:
                return JSONResponse(status_code=400, content={"error": {
                    "code": "INVALID_CONTENT_LENGTH", "message": "Header ukuran permintaan tidak valid.",
                    "request_id": request.state.request_id,
                }})
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data: blob:; object-src 'none'; frame-ancestors 'none'; base-uri 'self'"
        return response

    @application.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        detail = exc.detail if isinstance(exc.detail, dict) else {"code": "REQUEST_REJECTED"}
        code = detail.get("code", "REQUEST_REJECTED")
        message = _error_message(code)
        body = {"error": {"code": code, "message": message, "request_id": getattr(request.state, "request_id", "")}}
        allowed = {key: value for key, value in detail.items() if key not in {"code", "message", "input", "ctx"}}
        if allowed:
            body["error"]["details"] = allowed
        return JSONResponse(status_code=exc.status_code, content=body, headers=exc.headers)

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        details = [{"field": ".".join(str(part) for part in item["loc"] if part != "body"), "type": item["type"]}
                   for item in exc.errors()]
        return JSONResponse(status_code=422, content={"error": {
            "code": "VALIDATION_ERROR", "message": "Periksa kembali format data yang dimasukkan.",
            "request_id": getattr(request.state, "request_id", ""), "details": details,
        }})

    @application.get("/health/live", tags=["health"])
    def live():
        return {"status": "live"}

    @application.get("/health/ready", tags=["health"])
    def ready():
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            database = "ready"
        except Exception:
            return JSONResponse(status_code=503, content={"status": "not_ready", "database": "unavailable"})
        queue = "eager" if settings.celery_eager else "unknown"
        if not settings.celery_eager:
            try:
                import redis
                redis.Redis.from_url(settings.redis_url, socket_timeout=1.0).ping()
                queue = "ready"
            except Exception:
                return JSONResponse(status_code=503, content={"status": "not_ready", "database": database, "queue": "unavailable"})
        return {"status": "ready", "database": database, "queue": queue, "model": model_status()}

    @application.get("/api/v1/health/model", tags=["health"])
    def model_health():
        return model_status()

    application.include_router(auth_router)
    application.include_router(assessments_router)
    application.include_router(submissions_router)
    application.include_router(review_router)
    application.include_router(exports_router)

    web_dist = Path(__file__).resolve().parents[2] / "web" / "dist"
    index_file = web_dist / "index.html"
    if index_file.exists():
        assets_dir = web_dist / "assets"
        if assets_dir.is_dir():
            application.mount("/assets", StaticFiles(directory=assets_dir), name="web-assets")

        @application.get("/", include_in_schema=False)
        def web_index():
            return FileResponse(index_file)

    return application


def _error_message(code: str) -> str:
    messages = {
        "AUTH_REQUIRED": "Silakan masuk terlebih dahulu.",
        "SESSION_EXPIRED": "Sesi telah berakhir. Masuk kembali.",
        "CSRF_INVALID": "Token keamanan tidak valid. Muat ulang halaman.",
        "RESOURCE_NOT_FOUND": "Data tidak ditemukan atau Anda tidak berwenang melihatnya.",
        "FINALIZATION_BLOCKED": "Masih ada jawaban yang perlu diselesaikan sebelum finalisasi.",
        "MODEL_UNAVAILABLE": "Model lokal belum siap. Transkripsi dan penilaian manual tetap tersedia.",
        "MODEL_DEVICE_UNAVAILABLE": "Perangkat inferensi model tidak tersedia pada konfigurasi ini.",
        "PDF_TOO_LARGE": "Ukuran PDF melebihi batas 50 MiB.",
        "NOT_A_PDF": "Berkas tidak terdeteksi sebagai PDF.",
    }
    return messages.get(code, "Permintaan tidak dapat diproses.")


app = create_app()
