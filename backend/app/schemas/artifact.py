"""
AI Workspace Platform - Artifact Schemas
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class ArtifactRead(BaseModel):
    id: UUID
    chat_id: UUID
    project_id: Optional[UUID] = None
    file_id: Optional[UUID] = None
    filename: str
    mime_type: Optional[str] = None
    size: int
    requested_format: Optional[str] = None
    generated_format: Optional[str] = None
    fallback_from: Optional[str] = None
    fallback_reason: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ArtifactListResponse(BaseModel):
    artifacts: list[ArtifactRead]
    total: int
