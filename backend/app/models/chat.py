"""
AI Workspace Platform - Chat Model
SQLAlchemy model for chats table
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship

from app.db.base import Base, TimestampMixin
from app.db.types import GUID


class Chat(Base, TimestampMixin):
    """
    Chat model representing conversations within a project.

    Attributes:
        id: Unique identifier (UUID)
        project_id: Parent project ID
        title: Chat title/name
        model: AI model used for this chat
        context_tokens: Current context size in tokens
        summary: Compacted summary of older messages
    """
    __tablename__ = "chats"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    project_id = Column(GUID(), ForeignKey("projects.id"), nullable=True, index=True)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=True, index=True)
    title = Column(String(255), default="New Chat", nullable=False)

    # Model settings
    model = Column(String(100), nullable=False)

    # Context management
    context_tokens = Column(Integer, default=0, nullable=False)
    summary = Column(Text, nullable=True)

    # Timestamps from mixin: created_at, updated_at

    # Relationships
    # project = relationship("Project", back_populates="chats")
    # messages = relationship("Message", back_populates="chat")

    def __repr__(self):
        return f"<Chat {self.title}>"
