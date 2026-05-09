"""Feature snapshot computation and persistence.

Queries stored candles, runs the pure-function compute module, and persists
a FeatureSnapshot row.  Also provides helpers to back-fill computed signals
(spy_above_vwap, spy_trend_1d) on existing MarketContext rows.
"""

from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime

from loguru import logger
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from stocktopus.db.models import Candle, MarketContext
from stocktopus.db.models import FeatureSnapshot as FeatureSnapshotRow
from stocktopus.features.compute import (
    OHLCVBar,
    atr,
    rvol,
    sma,
    spy_above_vwap,
    spy_trend,
    vwap,
)
from stocktopus.features.models import FeatureVector

# How many daily candles to pull for MA/ATR computation.
_DAILY_LOOKBACK = 220  # 200 SMA needs 200 bars; 20 extra for warm-up
# How many intraday 1m bars to pull for VWAP and RVOL.
_INTRADAY_LOOKBACK = 390  # one full RTH session


async def compute_and_persist(
    session: AsyncSession,
    symbol: str,
    ts: datetime | None = None,
) -> FeatureVector:
    """Compute features for `symbol` at `ts` (defaults to now) and persist to DB.

    Returns the in-memory FeatureVector for immediate use.
    """
    ts = ts or datetime.now(UTC)

    # ── Fetch daily candles ────────────────────────────────────────────────────
    daily_stmt = (
        select(Candle)
        .where(
            Candle.symbol == symbol,
            Candle.timeframe == "1d",
            Candle.ts <= ts,
        )
        .order_by(Candle.ts.desc())
        .limit(_DAILY_LOOKBACK)
    )
    daily_rows = (await session.execute(daily_stmt)).scalars().all()
    daily_bars = [
        OHLCVBar(r.open, r.high, r.low, r.close, r.volume, r.vwap)
        for r in reversed(daily_rows)  # oldest-first
    ]
    daily_closes = [b.close for b in daily_bars]

    # ── Fetch intraday (1m) candles for current session ───────────────────────
    intraday_stmt = (
        select(Candle)
        .where(
            Candle.symbol == symbol,
            Candle.timeframe == "1m",
            Candle.ts <= ts,
        )
        .order_by(Candle.ts.desc())
        .limit(_INTRADAY_LOOKBACK)
    )
    intraday_rows = (await session.execute(intraday_stmt)).scalars().all()
    intraday_bars = [
        OHLCVBar(r.open, r.high, r.low, r.close, r.volume, r.vwap)
        for r in reversed(intraday_rows)  # oldest-first
    ]

    # ── Latest bar snapshot ───────────────────────────────────────────────────
    last_daily = daily_bars[-1] if daily_bars else None
    last_intraday = intraday_bars[-1] if intraday_bars else None
    latest_close = last_intraday or last_daily
    close: float | None = latest_close.close if latest_close else None

    # ── Compute features ──────────────────────────────────────────────────────
    sma_20 = sma(daily_closes, 20)
    sma_50 = sma(daily_closes, 50)
    sma_200 = sma(daily_closes, 200)
    atr_14 = atr(daily_bars, 14)
    atr_pct = (atr_14 / close * 100) if (atr_14 is not None and close) else None
    vwap_val = vwap(intraday_bars)
    above = spy_above_vwap(intraday_bars)
    trend = spy_trend(daily_closes)

    # RVOL: compare current bar volume to same-bar average across prior days.
    # Simplified: use average of most recent 20 daily volumes as proxy.
    rvol_val: float | None = None
    if last_intraday is not None and len(daily_bars) >= 20:
        avg_daily_vols = [b.volume for b in daily_bars[-20:]]
        # Scale by 390 (bars/session) as a rough same-bar proxy.
        per_bar_avgs = [v / 390 for v in avg_daily_vols]
        rvol_val = rvol(last_intraday.volume, per_bar_avgs)

    # Gap % from previous daily close.
    gap: float | None = None
    if len(daily_bars) >= 2 and last_daily:
        prev_close_price = daily_bars[-2].close
        if prev_close_price > 0:
            gap = (last_daily.open - prev_close_price) / prev_close_price * 100

    fv = FeatureVector(
        symbol=symbol,
        ts=ts,
        close=close or 0.0,
        open=last_daily.open if last_daily else None,
        high=last_daily.high if last_daily else None,
        low=last_daily.low if last_daily else None,
        volume=last_daily.volume if last_daily else None,
        sma_20d=sma_20,
        sma_50d=sma_50,
        sma_200d=sma_200,
        vwap=vwap_val,
        above_vwap=above,
        atr_14d=atr_14,
        atr_pct=atr_pct,
        rvol=rvol_val,
        trend_1d=trend,
        gap_pct=gap,
    )

    # ── Persist FeatureSnapshot row ───────────────────────────────────────────
    # PostgreSQL JSONB rejects NaN/Inf — sanitize all float values to None.
    def _sanitize(obj: object) -> object:
        if isinstance(obj, float) and not math.isfinite(obj):
            return None
        if isinstance(obj, dict):
            return {k: _sanitize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_sanitize(v) for v in obj]
        return obj

    features_json = _sanitize(fv.model_dump(mode="json"))

    stmt = (
        insert(FeatureSnapshotRow)
        .values(
            id=str(uuid.uuid4()),
            symbol=symbol,
            ts=ts,
            features=features_json,
        )
        .on_conflict_do_nothing()
    )
    await session.execute(stmt)
    await session.commit()
    logger.debug("Feature snapshot persisted", symbol=symbol, ts=ts)
    return fv


