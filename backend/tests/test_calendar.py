"""Tests for trading calendar utilities."""

from datetime import date

from stocktopus.calendar import (
    get_trading_days,
    is_trading_day,
    next_trading_day,
    previous_trading_day,
    session_close,
    session_open,
)

# Use known fixed dates to avoid flaky time-dependent tests.
# 2024-01-02 (Tuesday) was the first trading day of 2024.
# 2024-01-01 (Monday) was New Year's Day — NYSE closed.
# 2024-11-28 (Thursday) was Thanksgiving — NYSE closed.


def test_new_years_day_not_trading() -> None:
    assert is_trading_day(date(2024, 1, 1)) is False


def test_first_trading_day_of_2024() -> None:
    assert is_trading_day(date(2024, 1, 2)) is True


def test_thanksgiving_not_trading() -> None:
    assert is_trading_day(date(2024, 11, 28)) is False


def test_get_trading_days_range() -> None:
    days = get_trading_days(date(2024, 1, 1), date(2024, 1, 5))
    # 1/1 is NYD (closed), 1/2–1/5 are Tue–Fri (open)
    assert date(2024, 1, 1) not in days
    assert date(2024, 1, 2) in days
    assert date(2024, 1, 3) in days
    assert date(2024, 1, 4) in days
    assert date(2024, 1, 5) in days


def test_session_open_returns_none_for_holiday() -> None:
    assert session_open(date(2024, 1, 1)) is None


def test_session_open_returns_930_et() -> None:
    open_dt = session_open(date(2024, 1, 2))
    assert open_dt is not None
    # 9:30am ET = 14:30 UTC in winter (EST = UTC-5)
    assert open_dt.hour == 14
    assert open_dt.minute == 30


def test_session_close_returns_4pm_et() -> None:
    close_dt = session_close(date(2024, 1, 2))
    assert close_dt is not None
    # 4:00pm ET = 21:00 UTC in winter
    assert close_dt.hour == 21
    assert close_dt.minute == 0


def test_next_trading_day_skips_weekend() -> None:
    # 2024-01-05 is Friday; next trading day should be Monday 2024-01-08
    nxt = next_trading_day(date(2024, 1, 5))
    assert nxt == date(2024, 1, 8)


def test_next_trading_day_skips_holiday() -> None:
    # 2024-12-31 (Tue) → 2025-01-02 (Thu) skipping NYD
    nxt = next_trading_day(date(2024, 12, 31))
    assert nxt == date(2025, 1, 2)


def test_previous_trading_day_skips_weekend() -> None:
    # 2024-01-08 is Monday; previous trading day should be Friday 2024-01-05
    prev = previous_trading_day(date(2024, 1, 8))
    assert prev == date(2024, 1, 5)
