"""enable pgvector extension for PostgreSQL deployments

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-01
"""
from alembic import op


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    # Keep downgrade non-destructive: do not remove shared extensions automatically.
    return