async def backfill_market_context_signals(
    session: AsyncSession,
    symbol: str = "SPY",
    batch_size: int = 500,
) -> int:
    """Back-fill spy_above_vwap and spy_trend_1d on MarketContext rows that lack them.

    Uses batched candle loading: 1 daily query + 1 intraday query per unique date
    in the batch, instead of 2 queries per row.

    Returns the number of rows updated.
    """
    from datetime import date as DateType
    from datetime import time

    # ── 1. Fetch batch of context rows that still need signals ────────────────
    ctx_stmt = (
        select(MarketContext)
        .where(
            MarketContext.spy_above_vwap.is_(None),
            MarketContext.spy_trend_1d.is_(None),
        )
        .order_by(MarketContext.ts.asc())
        .limit(batch_size)
    )
    ctx_rows = (await session.execute(ctx_stmt)).scalars().all()
    if not ctx_rows:
        return 0

    max_ts = ctx_rows[-1].ts

    # ── 2. Load daily candles once (220 bars up to the latest row in batch) ───
    daily_stmt = (
        select(Candle)
        .where(
            Candle.symbol == symbol,
            Candle.timeframe == "1d",
            Candle.ts <= max_ts,
        )
        .order_by(Candle.ts.asc())
        .limit(_DAILY_LOOKBACK)
    )
    all_daily_rows = (await session.execute(daily_stmt)).scalars().all()
    all_daily: list[tuple[DateType, OHLCVBar]] = [
        (r.ts.date(), OHLCVBar(r.open, r.high, r.low, r.close, r.volume, r.vwap))
        for r in all_daily_rows
    ]

    # ── 3. Load intraday candles once per unique date in the batch ────────────
    unique_dates = sorted({r.ts.date() for r in ctx_rows})
    intraday_by_date: dict[DateType, list[tuple[datetime, OHLCVBar]]] = {}
    for d in unique_dates:
        day_start = datetime.combine(d, time.min).replace(tzinfo=UTC)
        day_end = datetime.combine(d, time.max).replace(tzinfo=UTC)
        intra_stmt = (
            select(Candle)
            .where(
                Candle.symbol == symbol,
                Candle.timeframe == "1m",
                Candle.ts >= day_start,
                Candle.ts <= day_end,
            )
            .order_by(Candle.ts.asc())
        )
        intra_rows = (await session.execute(intra_stmt)).scalars().all()
        intraday_by_date[d] = [
            (r.ts, OHLCVBar(r.open, r.high, r.low, r.close, r.volume, r.vwap))
            for r in intra_rows
        ]

    # ── 4. Compute signals for each row using pre-loaded data (in-memory) ─────
    updated = 0
    for ctx in ctx_rows:
        d = ctx.ts.date()

        daily_bars = [bar for dt, bar in all_daily if dt <= d]
        daily_closes = [b.close for b in daily_bars]

        intraday_bars = [bar for ts, bar in intraday_by_date.get(d, []) if ts <= ctx.ts]

        ctx.spy_above_vwap = spy_above_vwap(intraday_bars)
        ctx.spy_trend_1d = spy_trend(daily_closes)
        updated += 1

    # ── 5. Single commit flushes all row updates ──────────────────────────────
    await session.commit()
    logger.info(
        "Back-filled market context signals",
        symbol=symbol,
        rows_updated=updated,
        dates_loaded=len(unique_dates),
    )
    return updated
