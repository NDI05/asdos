from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from datetime import timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import LoginSession, User, now_utc

COOKIE_NAME = "asdos_session"
COOKIE_TTL = timedelta(hours=12)
password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
login_attempts: dict[str, deque[float]] = defaultdict(deque)


def hash_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def csrf_for(session_token: str) -> str:
    return hmac.new(settings.session_secret.encode(), session_token.encode(), hashlib.sha256).hexdigest()


def hash_password(password: str) -> str:
    if len(password) < 12 or len(password) > 256:
        raise ValueError("Kata sandi harus memiliki 12–256 karakter.")
    return password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, ValueError):
        return False


def enforce_login_rate_limit(request: Request) -> None:
    remote = request.client.host if request.client else "unknown"
    now = time.monotonic()
    recent = login_attempts[remote]
    while recent and now - recent[0] > 60:
        recent.popleft()
    if len(recent) >= 8:
        raise HTTPException(status_code=429, detail={"code": "LOGIN_RATE_LIMITED"})
    recent.append(now)


def create_session(db: Session, response: Response, user: User) -> str:
    token = secrets.token_urlsafe(48)
    csrf = csrf_for(token)
    row = LoginSession(
        user_id=user.id,
        token_hash=hash_token(token),
        csrf_hash=hash_token(csrf),
        expires_at=now_utc() + COOKIE_TTL,
    )
    db.add(row)
    db.commit()
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=int(COOKIE_TTL.total_seconds()),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/",
    )
    return csrf


def session_user(db: Session, request: Request, *, write: bool = False) -> tuple[User, LoginSession]:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail={"code": "AUTH_REQUIRED"})
    row = db.scalar(select(LoginSession).where(LoginSession.token_hash == hash_token(token)))
    now = now_utc()
    expires_at = row.expires_at if row else None
    if expires_at and expires_at.tzinfo is None:
        # SQLite returns timezone-aware DateTime values as naive; session times are written as UTC.
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if not row or row.revoked_at or expires_at <= now:
        raise HTTPException(status_code=401, detail={"code": "SESSION_EXPIRED"})
    user = db.get(User, row.user_id)
    if not user or user.disabled_at:
        raise HTTPException(status_code=401, detail={"code": "AUTH_REQUIRED"})
    if write:
        csrf = request.headers.get("x-csrf-token", "")
        expected = csrf_for(token)
        if not hmac.compare_digest(hash_token(csrf), row.csrf_hash) or not hmac.compare_digest(csrf, expected):
            raise HTTPException(status_code=403, detail={"code": "CSRF_INVALID"})
    return user, row


def revoke_session(db: Session, response: Response, row: LoginSession) -> None:
    row.revoked_at = now_utc()
    db.commit()
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, secure=settings.cookie_secure, samesite="strict")
