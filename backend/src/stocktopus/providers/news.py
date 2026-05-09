"""News provider — pluggable adapter for news and sentiment feeds."""

from abc import ABC, abstractmethod
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class NewsCategory(StrEnum):
    MACRO = "macro"
    FED = "fed"
    CPI_NFP = "cpi_nfp"
    EARNINGS = "earnings"
    GEOPOLITICS = "geopolitics"
    OTHER = "other"


class NewsArticle(BaseModel):
    id: str
    headline: str
    summary: str | None = None
    source: str
    url: str
    published_at: datetime
    symbols: list[str] = []
    categories: list[NewsCategory] = []
    sentiment_score: float | None = None  # -1.0 (bearish) to 1.0 (bullish), if pre-scored


class NewsProvider(ABC):
    """Abstract provider for news and sentiment data.

    Implementations: FinnhubNews, NewsAPINews (Phase 3b).
    """

    @abstractmethod
    async def get_news(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
        categories: list[NewsCategory] | None = None,
    ) -> list[NewsArticle]:
        """Fetch news articles for the given symbols and time window."""
        ...

    @abstractmethod
    async def get_macro_events(
        self,
        start: datetime,
        end: datetime,
    ) -> list[NewsArticle]:
        """Fetch scheduled macro events (FOMC, CPI, NFP, Fed speeches)."""
        ...
