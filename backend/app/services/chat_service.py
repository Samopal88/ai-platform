"""
AI Workspace Platform - Chat Service
SQLAlchemy CRUD operations for chats and messages.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.chat import Chat
from app.models.message import Message, MessageRole
from app.schemas.chat import ChatCreate, ChatUpdate, MessageCreate


# ---------------------------------------------------------------------------
# Chat CRUD
# ---------------------------------------------------------------------------

def create_chat(db: Session, data: ChatCreate) -> Chat:
    chat = Chat(
        project_id=data.project_id,  # may be None for personal chats
        user_id=data.user_id,
        title=data.title,
        model=data.model,
    )
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return chat


def get_chat(db: Session, chat_id: UUID) -> Optional[Chat]:
    return db.query(Chat).filter(Chat.id == chat_id).first()


def get_project_chat(db: Session, project_id: UUID, chat_id: UUID) -> Optional[Chat]:
    return (
        db.query(Chat)
        .filter(Chat.id == chat_id, Chat.project_id == project_id)
        .first()
    )


def list_chats(db: Session, project_id: Optional[UUID] = None) -> list:
    q = db.query(Chat)
    if project_id is not None:
        q = q.filter(Chat.project_id == project_id)
    chats = q.order_by(Chat.created_at.desc()).all()
    _attach_activity_metadata(db=db, chats=chats)
    return chats


def list_personal_chats(db: Session, user_id: Optional[UUID] = None) -> list:
    """Return chats with no project (personal/unattached chats)."""
    q = db.query(Chat).filter(Chat.project_id.is_(None))
    if user_id is not None:
        q = q.filter(Chat.user_id == user_id)
    chats = q.order_by(Chat.created_at.desc()).all()
    _attach_activity_metadata(db=db, chats=chats)
    return chats


def update_chat(db: Session, chat_id: UUID, data: ChatUpdate) -> Optional[Chat]:
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if chat is None:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(chat, field, value)
    db.commit()
    db.refresh(chat)
    return chat


def delete_chat(db: Session, chat_id: UUID) -> bool:
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if chat is None:
        return False
    db.delete(chat)
    db.commit()
    return True


def delete_project_chat(db: Session, project_id: UUID, chat_id: UUID) -> bool:
    chat = get_project_chat(db=db, project_id=project_id, chat_id=chat_id)
    if chat is None:
        return False
    db.delete(chat)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Message CRUD
# ---------------------------------------------------------------------------

def add_message(db: Session, data: MessageCreate) -> Message:
    message = Message(
        chat_id=data.chat_id,
        role=MessageRole(data.role),
        content=data.content,
        tokens_used=data.tokens_used,
        model=data.model,
        extra_data=data.extra_data,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def auto_title_from_first_user_message(db: Session, chat_id: UUID, first_message: str) -> Optional[Chat]:
    chat = get_chat(db=db, chat_id=chat_id)
    if chat is None:
        return None
    if (chat.title or "").strip() != "Новый чат":
        return chat
    raw = (first_message or "").strip()
    if not raw:
        return chat

    user_message_count = (
        db.query(func.count(Message.id))
        .filter(Message.chat_id == chat_id, Message.role == MessageRole.USER)
        .scalar()
        or 0
    )
    if int(user_message_count) != 1:
        return chat

    normalized = " ".join(raw.split())
    title = normalized[:50]
    if len(normalized) > 50:
        last_space = title.rfind(" ")
        if last_space > 20:
            title = title[:last_space]
        title += "…"
    title = title.strip()
    if not title:
        return chat

    chat.title = title
    db.commit()
    db.refresh(chat)
    return chat


def get_messages(db: Session, chat_id: UUID, limit: int = 100) -> list:
    # Fetch newest N first, then re-order to chronological sequence.
    rows = (
        db.query(Message)
        .filter(Message.chat_id == chat_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
        .all()
    )
    rows.reverse()
    return rows


def get_project_chat_messages(db: Session, project_id: UUID, chat_id: UUID, limit: int = 100) -> Optional[list]:
    chat = get_project_chat(db=db, project_id=project_id, chat_id=chat_id)
    if chat is None:
        return None
    return get_messages(db=db, chat_id=chat_id, limit=limit)


def _attach_activity_metadata(db: Session, chats: list[Chat]) -> None:
    """
    Populate transient activity fields for list responses:
    - message_count
    - last_message_at
    - last_message_preview
    """
    if not chats:
        return

    chat_ids = [c.id for c in chats]
    aggregate_rows = (
        db.query(
            Message.chat_id.label("chat_id"),
            func.count(Message.id).label("message_count"),
            func.max(Message.created_at).label("last_message_at"),
        )
        .filter(Message.chat_id.in_(chat_ids))
        .group_by(Message.chat_id)
        .all()
    )
    aggregate_map = {row.chat_id: row for row in aggregate_rows}

    for chat in chats:
        agg = aggregate_map.get(chat.id)
        if agg is None:
            chat.message_count = 0
            chat.last_message_at = None
            chat.last_message_preview = None
            continue

        chat.message_count = int(agg.message_count or 0)
        chat.last_message_at = agg.last_message_at

        last_msg = (
            db.query(Message.content)
            .filter(Message.chat_id == chat.id)
            .order_by(Message.created_at.desc())
            .first()
        )
        if last_msg and last_msg[0]:
            preview = str(last_msg[0]).strip().replace("\n", " ")
            chat.last_message_preview = preview[:120]
        else:
            chat.last_message_preview = None
