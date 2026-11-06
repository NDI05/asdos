from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import User
from .schemas import LoginRequest
from .security import (
    create_session,
    enforce_login_rate_limit,
    revoke_session,
    session_user,
    verify_password,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login")
def login(body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    enforce_login_rate_limit(request)
    user = db.scalar(select(User).where(User.username == body.username))
    if not user or user.disabled_at or not verify_password(user.password_hash, body.password):
        raise HTTPException(status_code=401, detail={"code": "INVALID_CREDENTIALS"})
    csrf = create_session(db, response, user)
    return {"user": {"id": user.id, "username": user.username, "display_name": user.display_name, "role": user.role}, "csrf_token": csrf}


@router.get("/session")
def get_session(request: Request, db: Session = Depends(get_db)):
    from .security import csrf_for

    user, _ = session_user(db, request)
    token = request.cookies["asdos_session"]
    return {"user": {"id": user.id, "username": user.username, "display_name": user.display_name, "role": user.role}, "csrf_token": csrf_for(token)}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    _, row = session_user(db, request, write=True)
    revoke_session(db, response, row)
    return {"status": "logged_out"}
