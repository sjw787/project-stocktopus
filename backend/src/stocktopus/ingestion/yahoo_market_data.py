"""Yahoo Finance market data provider — free historical OHLCV via yfinance.

Limitations vs Alpaca:
- 1m bars: last 7 days only
- 5m bars: last 60 days only
- 1d bars: full history (years)
- No live streaming (raises NotImplementedError)
- No bid/ask quotes (get_latest_quote returns last close as mid)
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from loguru import logger

from stocktopus.providers.market_data import Candle, MarketDataProvider

_YF_TF_MAP: dict[str, str] = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "60m",
    "1d": "1d",
    "1w": "1wk",
}


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


class YahooFinanceMarketData(MarketDataProvider):
    """Yahoo Finance implementation of MarketDataProvider.

    Uses the yfinance library (no API key required).
    Best for historical daily bars and short-window intraday backfills.
    """

    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[Candle]:
        import yfinance as yf

        tf = _YF_TF_MAP.get(timeframe)
        if tf is None:
            raise ValueError(f"Unsupported timeframe '{timeframe}'. Use: {list(_YF_TF_MAP)}")

        logger.debug(
            "Fetching candles via Yahoo Finance",
            symbol=symbol, tf=timeframe, start=start.date(), end=end.date(),
        )

        # yfinance Ticker.history is synchronous — run in thread.
        def _fetch() -> list[Candle]:
            import pandas as pd

            ticker = yf.Ticker(symbol)
            df = ticker.history(
                interval=tf,
                start=_to_utc(start),
                end=_to_utc(end),
                auto_adjust=True,
                actions=False,
            )
            if df.empty:
                logger.warning(
                    "No bars returned from Yahoo Finance",
                    symbol=symbol, tf=timeframe,
                )
                return []

            # Ensure index is UTC-aware datetime.
            if df.index.tz is None:
                df.index = df.index.tz_localize("UTC")
            else:
                df.index = df.index.tz_convert("UTC")

            candles: list[Candle] = []
            for ts, row in df.iterrows():
                candles.append(
                    Candle(
                        symbol=symbol,
                        timeframe=timeframe,
                        ts=pd.Timestamp(ts).to_pydatetime(),
                        open=float(row["Open"]),
                        high=float(row["High"]),
                        low=float(row["Low"]),
                        close=float(row["Close"]),
                        volume=float(row["Volume"]),
                        vwap=None,  # Yahoo doesn't provide VWAP
                    )
                )
            return candles

        result = await asyncio.to_thread(_fetch)
        logger.debug("Fetched candles via Yahoo Finance", symbol=symbol, count=len(result))
        return result

    async def stream_candles(
        self,
        symbols: list[str],
        timeframe: str,
    ) -> AsyncIterator[Candle]:
        raise NotImplementedError(
            "Yahoo Finance does not support live streaming. Use AlpacaMarketData for live data."
        )

    async def get_latest_quote(self, symbol: str) -> dict[str, float]:
        """Returns last close as both bid and ask (no real-time quote available)."""
        import yfinance as yf

        def _fetch() -> dict[str, float]:
            ticker = yf.Ticker(symbol)
            info = ticker.fast_info
            price = float(info.last_price or info.previous_close or 0)
            return {"bid": price, "ask": price, "bid_size": 0.0, "ask_size": 0.0}

        return await asyncio.to_thread(_fetch)
