"""Usage accounting helpers."""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.billing import UsageRecord
from app.models.user import User


def current_period_month() -> str:
    return datetime.now(UTC).strftime("%Y-%m")


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


def tokens_used_this_month(db: Session, user_id: UUID) -> int:
    total = (
        db.query(func.coalesce(func.sum(UsageRecord.total_tokens), 0))
        .filter(UsageRecord.user_id == user_id, UsageRecord.period_month == current_period_month())
        .scalar()
    )
    return int(total or 0)


def usage_summary_this_month(db: Session, user_id: UUID) -> dict:
    rows = (
        db.query(UsageRecord)
        .filter(UsageRecord.user_id == user_id, UsageRecord.period_month == current_period_month())
        .all()
    )
    summary = {
        "period_month": current_period_month(),
        "total_tokens": 0,
        "total_cost_rub": "0",
        "operations": {},
        "providers": {},
        "models": {},
    }
    total_cost = Decimal("0")
    for row in rows:
        total_tokens = int(row.total_tokens or 0)
        summary["total_tokens"] += total_tokens
        total_cost += Decimal(str(row.estimated_cost or 0))

        operation_key = row.operation or "unknown"
        provider_key = row.provider or "unknown"
        model_key = row.model or "unknown"

        summary["operations"][operation_key] = summary["operations"].get(operation_key, 0) + total_tokens
        summary["providers"][provider_key] = summary["providers"].get(provider_key, 0) + total_tokens
        summary["models"][model_key] = summary["models"].get(model_key, 0) + total_tokens

    summary["total_cost_rub"] = f"{total_cost:.6f}"
    return summary


def record_usage(
    db: Session,
    *,
    user: User,
    operation: str,
    project_id=None,
    chat_id=None,
    message_id=None,
    provider: str | None = None,
    model: str | None = None,
    tokens_input: int = 0,
    tokens_output: int = 0,
    tokens_embeddings: int = 0,
    units_images: int = 0,
    units_web: int = 0,
    estimated_cost: Decimal | int | str = 0,
) -> UsageRecord:
    total_tokens = int(tokens_input or 0) + int(tokens_output or 0) + int(tokens_embeddings or 0)
    row = UsageRecord(
        user_id=user.id,
        project_id=project_id,
        chat_id=chat_id,
        message_id=message_id,
        operation=operation,
        provider=provider,
        model=model,
        tokens_input=max(0, int(tokens_input or 0)),
        tokens_output=max(0, int(tokens_output or 0)),
        tokens_embeddings=max(0, int(tokens_embeddings or 0)),
        units_images=max(0, int(units_images or 0)),
        units_web=max(0, int(units_web or 0)),
        total_tokens=max(0, total_tokens),
        estimated_cost=Decimal(str(estimated_cost or 0)),
        currency="RUB",
        period_month=current_period_month(),
        created_at=datetime.now(UTC),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
