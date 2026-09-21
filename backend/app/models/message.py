"""
AI Workspace Platform - Message Model
SQLAlchemy model for messages table
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey, Enum
from app.db.types import GUID, GJSON
from sqlalchemy.orm import relationship
import enum

from app.db.base import Base


class MessageRole(str, enum.Enum):
    """Message role types"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Message(Base):
    """
    Message model representing individual messages in a chat.

    Attributes:
        id: Unique identifier (UUID)
        chat_id: Parent chat ID
        role: Message role (user, assistant, system)
        content: Message content
        tokens_used: Tokens used for this message
        model: Model that generated the response (for assistant messages)
        metadata: Additional metadata (files, tool calls, etc.)
    """
    __tablename__ = "messages"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    chat_id = Column(GUID(), ForeignKey("chats.id"), nullable=False, index=True)

    role = Column(Enum(MessageRole), nullable=False)
    content = Column(Text, nullable=False)

    # Token accounting
    tokens_used = Column(Integer, default=0, nullable=False)

    # Model info (for assistant messages)
    model = Column(String(100), nullable=True)

    # Additional data (not named 'metadata' — that name is reserved by SQLAlchemy Declarative)
    extra_data = Column(GJSON, nullable=True)

    # Timestamp
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    # chat = relationship("Chat", back_populates="messages")

    def __repr__(self):
        return f"<Message {self.role.value} {self.id}>"
