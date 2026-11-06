from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .database import get_db
from .models import Assessment, User
from .security import session_user


def require_actor(request: Request, db: Session = Depends(get_db)) -> User:
    user, _ = session_user(db, request)
    return user


def require_writer(request: Request, db: Session = Depends(get_db)) -> User:
    user, _ = session_user(db, request, write=True)
    return user


def require_owner_scope(db: Session, actor: User, assessment_id: str) -> Assessment:
    assessment = db.get(Assessment, assessment_id)
    if not assessment or assessment.owner_id != actor.id:
        raise HTTPException(status_code=404, detail={"code": "RESOURCE_NOT_FOUND"})
    return assessment
