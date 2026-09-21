"""
AI Workspace Platform - File Model
SQLAlchemy model for the files table.
"""
import uuid
from sqlalchemy import Boolean, Column, DateTime, String, BigInteger, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.db.base import Base, TimestampMixin
from app.db.types import GUID


class File(Base, TimestampMixin):
    """
    File model representing a user-uploaded file attached to a project.

    Attributes:
        id: Unique identifier (UUID)
        project_id: Owning project UUID
        filename: Original filename as supplied by the uploader
        size: File size in bytes
        mime_type: MIME type detected or supplied at upload time
        storage_path: Absolute path to the stored file on disk
    """
    __tablename__ = "files"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    project_id = Column(GUID(), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(512), nullable=False)
    size = Column(BigInteger, default=0, nullable=False)
    mime_type = Column(String(255), nullable=True)
    storage_path = Column(Text, nullable=False)
    mode = Column(String(32), default="read_only", nullable=False)
    versioning_enabled = Column(Boolean, default=False, nullable=False)
    extraction_status = Column(String(32), default="pending", nullable=False)
    index_status = Column(String(32), default="pending", nullable=False)
    last_indexed_at = Column(DateTime, nullable=True)
    text_hash = Column(String(128), nullable=True)

    def __repr__(self):
        return f"<File {self.filename} project={self.project_id}>"
