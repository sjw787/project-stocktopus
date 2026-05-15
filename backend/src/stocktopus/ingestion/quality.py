"""Data quality checks — validate stored candles for gaps, ordering, and sane OHLC."""

from datetime import date
from typing import NamedTuple

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stocktopus.calendar import get_trading_days, session_close, session_open
from stocktopus.db.models import Candle as CandleRow


class QualityReport(NamedTuple):
    symbol: str
    timeframe: str
    start: date
    end: date
    expected_sessions: int
    sessions_with_data: int
    missing_sessions: list[date]
    ohlc_violations: int
    negative_volume_count: int
    bar_count_violations: int  # sessions where bar count differs from expected
    passed: bool


def _expected_bars(timeframe: str) -> int | None:
    """Return expected RTH bar count per session for known timeframes, else None."""
    return {
        "1m": 390,  # 9:30–16:00 = 390 minutes
        "5m": 78,  # 390 / 5
        "15m": 26,  # 390 / 15
        "30m": 13,  # 390 / 30
        "1h": 7,  # 390 / 60, rounded (6.5)
        "1d": 1,
    }.get(timeframe)


async def check_candle_quality(
    session: AsyncSession,
    symbol: str,
    timeframe: str,
    start: date,
    end: date,
) -> QualityReport:
    """Run integrity checks on stored candles for the given symbol/timeframe/range."""
    trading_days = get_trading_days(start, end)
    expected_count = _expected_bars(timeframe)
    sessions_with_data: set[date] = set()
    missing_sessions: list[date] = []
    ohlc_violations = 0
    negative_volume_count = 0
    bar_count_violations = 0

    for td in trading_days:
        open_dt = session_open(td)
        close_dt = session_close(td)
        if open_dt is None or close_dt is None:
            continue

        stmt = (
            select(CandleRow)
            .where(
                CandleRow.symbol == symbol,
                CandleRow.timeframe == timeframe,
                CandleRow.ts >= open_dt,
                CandleRow.ts <= close_dt,
            )
            .order_by(CandleRow.ts)
        )
        rows = (await session.execute(stmt)).scalars().all()

        if not rows:
            missing_sessions.append(td)
            continue

        sessions_with_data.add(td)

        # Check bar count matches expected for this timeframe.
        if expected_count is not None and len(rows) != expected_count:
            bar_count_violations += 1
            logger.debug(
                "Bar count mismatch",
                date=td,
                symbol=symbol,
                expected=expected_count,
                actual=len(rows),
            )

        for row in rows:
            # OHLC sanity: high >= max(open, close), low <= min(open, close)
            if row.high < max(row.open, row.close) or row.low > min(row.open, row.close):
                ohlc_violations += 1
            if row.volume < 0:
                negative_volume_count += 1

    passed = (
        len(missing_sessions) == 0 and ohlc_violations == 0 and negative_volume_count == 0 and bar_count_violations == 0
    )

    report = QualityReport(
        symbol=symbol,
        timeframe=timeframe,
        start=start,
        end=end,
        expected_sessions=len(trading_days),
        sessions_with_data=len(sessions_with_data),
        missing_sessions=missing_sessions,
        ohlc_violations=ohlc_violations,
        negative_volume_count=negative_volume_count,
        bar_count_violations=bar_count_violations,
        passed=passed,
    )

    if passed:
        logger.info(
            "Data quality check passed",
            symbol=symbol,
            tf=timeframe,
            sessions=len(trading_days),
        )
    else:
        logger.warning(
            "Data quality check FAILED",
            symbol=symbol,
            tf=timeframe,
            missing=len(missing_sessions),
            ohlc_violations=ohlc_violations,
            bar_count_violations=bar_count_violations,
        )

    return report
