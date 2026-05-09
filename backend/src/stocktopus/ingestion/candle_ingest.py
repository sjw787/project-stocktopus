"""Candle ingestion service — backfill and live ingest with derived feature computation."""

from datetime import datetime, timedelta

import pandas as pd
from loguru import logger
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from stocktopus.db.models import Candle as CandleRow
from stocktopus.providers.market_data import Candle, MarketDataProvider

# Timeframes fetched and stored for each symbol.
INGEST_TIMEFRAMES = ["1m", "5m"]

# Max days to fetch in a single API call (avoid large payloads).
BATCH_DAYS = 30


async def backfill(
    session: AsyncSession,
    provider: MarketDataProvider,
    symbol: str,
    start: datetime,
    end: datetime,
    timeframes: list[str] | None = None,
) -> dict[str, int]:
    """Backfill candles for `symbol` between `start` and `end`.

    Returns a dict of {timeframe: rows_inserted}.
    """
    tfs = timeframes or INGEST_TIMEFRAMES
    results: dict[str, int] = {}

    for tf in tfs:
        inserted = 0
        cursor = start
        while cursor < end:
            batch_end = min(cursor + timedelta(days=BATCH_DAYS), end)
            logger.info(
                "Backfilling candles",
                symbol=symbol,
                tf=tf,
                start=cursor.date(),
                end=batch_end.date(),
            )
            candles = await provider.get_candles(symbol, tf, cursor, batch_end)
            if candles:
                inserted += await _upsert_candles(session, candles)
            else:
                logger.warning(
                    "API returned 0 bars for window",
                    symbol=symbol,
                    tf=tf,
                    start=cursor.date(),
                    end=batch_end.date(),
                )
            cursor = batch_end
        results[tf] = inserted
        logger.info("Backfill complete", symbol=symbol, tf=tf, inserted=inserted)

    return results


async def _upsert_candles(session: AsyncSession, candles: list[Candle]) -> int:
    """Bulk-upsert candles using ON CONFLICT DO NOTHING."""
    if not candles:
        return 0

    rows = [
        {
            "symbol": c.symbol,
            "timeframe": c.timeframe,
            "ts": c.ts,
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume,
            "vwap": c.vwap,
        }
        for c in candles
    ]

    stmt = (
        insert(CandleRow)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["symbol", "timeframe", "ts"])
    )
    result = await session.execute(stmt)
    await session.commit()
    return max(0, result.rowcount)


async def compute_derived_features(
    session: AsyncSession,
    symbol: str,
    as_of: datetime,
    lookback_days: int = 252,
) -> dict[str, float | None]:
    """Compute derived price features (SMAs, ATR, RVOL) from stored 1m candles.

    Returns a flat dict of feature_name → value, ready for FeatureSnapshot.
    """
    start = as_of - timedelta(days=lookback_days)

    stmt = (
        select(CandleRow)
        .where(
            CandleRow.symbol == symbol,
            CandleRow.timeframe == "1d",
            CandleRow.ts >= start,
            CandleRow.ts <= as_of,
        )
        .order_by(CandleRow.ts)
    )
    rows = (await session.execute(stmt)).scalars().all()

    if not rows:
        logger.warning("No daily candles for derived features", symbol=symbol)
        return {}

    df = pd.DataFrame(
        {
            "ts": [r.ts for r in rows],
            "open": [r.open for r in rows],
            "high": [r.high for r in rows],
            "low": [r.low for r in rows],
            "close": [r.close for r in rows],
            "volume": [r.volume for r in rows],
        }
    ).set_index("ts")

    features: dict[str, float | None] = {}

    # Simple moving averages
    for window in [20, 50, 200]:
        key = f"sma_{window}"
        if len(df) >= window:
            features[key] = float(df["close"].rolling(window).mean().iloc[-1])
        else:
            features[key] = None

    # Average True Range (14-period)
    if len(df) >= 14:
        prev_close = df["close"].shift(1)
        tr = pd.concat(
            [
                df["high"] - df["low"],
                (df["high"] - prev_close).abs(),
                (df["low"] - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        features["atr_14"] = float(tr.rolling(14).mean().iloc[-1])
    else:
        features["atr_14"] = None

    # Relative Volume (today vs 20-day average)
    if len(df) >= 20:
        avg_vol = df["volume"].rolling(20).mean().iloc[-1]
        today_vol = df["volume"].iloc[-1]
        features["rvol"] = float(today_vol / avg_vol) if avg_vol > 0 else None
    else:
        features["rvol"] = None

    # Latest close and gap vs previous close
    if len(df) >= 2:
        prev = df["close"].iloc[-2]
        curr = df["close"].iloc[-1]
        features["close"] = float(curr)
        features["gap_pct"] = float((curr - prev) / prev * 100) if prev > 0 else None
    elif len(df) == 1:
        features["close"] = float(df["close"].iloc[-1])
        features["gap_pct"] = None

    return features
