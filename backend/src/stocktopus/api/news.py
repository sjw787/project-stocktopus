"""News API — query stored news and macro events."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stocktopus.db.engine import get_session
from stocktopus.db.models import NewsEvent

router = APIRouter(prefix="/api/news", tags=["news"])


class NewsOut(BaseModel):
    id: str
    headline: str
    summary: str | None = None
    source: str
    url: str
    published_at: datetime
    symbols: list[str]
    categories: list[str]
    sentiment_score: float | None = None

    model_config = {"from_attributes": True}


@router.get("", response_model=list[NewsOut])
async def get_news(
    limit: int = Query(default=20, ge=1, le=200),
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[NewsEvent]:
    stmt = select(NewsEvent).order_by(NewsEvent.published_at.desc()).limit(limit)
    return list((await session.execute(stmt)).scalars().all())
