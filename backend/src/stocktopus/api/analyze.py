"""Analyze API — returns latest regime assessment or triggers a new one."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stocktopus.db.engine import get_session
from stocktopus.db.models import LLMLog

router = APIRouter(prefix="/api/analyze", tags=["analyze"])


class RegimeAssessmentOut(BaseModel):
    id: str
    ts: datetime
    symbol: str
    regime: str
    lean: str
    confidence: int
    reasoning: str
    key_risks: list[str]
    invalidation: str
    model_used: str
    prompt_version: str
    cost_usd: float
    latency_ms: int

    model_config = {"from_attributes": True}


@router.get("/latest", response_model=RegimeAssessmentOut)
async def get_latest_assessment(
    symbol: str = Query(default="SPY", description="Ticker symbol"),
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> RegimeAssessmentOut:
    """Return the most recent successful LLM regime assessment for a symbol."""
    row = (
        await session.execute(
            select(LLMLog)
            .where(LLMLog.symbol == symbol.upper(), LLMLog.parsed_ok.is_(True))
            .order_by(LLMLog.ts.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"No regime assessment found for {symbol}. "
            "Run `stocktopus analyze regime --symbol {symbol}` first.",
        )

    ra = row.regime_assessment or {}
    return RegimeAssessmentOut(
        id=row.id,
        ts=row.ts,
        symbol=row.symbol,
        regime=ra.get("regime", "unknown"),
        lean=ra.get("lean", "no_trade"),
        confidence=ra.get("confidence", 0),
        reasoning=ra.get("reasoning", ""),
        key_risks=ra.get("key_risks", []),
        invalidation=ra.get("invalidation", ""),
        model_used=ra.get("model_used", row.model),
        prompt_version=row.prompt_version,
        cost_usd=row.cost_usd,
        latency_ms=row.latency_ms,
    )
