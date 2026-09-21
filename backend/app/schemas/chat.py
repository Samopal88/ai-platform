"""
AI Workspace Platform - Chat and Message Pydantic schemas
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Chat schemas
# ---------------------------------------------------------------------------

class ChatCreate(BaseModel):
    project_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    title: str = Field("New Chat", min_length=1, max_length=255)
    model: str = Field(..., min_length=1, max_length=100)


class ChatUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    model: Optional[str] = Field(None, min_length=1, max_length=100)
    project_id: Optional[UUID] = None


class ChatRead(BaseModel):
    id: UUID
    project_id: Optional[UUID] = None
    title: str
    model: str
    context_tokens: int
    summary: Optional[str] = None
    message_count: int = 0
    last_message_at: Optional[datetime] = None
    last_message_preview: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Message schemas
# ---------------------------------------------------------------------------

class MessageCreate(BaseModel):
    chat_id: UUID
    role: str = Field(..., pattern=r"^(user|assistant|system)$")
    content: str = Field(..., min_length=1)
    tokens_used: int = Field(0, ge=0)
    model: Optional[str] = None
    extra_data: Optional[dict[str, Any]] = None


class MessageRead(BaseModel):
    id: UUID
    chat_id: UUID
    role: str
    content: str
    tokens_used: int
    model: Optional[str] = None
    extra_data: Optional[dict[str, Any]] = None
    created_at: datetime

    model_config = {"from_attributes": True}
