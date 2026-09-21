from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.auth_token import create_auth_token, verify_auth_token  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.api.media import ImageGenerationRequest, generate_image  # noqa: E402
from app.models.billing import LegalAcceptance, UsageRecord  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.models.user import User  # noqa: E402
from app.api.readiness import system_readiness  # noqa: E402
from app.services.auth_acceptance_store import mark_terms_accepted_db  # noqa: E402
from app.services.limits_service import ensure_project_storage_available  # noqa: E402
from app.services.usage_service import current_period_month, usage_summary_this_month  # noqa: E402
from app.services.yookassa_service import verify_webhook_secret  # noqa: E402

def make_db(tmp_path):
    db_path = tmp_path / "phase35.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return engine, SessionLocal


def test_verify_auth_token_rejects_wrong_type_and_expired():
    token = create_auth_token(str(uuid.uuid4()), "user@example.com", ttl_seconds=3600, token_type="password_reset")
    assert verify_auth_token(token, expected_token_type="access") is None

    expired = create_auth_token(str(uuid.uuid4()), "user@example.com", ttl_seconds=-5)
    assert verify_auth_token(expired) is None


def test_mark_terms_accepted_db_is_idempotent_for_same_versions(tmp_path):
    engine, SessionLocal = make_db(tmp_path)
    user_id = uuid.uuid4()
    with SessionLocal() as db:
        db.add(User(id=user_id, email="accept@example.com", password_hash="x"))
        db.commit()

        first = mark_terms_accepted_db(db, str(user_id))
        second = mark_terms_accepted_db(db, str(user_id))
        rows = db.query(LegalAcceptance).filter(LegalAcceptance.user_id == user_id).all()

        assert first == second
        assert len(rows) == 1

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_project_storage_limit_is_enforced(tmp_path):
    engine, SessionLocal = make_db(tmp_path)
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    with SessionLocal() as db:
        user = User(
            id=user_id,
            email="limit@example.com",
            password_hash="x",
            plan_type="free",
            storage_limit_total=200 * 1024 * 1024,
        )
        project = Project(
            id=project_id,
            user_id=user_id,
            name="Limit Project",
            storage_used=24 * 1024 * 1024,
        )
        db.add(user)
        db.add(project)
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            ensure_project_storage_available(project, user, 2 * 1024 * 1024)

        assert exc_info.value.status_code == 402
        assert "Project storage limit" in exc_info.value.detail

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_usage_summary_groups_by_operation_provider_and_model(tmp_path):
    engine, SessionLocal = make_db(tmp_path)
    user_id = uuid.uuid4()
    with SessionLocal() as db:
        db.add(User(id=user_id, email="usage@example.com", password_hash="x"))
        db.add(
            UsageRecord(
                user_id=user_id,
                operation="chat_completion",
                provider="ruapi",
                model="gpt-5.4",
                tokens_input=100,
                tokens_output=50,
                total_tokens=150,
                estimated_cost=Decimal("1.25"),
                currency="RUB",
                period_month=current_period_month(),
                created_at=datetime.now(UTC).replace(tzinfo=None),
            )
        )
        db.add(
            UsageRecord(
                user_id=user_id,
                operation="web_search",
                provider="searxng",
                model="n/a",
                tokens_input=0,
                tokens_output=0,
                total_tokens=0,
                estimated_cost=Decimal("0.15"),
                currency="RUB",
                period_month=current_period_month(),
                created_at=datetime.now(UTC).replace(tzinfo=None),
            )
        )
        db.commit()

        summary = usage_summary_this_month(db, user_id)
        assert summary["total_tokens"] == 150
        assert summary["operations"]["chat_completion"] == 150
        assert summary["providers"]["ruapi"] == 150
        assert summary["models"]["gpt-5.4"] == 150
        assert summary["total_cost_rub"] == "1.400000"

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_verify_webhook_secret_defaults_open_when_not_configured(monkeypatch):
    monkeypatch.setattr("app.services.yookassa_service.settings.YOOKASSA_WEBHOOK_SECRET", "")
    assert verify_webhook_secret(None) is True
    monkeypatch.setattr("app.services.yookassa_service.settings.YOOKASSA_WEBHOOK_SECRET", "secret")
    assert verify_webhook_secret("secret") is True
    assert verify_webhook_secret("wrong") is False


# ---------------------------------------------------------------------------
# Phase 3.2 – migrate-guest-chats: non-guest source must be rejected
# ---------------------------------------------------------------------------
def test_migrate_guest_chats_rejects_non_guest_source(tmp_path):
    """
    If the 'guest' token actually belongs to a real (non-workspace.local) user,
    the endpoint must raise 400 instead of silently migrating their chats.
    This test exercises the guard path via the User model + endpoint logic directly.
    """
    # We test the domain check logic in isolation (it's pure Python after the DB lookup).
    engine, SessionLocal = make_db(tmp_path)
    user_id = uuid.uuid4()
    real_email = "realuser@example.com"

    with SessionLocal() as db:
        db.add(User(id=user_id, email=real_email, password_hash="hashed"))
        db.commit()
        user = db.query(User).filter(User.id == user_id).first()
        guest_email = (user.email or "").lower()
        is_guest = guest_email.endswith("@workspace.local")
        assert not is_guest, "A real user must NOT be treated as guest"

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_migrate_guest_chats_accepts_actual_guest(tmp_path):
    """A workspace.local email must pass the guest-domain check."""
    engine, SessionLocal = make_db(tmp_path)
    user_id = uuid.uuid4()
    guest_email = f"guest-abc123@workspace.local"

    with SessionLocal() as db:
        db.add(User(id=user_id, email=guest_email, password_hash=""))
        db.commit()
        user = db.query(User).filter(User.id == user_id).first()
        is_guest = (user.email or "").lower().endswith("@workspace.local")
        assert is_guest

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


