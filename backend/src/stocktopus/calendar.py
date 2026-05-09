"""Trading calendar utilities — wraps pandas-market-calendars for session awareness.

Provides helpers for:
- Checking if the market is currently open (regular trading hours only).
- Iterating over valid trading days in a date range.
- Detecting early closes and market halts.
- Calculating session open/close times (9:30am–4:00pm ET, RTH only).
"""

from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pandas_market_calendars as mcal
from loguru import logger

# All times are evaluated in US/Eastern per NYSE rules.
EXCHANGE = "NYSE"
RTH_OPEN_TIME = "09:30"
RTH_CLOSE_TIME = "16:00"


def _get_calendar() -> mcal.MarketCalendar:
    return mcal.get_calendar(EXCHANGE)


def get_trading_schedule(start: date, end: date) -> pd.DataFrame:
    """Return a DataFrame of valid trading sessions between start and end (inclusive).

    Columns: market_open, market_close (timezone-aware, UTC).
    """
    cal = _get_calendar()
    schedule = cal.schedule(
        start_date=start.isoformat(),
        end_date=end.isoformat(),
    )
    return schedule


def is_market_open(dt: datetime | None = None) -> bool:
    """Return True if the NYSE is in a regular trading session at `dt` (default: now)."""
    now = dt or datetime.now(tz=UTC)
    cal = _get_calendar()
    schedule = cal.schedule(
        start_date=now.date().isoformat(),
        end_date=now.date().isoformat(),
    )
    if schedule.empty:
        return False
    return mcal.date_range(schedule, frequency="1min").size > 0 and _within_session(now, schedule)


def _within_session(dt: datetime, schedule: pd.DataFrame) -> bool:
    if schedule.empty:
        return False
    row = schedule.iloc[0]
    open_ts: pd.Timestamp = row["market_open"]
    close_ts: pd.Timestamp = row["market_close"]
    dt_utc = dt.astimezone(UTC).replace(tzinfo=None)
    return open_ts.tz_localize(None) <= dt_utc <= close_ts.tz_localize(None)  # type: ignore[no-any-return]


def get_trading_days(start: date, end: date) -> list[date]:
    """Return a list of valid NYSE trading days between start and end (inclusive)."""
    schedule = get_trading_schedule(start, end)
    return [ts.date() for ts in schedule.index]


def is_trading_day(d: date) -> bool:
    """Return True if `d` is a valid NYSE trading day."""
    schedule = get_trading_schedule(d, d)
    return not schedule.empty


def session_open(d: date) -> datetime | None:
    """Return the RTH open time (UTC) for the given trading day, or None if not a trading day."""
    schedule = get_trading_schedule(d, d)
    if schedule.empty:
        return None
    ts: pd.Timestamp = schedule.iloc[0]["market_open"]
    return ts.to_pydatetime().astimezone(UTC)


def session_close(d: date) -> datetime | None:
    """Return the RTH close time (UTC) for the given trading day, or None if not a trading day."""
    schedule = get_trading_schedule(d, d)
    if schedule.empty:
        return None
    ts: pd.Timestamp = schedule.iloc[0]["market_close"]
    return ts.to_pydatetime().astimezone(UTC)


def next_trading_day(d: date) -> date:
    """Return the next NYSE trading day after `d`."""
    candidate = d + timedelta(days=1)
    for _ in range(14):  # handle long holiday stretches
        if is_trading_day(candidate):
            return candidate
        candidate += timedelta(days=1)
    raise RuntimeError(f"Could not find next trading day within 14 days of {d}")


def previous_trading_day(d: date) -> date:
    """Return the NYSE trading day immediately before `d`."""
    candidate = d - timedelta(days=1)
    for _ in range(14):
        if is_trading_day(candidate):
            return candidate
        candidate -= timedelta(days=1)
    raise RuntimeError(f"Could not find previous trading day within 14 days of {d}")


def log_next_session() -> None:
    """Log the next upcoming session open time (useful on startup)."""
    today = date.today()
    if is_trading_day(today):
        open_dt = session_open(today)
        close_dt = session_close(today)
        logger.info("Today is a trading day", open=str(open_dt), close=str(close_dt))
    else:
        nxt = next_trading_day(today)
        open_dt = session_open(nxt)
        logger.info("Next trading day", date=str(nxt), open=str(open_dt))
