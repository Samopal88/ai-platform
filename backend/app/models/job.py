"""
AI Workspace Platform - Job Model
SQLAlchemy model for jobs table
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey, Enum
from app.db.types import GUID, GJSON
from sqlalchemy.orm import relationship
import enum

from app.db.base import Base


class JobStatus(str, enum.Enum):
    """Job status types"""
    QUEUED = "queued"
    STARTED = "started"
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Job(Base):
    """
    Job model representing long-running tasks.

    Jobs track the execution of tasks by the AI system.

    Attributes:
        id: Unique identifier (UUID)
        project_id: Parent project ID (optional)
        task_type: Type of task (chat, code, analysis, etc.)
        prompt: Task prompt/description
        status: Current job status
        mode: Execution mode (self, claude)
        answer: Task result/answer
        error: Error message if failed
        files_changed: List of files modified
        progress: Progress log entries
    """
    __tablename__ = "jobs"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    project_id = Column(GUID(), ForeignKey("projects.id"), nullable=True, index=True)

    # Task info
    task_type = Column(String(50), default="general", nullable=False)
    prompt = Column(Text, nullable=False)

    # Status
    status = Column(Enum(JobStatus), default=JobStatus.QUEUED, nullable=False, index=True)
    current_stage = Column(String(255), nullable=True)

    # Execution info
    mode = Column(String(20), default="self", nullable=False)

    # Results
    answer = Column(Text, nullable=True)
    error = Column(Text, nullable=True)

    # Metadata
    files_changed = Column(GJSON, default=list, nullable=False)
    progress = Column(GJSON, default=list, nullable=False)
    extra_data = Column(GJSON, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    # Relationships
    # project = relationship("Project", back_populates="jobs")

    def __repr__(self):
        return f"<Job {self.id} {self.status.value}>"

    @property
    def duration_ms(self) -> int:
        """Calculate job duration in milliseconds"""
        if self.started_at and self.finished_at:
            return int((self.finished_at - self.started_at).total_seconds() * 1000)
        return 0
