"""
AI Workspace Platform - Chat Artifact Model
Stores assistant-generated downloadable artifacts linked to chats.
"""
from __future__ import annotations

import uuid

from sqlalchemy import BigInteger, Column, ForeignKey, String, Text

from app.db.base import Base, TimestampMixin
from app.db.types import GUID


class ChatArtifact(Base, TimestampMixin):
    __tablename__ = "chat_artifacts"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    chat_id = Column(GUID(), ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(GUID(), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    user_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    file_id = Column(GUID(), ForeignKey("files.id", ondelete="SET NULL"), nullable=True, index=True)

    filename = Column(String(512), nullable=False)
    mime_type = Column(String(255), nullable=True)
    storage_path = Column(Text, nullable=False)
    size = Column(BigInteger, default=0, nullable=False)

    requested_format = Column(String(32), nullable=True)
    generated_format = Column(String(32), nullable=True)
    fallback_from = Column(String(32), nullable=True)
    fallback_reason = Column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<ChatArtifact {self.filename} chat={self.chat_id}>"
