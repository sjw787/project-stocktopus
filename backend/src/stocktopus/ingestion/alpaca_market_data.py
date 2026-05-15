"""Alpaca market data provider — implements MarketDataProvider using alpaca-py."""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from datetime import datetime

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.live import StockDataStream
from alpaca.data.models import Bar
from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from loguru import logger

from stocktopus.providers.market_data import Candle, MarketDataProvider

_TF_MAP: dict[str, TimeFrame] = {
    "1m": TimeFrame(1, TimeFrameUnit.Minute),
    "5m": TimeFrame(5, TimeFrameUnit.Minute),
    "15m": TimeFrame(15, TimeFrameUnit.Minute),
    "30m": TimeFrame(30, TimeFrameUnit.Minute),
    "1h": TimeFrame(1, TimeFrameUnit.Hour),
    "1d": TimeFrame(1, TimeFrameUnit.Day),
}


def _bar_to_candle(bar: Bar, symbol: str, timeframe: str) -> Candle:
    return Candle(
        symbol=symbol,
        timeframe=timeframe,
        ts=bar.timestamp,
        open=float(bar.open),
        high=float(bar.high),
        low=float(bar.low),
        close=float(bar.close),
        volume=float(bar.volume),
        vwap=float(bar.vwap) if bar.vwap is not None else None,
    )


class AlpacaMarketData(MarketDataProvider):
    """Alpaca implementation of MarketDataProvider.

    Uses alpaca-py for both historical REST and live websocket candles.
    """

    def __init__(self, api_key: str, secret_key: str, data_feed: str = "") -> None:
        self._client = StockHistoricalDataClient(api_key, secret_key)
        self._api_key = api_key
        self._secret_key = secret_key
        # Empty string → omit feed param so Alpaca uses the account default.
        self._data_feed: str | None = data_feed or None

    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[Candle]:
        tf = _TF_MAP.get(timeframe)
        if tf is None:
            raise ValueError(f"Unsupported timeframe '{timeframe}'. Use: {list(_TF_MAP)}")

        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=tf,
            start=start,
            end=end,
            **({"feed": self._data_feed} if self._data_feed else {}),
        )
        logger.debug(
            "Fetching candles",
            symbol=symbol,
            tf=timeframe,
            start=start,
            end=end,
            feed=self._data_feed,
        )
        # Alpaca's historical client is synchronous; run in thread to avoid blocking the loop.
        bars = await asyncio.to_thread(self._client.get_stock_bars, request)
        if symbol not in bars:
            logger.warning("No bars returned for symbol", symbol=symbol, tf=timeframe)
            return []
        result = [_bar_to_candle(bar, symbol, timeframe) for bar in bars[symbol]]
        logger.debug("Fetched candles", symbol=symbol, count=len(result))
        return result

    async def stream_candles(
        self,
        symbols: list[str],
        timeframe: str,
    ) -> AsyncIterator[Candle]:
        """Yield live candles from Alpaca websocket.

        NOTE: Alpaca's free websocket stream provides 1m bars.
        timeframe is accepted for interface compliance but the stream always emits 1m bars.
        """
        queue: asyncio.Queue[Candle] = asyncio.Queue()
        stream = StockDataStream(self._api_key, self._secret_key)

        async def _bar_handler(bar: Bar) -> None:
            await queue.put(_bar_to_candle(bar, bar.symbol, "1m"))

        stream.subscribe_bars(_bar_handler, *symbols)
        task = asyncio.create_task(stream.run())
        try:
            while True:
                yield await queue.get()
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def get_latest_quote(self, symbol: str) -> dict[str, float]:
        request = StockLatestQuoteRequest(symbol_or_symbols=symbol)
        # Sync HTTP call — run in thread to avoid blocking the event loop.
        quotes = await asyncio.to_thread(self._client.get_stock_latest_quote, request)
        q = quotes[symbol]
        return {
            "bid": float(q.bid_price),
            "ask": float(q.ask_price),
            "bid_size": float(q.bid_size),
            "ask_size": float(q.ask_size),
        }
