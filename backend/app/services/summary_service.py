"""
Phase 8.2 – Chat summary service.

Generates and stores a Summary DB record for long chats that exceed a message
threshold.  The summary is then included in the context builder for future turns.

Design:
- Triggered only when a chat crosses SUMMARY_THRESHOLD messages.
- Creates at most one summary per threshold band (avoids duplicate runs).
- Stored in the `summaries` table (models.context.Summary).
- Summary text is generated via the model router (provider-agnostic).
- Falls back to a no-op if no AI provider is configured.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.context import Summary
from app.services.model_router import ModelRouter

_log = logging.getLogger(__name__)

# Summarize when a chat has at least this many messages
SUMMARY_THRESHOLD = 20
# After a summary, wait this many messages before creating another
SUMMARY_BAND = 10
# Max input chars to send to the summarizer
MAX_INPUT_CHARS = 8000
# Model to use for summarization (cheap/fast)
_SUMMARY_MODEL = "gpt-4o-mini"

_router = ModelRouter()


def _format_messages_for_summary(messages: list) -> str:
    """Format a list of ORM message objects into a readable transcript."""
    lines = []
    for m in messages:
        role = getattr(m, "role", "user")
        if hasattr(role, "value"):
            role = role.value
        content = (getattr(m, "content", "") or "").strip()
        if content:
            lines.append(f"{role.capitalize()}: {content[:500]}")
    return "\n".join(lines)[:MAX_INPUT_CHARS]


def maybe_summarize_chat(
    db: Session,
    chat_id,
    project_id=None,
    messages: Optional[list] = None,
) -> Optional[Summary]:
    """
    If the chat has crossed the next summary threshold, generate and store a summary.

    Returns the new Summary object if one was created, else None.
    """
    from uuid import UUID

    chat_id_uuid = chat_id if isinstance(chat_id, UUID) else UUID(str(chat_id))
    project_id_uuid = None
    if project_id is not None:
        try:
            project_id_uuid = project_id if isinstance(project_id, UUID) else UUID(str(project_id))
        except (ValueError, AttributeError):
            pass

    # Count existing summaries for this chat
    existing_count = db.query(Summary).filter(Summary.chat_id == chat_id_uuid).count()
    next_threshold = SUMMARY_THRESHOLD + existing_count * SUMMARY_BAND

    msg_count = len(messages) if messages is not None else 0

    if messages is None or msg_count < next_threshold:
        return None

    transcript = _format_messages_for_summary(messages)
    if not transcript.strip():
        return None

    prompt_messages = [
        {
            "role": "system",
            "content": (
                "You are a concise conversation summarizer. "
                "Summarize the following chat transcript in 3-5 sentences, "
                "capturing the key decisions, facts, and context. "
                "Be brief and factual. Do not repeat yourself."
            ),
        },
        {"role": "user", "content": f"Transcript:\n{transcript}"},
    ]

    try:
        response = _router.route_response(prompt_messages, model_id=_SUMMARY_MODEL, max_tokens=300)
        summary_text = (response.text or "").strip()
        if not summary_text:
            return None
        usage = response.usage
    except Exception as exc:
        _log.debug("summary generation failed for chat %s: %s", chat_id_uuid, exc)
        return None

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db_summary = Summary(
        chat_id=chat_id_uuid,
        project_id=project_id_uuid,
        summary_text=summary_text,
        from_message_id=None,
        to_message_id=None,
        model=_SUMMARY_MODEL,
        tokens_input=getattr(usage, "prompt_tokens", 0),
        tokens_output=getattr(usage, "completion_tokens", 0),
        created_at=now,
    )
    db.add(db_summary)
    db.commit()
    db.refresh(db_summary)
    _log.info("Created summary for chat %s (%d messages)", chat_id_uuid, msg_count)
    return db_summary


def get_chat_summaries(db: Session, chat_id) -> list[Summary]:
    """Return all summaries for a chat, oldest first."""
    from uuid import UUID
    chat_id_uuid = chat_id if isinstance(chat_id, UUID) else UUID(str(chat_id))
    return (
        db.query(Summary)
        .filter(Summary.chat_id == chat_id_uuid)
        .order_by(Summary.created_at)
        .all()
    )
