"""add paper_trades table

Revision ID: 0004_add_paper_trades
Revises: 0003_add_trade_rejections
Create Date: 2026-05-09 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_add_paper_trades"
down_revision: str | None = "0003_add_trade_rejections"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "paper_trades",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("is_paper", sa.Boolean, nullable=False, server_default="true"),
        # Entry
        sa.Column("entry_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("entry_price", sa.Float, nullable=False),
        sa.Column("qty", sa.Float, nullable=False),
        sa.Column("direction", sa.String(8), nullable=False, server_default="long"),
        sa.Column("stop_loss", sa.Float, nullable=False),
        sa.Column("take_profit", sa.Float, nullable=False),
        sa.Column("entry_order_id", sa.String(64), nullable=True),
        # Exit
        sa.Column("exit_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exit_price", sa.Float, nullable=True),
        sa.Column("exit_reason", sa.String(32), nullable=True),
        sa.Column("exit_order_id", sa.String(64), nullable=True),
        sa.Column("realized_pnl", sa.Numeric(12, 4), nullable=True),
        # AI context
        sa.Column("regime", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("lean", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("llm_confidence", sa.Integer, nullable=False, server_default="0"),
        sa.Column("strategy_name", sa.String(64), nullable=False, server_default=""),
        sa.Column("strategy_version", sa.String(16), nullable=False, server_default="v1"),
        # Notes
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("rationale", sa.Text, nullable=True),
        # FKs
        sa.Column(
            "llm_log_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("llm_logs.id"),
            nullable=True,
        ),
        sa.Column(
            "feature_snapshot_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("feature_snapshots.id"),
            nullable=True,
        ),
    )
    op.create_index("ix_paper_trades_symbol_ts", "paper_trades", ["symbol", "entry_ts"])
    op.create_index("ix_paper_trades_regime", "paper_trades", ["regime"])


def downgrade() -> None:
    op.drop_index("ix_paper_trades_regime", table_name="paper_trades")
    op.drop_index("ix_paper_trades_symbol_ts", table_name="paper_trades")
    op.drop_table("paper_trades")
