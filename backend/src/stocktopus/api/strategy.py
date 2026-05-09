"""Strategy evaluation API endpoint.

GET /api/strategy/evaluate?symbol=SPY
  → Runs: features → LLM regime → strategy signal → risk filter
  → Returns TradeThesisOut or a no-signal response
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from stocktopus.config import Settings, get_settings
from stocktopus.db.engine import get_db_session
from stocktopus.db.models import FeatureSnapshot
from stocktopus.features.models import FeatureVector, RegimeAssessment
from stocktopus.llm.research_director import ResearchDirector
from stocktopus.risk.filter import FilterResult, RiskFilter
from stocktopus.strategies.base import StrategyContext
from stocktopus.strategies.opening_momentum import OpeningMomentumStrategy

router = APIRouter(prefix="/api/strategy", tags=["strategy"])


# ── Response schemas ───────────────────────────────────────────────────────────


class RiskCheckOut(BaseModel):
    check_name: str
    verdict: str
    reason: str


class TradeThesisOut(BaseModel):
    symbol: str
    direction: str
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_reward: float | None
    strategy_name: str
    strategy_version: str
    rationale: str
    regime: str
    lean: str
    confidence: int
    generated_at: datetime


class EvaluateResponse(BaseModel):
    symbol: str
    evaluated_at: datetime
    signal: bool  # True = thesis generated; False = no trade
    risk_approved: bool | None  # None if no signal
    thesis: TradeThesisOut | None
    risk_checks: list[RiskCheckOut] | None  # Only populated if thesis was generated


# ── Dependency helpers ────────────────────────────────────────────────────────


def _build_director(settings: Settings) -> ResearchDirector:
    """Construct the ResearchDirector with the configured LLM provider."""
    active = settings.active_llm_provider.lower()
    if active == "anthropic":
        from stocktopus.llm.anthropic_provider import AnthropicProvider

        if not settings.anthropic_api_key:
            raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not configured")
        llm = AnthropicProvider(api_key=settings.anthropic_api_key)
    else:
        from stocktopus.llm.openai_provider import OpenAIProvider

        if not settings.openai_api_key:
            raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")
        llm = OpenAIProvider(api_key=settings.openai_api_key)

    return ResearchDirector(llm=llm, daily_budget_usd=settings.llm_daily_budget_usd)


# ── Endpoint ──────────────────────────────────────────────────────────────────


@router.get("/evaluate", response_model=EvaluateResponse)
async def evaluate(
    symbol: str = Query("SPY", description="Ticker symbol"),
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> EvaluateResponse:
    """Evaluate the opening momentum strategy signal for a given symbol.

    Pipeline:
    1. Load the latest feature snapshot for `symbol`.
    2. Run LLM regime assessment (cached in llm_logs if recent).
    3. Run the OpeningMomentumStrategy.
    4. Run the RiskFilter.
    5. Return the full evaluation result.
    """
    sym = symbol.upper()

    # 1. Latest feature snapshot
    q = (
        select(FeatureSnapshot)
        .where(FeatureSnapshot.symbol == sym)
        .order_by(desc(FeatureSnapshot.ts))
        .limit(1)
    )
    snap = (await session.execute(q)).scalar_one_or_none()
    if snap is None:
        raise HTTPException(
            status_code=404,
            detail=f"No feature snapshots found for {sym}. Run feature compute first.",
        )

    fv = FeatureVector(**snap.features)

    # 2. LLM regime assessment
    director = _build_director(settings)
    assessment: RegimeAssessment = await director.analyze(session, symbol=sym)

    # 3. Strategy signal
    strat = OpeningMomentumStrategy()
    ctx = StrategyContext(
        symbol=sym,
        ts=snap.ts,
        features=fv,
        regime=assessment,
    )
    thesis = strat.evaluate(ctx)

    now = datetime.utcnow()

    if thesis is None:
        return EvaluateResponse(
            symbol=sym,
            evaluated_at=now,
            signal=False,
            risk_approved=None,
            thesis=None,
            risk_checks=None,
        )

    # 4. Risk filter
    risk = RiskFilter.from_settings(
        max_position_usd=settings.max_position_usd,
        max_daily_loss_usd=settings.max_daily_loss_usd,
        max_trades_per_day=settings.max_trades_per_day,
    )
    fr: FilterResult = risk.evaluate(ctx, thesis)

    thesis_out = TradeThesisOut(
        symbol=thesis.symbol,
        direction=thesis.direction,
        entry_price=thesis.entry_price,
        stop_loss=thesis.stop_loss,
        take_profit=thesis.take_profit,
        risk_reward=thesis.risk_reward,
        strategy_name=thesis.strategy_name,
        strategy_version=thesis.strategy_version,
        rationale=thesis.rationale,
        regime=assessment.regime,
        lean=assessment.lean,
        confidence=assessment.confidence,
        generated_at=thesis.generated_at,
    )

    checks_out = [
        RiskCheckOut(check_name=r.check_name, verdict=r.verdict, reason=r.reason)
        for r in fr.results
    ]

    return EvaluateResponse(
        symbol=sym,
        evaluated_at=now,
        signal=True,
        risk_approved=fr.approved,
        thesis=thesis_out,
        risk_checks=checks_out,
    )
