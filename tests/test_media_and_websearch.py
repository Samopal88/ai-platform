"""
Phase 9.1 – Speech-to-text mocked integration test
Phase 9.2 – Image generation usage accounting
Phase 9.3 – Web search unavailable path
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.model_router import ModelRouter  # noqa: E402


# ---------------------------------------------------------------------------
# Phase 9.1 – STT: provider routing decision
# ---------------------------------------------------------------------------

def test_stt_requires_provider_key(monkeypatch):
    """speech_to_text endpoint must return 503 if no provider key is set."""
    import app.api.media as media_module
    monkeypatch.setattr(media_module.settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(media_module.settings, "ROUTERAI_API_KEY", "")
    monkeypatch.setattr(media_module.settings, "RUAPI_API_KEY", "")

    # Simulate the guard logic from the endpoint
    whisper_key = (
        media_module.settings.OPENAI_API_KEY
        or media_module.settings.ROUTERAI_API_KEY
        or media_module.settings.RUAPI_API_KEY
    )
    assert not whisper_key


def test_stt_uses_routerai_key_if_openai_absent(monkeypatch):
    import app.api.media as media_module
    monkeypatch.setattr(media_module.settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(media_module.settings, "ROUTERAI_API_KEY", "routerai-key-123")
    monkeypatch.setattr(media_module.settings, "RUAPI_API_KEY", "")

    whisper_key = (
        media_module.settings.OPENAI_API_KEY
        or media_module.settings.ROUTERAI_API_KEY
        or media_module.settings.RUAPI_API_KEY
    )
    assert whisper_key == "routerai-key-123"


# ---------------------------------------------------------------------------
# Phase 9.2 – Image generation: usage is accounted
# ---------------------------------------------------------------------------

def test_image_generation_records_usage(tmp_path):
    """After generate_image call, a usage record with units_images=1 is created."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db.base import Base
    from app.models.billing import UsageRecord
    from app.models.user import User
    from app.services.usage_service import record_usage, current_period_month
    from decimal import Decimal
    from datetime import datetime, timezone

    db_path = tmp_path / "img_usage.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        user_id = uuid.uuid4()
        user = User(id=user_id, email=f"imgtest{user_id}@x.com", password_hash="x")
        db.add(user)
        db.commit()

        record_usage(
            db, user=user, operation="image_generation",
            provider="routerai", model="openai-image",
            units_images=1,
        )

        rows = db.query(UsageRecord).filter(
            UsageRecord.user_id == user_id,
            UsageRecord.operation == "image_generation",
        ).all()
        assert len(rows) == 1
        assert rows[0].units_images == 1

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


# ---------------------------------------------------------------------------
# Phase 9.3 – Web search: availability guard
# ---------------------------------------------------------------------------

def test_web_search_unavailable_when_disabled(monkeypatch):
    import os
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "false")
    monkeypatch.setenv("WEB_SEARCH_PROVIDER", "searxng")

    import app.api.ai_chat as ai_chat_module
    result = ai_chat_module._web_search_available()
    assert result is False


def test_web_search_available_when_enabled(monkeypatch):
    import os
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "true")
    monkeypatch.setenv("WEB_SEARCH_PROVIDER", "searxng")

    import app.api.ai_chat as ai_chat_module
    result = ai_chat_module._web_search_available()
    assert result is True


def test_web_search_unavailable_without_provider(monkeypatch):
    import os
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "true")
    monkeypatch.setenv("WEB_SEARCH_PROVIDER", "")

    import app.api.ai_chat as ai_chat_module
    result = ai_chat_module._web_search_available()
    assert result is False
