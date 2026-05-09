"""Market context ingestion — computes and persists broad-market snapshots."""

from datetime import datetime

from loguru import logger
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from stocktopus.db.models import MarketContext as MarketContextRow
from stocktopus.providers.market_data import MarketDataProvider

# Breadth proxy symbols tracked every minute during RTH.
CONTEXT_SYMBOLS = ["SPY", "QQQ", "IWM", "DIA", "VIX", "XLK", "XLF", "XLE", "XLV", "XLI"]


async def snapshot_market_context(
    session: AsyncSession,
    provider: MarketDataProvider,
    ts: datetime,
    prev_close: dict[str, float] | None = None,
) -> MarketContextRow | None:
    """Fetch latest quotes for all context symbols and persist a MarketContext row.

    `prev_close` is a dict of symbol → previous session close price, used to
    compute gap%. If not provided, gap_pct will be None.

    Returns the persisted row, or None if the upsert hit a conflict (idempotent).
    """
    prices: dict[str, float] = {}
    for symbol in CONTEXT_SYMBOLS:
        try:
            quote = await provider.get_latest_quote(symbol)
            mid = (quote["bid"] + quote["ask"]) / 2
            prices[symbol] = mid
        except Exception as exc:
            logger.warning("Failed to fetch quote", symbol=symbol, error=str(exc))

    spy_price = prices.get("SPY")
    spy_gap_pct: float | None = None
    if spy_price is not None and prev_close and "SPY" in prev_close:
        prev = prev_close["SPY"]
        spy_gap_pct = (spy_price - prev) / prev * 100 if prev > 0 else None

    row_data = {
        "ts": ts,
        "vix": prices.get("VIX"),  # VIX not available on Alpaca IEX free tier; will be None
        "spy_gap_pct": spy_gap_pct,
        "spy_price": spy_price,
        "qqq_price": prices.get("QQQ"),
        "iwm_price": prices.get("IWM"),
        "dia_price": prices.get("DIA"),
        "xlk": prices.get("XLK"),
        "xlf": prices.get("XLF"),
        "xle": prices.get("XLE"),
        "xlv": prices.get("XLV"),
        "xli": prices.get("XLI"),
        # spy_above_vwap and spy_trend_1d require stored candle history;
        # they are computed and back-filled by the Phase 4 feature extraction module.
    }

    stmt = (
        insert(MarketContextRow)
        .values(**row_data)
        .on_conflict_do_nothing(constraint="uq_market_context_ts")
        .returning(MarketContextRow)
    )
    result = await session.execute(stmt)
    await session.commit()

    row = result.scalars().first()
    if row:
        logger.debug("Market context snapshot saved", ts=ts, vix=row_data.get("vix"))
    return row
