"""add trade_rejections table

Revision ID: 0003_add_trade_rejections
Revises: 0002_add_llm_logs
Create Date: 2026-05-09 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_add_trade_rejections"
down_revision: str | None = "0002_add_llm_logs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trade_rejections",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("strategy_name", sa.String(64), nullable=False, server_default=""),
        sa.Column("strategy_version", sa.String(16), nullable=False, server_default="v1"),
        sa.Column("check_name", sa.String(64), nullable=False, server_default=""),
        sa.Column("reason", sa.Text, nullable=False, server_default=""),
        sa.Column("check_results", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("thesis_snapshot", postgresql.JSONB, nullable=True),
        sa.Column(
            "feature_snapshot_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("feature_snapshots.id"),
            nullable=True,
        ),
    )
    op.create_index("ix_trade_rejections_symbol_ts", "trade_rejections", ["symbol", "ts"])
    op.create_index("ix_trade_rejections_ts", "trade_rejections", ["ts"])


def downgrade() -> None:
    op.drop_index("ix_trade_rejections_ts", table_name="trade_rejections")
    op.drop_index("ix_trade_rejections_symbol_ts", table_name="trade_rejections")
    op.drop_table("trade_rejections")
