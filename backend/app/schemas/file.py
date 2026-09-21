"""
AI Workspace Platform - File Schemas
Pydantic schemas for file API responses.
"""
import uuid
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel


class FileRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    filename: str
    size: int
    mime_type: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class FileListResponse(BaseModel):
    files: List[FileRead]
    total: int
