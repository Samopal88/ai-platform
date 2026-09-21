"""Plan/limit enforcement helpers."""
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.user import User
from app.services.plan_service import get_plan_definition
from app.services.usage_service import tokens_used_this_month


def _plan_for_user(user: User):
    return get_plan_definition(user.plan_type or "free") or get_plan_definition("free")


def ensure_project_limit(db: Session, user: User) -> None:
    plan = _plan_for_user(user)
    current = db.query(func.count(Project.id)).filter(Project.user_id == user.id).scalar() or 0
    limit = int(plan.project_limit if plan else user.token_limit_month)
    if int(current) >= limit:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Project limit reached for current plan ({limit}).",
        )


def ensure_storage_available(user: User, size_delta: int) -> None:
    plan = _plan_for_user(user)
    limit = int(plan.storage_limit_total if plan else user.storage_limit_total)
    if int(user.storage_used or 0) + int(size_delta or 0) > limit:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Storage limit reached for current plan.",
        )


def ensure_project_storage_available(project: Project, user: User, size_delta: int) -> None:
    plan = _plan_for_user(user)
    limit = int(plan.storage_limit_per_project if plan else user.storage_limit_total)
    if int(project.storage_used or 0) + int(size_delta or 0) > limit:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Project storage limit reached for current plan.",
        )


def ensure_token_available(db: Session, user: User, token_delta: int) -> None:
    plan = _plan_for_user(user)
    limit = int(plan.token_limit_month if plan else user.token_limit_month)
    used = tokens_used_this_month(db, user.id)
    if used + int(token_delta or 0) > limit:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Token limit reached for current plan.",
        )
