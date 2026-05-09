"""Market context API — query latest regime snapshot."""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stocktopus.db.engine import get_session
from stocktopus.db.models import MarketContext

router = APIRouter(prefix="/api/context", tags=["context"])


class ContextOut(BaseModel):
    ts: datetime
    vix: float | None = None
    spy_gap_pct: float | None = None
    spy_price: float | None = None
    qqq_price: float | None = None
    iwm_price: float | None = None
    dia_price: float | None = None
    xlk: float | None = None
    xlf: float | None = None
    xle: float | None = None
    xlv: float | None = None
    xli: float | None = None
    spy_above_vwap: bool | None = None
    spy_trend_1d: str | None = None

    model_config = {"from_attributes": True}


@router.get("/latest", response_model=ContextOut | None)
async def get_latest_context(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> MarketContext | None:
    stmt = select(MarketContext).order_by(MarketContext.ts.desc()).limit(1)
    return (await session.execute(stmt)).scalars().first()
