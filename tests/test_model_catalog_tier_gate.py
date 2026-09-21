"""
Phase 5.1 – Model catalog tier-gating tests
Phase 5.2 – Provider normalization tests

Verifies:
- model_allowed_for_plan enforces tier access correctly
- free plan cannot access starter/pro models
- starter plan can access starter/free but not pro
- medium/pro plans can access all tiers
- Unknown models are allowed (pass-through)
- model_has_capability returns correct capability flags
- list_models returns catalog with required fields
- get_model returns correct entry or None
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.model_catalog import (
    model_allowed_for_plan,
    model_has_capability,
    list_models,
    get_model,
    MODEL_CATALOG,
)


# ---------------------------------------------------------------------------
# Phase 5.1 – Tier gate
# ---------------------------------------------------------------------------

def test_free_plan_can_access_free_tier_model():
    # claude-haiku-4.5 is tier=free
    assert model_allowed_for_plan("claude-haiku-4.5", "free") is True


def test_free_plan_cannot_access_starter_tier_model():
    # claude-sonnet-4.6 is tier=starter
    assert model_allowed_for_plan("claude-sonnet-4.6", "free") is False


def test_free_plan_cannot_access_pro_tier_model():
    # claude-opus-4.6 is tier=pro
    assert model_allowed_for_plan("claude-opus-4.6", "free") is False


def test_starter_plan_can_access_free_tier_model():
    assert model_allowed_for_plan("claude-haiku-4.5", "starter") is True


def test_starter_plan_can_access_starter_tier_model():
    assert model_allowed_for_plan("claude-sonnet-4.6", "starter") is True


def test_starter_plan_cannot_access_pro_tier_model():
    assert model_allowed_for_plan("claude-opus-4.6", "starter") is False


def test_pro_plan_can_access_pro_tier_model():
    assert model_allowed_for_plan("claude-opus-4.6", "pro") is True


def test_medium_plan_can_access_pro_tier_model():
    # medium maps to pro effective tier
    assert model_allowed_for_plan("claude-opus-4.6", "medium") is True


def test_unknown_model_always_allowed():
    assert model_allowed_for_plan("some-unknown-model-xyz", "free") is True


def test_starter_490_alias_works():
    # starter_490 is an alias for starter
    assert model_allowed_for_plan("claude-sonnet-4.6", "starter_490") is True
    assert model_allowed_for_plan("claude-opus-4.6", "starter_490") is False


# ---------------------------------------------------------------------------
# Phase 5.2 – Catalog completeness
# ---------------------------------------------------------------------------

def test_list_models_returns_nonempty_list():
    models = list_models()
    assert isinstance(models, list)
    assert len(models) >= 5


def test_all_catalog_entries_have_required_fields():
    for m in MODEL_CATALOG:
        assert "id" in m, f"Missing id in {m}"
        assert "provider" in m, f"Missing provider in {m}"
        assert "capabilities" in m, f"Missing capabilities in {m}"
        assert "tier" in m, f"Missing tier in {m}"
        assert m["tier"] in {"free", "starter", "medium", "pro"}, f"Unknown tier: {m['tier']}"


def test_get_model_returns_correct_entry():
    m = get_model("gpt-4o")
    assert m is not None
    assert m["id"] == "gpt-4o"
    assert "text" in m["capabilities"]


def test_get_model_returns_none_for_unknown():
    assert get_model("nonexistent-xyz-999") is None


def test_model_has_capability_vision():
    assert model_has_capability("claude-opus-4.6", "vision") is True
    assert model_has_capability("deepseek-chat", "vision") is False


def test_model_has_capability_streaming():
    # All catalog models should support streaming
    for m in MODEL_CATALOG:
        assert model_has_capability(m["id"], "streaming"), f"{m['id']} missing streaming"


def test_catalog_has_at_least_one_free_tier_model():
    free_models = [m for m in MODEL_CATALOG if m["tier"] == "free"]
    assert len(free_models) >= 1


def test_catalog_has_at_least_one_pro_tier_model():
    pro_models = [m for m in MODEL_CATALOG if m["tier"] == "pro"]
    assert len(pro_models) >= 1
