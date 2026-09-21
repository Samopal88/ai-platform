"""Billing endpoints for YooKassa-backed paid plans."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.auth_deps import get_current_user
from app.core.config import settings
from app.db.session import SessionLocal, get_db
from app.models.billing import Payment, Plan, Subscription
from app.models.user import User
from app.services.plan_service import get_plan_definition
from app.services.usage_service import current_period_month, tokens_used_this_month, usage_summary_this_month
from app.services.yookassa_service import (
    YooKassaNotConfigured,
    create_payment,
    verify_webhook_secret,
    webhook_secret_configured,
)

router = APIRouter(prefix="/api/billing", tags=["Billing"])


class CheckoutRequest(BaseModel):
    plan_code: str


def _webhook_secret_from_request(request: Request) -> str | None:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[len("Bearer "):].strip()
    return request.headers.get("X-AI-Platform-Webhook-Secret")


def _latest_subscription(db: Session, user_id) -> Subscription | None:
    return (
        db.query(Subscription)
        .filter(Subscription.user_id == user_id)
        .order_by(Subscription.created_at.desc())
        .first()
    )


def _get_or_create_plan(db: Session, plan_code: str) -> Plan:
    plan_def = get_plan_definition(plan_code)
    if plan_def is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    plan = db.query(Plan).filter(Plan.code == plan_def.code).first()
    if plan is None:
        plan = Plan(
            code=plan_def.code,
            name=plan_def.name,
            project_limit=plan_def.project_limit,
            storage_limit_total=plan_def.storage_limit_total,
            storage_limit_per_project=plan_def.storage_limit_per_project,
            token_limit_month=plan_def.token_limit_month,
            price_amount=Decimal(str(plan_def.price_amount)),
            price_currency=plan_def.price_currency,
            is_active=True,
        )
        db.add(plan)
        db.flush()
    return plan


def _activate_subscription(db: Session, payment: Payment, plan_code: str) -> None:
    plan = _get_or_create_plan(db, plan_code)
    user = db.query(User).filter(User.id == payment.user_id).first()
    if user is None:
        return

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    period_end = now + timedelta(days=30)
    user.plan_type = plan_code

    subscription = (
        db.query(Subscription)
        .filter(Subscription.user_id == user.id, Subscription.provider == "yookassa")
        .order_by(Subscription.created_at.desc())
        .first()
    )
    if subscription is None:
        subscription = Subscription(
            user_id=user.id,
            plan_id=plan.id,
            provider="yookassa",
            status="active",
            current_period_start=now,
            current_period_end=period_end,
        )
        db.add(subscription)
    else:
        subscription.plan_id = plan.id
        subscription.status = "active"
        subscription.current_period_start = now
        subscription.current_period_end = period_end


@router.post("/checkout")
def create_checkout(
    data: CheckoutRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plan = get_plan_definition(data.plan_code)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    if plan.is_free or plan.price_amount <= 0:
        raise HTTPException(status_code=422, detail="Free plan does not require checkout")

    existing_pending = (
        db.query(Payment)
        .filter(
            Payment.user_id == current_user.id,
            Payment.provider == "yookassa",
            Payment.kind == "subscription",
            Payment.status.in_(["pending", "waiting_for_capture"]),
        )
        .order_by(Payment.created_at.desc())
        .first()
    )
    if existing_pending and (existing_pending.payment_metadata or {}).get("plan_code") == plan.code:
        return {
            "payment_id": str(existing_pending.id),
            "provider_payment_id": existing_pending.provider_payment_id,
            "status": existing_pending.status,
            "confirmation_url": (existing_pending.payment_metadata or {}).get("confirmation_url"),
            "reused_pending_payment": True,
        }

    return_url = settings.YOOKASSA_RETURN_URL or f"{settings.PUBLIC_BASE_URL}/chat"
    idempotency_key = str(uuid4())
    payment = Payment(
        user_id=current_user.id,
        provider="yookassa",
        kind="subscription",
        status="pending",
        amount=Decimal(str(plan.price_amount)),
        currency="RUB",
        payment_metadata={"plan_code": plan.code},
        idempotency_key=idempotency_key,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)

    try:
        result = create_payment(
            amount=Decimal(str(plan.price_amount)),
            description=f"AI Platform: тариф {plan.name}",
            return_url=return_url,
            metadata={"user_id": str(current_user.id), "plan_code": plan.code, "payment_id": str(payment.id)},
            idempotency_key=idempotency_key,
        )
    except YooKassaNotConfigured as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))

    payment.provider_payment_id = result.get("id")
    payment.status = result.get("status") or "pending"
    payment_meta = dict(payment.payment_metadata or {})
    payment_meta["confirmation_url"] = (result.get("confirmation") or {}).get("confirmation_url")
    payment.payment_metadata = payment_meta
    db.commit()

    confirmation = result.get("confirmation") or {}
    return {
        "payment_id": str(payment.id),
        "provider_payment_id": payment.provider_payment_id,
        "status": payment.status,
        "confirmation_url": confirmation.get("confirmation_url"),
        "reused_pending_payment": False,
    }


@router.get("/me")
def billing_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plan = get_plan_definition(current_user.plan_type) or get_plan_definition("free")
    used_tokens = tokens_used_this_month(db, current_user.id)
    subscription = _latest_subscription(db, current_user.id)
    recent_payments = (
        db.query(Payment)
        .filter(Payment.user_id == current_user.id)
        .order_by(Payment.created_at.desc())
        .limit(10)
        .all()
    )
    return {
        "plan": asdict(plan) if plan else None,
        "usage": {
            "period_month": current_period_month(),
            "tokens_used": used_tokens,
            "tokens_limit": plan.token_limit_month if plan else 0,
            "tokens_remaining": max(0, (plan.token_limit_month if plan else 0) - used_tokens),
            "storage_used": current_user.storage_used or 0,
            "storage_limit": plan.storage_limit_total if plan else 0,
        },
        "usage_summary": usage_summary_this_month(db, current_user.id),
        "subscription": None if subscription is None else {
            "id": str(subscription.id),
            "status": subscription.status,
            "provider": subscription.provider,
            "current_period_start": subscription.current_period_start.isoformat() if subscription.current_period_start else None,
            "current_period_end": subscription.current_period_end.isoformat() if subscription.current_period_end else None,
            "cancel_at_period_end": subscription.cancel_at_period_end,
        },
        "payments": [
            {
                "id": str(payment.id),
                "provider": payment.provider,
                "provider_payment_id": payment.provider_payment_id,
                "kind": payment.kind,
                "status": payment.status,
                "amount": float(payment.amount),
                "currency": payment.currency,
                "created_at": payment.created_at.isoformat() if payment.created_at else None,
            }
            for payment in recent_payments
        ],
        "provider_status": {
            "yookassa_configured": bool(settings.YOOKASSA_SHOP_ID and settings.YOOKASSA_SECRET_KEY),
            "webhook_secret_configured": webhook_secret_configured(),
        },
    }


@router.post("/yookassa/webhook")
async def yookassa_webhook(request: Request):
    if not verify_webhook_secret(_webhook_secret_from_request(request)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook secret")

    payload = await request.json()
    event = payload.get("event")
    payment_object = payload.get("object") or {}
    provider_payment_id = payment_object.get("id")
    payment_status = payment_object.get("status")
    metadata = payment_object.get("metadata") or {}

    if not provider_payment_id:
        raise HTTPException(status_code=422, detail="Missing payment id")

    db = SessionLocal()
    try:
        payment = (
            db.query(Payment)
            .filter(Payment.provider == "yookassa", Payment.provider_payment_id == provider_payment_id)
            .first()
        )
        if payment is None:
            local_payment_id = metadata.get("payment_id")
            if local_payment_id:
                try:
                    payment = db.query(Payment).filter(Payment.id == UUID(local_payment_id)).first()
                except ValueError:
                    payment = None
        if payment is None:
            return {"ok": True, "ignored": True}

        if payment.status == "succeeded":
            return {"ok": True, "status": payment.status}

        payment.provider_payment_id = provider_payment_id
        payment.status = payment_status or "pending"
        payment_metadata = dict(payment.payment_metadata or {})
        payment_metadata.update(metadata)
        payment_metadata["event"] = event
        payment.payment_metadata = payment_metadata

        plan_code = payment_metadata.get("plan_code")
        if payment.status == "succeeded" and plan_code:
            _activate_subscription(db, payment, plan_code)

        db.commit()
        return {"ok": True, "status": payment.status}
    finally:
        db.close()
