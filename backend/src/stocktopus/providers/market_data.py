"""Market data provider — pluggable adapter for price/volume feeds."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import datetime

from pydantic import BaseModel


class Candle(BaseModel):
    symbol: str
    timeframe: str  # "1m" | "5m" | "1d" etc.
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: float | None = None


class MarketDataProvider(ABC):
    """Abstract provider for market price/volume data.

    Implementations: AlpacaMarketData (Phase 3a).
    Extend for Polygon, Alpha Vantage, etc. without changing call sites.
    """

    @abstractmethod
    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[Candle]:
        """Fetch historical candles for a symbol and timeframe."""
        ...

    @abstractmethod
    async def stream_candles(
        self,
        symbols: list[str],
        timeframe: str,
    ) -> AsyncIterator[Candle]:
        """Stream live candles via websocket."""
        ...

    @abstractmethod
    async def get_latest_quote(self, symbol: str) -> dict[str, float]:
        """Return the latest bid/ask/last price for a symbol."""
        ...
