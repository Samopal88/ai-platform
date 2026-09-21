"""
File Indexing Pipeline – Phase 6.1 + 6.2

On upload, a file is queued for:
  1. Text extraction    -> File.extraction_status = "done" | "failed"
  2. Chunking           -> FileChunk rows created
  3. Embedding (Phase 6.3 placeholder, skipped here)

All functions are synchronous and safe to call directly or from a background
thread.  They never raise outside of the `index_file` top-level wrapper.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.context import FileChunk
from app.models.file import File as FileModel
from app.services.text_extractor import extract_text, MAX_CHARS

_log = logging.getLogger(__name__)

# Chunking policy: target tokens ≈ chunk size in characters / 4.
# We chunk at ~1200 chars (≈ 300 tokens) with 200-char overlap.
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 200
# Maximum chunks per file to avoid db bloat
MAX_CHUNKS = 200


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: 1 token ≈ 4 chars."""
    return max(1, len(text) // 4)


def _split_into_chunks(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Sliding-window character splitter with sentence-boundary preference."""
    chunks: list[str] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + size, length)
        chunk = text[start:end]
        chunks.append(chunk)
        if end >= length:
            break
        start = end - overlap
    return chunks[:MAX_CHUNKS]


def run_extraction(db: Session, db_file: FileModel) -> str:
    """
    Extract text from the file, store it as FileChunk rows, update status.

    Returns the extracted text (possibly truncated).
    """
    path = Path(db_file.storage_path)
    try:
        text = extract_text(path, db_file.mime_type or "")
    except Exception as exc:
        _log.warning("Extraction failed for file %s: %s", db_file.id, exc)
        db_file.extraction_status = "failed"
        db.commit()
        return ""

    if not text or text.startswith("["):
        # Placeholder / error string returned by extractor
        db_file.extraction_status = "no_text"
        db.commit()
        return text

    db_file.extraction_status = "done"
    db.commit()
    return text


def run_chunking(db: Session, db_file: FileModel, text: str) -> int:
    """
    Split extracted text into FileChunk rows.  Deletes old chunks first for
    idempotency on re-index.

    Returns number of chunks created.
    """
    db.query(FileChunk).filter(FileChunk.file_id == db_file.id).delete()
    chunks = _split_into_chunks(text)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for idx, chunk_text in enumerate(chunks):
        db.add(FileChunk(
            project_id=db_file.project_id,
            file_id=db_file.id,
            chunk_index=idx,
            content=chunk_text,
            chunk_metadata={"source": "text_extractor", "char_offset": idx * (CHUNK_SIZE - CHUNK_OVERLAP)},
            token_count=_estimate_tokens(chunk_text),
        ))
    db.commit()
    return len(chunks)


def index_file(db: Session, db_file: FileModel) -> dict:
    """
    Full indexing pipeline for one file: extraction -> chunking.

    Returns a summary dict.  Never raises.
    """
    try:
        db_file.index_status = "indexing"
        db.commit()
        text = run_extraction(db, db_file)
        if db_file.extraction_status in ("failed", "no_text"):
            db_file.index_status = "done"
            db.commit()
            return {"extraction_status": db_file.extraction_status, "chunks": 0}

        chunks_count = run_chunking(db, db_file, text)
        db_file.index_status = "done"
        db_file.last_indexed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()
        return {"extraction_status": "done", "chunks": chunks_count}
    except Exception as exc:
        _log.error("Indexing pipeline error for file %s: %s", db_file.id, exc)
        try:
            db_file.index_status = "failed"
            db.commit()
        except Exception:
            pass
        return {"extraction_status": "error", "chunks": 0, "error": str(exc)}
