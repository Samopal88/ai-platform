"""Public plan catalog endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.services.plan_service import get_plan_definition, list_plan_definitions

router = APIRouter(prefix="/api/plans", tags=["Plans"])


@router.get("")
def list_plans():
    return {"plans": list_plan_definitions()}


@router.get("/{code}")
def get_plan(code: str):
    plan = get_plan_definition(code)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan.__dict__
