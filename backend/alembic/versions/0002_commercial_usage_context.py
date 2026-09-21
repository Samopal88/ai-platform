"""commercial, usage, context, and file edit schema

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-29
"""
from alembic import op
import sqlalchemy as sa


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plans",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("project_limit", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("storage_limit_total", sa.BigInteger(), nullable=False, server_default="52428800"),
        sa.Column("storage_limit_per_project", sa.BigInteger(), nullable=False, server_default="52428800"),
        sa.Column("token_limit_month", sa.BigInteger(), nullable=False, server_default="50000"),
        sa.Column("price_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("price_currency", sa.String(3), nullable=False, server_default="RUB"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_plans_code", "plans", ["code"])

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plan_id", sa.String(36), sa.ForeignKey("plans.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False, server_default="yookassa"),
        sa.Column("provider_customer_id", sa.String(255), nullable=True),
        sa.Column("provider_subscription_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(64), nullable=False, server_default="pending"),
        sa.Column("current_period_start", sa.DateTime(), nullable=True),
        sa.Column("current_period_end", sa.DateTime(), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"])
    op.create_index("ix_subscriptions_plan_id", "subscriptions", ["plan_id"])
    op.create_index("ix_subscriptions_status", "subscriptions", ["status"])
    op.create_index("ix_subscriptions_provider_customer_id", "subscriptions", ["provider_customer_id"])
    op.create_index("ix_subscriptions_provider_subscription_id", "subscriptions", ["provider_subscription_id"])

    op.create_table(
        "payments",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False, server_default="yookassa"),
        sa.Column("provider_payment_id", sa.String(255), nullable=True, unique=True),
        sa.Column("kind", sa.String(64), nullable=False, server_default="subscription"),
        sa.Column("status", sa.String(64), nullable=False, server_default="pending"),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="RUB"),
        sa.Column("payment_metadata", sa.JSON(), nullable=True),
        sa.Column("idempotency_key", sa.String(255), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_payments_user_id", "payments", ["user_id"])
    op.create_index("ix_payments_status", "payments", ["status"])

    op.create_table(
        "usage_records",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("chat_id", sa.String(36), sa.ForeignKey("chats.id", ondelete="SET NULL"), nullable=True),
        sa.Column("message_id", sa.String(36), sa.ForeignKey("messages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("operation", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(64), nullable=True),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("tokens_input", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("tokens_output", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("tokens_embeddings", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("units_images", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("units_web", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("estimated_cost", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="RUB"),
        sa.Column("period_month", sa.String(7), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_usage_records_user_id", "usage_records", ["user_id"])
    op.create_index("ix_usage_records_project_id", "usage_records", ["project_id"])
    op.create_index("ix_usage_records_chat_id", "usage_records", ["chat_id"])
    op.create_index("ix_usage_records_message_id", "usage_records", ["message_id"])
    op.create_index("ix_usage_records_operation", "usage_records", ["operation"])
    op.create_index("ix_usage_records_period_month", "usage_records", ["period_month"])

    op.create_table(
        "legal_acceptances",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("terms_version", sa.String(64), nullable=False),
        sa.Column("privacy_version", sa.String(64), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), nullable=False),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
    )
    op.create_index("ix_legal_acceptances_user_id", "legal_acceptances", ["user_id"])

    op.add_column("files", sa.Column("mode", sa.String(32), nullable=False, server_default="read_only"))
    op.add_column("files", sa.Column("versioning_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("files", sa.Column("extraction_status", sa.String(32), nullable=False, server_default="pending"))
    op.add_column("files", sa.Column("index_status", sa.String(32), nullable=False, server_default="pending"))
    op.add_column("files", sa.Column("last_indexed_at", sa.DateTime(), nullable=True))
    op.add_column("files", sa.Column("text_hash", sa.String(128), nullable=True))

    op.create_table(
        "file_versions",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("file_id", sa.String(36), sa.ForeignKey("files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("mime_type", sa.String(255), nullable=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_reason", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_file_versions_file_id", "file_versions", ["file_id"])

    op.create_table(
        "file_chunks",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_id", sa.String(36), sa.ForeignKey("files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("chunk_metadata", sa.JSON(), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_file_chunks_project_id", "file_chunks", ["project_id"])
    op.create_index("ix_file_chunks_file_id", "file_chunks", ["file_id"])

    op.create_table(
        "embeddings",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_id", sa.String(36), sa.ForeignKey("files.id", ondelete="CASCADE"), nullable=True),
        sa.Column("chunk_id", sa.String(36), sa.ForeignKey("file_chunks.id", ondelete="CASCADE"), nullable=True),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("embedding", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_embeddings_project_id", "embeddings", ["project_id"])
    op.create_index("ix_embeddings_file_id", "embeddings", ["file_id"])
    op.create_index("ix_embeddings_chunk_id", "embeddings", ["chunk_id"])

    op.create_table(
        "memories",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(64), nullable=False, server_default="fact"),
        sa.Column("key", sa.String(255), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source", sa.String(255), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_memories_project_id", "memories", ["project_id"])
    op.create_index("ix_memories_user_id", "memories", ["user_id"])

    op.create_table(
        "summaries",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("chat_id", sa.String(36), sa.ForeignKey("chats.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("from_message_id", sa.String(36), sa.ForeignKey("messages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("to_message_id", sa.String(36), sa.ForeignKey("messages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("tokens_input", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_output", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_summaries_chat_id", "summaries", ["chat_id"])
    op.create_index("ix_summaries_project_id", "summaries", ["project_id"])

    op.create_table(
        "agent_tasks",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True),
        sa.Column("chat_id", sa.String(36), sa.ForeignKey("chats.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(64), nullable=False, server_default="created"),
        sa.Column("task_type", sa.String(64), nullable=False),
        sa.Column("mode", sa.String(64), nullable=False, server_default="plan"),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("plan", sa.JSON(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("requires_approval", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_agent_tasks_user_id", "agent_tasks", ["user_id"])
    op.create_index("ix_agent_tasks_project_id", "agent_tasks", ["project_id"])
    op.create_index("ix_agent_tasks_chat_id", "agent_tasks", ["chat_id"])
    op.create_index("ix_agent_tasks_status", "agent_tasks", ["status"])

    op.create_table(
        "file_edit_proposals",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("agent_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_id", sa.String(36), sa.ForeignKey("files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("base_version_id", sa.String(36), sa.ForeignKey("file_versions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("proposed_content_path", sa.Text(), nullable=False),
        sa.Column("diff_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(64), nullable=False, server_default="pending"),
        sa.Column("approved_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("applied_version_id", sa.String(36), sa.ForeignKey("file_versions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_file_edit_proposals_task_id", "file_edit_proposals", ["task_id"])
    op.create_index("ix_file_edit_proposals_file_id", "file_edit_proposals", ["file_id"])
    op.create_index("ix_file_edit_proposals_status", "file_edit_proposals", ["status"])


def downgrade() -> None:
    op.drop_table("file_edit_proposals")
    op.drop_table("agent_tasks")
    op.drop_table("summaries")
    op.drop_table("memories")
    op.drop_table("embeddings")
    op.drop_table("file_chunks")
    op.drop_table("file_versions")
    op.drop_column("files", "text_hash")
    op.drop_column("files", "last_indexed_at")
    op.drop_column("files", "index_status")
    op.drop_column("files", "extraction_status")
    op.drop_column("files", "versioning_enabled")
    op.drop_column("files", "mode")
    op.drop_table("legal_acceptances")
    op.drop_table("usage_records")
    op.drop_table("payments")
    op.drop_table("subscriptions")
    op.drop_table("plans")
