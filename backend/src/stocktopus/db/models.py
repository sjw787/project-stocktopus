"""ORM models — all database tables defined here and imported by Alembic."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ── Candles ───────────────────────────────────────────────────────────────────


class Candle(Base):
    """OHLCV price candles — stored in a TimescaleDB hypertable partitioned by ts."""

    __tablename__ = "candles"
    __table_args__ = (
        Index("ix_candles_symbol_tf_ts", "symbol", "timeframe", "ts"),
    )

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    timeframe: Mapped[str] = mapped_column(String(8), primary_key=True)  # "1m", "5m", "1d"
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False)
    vwap: Mapped[float | None] = mapped_column(Float, nullable=True)


# ── News Events ───────────────────────────────────────────────────────────────


class NewsEvent(Base):
    """Normalised news articles and macro events from all news providers."""

    __tablename__ = "news_events"
    __table_args__ = (
        UniqueConstraint("dedup_hash", name="uq_news_events_dedup_hash"),
        Index("ix_news_events_published_at", "published_at"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    symbols: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    categories: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    dedup_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


# ── Market Context ────────────────────────────────────────────────────────────


class MarketContext(Base):
    """Snapshot of broad market context computed every minute during RTH."""

    __tablename__ = "market_context"
    __table_args__ = (
        UniqueConstraint("ts", name="uq_market_context_ts"),
        Index("ix_market_context_ts", "ts"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Core breadth proxies
    vix: Mapped[float | None] = mapped_column(Float, nullable=True)
    spy_gap_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    spy_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    qqq_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    iwm_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    dia_price: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Sector ETF proxies (level prices)
    xlk: Mapped[float | None] = mapped_column(Float, nullable=True)  # tech
    xlf: Mapped[float | None] = mapped_column(Float, nullable=True)  # financials
    xle: Mapped[float | None] = mapped_column(Float, nullable=True)  # energy
    xlv: Mapped[float | None] = mapped_column(Float, nullable=True)  # health care
    xli: Mapped[float | None] = mapped_column(Float, nullable=True)  # industrials

    # Computed regime signals
    spy_above_vwap: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    spy_trend_1d: Mapped[str | None] = mapped_column(String(16), nullable=True)  # up/down/flat
    extra: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


# ── Feature Snapshots ─────────────────────────────────────────────────────────


class FeatureSnapshot(Base):
    """Immutable snapshot of all computed features at a decision point.

    Used for audit, replay, and training data generation.
    """

    __tablename__ = "feature_snapshots"
    __table_args__ = (Index("ix_feature_snapshots_symbol_ts", "symbol", "ts"),)

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    features: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )


# ── Trade Lots (for tax tracking) ─────────────────────────────────────────────


class TradeLot(Base):
    """Individual trade lots for tax tracking — P&L, holding period, wash-sale."""

    __tablename__ = "trade_lots"
    __table_args__ = (Index("ix_trade_lots_symbol_entry_date", "symbol", "entry_date"),)

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # user_id kept as nullable for future multi-user support
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    entry_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    exit_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    qty: Mapped[float] = mapped_column(Float, nullable=False)
    cost_basis: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    proceeds: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    realized_pnl: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    stcg_ltcg: Mapped[str | None] = mapped_column(String(8), nullable=True)  # "stcg"|"ltcg"
    wash_sale_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    disallowed_loss: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False, default=0)
    feature_snapshot_id: Mapped[str | None] = mapped_column(
        ForeignKey("feature_snapshots.id"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    feature_snapshot: Mapped["FeatureSnapshot | None"] = relationship("FeatureSnapshot")
