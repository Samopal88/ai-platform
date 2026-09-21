"""Simple signed auth token helpers for MVP email login."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from app.core.config import settings

_ENV = settings.ENVIRONMENT.lower()
_RAW_SECRET = (
    getattr(settings, "AUTH_TOKEN_SECRET", "")
    or getattr(settings, "SECRET_KEY", "")
    or ""
).strip()
_DEV_FALLBACK_SECRET = "dev-insecure-auth-secret"
if _ENV in {"production", "prod"}:
    if not _RAW_SECRET:
        raise RuntimeError("AUTH_TOKEN_SECRET or SECRET_KEY is required in production")
    if _RAW_SECRET == _DEV_FALLBACK_SECRET:
        raise RuntimeError("Production must not use the dev-insecure auth secret")
_SECRET = (_RAW_SECRET or _DEV_FALLBACK_SECRET).encode("utf-8")
_DEFAULT_TTL_SECONDS = int(getattr(settings, "AUTH_TOKEN_TTL_SECONDS", 60 * 60 * 24 * 30))
_FUTURE_SKEW_SECONDS = 300


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def create_auth_token(
    user_id: str,
    email: str,
    ttl_seconds: int | None = None,
    token_type: str = "access",
) -> str:
    now = int(time.time())
    ttl = _DEFAULT_TTL_SECONDS if ttl_seconds is None else int(ttl_seconds)
    payload = {
        "uid": user_id,
        "email": (email or "").strip().lower(),
        "typ": token_type,
        "iat": now,
        "exp": now + ttl,
    }
    payload_raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    payload_part = _b64url_encode(payload_raw)
    sig = hmac.new(_SECRET, payload_part.encode("ascii"), hashlib.sha256).digest()
    sig_part = _b64url_encode(sig)
    return f"{payload_part}.{sig_part}"


def verify_auth_token(token: str, expected_token_type: str = "access") -> dict[str, Any] | None:
    try:
        payload_part, sig_part = token.split(".", 1)
    except ValueError:
        return None

    expected_sig = hmac.new(_SECRET, payload_part.encode("ascii"), hashlib.sha256).digest()
    try:
        provided_sig = _b64url_decode(sig_part)
    except Exception:
        return None

    if not hmac.compare_digest(expected_sig, provided_sig):
        return None

    try:
        payload = json.loads(_b64url_decode(payload_part).decode("utf-8"))
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None
    uid = payload.get("uid")
    email = payload.get("email")
    token_type = payload.get("typ")
    iat = payload.get("iat")
    if not uid or not isinstance(uid, str):
        return None
    if token_type != expected_token_type:
        return None
    try:
        issued_at = int(iat)
    except Exception:
        return None
    if issued_at > int(time.time()) + _FUTURE_SKEW_SECONDS:
        return None
    exp = payload.get("exp")
    if exp is not None:
        try:
            if int(exp) < int(time.time()):
                return None
        except Exception:
            return None
    if not isinstance(email, str):
        payload["email"] = ""
    return payload
