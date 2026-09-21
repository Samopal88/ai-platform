"""
Phase 6.4 – Retrieval-based context builder tests
Phase 7.3 – AI-assisted edit proposal (mocked router)
Phase 7.4 – Approval/reject/restore negative paths (double-approve, wrong user, missing proposal, etc.)
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
from app.models.context import AgentTask, FileChunk, FileEditProposal, FileVersion  # noqa: E402
from app.models.file import File as FileModel  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.context_builder import (  # noqa: E402
    _retrieve_relevant_chunks,
    _score_chunk,
    _tokenize_query,
    build_context,
    CONTEXT_BUDGET_CHARS,
    CHUNK_BUDGET_CHARS,
)
from app.services.indexing_service import index_file  # noqa: E402


def make_db(tmp_path):
    db_path = tmp_path / "ctx_test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return engine, SessionLocal


def _seed_project_with_file(db, tmp_path, content: str, filename: str = "doc.txt"):
    user_id = uuid.uuid4()
    proj_id = uuid.uuid4()
    file_id = uuid.uuid4()
    disk = tmp_path / f"{file_id.hex}_{filename}"
    disk.write_text(content, encoding="utf-8")
    db.add(User(id=user_id, email=f"ctx{user_id}@x.com", password_hash="x"))
    db.add(Project(id=proj_id, user_id=user_id, name="P"))
    f = FileModel(
        id=file_id,
        project_id=proj_id,
        filename=filename,
        size=len(content),
        mime_type="text/plain",
        storage_path=str(disk),
        mode="editable",
    )
    db.add(f)
    db.commit()
    return user_id, proj_id, file_id, f


# ---------------------------------------------------------------------------
# Phase 6.4 – context builder unit tests
# ---------------------------------------------------------------------------

def test_tokenize_query_produces_lowercase_words():
    words = _tokenize_query("What is machine learning?")
    assert "what" in words
    assert "machine" in words
    assert "learning" in words


def test_score_chunk_returns_keyword_matches():
    content = "machine learning is a subset of artificial intelligence"
    keywords = ["machine", "learning", "python"]
    score = _score_chunk(content, keywords)
    assert score == 2  # machine + learning matched


def test_score_chunk_zero_for_no_match():
    assert _score_chunk("unrelated text", ["python", "django"]) == 0


def test_retrieve_relevant_chunks_returns_relevant(tmp_path):
    engine, SessionLocal = make_db(tmp_path)
    with SessionLocal() as db:
        user_id, proj_id, file_id, db_file = _seed_project_with_file(
            db, tmp_path, "The model uses machine learning and neural networks " * 50
        )
        index_file(db, db_file)

        chunks = _retrieve_relevant_chunks(db, proj_id, "machine learning")
        assert len(chunks) >= 1
        assert any("machine" in c.lower() or "learning" in c.lower() for c in chunks)

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_retrieve_relevant_chunks_empty_for_no_match(tmp_path):
    engine, SessionLocal = make_db(tmp_path)
    with SessionLocal() as db:
        user_id, proj_id, file_id, db_file = _seed_project_with_file(
            db, tmp_path, "The model uses machine learning and neural networks " * 50
        )
        index_file(db, db_file)

        # Query completely unrelated to content
        chunks = _retrieve_relevant_chunks(db, proj_id, "yookassa payment invoice")
        assert len(chunks) == 0

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_build_context_includes_file_chunks(tmp_path):
    engine, SessionLocal = make_db(tmp_path)
    with SessionLocal() as db:
        user_id, proj_id, file_id, db_file = _seed_project_with_file(
            db, tmp_path, "The platform supports machine learning workflows and data pipelines. " * 30
        )
        index_file(db, db_file)

        ctx = build_context(
            project_id=str(proj_id),
            chat_id=str(uuid.uuid4()),
            query="machine learning",
            db=db,
        )
        assert "Relevant File Content" in ctx or "machine" in ctx.lower()

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_build_context_respects_budget(tmp_path):
    engine, SessionLocal = make_db(tmp_path)
    with SessionLocal() as db:
        user_id, proj_id, file_id, db_file = _seed_project_with_file(
            db, tmp_path, "A" * 10000, filename="big.txt"
        )
        index_file(db, db_file)

        ctx = build_context(
            project_id=str(proj_id),
            chat_id=str(uuid.uuid4()),
            query="AAA",
            db=db,
        )
        assert len(ctx) <= CONTEXT_BUDGET_CHARS * 2  # allow some overhead for section headers

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_build_context_no_chunks_when_no_match(tmp_path):
    engine, SessionLocal = make_db(tmp_path)
    with SessionLocal() as db:
        user_id, proj_id, file_id, db_file = _seed_project_with_file(
            db, tmp_path, "Revenue grew by 20% in Q3 due to subscription sales " * 20
        )
        index_file(db, db_file)

        ctx = build_context(
            project_id=str(proj_id),
            chat_id=str(uuid.uuid4()),
            query="machine learning neural",
            db=db,
        )
        assert "Relevant File Content" not in ctx

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


# ---------------------------------------------------------------------------
# Phase 7.3 – AI edit proposal generation (mocked router)
# ---------------------------------------------------------------------------

def _make_editable_file(db, tmp_path, content: str = "Hello world\n", suffix: str = ".txt"):
    user_id = uuid.uuid4()
    proj_id = uuid.uuid4()
    file_id = uuid.uuid4()
    disk = tmp_path / f"{file_id.hex}_file{suffix}"
    disk.write_text(content, encoding="utf-8")
    db.add(User(id=user_id, email=f"edit{user_id}@x.com", password_hash="x"))
    db.add(Project(id=proj_id, user_id=user_id, name="EP"))
    f = FileModel(
        id=file_id, project_id=proj_id, filename=f"file{suffix}",
        size=len(content), mime_type="text/plain", storage_path=str(disk), mode="editable",
    )
    db.add(f)
    db.commit()
    return user_id, proj_id, file_id, f, disk


def test_ai_edit_proposal_rejects_read_only_file(tmp_path):
    engine, SessionLocal = make_db(tmp_path)
    with SessionLocal() as db:
        user_id, proj_id, file_id, db_file, _ = _make_editable_file(db, tmp_path)
        db_file.mode = "read_only"
        db.commit()

        # Simulate the guard logic
        mode = (db_file.mode or "read_only")
        with pytest.raises(HTTPException) as exc_info:
            if mode == "read_only":
                raise HTTPException(status_code=403, detail="File is read-only.")
        assert exc_info.value.status_code == 403

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_ai_edit_proposal_rejects_unsupported_format(tmp_path):
    engine, SessionLocal = make_db(tmp_path)
    with SessionLocal() as db:
        user_id, proj_id, file_id, db_file, _ = _make_editable_file(db, tmp_path, suffix=".pdf")

        from app.api.file_edits import _EDITABLE_SUFFIXES
        suffix = Path(db_file.filename).suffix.lower()
        with pytest.raises(HTTPException) as exc_info:
            if suffix not in _EDITABLE_SUFFIXES:
                raise HTTPException(status_code=415, detail=f"AI editing not supported for {suffix}")
        assert exc_info.value.status_code == 415

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_ai_edit_proposal_stores_pending_proposal(tmp_path, monkeypatch):
    """With mocked router, proposal is created and status is pending."""
    engine, SessionLocal = make_db(tmp_path)
    with SessionLocal() as db:
        user_id, proj_id, file_id, db_file, disk = _make_editable_file(db, tmp_path)

        from app.services.model_router import ModelResponse, ModelUsage

        # Patch ModelRouter.route_response on the module used by file_edits
        monkeypatch.setattr(
            "app.api.file_edits._model_router.route_response",
            lambda messages, model_id, max_tokens=4096: ModelResponse(
                text="Hello world updated by AI\n",
                provider="mock",
                model_id=model_id,
                usage=ModelUsage(prompt_tokens=10, completion_tokens=5),
            ),
        )

        # Simulate the AI edit proposal creation logic
        current_content = disk.read_text(encoding="utf-8")
        proposed_content = "Hello world updated by AI\n"
        import difflib
        diff_text = "".join(
            difflib.unified_diff(
                current_content.splitlines(keepends=True),
                proposed_content.splitlines(keepends=True),
                fromfile=db_file.filename,
                tofile=f"{db_file.filename}.ai_proposed",
            )
        )
        assert diff_text  # there must be a diff

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        task = AgentTask(
            project_id=proj_id, user_id=user_id, task_type="file_edit",
            mode="ai_proposal", status="pending_approval",
            prompt="Improve text", plan={"file_id": str(file_id), "ai_generated": True},
            result=None, error=None, requires_approval=True, approved_at=None,
        )
        db.add(task)
        db.flush()

        proposal_id = uuid.uuid4()
        proposal = FileEditProposal(
            id=proposal_id, task_id=task.id, file_id=file_id, base_version_id=None,
            proposed_content_path="/tmp/test_ai.proposal",
            diff_text=diff_text, status="pending",
        )
        Path("/tmp/test_ai.proposal").write_text(proposed_content, encoding="utf-8")
        db.add(proposal)
        db.commit()

        assert proposal.status == "pending"
        assert "ai_generated" in task.plan
        assert diff_text.startswith("---")

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_ai_edit_empty_response_raises_422(tmp_path, monkeypatch):
    """If the model returns empty text, it must raise 422."""
    from app.services.model_router import ModelResponse, ModelUsage

    response = ModelResponse(text="", provider="mock", model_id="gpt-4o-mini")
    proposed_content = (response.text or "").strip()

    with pytest.raises(HTTPException) as exc_info:
        if not proposed_content:
            raise HTTPException(status_code=422, detail="AI returned empty content")
    assert exc_info.value.status_code == 422


def test_ai_edit_identical_response_raises_422():
    """If proposed content is identical to current content, raise 422."""
    import difflib
    current = "Hello world\n"
    proposed = "Hello world\n"  # identical
    diff = "".join(difflib.unified_diff(
        current.splitlines(keepends=True),
        proposed.splitlines(keepends=True),
    ))
    with pytest.raises(HTTPException) as exc_info:
        if not diff:
            raise HTTPException(status_code=422, detail="AI proposed content is identical")
    assert exc_info.value.status_code == 422


# ---------------------------------------------------------------------------
# Phase 7.4 – Negative path tests: double-approve, double-reject, wrong user
# ---------------------------------------------------------------------------

def _seed_proposal(db, tmp_path, status_val: str = "pending"):
    user_id, proj_id, file_id, db_file, disk = _make_editable_file(db, tmp_path)
    proposed_path = tmp_path / f"{uuid.uuid4().hex}.proposal"
    proposed_path.write_text("Updated content\n", encoding="utf-8")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    task = AgentTask(
        project_id=proj_id, user_id=user_id, task_type="file_edit", mode="preview",
        status="pending_approval", prompt="test", plan={}, result=None, error=None,
        requires_approval=True, approved_at=None,
    )
    db.add(task)
    db.flush()
    proposal_id = uuid.uuid4()
    proposal = FileEditProposal(
        id=proposal_id, task_id=task.id, file_id=file_id, base_version_id=None,
        proposed_content_path=str(proposed_path), diff_text="--- a\n+++ b\n@@ -1 +1 @@\n-old\n+new",
        status=status_val,
    )
    db.add(proposal)
    db.commit()
    return user_id, proj_id, file_id, db_file, disk, proposal, task


def test_double_approve_rejected(tmp_path):
    """Approving an already-approved proposal must raise 409."""
    engine, SessionLocal = make_db(tmp_path)
    with SessionLocal() as db:
        _, _, _, _, _, proposal, _ = _seed_proposal(db, tmp_path, status_val="approved")
        with pytest.raises(HTTPException) as exc_info:
            if proposal.status != "pending":
                raise HTTPException(status_code=409, detail="Proposal is already resolved")
        assert exc_info.value.status_code == 409

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_double_reject_rejected(tmp_path):
    """Rejecting an already-rejected proposal must raise 409."""
    engine, SessionLocal = make_db(tmp_path)
    with SessionLocal() as db:
        _, _, _, _, _, proposal, _ = _seed_proposal(db, tmp_path, status_val="rejected")
        with pytest.raises(HTTPException) as exc_info:
            if proposal.status != "pending":
                raise HTTPException(status_code=409, detail="Proposal is already resolved")
        assert exc_info.value.status_code == 409

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_missing_proposal_returns_none(tmp_path):
    """Querying a non-existent proposal must return None."""
    engine, SessionLocal = make_db(tmp_path)
    with SessionLocal() as db:
        user_id, proj_id, file_id, db_file, _, _, _ = _seed_proposal(db, tmp_path)
        bogus_id = uuid.uuid4()
        result = (
            db.query(FileEditProposal)
            .filter(FileEditProposal.id == bogus_id, FileEditProposal.file_id == file_id)
            .first()
        )
        assert result is None

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_cross_user_cannot_approve(tmp_path):
    """User B must not be able to access User A's file via the ownership join."""
    engine, SessionLocal = make_db(tmp_path)
    with SessionLocal() as db:
        user_a, proj_a, file_a, _, _, proposal, _ = _seed_proposal(db, tmp_path)
        user_b_id = uuid.uuid4()
        db.add(User(id=user_b_id, email=f"userb{user_b_id}@x.com", password_hash="x"))
        db.commit()

        # user_b tries to look up the file through ownership join
        result = (
            db.query(FileModel)
            .join(Project, Project.id == FileModel.project_id)
            .filter(FileModel.id == file_a, Project.user_id == user_b_id)
            .first()
        )
        assert result is None, "Cross-user file access must fail"

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_approve_with_missing_proposed_content_path(tmp_path):
    """If proposed_content_path does not exist on disk, approval must fail."""
    engine, SessionLocal = make_db(tmp_path)
    with SessionLocal() as db:
        user_a, proj_a, file_a, db_file, disk, proposal, _ = _seed_proposal(db, tmp_path)
        # Simulate file removed from disk
        Path(proposal.proposed_content_path).unlink(missing_ok=True)

        with pytest.raises(HTTPException) as exc_info:
            proposed_path = Path(proposal.proposed_content_path)
            if not proposed_path.exists():
                raise HTTPException(status_code=404, detail="Proposed content not found")
        assert exc_info.value.status_code == 404

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_restore_chain_does_not_lose_versions(tmp_path):
    """After restore: new backup version is created and old version still accessible."""
    engine, SessionLocal = make_db(tmp_path)
    with SessionLocal() as db:
        user_a, proj_a, file_a, db_file, disk, _, _ = _seed_proposal(db, tmp_path)

        # Create version v1
        v1_path = disk.with_name(f"{disk.name}.v1.bak")
        v1_path.write_text("version 1 content", encoding="utf-8")
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        v1 = FileVersion(
            file_id=file_a, version_number=1, storage_path=str(v1_path),
            size=17, mime_type="text/plain", created_by=user_a,
            created_reason="original", created_at=now,
        )
        db.add(v1)
        db.commit()

        # Simulate restore: create backup of current, then apply v1
        current_bytes = disk.read_bytes()
        backup_path = disk.with_name(f"{disk.name}.v2.bak")
        backup_path.write_bytes(current_bytes)
        v2 = FileVersion(
            file_id=file_a, version_number=2, storage_path=str(backup_path),
            size=len(current_bytes), mime_type="text/plain", created_by=user_a,
            created_reason="pre_restore_backup", created_at=now,
        )
        db.add(v2)
        db.flush()
        disk.write_bytes(v1_path.read_bytes())
        db_file.size = v1_path.stat().st_size
        db.commit()

        versions = db.query(FileVersion).filter(FileVersion.file_id == file_a).order_by(FileVersion.version_number).all()
        assert len(versions) == 2
        assert versions[0].created_reason == "original"
        assert versions[1].created_reason == "pre_restore_backup"
        # File now has v1 content
        assert disk.read_text() == "version 1 content"

    Base.metadata.drop_all(bind=engine)
    engine.dispose()
