"""News ingestion service — dedup, tag, and persist news articles."""

import hashlib
from datetime import datetime

from loguru import logger
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from stocktopus.db.models import NewsEvent
from stocktopus.providers.news import NewsArticle, NewsProvider


def _dedup_hash(article: NewsArticle) -> str:
    """Stable hash from URL + headline for deduplication."""
    raw = f"{article.url}::{article.headline}"
    return hashlib.sha256(raw.encode()).hexdigest()[:64]


async def ingest_news(
    session: AsyncSession,
    provider: NewsProvider,
    symbols: list[str],
    start: datetime,
    end: datetime,
) -> int:
    """Fetch and persist news articles for the given symbols and window.

    Returns the number of new rows inserted.
    """
    articles = await provider.get_news(symbols=symbols, start=start, end=end)
    logger.info("Fetched news articles", count=len(articles), symbols=symbols)
    return await _upsert_articles(session, articles)


async def ingest_macro_events(
    session: AsyncSession,
    provider: NewsProvider,
    start: datetime,
    end: datetime,
) -> int:
    """Fetch and persist scheduled macro events (FOMC, CPI, NFP, Fed speeches)."""
    articles = await provider.get_macro_events(start=start, end=end)
    logger.info("Fetched macro events", count=len(articles))
    return await _upsert_articles(session, articles)


async def _upsert_articles(session: AsyncSession, articles: list[NewsArticle]) -> int:
    if not articles:
        return 0

    rows = [
        {
            "id": article.id,
            "headline": article.headline,
            "summary": article.summary,
            "source": article.source,
            "url": article.url,
            "published_at": article.published_at,
            "symbols": article.symbols,
            "categories": [c.value for c in article.categories],
            "sentiment_score": article.sentiment_score,
            "dedup_hash": _dedup_hash(article),
            "raw_payload": None,
        }
        for article in articles
    ]

    stmt = insert(NewsEvent).values(rows).on_conflict_do_nothing(constraint="uq_news_events_dedup_hash")
    result = await session.execute(stmt)
    await session.commit()
    inserted = result.rowcount
    logger.info("News upsert complete", inserted=inserted, total_attempted=len(rows))
    return inserted
