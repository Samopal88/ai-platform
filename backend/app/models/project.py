"""
AI Workspace Platform - Project Model
SQLAlchemy model for projects table
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, BigInteger, Text, ForeignKey
from sqlalchemy.orm import relationship

from app.db.base import Base, TimestampMixin
from app.db.types import GUID


class Project(Base, TimestampMixin):
    """
    Project model representing user projects.

    A project is the main unit of work containing chats, files, and memory.

    Attributes:
        id: Unique identifier (UUID)
        user_id: Owner user ID
        name: Project name
        description: Project description
        storage_used: Storage used by project files in bytes
        file_count: Number of files in project
        default_model: Default AI model for chats
    """
    __tablename__ = "projects"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Storage metrics
    storage_used = Column(BigInteger, default=0, nullable=False)
    file_count = Column(Integer, default=0, nullable=False)

    # Settings
    default_model = Column(String(100), default="claude-sonnet-4-20250514", nullable=False)

    # Project-level instructions injected as system context into every AI completion
    instructions = Column(Text, nullable=True, default=None)

    # Timestamps from mixin: created_at, updated_at

    # Relationships
    # user = relationship("User", back_populates="projects")
    # chats = relationship("Chat", back_populates="project")
    # files = relationship("File", back_populates="project")
    # memories = relationship("Memory", back_populates="project")
    # jobs = relationship("Job", back_populates="project")

    def __repr__(self):
        return f"<Project {self.name}>"
