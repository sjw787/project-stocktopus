"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── candles ───────────────────────────────────────────────────────────────
    op.create_table(
        "candles",
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("timeframe", sa.String(8), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Float(), nullable=False),
        sa.Column("vwap", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("symbol", "timeframe", "ts"),
    )
    op.create_index("ix_candles_symbol_tf_ts", "candles", ["symbol", "timeframe", "ts"])
    # TimescaleDB: promote to hypertable partitioned by ts (no-op if not available)
    op.execute(
        "SELECT create_hypertable('candles', 'ts', if_not_exists => TRUE) "
        "FROM (SELECT 1) t WHERE EXISTS "
        "(SELECT 1 FROM pg_proc WHERE proname = 'create_hypertable')"
    )

    # ── news_events ───────────────────────────────────────────────────────────
    op.create_table(
        "news_events",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("symbols", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("categories", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("sentiment_score", sa.Float(), nullable=True),
        sa.Column("dedup_hash", sa.String(64), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedup_hash", name="uq_news_events_dedup_hash"),
    )
    op.create_index("ix_news_events_published_at", "news_events", ["published_at"])

    # ── market_context ────────────────────────────────────────────────────────
    op.create_table(
        "market_context",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("vix", sa.Float(), nullable=True),
        sa.Column("spy_gap_pct", sa.Float(), nullable=True),
        sa.Column("spy_price", sa.Float(), nullable=True),
        sa.Column("qqq_price", sa.Float(), nullable=True),
        sa.Column("iwm_price", sa.Float(), nullable=True),
        sa.Column("dia_price", sa.Float(), nullable=True),
        sa.Column("xlk", sa.Float(), nullable=True),
        sa.Column("xlf", sa.Float(), nullable=True),
        sa.Column("xle", sa.Float(), nullable=True),
        sa.Column("xlv", sa.Float(), nullable=True),
        sa.Column("xli", sa.Float(), nullable=True),
        sa.Column("spy_above_vwap", sa.Boolean(), nullable=True),
        sa.Column("spy_trend_1d", sa.String(16), nullable=True),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ts", name="uq_market_context_ts"),
    )
    op.create_index("ix_market_context_ts", "market_context", ["ts"])

    # ── feature_snapshots ─────────────────────────────────────────────────────
    op.create_table(
        "feature_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("features", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_feature_snapshots_symbol_ts", "feature_snapshots", ["symbol", "ts"])

    # ── trade_lots ────────────────────────────────────────────────────────────
    op.create_table(
        "trade_lots",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=True),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("entry_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exit_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("qty", sa.Float(), nullable=False),
        sa.Column("cost_basis", sa.Numeric(12, 4), nullable=False),
        sa.Column("proceeds", sa.Numeric(12, 4), nullable=True),
        sa.Column("realized_pnl", sa.Numeric(12, 4), nullable=True),
        sa.Column("stcg_ltcg", sa.String(8), nullable=True),
        sa.Column("wash_sale_flag", sa.Boolean(), nullable=False),
        sa.Column("disallowed_loss", sa.Numeric(12, 4), nullable=False),
        sa.Column("feature_snapshot_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["feature_snapshot_id"], ["feature_snapshots.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trade_lots_symbol_entry_date", "trade_lots", ["symbol", "entry_date"])


def downgrade() -> None:
    op.drop_table("trade_lots")
    op.drop_table("feature_snapshots")
    op.drop_table("market_context")
    op.drop_table("news_events")
    op.drop_table("candles")
