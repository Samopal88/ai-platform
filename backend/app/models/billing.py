"""Commercial plan, subscription, payment, and usage models."""
from __future__ import annotations

import uuid

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text

from app.db.base import Base, TimestampMixin
from app.db.types import GJSON, GUID


class Plan(Base, TimestampMixin):
    __tablename__ = "plans"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    code = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    project_limit = Column(Integer, nullable=False, default=1)
    storage_limit_total = Column(BigInteger, nullable=False, default=50 * 1024 * 1024)
    storage_limit_per_project = Column(BigInteger, nullable=False, default=50 * 1024 * 1024)
    token_limit_month = Column(BigInteger, nullable=False, default=50_000)
    price_amount = Column(Numeric(12, 2), nullable=False, default=0)
    price_currency = Column(String(3), nullable=False, default="RUB")
    is_active = Column(Boolean, nullable=False, default=True)


class Subscription(Base, TimestampMixin):
    __tablename__ = "subscriptions"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_id = Column(GUID(), ForeignKey("plans.id", ondelete="RESTRICT"), nullable=False, index=True)
    provider = Column(String(64), nullable=False, default="yookassa")
    provider_customer_id = Column(String(255), nullable=True, index=True)
    provider_subscription_id = Column(String(255), nullable=True, index=True)
    status = Column(String(64), nullable=False, default="pending", index=True)
    current_period_start = Column(DateTime, nullable=True)
    current_period_end = Column(DateTime, nullable=True)
    cancel_at_period_end = Column(Boolean, nullable=False, default=False)


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(64), nullable=False, default="yookassa")
    provider_payment_id = Column(String(255), nullable=True, unique=True)
    kind = Column(String(64), nullable=False, default="subscription")
    status = Column(String(64), nullable=False, default="pending", index=True)
    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="RUB")
    payment_metadata = Column(GJSON, nullable=True)
    idempotency_key = Column(String(255), nullable=True, unique=True)


class UsageRecord(Base):
    __tablename__ = "usage_records"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(GUID(), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    chat_id = Column(GUID(), ForeignKey("chats.id", ondelete="SET NULL"), nullable=True, index=True)
    message_id = Column(GUID(), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True, index=True)
    operation = Column(String(64), nullable=False, index=True)
    provider = Column(String(64), nullable=True)
    model = Column(String(128), nullable=True)
    tokens_input = Column(BigInteger, nullable=False, default=0)
    tokens_output = Column(BigInteger, nullable=False, default=0)
    tokens_embeddings = Column(BigInteger, nullable=False, default=0)
    units_images = Column(Integer, nullable=False, default=0)
    units_web = Column(Integer, nullable=False, default=0)
    total_tokens = Column(BigInteger, nullable=False, default=0)
    estimated_cost = Column(Numeric(12, 6), nullable=False, default=0)
    currency = Column(String(3), nullable=False, default="RUB")
    period_month = Column(String(7), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False)


class LegalAcceptance(Base):
    __tablename__ = "legal_acceptances"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    terms_version = Column(String(64), nullable=False)
    privacy_version = Column(String(64), nullable=False)
    accepted_at = Column(DateTime, nullable=False)
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(Text, nullable=True)
