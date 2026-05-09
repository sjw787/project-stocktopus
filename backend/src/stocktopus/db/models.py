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


# ── LLM Logs ──────────────────────────────────────────────────────────────────


class LLMLog(Base):
    """Replay log for every LLM prompt/response pair.

    Persisted immediately after each LLM call regardless of parse outcome,
    enabling offline replay, cost audit, and training-data generation.
    """

    __tablename__ = "llm_logs"
    __table_args__ = (
        Index("ix_llm_logs_symbol_ts", "symbol", "ts"),
        Index("ix_llm_logs_ts", "ts"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(16), nullable=False, default="v1")
    model: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    user_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    raw_response: Mapped[str] = mapped_column(Text, nullable=False, default="")
    parsed_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    regime_assessment: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    feature_snapshot_id: Mapped[str | None] = mapped_column(
        ForeignKey("feature_snapshots.id"), nullable=True
    )
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    feature_snapshot: Mapped["FeatureSnapshot | None"] = relationship(
        "FeatureSnapshot", foreign_keys=[feature_snapshot_id]
    )


# ── Trade Rejections ──────────────────────────────────────────────────────────


class TradeRejection(Base):
    """Audit log for every trade blocked by the risk filter.

    Stored immediately when RiskFilter.evaluate() returns approved=False.
    """

    __tablename__ = "trade_rejections"
    __table_args__ = (
        Index("ix_trade_rejections_symbol_ts", "symbol", "ts"),
        Index("ix_trade_rejections_ts", "ts"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    strategy_name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    strategy_version: Mapped[str] = mapped_column(String(16), nullable=False, default="v1")

    # First failing check (for quick filtering)
    check_name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Full list of check results serialised as JSONB
    check_results: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # The proposed thesis that was rejected
    thesis_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    feature_snapshot_id: Mapped[str | None] = mapped_column(
        ForeignKey("feature_snapshots.id"), nullable=True
    )
    feature_snapshot: Mapped["FeatureSnapshot | None"] = relationship(
        "FeatureSnapshot", foreign_keys=[feature_snapshot_id]
    )
