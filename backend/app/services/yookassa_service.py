"""Minimal YooKassa integration wrapper."""
from __future__ import annotations

import uuid
from decimal import Decimal

import requests

from app.core.config import settings


YOOKASSA_API = "https://api.yookassa.ru/v3"


class YooKassaNotConfigured(RuntimeError):
    pass


def ensure_yookassa_configured() -> None:
    if not settings.YOOKASSA_SHOP_ID or not settings.YOOKASSA_SECRET_KEY:
        raise YooKassaNotConfigured("YooKassa credentials are not configured")


def webhook_secret_configured() -> bool:
    return bool((settings.YOOKASSA_WEBHOOK_SECRET or "").strip())


def verify_webhook_secret(provided_secret: str | None) -> bool:
    expected = (settings.YOOKASSA_WEBHOOK_SECRET or "").strip()
    if not expected:
        return True
    return bool(provided_secret and provided_secret.strip() == expected)


def create_payment(
    *,
    amount: Decimal,
    description: str,
    return_url: str,
    metadata: dict,
    idempotency_key: str | None = None,
) -> dict:
    ensure_yookassa_configured()
    key = idempotency_key or str(uuid.uuid4())
    payload = {
        "amount": {
            "value": f"{amount:.2f}",
            "currency": "RUB",
        },
        "confirmation": {
            "type": "redirect",
            "return_url": return_url,
        },
        "capture": True,
        "description": description[:128],
        "metadata": metadata,
    }
    response = requests.post(
        f"{YOOKASSA_API}/payments",
        json=payload,
        auth=(settings.YOOKASSA_SHOP_ID, settings.YOOKASSA_SECRET_KEY),
        headers={"Idempotence-Key": key},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()
