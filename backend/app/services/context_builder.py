"""
Context builder v2 — Phase 6.4

Retrieval-based context assembly:
  1. Project description + instructions
  2. Relevant FileChunk rows (keyword/substring retrieval, no pgvector required)
  3. Relevant memories (up to 3)
  4. Recent conversation (last 10 messages)

Budget: total context is capped at CONTEXT_BUDGET_CHARS (default 12 000 chars)
so the assembled prompt never floods a model's context window.

Backward-compatible: the old `build_context(project_id, chat_id, query) -> str`
signature is preserved.  New callers can pass `db` to avoid a second SessionLocal
instantiation.
"""
from __future__ import annotations

import logging
import re
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.session import SessionLocal

_log = logging.getLogger(__name__)

# Hard cap on total assembled context (chars).  ~3 tokens/char → ~4 000 tokens.
CONTEXT_BUDGET_CHARS: int = 12_000
# Per-section budget for file chunks.  Remaining budget goes to the rest.
CHUNK_BUDGET_CHARS: int = 6_000
# Maximum individual chunk excerpt length injected into context.
MAX_CHUNK_EXCERPT: int = 800


def _tokenize_query(query: str) -> list[str]:
    """Extract unique lowercase words from query for keyword matching."""
    return list({w.lower() for w in re.findall(r"\w+", query) if len(w) >= 3})


def _score_chunk(content: str, keywords: list[str]) -> int:
    """Simple keyword-overlap score for relevance ranking (no vectors needed)."""
    lower = content.lower()
    return sum(1 for kw in keywords if kw in lower)


def _retrieve_relevant_chunks(
    db: Session,
    project_id: UUID,
    query: str,
    budget_chars: int = CHUNK_BUDGET_CHARS,
    max_chunks: int = 10,
) -> list[str]:
    """
    Return up to `max_chunks` file chunk excerpts relevant to `query`,
    using keyword overlap scoring.  Works with SQLite and PostgreSQL (no pgvector).
    """
    from app.models.context import FileChunk
    from app.models.file import File as FileModel

    keywords = _tokenize_query(query)
    if not keywords:
        return []

    try:
        chunks = (
            db.query(FileChunk)
            .join(FileModel, FileModel.id == FileChunk.file_id)
            .filter(
                FileChunk.project_id == project_id,
                FileModel.project_id == project_id,
            )
            .order_by(FileChunk.file_id, FileChunk.chunk_index)
            .limit(500)  # retrieve candidate pool; we re-rank below
            .all()
        )
    except Exception as exc:
        _log.debug("chunk retrieval failed: %s", exc)
        return []

    scored = sorted(
        ((c, _score_chunk(c.content, keywords)) for c in chunks),
        key=lambda x: x[1],
        reverse=True,
    )

    results: list[str] = []
    total_chars = 0
    seen_files: dict[str, list[str]] = {}

    for chunk, score in scored:
        if score == 0:
            break
        if len(results) >= max_chunks:
            break
        excerpt = (chunk.content or "")[:MAX_CHUNK_EXCERPT].strip()
        if not excerpt:
            continue
        total_chars += len(excerpt)
        if total_chars > budget_chars:
            break
        fid = str(chunk.file_id)
        seen_files.setdefault(fid, []).append(excerpt)
        results.append(excerpt)

    return results


def _build_context_inner(
    db: Session,
    project_id_str: str,
    chat_id_str: str,
    query: str,
) -> str:
    from app.services import chat_service, project_service
    from app.services.memory_service import search_memories

    project_id_uuid: Optional[UUID] = None
    try:
        project_id_uuid = UUID(project_id_str) if project_id_str else None
    except (ValueError, AttributeError):
        pass

    chat_id_uuid: Optional[UUID] = None
    try:
        chat_id_uuid = UUID(chat_id_str) if chat_id_str else None
    except (ValueError, AttributeError):
        pass

    sections: list[str] = []
    budget_left = CONTEXT_BUDGET_CHARS

    # --- Project description ---
    if project_id_uuid is not None:
        try:
            project = project_service.get_project(db, project_id_uuid)
            if project and project.description:
                desc = project.description.strip()[:1000]
                sections.append(f"## Project\n{desc}")
                budget_left -= len(desc)
        except Exception:
            pass

    # --- Relevant file chunks (Phase 6.4 retrieval) ---
    if project_id_uuid is not None and query and budget_left > 500:
        try:
            chunk_excerpts = _retrieve_relevant_chunks(
                db,
                project_id_uuid,
                query,
                budget_chars=min(CHUNK_BUDGET_CHARS, budget_left - 500),
            )
            if chunk_excerpts:
                chunk_text = "\n---\n".join(chunk_excerpts)
                sections.append(f"## Relevant File Content\n{chunk_text}")
                budget_left -= len(chunk_text)
        except Exception as exc:
            _log.debug("chunk context failed: %s", exc)

    # --- Relevant memories ---
    if project_id_uuid is not None and query and budget_left > 200:
        try:
            memories = search_memories(str(project_id_uuid), query)[:3]
            if memories:
                mem_lines = "\n".join(f"- {m['key']}: {m['value']}" for m in memories)
                sections.append(f"## Relevant Memory\n{mem_lines}")
                budget_left -= len(mem_lines)
        except Exception:
            pass

    # --- Recent chat history ---
    if budget_left > 200:
        try:
            messages: list = []
            if project_id_uuid is not None and chat_id_uuid is not None:
                msgs = chat_service.get_project_chat_messages(
                    db, project_id_uuid, chat_id_uuid, limit=10
                )
                if msgs:
                    messages = list(msgs)
            elif chat_id_uuid is not None:
                messages = chat_service.get_messages(db, chat_id_uuid, limit=10)

            if messages:
                history_lines = []
                for msg in messages:
                    role = getattr(msg, "role", "user")
                    content = (getattr(msg, "content", "") or "")[:400]
                    history_lines.append(f"{role.capitalize()}: {content}")
                history_text = "\n".join(history_lines)
                sections.append(f"## Recent Conversation\n{history_text}")
        except Exception:
            pass

    # --- Chat summaries (Phase 8.2) — inject before conversation for long chats ---
    if chat_id_uuid is not None and budget_left > 200:
        try:
            from app.services.summary_service import get_chat_summaries
            summaries = get_chat_summaries(db, chat_id_uuid)
            if summaries:
                summary_text = "\n---\n".join(s.summary_text for s in summaries[-2:])
                sections.insert(1, f"## Chat Summary\n{summary_text}")
                budget_left -= len(summary_text)
        except Exception:
            pass

    if not sections:
        return ""
    return "\n\n".join(sections)


def build_context(
    project_id: str,
    chat_id: str,
    query: str,
    db: Optional[Session] = None,
) -> str:
    """
    Assemble context for AI prompt injection.

    Phase 6.4: Now includes retrieval from FileChunk rows via keyword scoring.
    Budget-capped at CONTEXT_BUDGET_CHARS.
    """
    if db is not None:
        return _build_context_inner(db, project_id, chat_id, query)

    _db = SessionLocal()
    try:
        return _build_context_inner(_db, project_id, chat_id, query)
    finally:
        _db.close()
