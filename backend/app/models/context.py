"""Project context, indexing, memory, and safe file-edit models."""
from __future__ import annotations

import uuid

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, String, Text

from app.db.base import Base, TimestampMixin
from app.db.types import GJSON, GUID


class FileVersion(Base):
    __tablename__ = "file_versions"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    file_id = Column(GUID(), ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False)
    storage_path = Column(Text, nullable=False)
    size = Column(BigInteger, nullable=False, default=0)
    mime_type = Column(String(255), nullable=True)
    created_by = Column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_reason = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False)


class FileChunk(Base, TimestampMixin):
    __tablename__ = "file_chunks"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    project_id = Column(GUID(), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    file_id = Column(GUID(), ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    chunk_metadata = Column(GJSON, nullable=True)
    token_count = Column(Integer, nullable=False, default=0)


class Embedding(Base, TimestampMixin):
    __tablename__ = "embeddings"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    project_id = Column(GUID(), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    file_id = Column(GUID(), ForeignKey("files.id", ondelete="CASCADE"), nullable=True, index=True)
    chunk_id = Column(GUID(), ForeignKey("file_chunks.id", ondelete="CASCADE"), nullable=True, index=True)
    provider = Column(String(64), nullable=False)
    model = Column(String(128), nullable=False)
    embedding = Column(GJSON, nullable=False)


class Memory(Base, TimestampMixin):
    __tablename__ = "memories"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    project_id = Column(GUID(), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(String(64), nullable=False, default="fact")
    key = Column(String(255), nullable=True)
    content = Column(Text, nullable=False)
    source = Column(String(255), nullable=True)
    expires_at = Column(DateTime, nullable=True)
    pinned = Column(Boolean, nullable=False, default=False)


class Summary(Base):
    __tablename__ = "summaries"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    chat_id = Column(GUID(), ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(GUID(), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    summary_text = Column(Text, nullable=False)
    from_message_id = Column(GUID(), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    to_message_id = Column(GUID(), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    model = Column(String(128), nullable=True)
    tokens_input = Column(Integer, nullable=False, default=0)
    tokens_output = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False)


class AgentTask(Base, TimestampMixin):
    __tablename__ = "agent_tasks"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(GUID(), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    chat_id = Column(GUID(), ForeignKey("chats.id", ondelete="SET NULL"), nullable=True, index=True)
    status = Column(String(64), nullable=False, default="created", index=True)
    task_type = Column(String(64), nullable=False)
    mode = Column(String(64), nullable=False, default="plan")
    prompt = Column(Text, nullable=False)
    plan = Column(GJSON, nullable=True)
    result = Column(GJSON, nullable=True)
    error = Column(Text, nullable=True)
    requires_approval = Column(Boolean, nullable=False, default=False)
    approved_at = Column(DateTime, nullable=True)


class FileEditProposal(Base, TimestampMixin):
    __tablename__ = "file_edit_proposals"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    task_id = Column(GUID(), ForeignKey("agent_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    file_id = Column(GUID(), ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True)
    base_version_id = Column(GUID(), ForeignKey("file_versions.id", ondelete="SET NULL"), nullable=True)
    proposed_content_path = Column(Text, nullable=False)
    diff_text = Column(Text, nullable=False)
    status = Column(String(64), nullable=False, default="pending", index=True)
    approved_by = Column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    applied_version_id = Column(GUID(), ForeignKey("file_versions.id", ondelete="SET NULL"), nullable=True)
