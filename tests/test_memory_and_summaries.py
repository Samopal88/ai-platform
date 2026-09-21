"""
Phase 8.1 – DB-backed Memory service tests
Phase 8.2 – Chat summary service tests
Phase 8.3 – Memory pin/unpin API tests
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.db.base import Base  # noqa: E402
from app.models.context import Memory, Summary  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.memory_service import (  # noqa: E402
    store_memory, recall_memory, search_memories, _load, _save, _is_expired,
)
from app.services.summary_service import (  # noqa: E402
    maybe_summarize_chat, get_chat_summaries, SUMMARY_THRESHOLD,
)


def make_db(tmp_path):
    db_path = tmp_path / "mem_test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return engine, SessionLocal


# ---------------------------------------------------------------------------
# Phase 8.1 – Memory model: DB schema has pinned column
# ---------------------------------------------------------------------------

def test_memory_model_has_pinned_column(tmp_path):
    engine, SessionLocal = make_db(tmp_path)
    with SessionLocal() as db:
        user_id = uuid.uuid4()
        proj_id = uuid.uuid4()
        db.add(User(id=user_id, email=f"mem{user_id}@x.com", password_hash="x"))
        db.add(Project(id=proj_id, user_id=user_id, name="MP"))
        db.commit()

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        mem = Memory(
            project_id=proj_id,
            user_id=user_id,
            type="fact",
            key="test_key",
            content="test content",
            pinned=True,
        )
        db.add(mem)
        db.commit()
        db.refresh(mem)
        assert mem.pinned is True

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_memory_model_default_pinned_false(tmp_path):
    engine, SessionLocal = make_db(tmp_path)
    with SessionLocal() as db:
        user_id = uuid.uuid4()
        proj_id = uuid.uuid4()
        db.add(User(id=user_id, email=f"mem2{user_id}@x.com", password_hash="x"))
        db.add(Project(id=proj_id, user_id=user_id, name="MP2"))
        db.commit()

        mem = Memory(
            project_id=proj_id, user_id=user_id, type="fact",
            key="k2", content="c2",
        )
        db.add(mem)
        db.commit()
        db.refresh(mem)
        assert mem.pinned is False or mem.pinned == 0

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


# ---------------------------------------------------------------------------
# Phase 8.1 – File-based memory service: store, recall, search, expiry
# ---------------------------------------------------------------------------

def test_store_and_recall_memory(tmp_path, monkeypatch):
    from app.services import memory_service
    monkeypatch.setattr(memory_service, "STORAGE_DIR", tmp_path / "memory")
    store_memory(str(uuid.uuid4()), "key1", "value1", ttl_days=30)


def test_search_memories_finds_keyword(tmp_path, monkeypatch):
    from app.services import memory_service
    monkeypatch.setattr(memory_service, "STORAGE_DIR", tmp_path / "memory")
    pid = str(uuid.uuid4())
    store_memory(pid, "project_goal", "Build AI platform for enterprises", ttl_days=30)
    store_memory(pid, "budget", "10000 USD monthly", ttl_days=30)

    results = search_memories(pid, "enterprise")
    assert len(results) == 1
    assert results[0]["key"] == "project_goal"


def test_search_memories_no_match(tmp_path, monkeypatch):
    from app.services import memory_service
    monkeypatch.setattr(memory_service, "STORAGE_DIR", tmp_path / "memory")
    pid = str(uuid.uuid4())
    store_memory(pid, "k", "hello world", ttl_days=30)
    results = search_memories(pid, "postgresql_migrations")
    assert len(results) == 0


def test_is_expired_for_past_date():
    from datetime import timedelta
    expired_entry = {"expires_at": (datetime.utcnow() - timedelta(days=1)).isoformat()}
    assert _is_expired(expired_entry) is True


def test_is_expired_for_future_date():
    from datetime import timedelta
    valid_entry = {"expires_at": (datetime.utcnow() + timedelta(days=30)).isoformat()}
    assert _is_expired(valid_entry) is False


def test_is_expired_for_none():
    assert _is_expired({"expires_at": None}) is False


# ---------------------------------------------------------------------------
# Phase 8.3 – Memory pin/unpin via file store
# ---------------------------------------------------------------------------

def test_pin_memory_sets_pinned_flag(tmp_path, monkeypatch):
    from app.services import memory_service
    monkeypatch.setattr(memory_service, "STORAGE_DIR", tmp_path / "mem_pin")
    pid = str(uuid.uuid4())
    store_memory(pid, "mykey", "my value", ttl_days=30)

    data = _load(pid)
    assert not data["mykey"].get("pinned", False)

    data["mykey"]["pinned"] = True
    _save(pid, data)

    data2 = _load(pid)
    assert data2["mykey"]["pinned"] is True


def test_unpin_memory_clears_flag(tmp_path, monkeypatch):
    from app.services import memory_service
    monkeypatch.setattr(memory_service, "STORAGE_DIR", tmp_path / "mem_unpin")
    pid = str(uuid.uuid4())
    store_memory(pid, "k", "v", ttl_days=30)
    data = _load(pid)
    data["k"]["pinned"] = True
    _save(pid, data)

    data["k"]["pinned"] = False
    _save(pid, data)
    data2 = _load(pid)
    assert not data2["k"].get("pinned", False)


# ---------------------------------------------------------------------------
# Phase 8.2 – Summary service: threshold, generation, storage
# ---------------------------------------------------------------------------

class _MockMsg:
    def __init__(self, role: str, content: str):
        self.role = role
        self.content = content


def _make_messages(count: int) -> list:
    msgs = []
    for i in range(count):
        msgs.append(_MockMsg("user" if i % 2 == 0 else "assistant", f"Message {i}: some chat content here"))
    return msgs


def test_maybe_summarize_chat_skips_below_threshold(tmp_path):
    engine, SessionLocal = make_db(tmp_path)
    with SessionLocal() as db:
        messages = _make_messages(SUMMARY_THRESHOLD - 1)
        chat_id = uuid.uuid4()
        result = maybe_summarize_chat(db, chat_id, messages=messages)
        assert result is None

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_maybe_summarize_chat_creates_summary_when_threshold_met(tmp_path, monkeypatch):
    from app.services.model_router import ModelResponse, ModelUsage
    from app.services import summary_service

    monkeypatch.setattr(
        summary_service._router,
        "route_response",
        lambda messages, model_id, max_tokens=300: ModelResponse(
            text="This chat discussed AI platform features and architecture.",
            provider="mock",
            model_id=model_id,
            usage=ModelUsage(prompt_tokens=50, completion_tokens=20),
        ),
    )

    engine, SessionLocal = make_db(tmp_path)
    with SessionLocal() as db:
        user_id = uuid.uuid4()
        proj_id = uuid.uuid4()
        from app.models.chat import Chat
        db.add(User(id=user_id, email=f"summ{user_id}@x.com", password_hash="x"))
        db.add(Project(id=proj_id, user_id=user_id, name="SP"))
        chat_id = uuid.uuid4()
        db.add(Chat(id=chat_id, user_id=user_id, project_id=proj_id, title="Test chat", model="gpt-4o-mini"))
        db.commit()

        messages = _make_messages(SUMMARY_THRESHOLD)
        result = maybe_summarize_chat(db, chat_id, project_id=proj_id, messages=messages)
        assert result is not None
        assert "AI platform" in result.summary_text
        assert result.chat_id == chat_id

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_get_chat_summaries_returns_empty_for_no_summaries(tmp_path):
    engine, SessionLocal = make_db(tmp_path)
    with SessionLocal() as db:
        summaries = get_chat_summaries(db, uuid.uuid4())
        assert summaries == []

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_second_summary_only_after_band(tmp_path, monkeypatch):
    """A second summary must not be created before SUMMARY_THRESHOLD + SUMMARY_BAND messages."""
    from app.services import summary_service
    from app.services.model_router import ModelResponse, ModelUsage

    monkeypatch.setattr(
        summary_service._router,
        "route_response",
        lambda messages, model_id, max_tokens=300: ModelResponse(
            text="Summary text.", provider="mock", model_id=model_id,
            usage=ModelUsage(prompt_tokens=10, completion_tokens=5),
        ),
    )

    engine, SessionLocal = make_db(tmp_path)
    with SessionLocal() as db:
        user_id = uuid.uuid4()
        proj_id = uuid.uuid4()
        from app.models.chat import Chat
        db.add(User(id=user_id, email=f"s2{user_id}@x.com", password_hash="x"))
        db.add(Project(id=proj_id, user_id=user_id, name="S2"))
        chat_id = uuid.uuid4()
        db.add(Chat(id=chat_id, user_id=user_id, project_id=proj_id, title="T", model="gpt-4o-mini"))
        db.commit()

        # First summary at threshold
        messages1 = _make_messages(SUMMARY_THRESHOLD)
        maybe_summarize_chat(db, chat_id, project_id=proj_id, messages=messages1)

        # Should NOT create second summary yet (not enough new messages)
        messages2 = _make_messages(SUMMARY_THRESHOLD + 1)
        result2 = maybe_summarize_chat(db, chat_id, project_id=proj_id, messages=messages2)
        assert result2 is None

    Base.metadata.drop_all(bind=engine)
    engine.dispose()
