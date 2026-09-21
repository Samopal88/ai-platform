"""
AI Workspace Platform - User Model
SQLAlchemy model for users table
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Boolean, BigInteger
from sqlalchemy.orm import relationship

from app.db.base import Base, TimestampMixin
from app.db.types import GUID


class User(Base, TimestampMixin):
    """
    User model representing platform users.

    Attributes:
        id: Unique identifier (UUID)
        email: User email (unique)
        password_hash: Hashed password
        plan_type: Subscription plan (starter, medium, pro)
        token_limit_month: Monthly token limit
        storage_limit_total: Total storage limit in bytes
        storage_used: Currently used storage in bytes
        tokens_used_month: Tokens used this month
        is_active: Whether user account is active
    """
    __tablename__ = "users"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)

    # Plan and limits
    plan_type = Column(String(50), default="starter", nullable=False)
    token_limit_month = Column(BigInteger, default=1_000_000, nullable=False)
    storage_limit_total = Column(BigInteger, default=1_073_741_824, nullable=False)  # 1 GB
    storage_used = Column(BigInteger, default=0, nullable=False)
    tokens_used_month = Column(BigInteger, default=0, nullable=False)

    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)

    # Timestamps from mixin: created_at, updated_at

    # Relationships (will be defined when other models are created)
    # projects = relationship("Project", back_populates="user")
    # usage_records = relationship("Usage", back_populates="user")

    def __repr__(self):
        return f"<User {self.email}>"

    def can_use_tokens(self, amount: int) -> bool:
        """Check if user has enough token quota"""
        return (self.tokens_used_month + amount) <= self.token_limit_month

    def can_use_storage(self, amount: int) -> bool:
        """Check if user has enough storage quota"""
        return (self.storage_used + amount) <= self.storage_limit_total