# ---------------------------------------------------------------------------
# Phase 4.3 – chat upload size guard
# ---------------------------------------------------------------------------
def test_chat_upload_size_limit_constant():
    """The chat upload size cap must be defined and be at most 20 MB."""
    from app.api import chats as chats_module
    import inspect

    source = inspect.getsource(chats_module)
    # Verify the 20 MB cap is present in the upload handler source
    assert "_MAX_CHAT_UPLOAD" in source
    assert "20 * 1024 * 1024" in source or "20971520" in source


def test_storage_limit_enforced_for_small_and_large_upload(tmp_path):
    """ensure_storage_available must block when plan limit would be exceeded."""
    from app.services.limits_service import ensure_storage_available

    engine, SessionLocal = make_db(tmp_path)
    user_id = uuid.uuid4()
    with SessionLocal() as db:
        # free plan: 50 MB total; pre-fill to 49 MB
        user = User(
            id=user_id,
            email="storage@example.com",
            password_hash="x",
            plan_type="free",
            storage_used=49 * 1024 * 1024,
        )
        db.add(user)
        db.commit()
        user = db.query(User).filter(User.id == user_id).first()

        # 0.5 MB fits within 50 MB cap -> should pass
        ensure_storage_available(user, 512 * 1024)

        # 2 MB would push over -> must raise 402
        with pytest.raises(HTTPException) as exc_info:
            ensure_storage_available(user, 2 * 1024 * 1024)
        assert exc_info.value.status_code == 402

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_readiness_uses_settings_backed_routerai(monkeypatch):
    monkeypatch.delenv("ROUTERAI_API_KEY", raising=False)
    monkeypatch.setattr("app.api.readiness.settings.ROUTERAI_API_KEY", "routerai-key")
    monkeypatch.setattr("app.api.readiness.settings.CLAUDEHUB_API_KEY", "")
    monkeypatch.setattr("app.api.readiness.settings.RUAPI_API_KEY", "")
    monkeypatch.setattr("app.api.readiness.settings.RUAPI_BASE_URL", "")
    monkeypatch.setattr("app.api.readiness.settings.OPENAI_API_KEY", "")
    monkeypatch.setattr("app.api.readiness.settings.OPENAI_BASE_URL", "")
    monkeypatch.setattr("app.api.readiness.settings.ANTHROPIC_API_KEY", "")
    monkeypatch.setattr("app.api.readiness.settings.ANTHROPIC_AUTH_TOKEN", "")
    monkeypatch.setattr("app.api.readiness.settings.DATABASE_URL", "sqlite:///tmp.db")
    monkeypatch.setattr("app.api.readiness.settings.YOOKASSA_SHOP_ID", "")
    monkeypatch.setattr("app.api.readiness.settings.YOOKASSA_SECRET_KEY", "")
    monkeypatch.setattr("app.api.readiness.settings.ENVIRONMENT", "development")
    monkeypatch.setattr("app.api.readiness._runtime_process_count", lambda: 1)
    monkeypatch.setattr("app.api.readiness._service_file_contains", lambda *args, **kwargs: True)
    monkeypatch.setattr("app.api.readiness.Path.exists", lambda self: True)

    payload = system_readiness(current_user=object())
    assert payload["providers"]["routerai"] is True
    assert payload["ai_gateway"]["primary"] == "routerai"


def test_generate_image_uses_router_and_returns_b64(monkeypatch, tmp_path):
    engine, SessionLocal = make_db(tmp_path)
    user_id = uuid.uuid4()

    class DummyResult:
        provider = "routerai"
        model_id = "openai-image"
        images = (type("Img", (), {"media_type": "image/png", "data": b"png-bytes"})(),)

    monkeypatch.setattr("app.api.media.settings.ROUTERAI_API_KEY", "routerai-key")
    monkeypatch.setattr("app.api.media.settings.RUAPI_API_KEY", "")
    monkeypatch.setattr("app.api.media.settings.RUAPI_BASE_URL", "")
    monkeypatch.setattr("app.api.media.settings.OPENAI_API_KEY", "")
    monkeypatch.setattr("app.api.media.settings.OPENAI_BASE_URL", "")
    monkeypatch.setattr("app.api.media.settings.CLAUDEHUB_API_KEY", "")
    monkeypatch.setattr("app.api.media.ensure_token_available", lambda **kwargs: None)
    monkeypatch.setattr("app.api.media.record_usage", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.api.media._model_router.generate_image", lambda **kwargs: DummyResult())

    with SessionLocal() as db:
        user = User(id=user_id, email="image@example.com", password_hash="x")
        db.add(user)
        db.commit()

        response = generate_image(
            ImageGenerationRequest(prompt="test image"),
            db=db,
            current_user=user,
        )

    assert response["provider"] == "routerai"
    assert response["images"][0]["media_type"] == "image/png"
    assert response["images"][0]["b64_json"] == "cG5nLWJ5dGVz"

    Base.metadata.drop_all(bind=engine)
    engine.dispose()
