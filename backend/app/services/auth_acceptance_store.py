"""File-based storage for legal acceptance (MVP)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID


_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_STORE_PATH = _PROJECT_ROOT / "storage" / "auth_acceptance.json"


def _load_store() -> dict:
    if not _STORE_PATH.exists():
        return {}
    try:
        return json.loads(_STORE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_store(data: dict) -> None:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STORE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def mark_terms_accepted(user_id: str) -> str:
    """Persist terms acceptance server-side and return ISO UTC timestamp."""
    accepted_at = datetime.now(timezone.utc).isoformat()
    data = _load_store()
    data[user_id] = {
        "accepted_terms": True,
        "accepted_at": accepted_at,
    }
    _save_store(data)
    return accepted_at


def mark_terms_accepted_db(
    db,
    user_id: str,
    *,
    terms_version: str = "2026-04-29",
    privacy_version: str = "2026-04-29",
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> str:
    """Persist terms acceptance in the database and return ISO UTC timestamp."""
    from app.models.billing import LegalAcceptance

    existing = (
        db.query(LegalAcceptance)
        .filter(
            LegalAcceptance.user_id == UUID(str(user_id)),
            LegalAcceptance.terms_version == terms_version,
            LegalAcceptance.privacy_version == privacy_version,
        )
        .order_by(LegalAcceptance.accepted_at.desc())
        .first()
    )
    if existing is not None:
        return accepted_at_to_iso(existing.accepted_at)

    accepted_at_dt = datetime.now(timezone.utc)
    row = LegalAcceptance(
        user_id=UUID(str(user_id)),
        terms_version=terms_version,
        privacy_version=privacy_version,
        accepted_at=accepted_at_dt,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(row)
    db.commit()
    return accepted_at_to_iso(accepted_at_dt)


def accepted_at_to_iso(value: datetime) -> str:
    return value.replace(tzinfo=timezone.utc).isoformat() if value.tzinfo is None else value.isoformat()
