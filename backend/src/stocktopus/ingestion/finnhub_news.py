"""Finnhub news provider — fetches company and general market news."""

from __future__ import annotations

import asyncio
import hashlib
import json
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from typing import Any

from loguru import logger

from stocktopus.providers.news import NewsArticle, NewsCategory, NewsProvider

_FINNHUB_BASE = "https://finnhub.io/api/v1"

# Finnhub category → our NewsCategory
_CATEGORY_MAP: dict[str, NewsCategory] = {
    "general": NewsCategory.OTHER,
    "forex": NewsCategory.OTHER,
    "crypto": NewsCategory.OTHER,
    "merger": NewsCategory.OTHER,
    "federal reserve": NewsCategory.FED,
    "cpi": NewsCategory.CPI_NFP,
    "nfp": NewsCategory.CPI_NFP,
    "earnings": NewsCategory.EARNINGS,
    "economic": NewsCategory.MACRO,
    "geopolitics": NewsCategory.GEOPOLITICS,
}

# Macro keywords → category override
_MACRO_KEYWORDS: list[tuple[list[str], NewsCategory]] = [
    (["federal reserve", "fed ", " fed", "fomc", "powell", "interest rate"], NewsCategory.FED),
    (["cpi", "consumer price", "inflation", "pce"], NewsCategory.CPI_NFP),
    (["nfp", "non-farm", "payroll", "unemployment", "jobs report"], NewsCategory.CPI_NFP),
    (["earnings", "eps", "revenue miss", "revenue beat", "quarterly"], NewsCategory.EARNINGS),
    (["gdp", "macro", "economic", "recession", "treasury", "yield curve"], NewsCategory.MACRO),
    (["ukraine", "russia", "china", "tariff", "sanction", "geopolit"], NewsCategory.GEOPOLITICS),
]


def _classify(headline: str, summary: str) -> list[NewsCategory]:
    text = (headline + " " + (summary or "")).lower()
    for keywords, cat in _MACRO_KEYWORDS:
        if any(kw in text for kw in keywords):
            return [cat]
    return [NewsCategory.OTHER]


def _article_id(url: str, headline: str) -> str:
    raw = f"{url}::{headline}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _fetch_json(url: str) -> Any:
    """Synchronous HTTP GET — runs in a thread via asyncio.to_thread."""
    req = urllib.request.Request(url, headers={"User-Agent": "stocktopus/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


class FinnhubNewsProvider(NewsProvider):
    """Fetches company news and general market news from Finnhub.

    Uses the free-tier REST API (no websocket). All I/O is wrapped in
    ``asyncio.to_thread`` so it is safe to await from async code.
    """

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def _url(self, path: str, **params: Any) -> str:
        params["token"] = self._api_key
        qs = urllib.parse.urlencode(params)
        return f"{_FINNHUB_BASE}{path}?{qs}"

    def _parse_articles(self, items: list[dict[str, Any]]) -> list[NewsArticle]:
        articles: list[NewsArticle] = []
        for item in items:
            headline = item.get("headline") or item.get("summary") or ""
            summary = item.get("summary") or None
            url = item.get("url") or ""
            if not headline or not url:
                continue
            ts_raw = item.get("datetime") or item.get("timestamp")
            if ts_raw:
                try:
                    published_at = datetime.fromtimestamp(int(ts_raw), tz=UTC)
                except (ValueError, TypeError):
                    published_at = datetime.now(tz=UTC)
            else:
                published_at = datetime.now(tz=UTC)

            related = item.get("related") or ""
            symbols = [s.strip().upper() for s in related.split(",") if s.strip()] if related else []

            categories = _classify(headline, summary or "")

            articles.append(
                NewsArticle(
                    id=_article_id(url, headline),
                    headline=headline,
                    summary=summary,
                    source="finnhub",
                    url=url,
                    published_at=published_at,
                    symbols=symbols,
                    categories=categories,
                    sentiment_score=None,
                )
            )
        return articles

    async def get_news(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
        categories: list[NewsCategory] | None = None,
    ) -> list[NewsArticle]:
        from_str = start.strftime("%Y-%m-%d")
        to_str = end.strftime("%Y-%m-%d")
        seen_ids: set[str] = set()
        all_articles: list[NewsArticle] = []

        for symbol in symbols:
            url = self._url("/company-news", symbol=symbol, _from=from_str, to=to_str)
            try:
                items = await asyncio.to_thread(_fetch_json, url)
                if not isinstance(items, list):
                    logger.warning("Finnhub company-news unexpected response for %s", symbol)
                    continue
                for article in self._parse_articles(items):
                    if article.id not in seen_ids:
                        if not article.symbols:
                            article = article.model_copy(update={"symbols": [symbol.upper()]})
                        seen_ids.add(article.id)
                        all_articles.append(article)
            except Exception:
                logger.exception("Failed to fetch Finnhub news for %s", symbol)

        logger.info("Finnhub news fetched", symbol_count=len(symbols), articles=len(all_articles))
        return all_articles

    async def get_macro_events(
        self,
        start: datetime,
        end: datetime,
    ) -> list[NewsArticle]:
        url = self._url("/news", category="general", minId=0)
        try:
            items = await asyncio.to_thread(_fetch_json, url)
            if not isinstance(items, list):
                return []
            articles = self._parse_articles(items)
            # Filter to macro/fed/economic articles only
            macro_cats = {NewsCategory.FED, NewsCategory.CPI_NFP, NewsCategory.MACRO, NewsCategory.GEOPOLITICS}
            return [a for a in articles if any(c in macro_cats for c in a.categories)]
        except Exception:
            logger.exception("Failed to fetch Finnhub general news")
            return []
