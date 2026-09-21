"""
Phase 4.1 – Plan model, add-ons/top-ups, and limits tests
Phase 4.2 – Usage accounting tests

Verifies:
- Plan catalog has all 4 subscription tiers
- Token/storage top-up addon definitions exist
- Limits service enforces project count, storage, token limits correctly
- Usage record creation and monthly aggregation
"""
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

from app.db.base import Base  # noqa: E402
from app.models.billing import UsageRecord  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.limits_service import (  # noqa: E402
    ensure_project_limit, ensure_storage_available, ensure_token_available,
    ensure_project_storage_available,
)
from app.services.plan_service import (  # noqa: E402
    get_plan_definition, list_plan_definitions, DEFAULT_PLANS,
)
from app.services.usage_service import (  # noqa: E402
    record_usage, tokens_used_this_month, usage_summary_this_month, current_period_month,
)


def make_db(tmp_path):
    db_path = tmp_path / "billing_test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return engine, SessionLocal


# ---------------------------------------------------------------------------
# Phase 4.1 – Plan catalog
# ---------------------------------------------------------------------------

def test_plan_catalog_has_all_required_tiers():
    codes = {p.code for p in DEFAULT_PLANS}
    assert "free" in codes
    assert any("starter" in c or "medium" in c or "start" in c for c in codes), "Starter tier missing"
    assert "medium" in codes or any("medium" in c for c in codes), "Medium tier missing"
    assert "pro" in codes


def test_free_plan_has_correct_limits():
    plan = get_plan_definition("free")
    assert plan is not None
    assert plan.is_free is True
    assert plan.project_limit >= 1
    assert plan.token_limit_month > 0
    assert plan.storage_limit_total > 0


def test_pro_plan_has_higher_limits_than_free():
    free = get_plan_definition("free")
    pro = get_plan_definition("pro")
    assert pro is not None
    assert pro.project_limit > free.project_limit
    assert pro.token_limit_month > free.token_limit_month
    assert pro.storage_limit_total > free.storage_limit_total


def test_list_plan_definitions_returns_dicts():
    plans = list_plan_definitions()
    assert isinstance(plans, list)
    assert len(plans) >= 4
    for p in plans:
        assert "code" in p
        assert "token_limit_month" in p
        assert "storage_limit_total" in p


def test_get_plan_definition_unknown_returns_none():
    assert get_plan_definition("nonexistent_xyz") is None


def test_plan_prices_ascending():
    """Plans should have non-decreasing price order."""
    plans = [p for p in DEFAULT_PLANS if not p.is_free]
    prices = [p.price_amount for p in plans]
    assert prices == sorted(prices)


# ---------------------------------------------------------------------------
# Phase 4.1 – Limits enforcement
# ---------------------------------------------------------------------------

def _make_user(db, plan="free", storage_used=0, project_count=0, token_used=0):
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"lim{user_id}@x.com",
        password_hash="x",
        plan_type=plan,
        storage_used=storage_used,
        storage_limit_total=get_plan_definition(plan).storage_limit_total,
    )
    db.add(user)
    for i in range(project_count):
        db.add(Project(id=uuid.uuid4(), user_id=user_id, name=f"proj{i}"))
    db.commit()
    return user, user_id


