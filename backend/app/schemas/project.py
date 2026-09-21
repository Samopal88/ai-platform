"""
Pydantic v2 schemas for the Project resource.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    instructions: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    instructions: Optional[str] = None


class ProjectRead(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    instructions: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    file_count: int = 0
    storage_used: int = 0
    chat_count: int = 0
    last_message_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
