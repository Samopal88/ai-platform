"""
AI Workspace Platform - Artifact Service
Persistence helpers for assistant-generated artifacts.
"""
from __future__ import annotations

import mimetypes
import uuid
from pathlib import Path
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.chat_artifact import ChatArtifact
from app.services.file_service import UPLOAD_ROOT

ARTIFACT_ROOT = UPLOAD_ROOT / "_artifacts"


def _chat_artifact_dir(chat_id: UUID) -> Path:
    d = ARTIFACT_ROOT / str(chat_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_personal_artifact_content(chat_id: UUID, filename: str, content: bytes, mime_type: Optional[str] = None) -> tuple[str, str]:
    if not mime_type:
        guessed, _ = mimetypes.guess_type(filename)
        mime_type = guessed or "application/octet-stream"
    file_id = uuid.uuid4()
    safe_name = f"{file_id.hex}_{Path(filename).name}"
    dest = _chat_artifact_dir(chat_id) / safe_name
    dest.write_bytes(content)
    return str(dest), mime_type


def create_artifact_record(
    db: Session,
    *,
    chat_id: UUID,
    user_id: UUID,
    project_id: Optional[UUID],
    filename: str,
    mime_type: Optional[str],
    storage_path: str,
    size: int,
    requested_format: Optional[str],
    generated_format: Optional[str],
    fallback_from: Optional[str] = None,
    fallback_reason: Optional[str] = None,
    file_id: Optional[UUID] = None,
) -> ChatArtifact:
    row = ChatArtifact(
        chat_id=chat_id,
        user_id=user_id,
        project_id=project_id,
        file_id=file_id,
        filename=filename,
        mime_type=mime_type,
        storage_path=storage_path,
        size=max(0, int(size)),
        requested_format=requested_format,
        generated_format=generated_format,
        fallback_from=fallback_from,
        fallback_reason=fallback_reason,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_chat_artifacts(db: Session, chat_id: UUID) -> list[ChatArtifact]:
    return (
        db.query(ChatArtifact)
        .filter(ChatArtifact.chat_id == chat_id)
        .order_by(ChatArtifact.created_at.desc())
        .all()
    )


def get_chat_artifact(db: Session, chat_id: UUID, artifact_id: UUID) -> Optional[ChatArtifact]:
    return (
        db.query(ChatArtifact)
        .filter(ChatArtifact.chat_id == chat_id, ChatArtifact.id == artifact_id)
        .first()
    )
