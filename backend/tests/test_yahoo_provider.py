"""Unit tests for Yahoo Finance market data provider."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from stocktopus.ingestion.yahoo_market_data import YahooFinanceMarketData, _to_utc
from stocktopus.providers.market_data import Candle

# ── _to_utc helper ────────────────────────────────────────────────────────────


def test_to_utc_naive_datetime_gets_utc_tzinfo() -> None:
    naive = datetime(2024, 1, 2, 9, 30)
    result = _to_utc(naive)
    assert result.tzinfo is not None
    assert result.tzinfo == UTC


def test_to_utc_aware_datetime_converted_to_utc() -> None:
    from datetime import timedelta, timezone

    et = timezone(timedelta(hours=-5))
    aware = datetime(2024, 1, 2, 9, 30, tzinfo=et)
    result = _to_utc(aware)
    assert result.tzinfo == UTC
    assert result.hour == 14  # 9:30 ET → 14:30 UTC


# ── get_candles ───────────────────────────────────────────────────────────────


def _make_ticker_mock(df: pd.DataFrame) -> MagicMock:
    """Build a mock yf.Ticker whose .history() returns df."""
    ticker = MagicMock()
    ticker.history.return_value = df
    return ticker


def _spy_df(n: int = 3, interval_minutes: int = 1) -> pd.DataFrame:
    """Return a minimal OHLCV DataFrame with a UTC-aware DatetimeIndex."""
    base = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
    idx = pd.date_range(base, periods=n, freq=f"{interval_minutes}min", tz="UTC")
    return pd.DataFrame(
        {
            "Open": [470.0 + i for i in range(n)],
            "High": [471.0 + i for i in range(n)],
            "Low": [469.0 + i for i in range(n)],
            "Close": [470.5 + i for i in range(n)],
            "Volume": [1_000_000.0 + i * 100_000 for i in range(n)],
        },
        index=idx,
    )


@pytest.mark.asyncio
async def test_get_candles_returns_candle_list() -> None:
    df = _spy_df(n=3)
    provider = YahooFinanceMarketData()

    with patch("yfinance.Ticker", return_value=_make_ticker_mock(df)):
        candles = await provider.get_candles(
            symbol="SPY",
            timeframe="1m",
            start=datetime(2024, 1, 2, tzinfo=UTC),
            end=datetime(2024, 1, 3, tzinfo=UTC),
        )

    assert len(candles) == 3
    assert all(isinstance(c, Candle) for c in candles)
    assert candles[0].symbol == "SPY"
    assert candles[0].timeframe == "1m"
    assert candles[0].open == pytest.approx(470.0)
    assert candles[0].vwap is None  # Yahoo never sets vwap


@pytest.mark.asyncio
async def test_get_candles_empty_dataframe_returns_empty_list() -> None:
    empty_df = pd.DataFrame()
    provider = YahooFinanceMarketData()

    with patch("yfinance.Ticker", return_value=_make_ticker_mock(empty_df)):
        candles = await provider.get_candles(
            symbol="SPY",
            timeframe="1d",
            start=datetime(2024, 1, 2, tzinfo=UTC),
            end=datetime(2024, 1, 5, tzinfo=UTC),
        )

    assert candles == []


@pytest.mark.asyncio
async def test_get_candles_maps_timeframe_to_yfinance_interval() -> None:
    df = _spy_df(n=1)
    provider = YahooFinanceMarketData()
    ticker_mock = _make_ticker_mock(df)

    with patch("yfinance.Ticker", return_value=ticker_mock):
        await provider.get_candles(
            symbol="SPY",
            timeframe="1h",
            start=datetime(2024, 1, 2, tzinfo=UTC),
            end=datetime(2024, 1, 3, tzinfo=UTC),
        )

    # "1h" should be mapped to "60m" for yfinance
    _, kwargs = ticker_mock.history.call_args
    assert (
        kwargs.get("interval") == "60m"
        or ticker_mock.history.call_args[0][0] == "60m"
        or ticker_mock.history.call_args_list[0].kwargs.get("interval") == "60m"
    )


@pytest.mark.asyncio
async def test_get_candles_unsupported_timeframe_raises() -> None:
    provider = YahooFinanceMarketData()
    with pytest.raises(ValueError, match="Unsupported timeframe"):
        await provider.get_candles(
            symbol="SPY",
            timeframe="999m",
            start=datetime(2024, 1, 2, tzinfo=UTC),
            end=datetime(2024, 1, 3, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_get_candles_naive_timezone_index_is_localized() -> None:
    """If yfinance returns naive timestamps, the provider should handle them."""
    df = _spy_df(n=2)
    # Strip timezone from index to simulate naive timestamps.
    df.index = df.index.tz_localize(None)
    provider = YahooFinanceMarketData()

    with patch("yfinance.Ticker", return_value=_make_ticker_mock(df)):
        candles = await provider.get_candles(
            symbol="SPY",
            timeframe="5m",
            start=datetime(2024, 1, 2, tzinfo=UTC),
            end=datetime(2024, 1, 3, tzinfo=UTC),
        )

    assert len(candles) == 2
    for c in candles:
        assert c.ts.tzinfo is not None


# ── stream_candles raises NotImplementedError ─────────────────────────────────


@pytest.mark.asyncio
async def test_stream_candles_raises_not_implemented() -> None:
    provider = YahooFinanceMarketData()
    with pytest.raises(NotImplementedError, match="Yahoo Finance does not support live streaming"):
        await provider.stream_candles(symbols=["SPY"], timeframe="1m")


# ── get_latest_quote ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_latest_quote_returns_bid_ask_from_last_price() -> None:
    provider = YahooFinanceMarketData()
    ticker_mock = MagicMock()
    ticker_mock.fast_info.last_price = 471.23
    ticker_mock.fast_info.previous_close = 469.00

    with patch("yfinance.Ticker", return_value=ticker_mock):
        quote = await provider.get_latest_quote("SPY")

    assert quote["bid"] == pytest.approx(471.23)
    assert quote["ask"] == pytest.approx(471.23)
    assert quote["bid_size"] == 0.0
    assert quote["ask_size"] == 0.0


@pytest.mark.asyncio
async def test_get_latest_quote_falls_back_to_previous_close() -> None:
    provider = YahooFinanceMarketData()
    ticker_mock = MagicMock()
    ticker_mock.fast_info.last_price = None
    ticker_mock.fast_info.previous_close = 468.50

    with patch("yfinance.Ticker", return_value=ticker_mock):
        quote = await provider.get_latest_quote("SPY")

    assert quote["bid"] == pytest.approx(468.50)
