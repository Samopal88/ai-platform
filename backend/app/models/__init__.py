"""
AI Workspace Platform - Database Models
SQLAlchemy models for the platform

Note: Database connection is optional for MVP demo.
File-based storage is used as fallback.
"""
from app.models.user import User
from app.models.project import Project
from app.models.chat import Chat
from app.models.message import Message, MessageRole
from app.models.file import File
from app.models.chat_artifact import ChatArtifact
from app.models.job import Job, JobStatus
from app.models.billing import Plan, Subscription, Payment, UsageRecord, LegalAcceptance
from app.models.context import (
    FileVersion,
    FileChunk,
    Embedding,
    Memory,
    Summary,
    AgentTask,
    FileEditProposal,
)

__all__ = [
    "User",
    "Project",
    "Chat",
    "Message",
    "MessageRole",
    "File",
    "ChatArtifact",
    "Job",
    "JobStatus",
    "Plan",
    "Subscription",
    "Payment",
    "UsageRecord",
    "LegalAcceptance",
    "FileVersion",
    "FileChunk",
    "Embedding",
    "Memory",
    "Summary",
    "AgentTask",
    "FileEditProposal",
]
