"""Candles API — query stored OHLCV data."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stocktopus.db.engine import get_session
from stocktopus.db.models import Candle as CandleRow

router = APIRouter(prefix="/api/candles", tags=["candles"])


class CandleOut(BaseModel):
    symbol: str
    timeframe: str
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: float | None = None

    model_config = {"from_attributes": True}


@router.get("", response_model=list[CandleOut])
async def get_candles(
    symbol: str = Query(default="SPY", description="Ticker symbol"),
    timeframe: str = Query(default="1m", description="Bar timeframe"),
    limit: int = Query(default=50, ge=1, le=1000, description="Max bars to return"),
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[CandleRow]:
    stmt = (
        select(CandleRow)
        .where(CandleRow.symbol == symbol.upper(), CandleRow.timeframe == timeframe)
        .order_by(CandleRow.ts.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return list(reversed(rows))
