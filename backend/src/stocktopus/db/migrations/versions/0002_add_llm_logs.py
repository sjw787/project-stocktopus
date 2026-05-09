"""add llm_logs table

Revision ID: 0002_add_llm_logs
Revises: 0001_initial_schema
Create Date: 2026-05-08 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_add_llm_logs"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_logs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("prompt_version", sa.String(16), nullable=False, server_default="v1"),
        sa.Column("model", sa.String(64), nullable=False, server_default=""),
        sa.Column("user_prompt", sa.Text, nullable=False),
        sa.Column("raw_response", sa.Text, nullable=False, server_default=""),
        sa.Column("parsed_ok", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("regime_assessment", postgresql.JSONB, nullable=True),
        sa.Column(
            "feature_snapshot_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("feature_snapshots.id"),
            nullable=True,
        ),
        sa.Column("prompt_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("latency_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_llm_logs_symbol_ts", "llm_logs", ["symbol", "ts"])
    op.create_index("ix_llm_logs_ts", "llm_logs", ["ts"])


def downgrade() -> None:
    op.drop_index("ix_llm_logs_ts", table_name="llm_logs")
    op.drop_index("ix_llm_logs_symbol_ts", table_name="llm_logs")
    op.drop_table("llm_logs")
