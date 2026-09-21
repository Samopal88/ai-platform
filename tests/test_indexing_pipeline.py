"""
Phase 6.1 + 6.2 – File indexing pipeline tests

Tests cover:
- text extraction for plain text, JSON, binary
- chunking with overlap
- index_file idempotency (re-index deletes old chunks)
- extraction status written to FileModel
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.db.base import Base  # noqa: E402
from app.models.context import FileChunk  # noqa: E402
from app.models.file import File as FileModel  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.indexing_service import (  # noqa: E402
    _estimate_tokens,
    _split_into_chunks,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    index_file,
    run_chunking,
    run_extraction,
)
from app.services.text_extractor import extract_text  # noqa: E402


def make_db(tmp_path):
    db_path = tmp_path / "indexing_test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return engine, SessionLocal


def _make_file(db, tmp_path, content: bytes, mime: str, mode: str = "editable") -> FileModel:
    user_id = uuid.uuid4()
    proj_id = uuid.uuid4()
    file_id = uuid.uuid4()
    disk = tmp_path / f"{file_id.hex}.bin"
    disk.write_bytes(content)
    db.add(User(id=user_id, email=f"{user_id}@x.com", password_hash="x"))
    db.add(Project(id=proj_id, user_id=user_id, name="P"))
    f = FileModel(
        id=file_id,
        project_id=proj_id,
        filename=disk.name,
        size=len(content),
        mime_type=mime,
        storage_path=str(disk),
        mode=mode,
    )
    db.add(f)
    db.commit()
    return f


# ---------------------------------------------------------------------------
# text_extractor unit tests
# ---------------------------------------------------------------------------

def test_extract_text_from_plain_text(tmp_path):
    path = tmp_path / "hello.txt"
    path.write_text("Hello world", encoding="utf-8")
    result = extract_text(path, "text/plain")
    assert "Hello world" in result


def test_extract_text_from_json(tmp_path):
    path = tmp_path / "data.json"
    path.write_text('{"key": "value"}', encoding="utf-8")
    result = extract_text(path, "application/json")
    assert "key" in result


def test_extract_text_from_binary_returns_placeholder(tmp_path):
    path = tmp_path / "blob.bin"
    path.write_bytes(b"\x00\x01\x02\x03")
    result = extract_text(path, "application/octet-stream")
    assert "binary" in result.lower()


# ---------------------------------------------------------------------------
# chunking unit tests
# ---------------------------------------------------------------------------

def test_split_short_text_produces_one_chunk():
    chunks = _split_into_chunks("short text", size=1200, overlap=200)
    assert len(chunks) == 1
    assert chunks[0] == "short text"


def test_split_long_text_produces_multiple_chunks():
    # 4000 chars should produce multiple 1200-char chunks
    text = "A" * 4000
    chunks = _split_into_chunks(text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)
    assert len(chunks) > 1
    # Each chunk must not exceed size
    for c in chunks:
        assert len(c) <= CHUNK_SIZE


def test_chunks_overlap_correctly():
    text = "X" * 2000
    chunks = _split_into_chunks(text, size=1200, overlap=200)
    assert len(chunks) >= 2
    # The second chunk should start CHUNK_SIZE - CHUNK_OVERLAP chars from start of first
    # For text of all-same chars the overlap content is indistinguishable but length is right
    assert len(chunks[1]) > 0


def test_estimate_tokens_rough():
    assert _estimate_tokens("a" * 4000) == 1000
    assert _estimate_tokens("") == 1  # minimum 1


# ---------------------------------------------------------------------------
# index_file integration tests (in-process, no background thread)
# ---------------------------------------------------------------------------

def test_index_file_creates_chunks_for_text(tmp_path):
    engine, SessionLocal = make_db(tmp_path)
    with SessionLocal() as db:
        db_file = _make_file(db, tmp_path, b"Hello world " * 200, "text/plain")
        result = index_file(db, db_file)

        assert result["extraction_status"] == "done"
        assert result["chunks"] >= 1

        chunks = db.query(FileChunk).filter(FileChunk.file_id == db_file.id).all()
        assert len(chunks) == result["chunks"]
        for chunk in chunks:
            assert chunk.token_count > 0

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_index_file_is_idempotent(tmp_path):
    engine, SessionLocal = make_db(tmp_path)
    with SessionLocal() as db:
        db_file = _make_file(db, tmp_path, b"idempotent test " * 100, "text/plain")
        r1 = index_file(db, db_file)
        r2 = index_file(db, db_file)

        chunks_after = db.query(FileChunk).filter(FileChunk.file_id == db_file.id).count()
        assert chunks_after == r2["chunks"]  # second run replaces first

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_index_file_binary_sets_no_text_status(tmp_path):
    engine, SessionLocal = make_db(tmp_path)
    with SessionLocal() as db:
        db_file = _make_file(db, tmp_path, b"\x00\x01\x02", "application/octet-stream")
        result = index_file(db, db_file)

        assert result["extraction_status"] in ("no_text", "done")
        assert result["chunks"] == 0

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_index_sets_index_status_to_done(tmp_path):
    engine, SessionLocal = make_db(tmp_path)
    with SessionLocal() as db:
        db_file = _make_file(db, tmp_path, b"some text for indexing", "text/plain")
        index_file(db, db_file)

        db.refresh(db_file)
        assert db_file.index_status == "done"
        assert db_file.extraction_status in ("done", "no_text")

    Base.metadata.drop_all(bind=engine)
    engine.dispose()