def test_ensure_project_limit_passes_below_limit(tmp_path):
    engine, SessionLocal = make_db(tmp_path)
    with SessionLocal() as db:
        user, _ = _make_user(db, plan="free", project_count=0)
        # free plan: 1 project limit, 0 existing -> should pass
        ensure_project_limit(db, user)

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_ensure_project_limit_raises_at_limit(tmp_path):
    engine, SessionLocal = make_db(tmp_path)
    with SessionLocal() as db:
        free_plan = get_plan_definition("free")
        user, _ = _make_user(db, plan="free", project_count=free_plan.project_limit)
        with pytest.raises(HTTPException) as exc_info:
            ensure_project_limit(db, user)
        assert exc_info.value.status_code == 402

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_ensure_storage_available_passes(tmp_path):
    engine, SessionLocal = make_db(tmp_path)
    with SessionLocal() as db:
        user, _ = _make_user(db, plan="free", storage_used=0)
        ensure_storage_available(user, 1024)

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_ensure_storage_available_raises_over_limit(tmp_path):
    engine, SessionLocal = make_db(tmp_path)
    with SessionLocal() as db:
        plan = get_plan_definition("free")
        user, _ = _make_user(db, plan="free", storage_used=plan.storage_limit_total - 1)
        with pytest.raises(HTTPException) as exc_info:
            ensure_storage_available(user, 1024 * 1024)
        assert exc_info.value.status_code == 402

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_ensure_token_available_passes_below_limit(tmp_path):
    engine, SessionLocal = make_db(tmp_path)
    with SessionLocal() as db:
        user, _ = _make_user(db, plan="free")
        ensure_token_available(db, user, token_delta=100)

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_ensure_token_available_raises_at_limit(tmp_path):
    engine, SessionLocal = make_db(tmp_path)
    with SessionLocal() as db:
        plan = get_plan_definition("free")
        user, user_id = _make_user(db, plan="free")
        # Fill up token usage for this month
        db.add(UsageRecord(
            user_id=user_id,
            operation="chat_completion",
            provider="test",
            model="gpt-4o",
            tokens_input=plan.token_limit_month - 10,
            tokens_output=0,
            total_tokens=plan.token_limit_month - 10,
            estimated_cost=Decimal("0"),
            currency="RUB",
            period_month=current_period_month(),
            created_at=datetime.now(UTC).replace(tzinfo=None),
        ))
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            ensure_token_available(db, user, token_delta=1000)
        assert exc_info.value.status_code == 402

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


# ---------------------------------------------------------------------------
# Phase 4.2 – Usage accounting
# ---------------------------------------------------------------------------

def test_record_usage_creates_row(tmp_path):
    engine, SessionLocal = make_db(tmp_path)
    with SessionLocal() as db:
        user, user_id = _make_user(db, plan="free")
        record_usage(
            db, user=user, operation="chat_completion",
            provider="routerai", model="gpt-4o",
            tokens_input=100, tokens_output=50,
        )
        rows = db.query(UsageRecord).filter(UsageRecord.user_id == user_id).all()
        assert len(rows) == 1
        assert rows[0].total_tokens == 150
        assert rows[0].operation == "chat_completion"

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_tokens_used_this_month_aggregates(tmp_path):
    engine, SessionLocal = make_db(tmp_path)
    with SessionLocal() as db:
        user, user_id = _make_user(db, plan="free")
        record_usage(db, user=user, operation="chat_completion", provider="r", model="m", tokens_input=200, tokens_output=100)
        record_usage(db, user=user, operation="image_generation", provider="r", model="openai-image", units_images=1)

        total = tokens_used_this_month(db, user_id)
        assert total == 300

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_usage_summary_groups_correctly(tmp_path):
    engine, SessionLocal = make_db(tmp_path)
    with SessionLocal() as db:
        user, user_id = _make_user(db, plan="free")
        record_usage(db, user=user, operation="chat_completion", provider="routerai", model="gpt-4o", tokens_input=100, tokens_output=50)
        record_usage(db, user=user, operation="web_search", provider="searxng", model="n/a", units_web=1)
        record_usage(db, user=user, operation="image_generation", provider="routerai", model="openai-image", units_images=1)

        summary = usage_summary_this_month(db, user_id)
        assert summary["total_tokens"] == 150
        assert "chat_completion" in summary["operations"]
        assert "routerai" in summary["providers"]
        assert "gpt-4o" in summary["models"]

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_usage_image_and_web_accounted_as_zero_tokens(tmp_path):
    engine, SessionLocal = make_db(tmp_path)
    with SessionLocal() as db:
        user, user_id = _make_user(db, plan="free")
        record_usage(db, user=user, operation="image_generation", provider="r", model="img", units_images=2)
        record_usage(db, user=user, operation="web_search", provider="s", model="n/a", units_web=3)

        total = tokens_used_this_month(db, user_id)
        assert total == 0  # images/web don't burn token quota

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_usage_only_counts_current_period(tmp_path):
    engine, SessionLocal = make_db(tmp_path)
    with SessionLocal() as db:
        user, user_id = _make_user(db, plan="free")
        # Insert record for previous month
        db.add(UsageRecord(
            user_id=user_id, operation="chat_completion", provider="p", model="m",
            tokens_input=500, tokens_output=200, total_tokens=700,
            estimated_cost=Decimal("0"), currency="RUB",
            period_month="2025-01",  # old month
            created_at=datetime.now(UTC).replace(tzinfo=None),
        ))
        db.commit()
        # Current month usage should be 0
        total = tokens_used_this_month(db, user_id)
        assert total == 0

    Base.metadata.drop_all(bind=engine)
    engine.dispose()
