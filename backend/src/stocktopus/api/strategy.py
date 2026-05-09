"""Strategy evaluation API endpoint.

GET /api/strategy/evaluate?symbol=SPY
  → Runs: features → LLM regime → strategy signal → risk filter
  → Returns TradeThesisOut or a no-signal response

GET /api/strategy/config
  → Returns current strategy configuration from settings

POST /api/strategy/backtest
  → Runs a quick offline backtest against stored candle data
"""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from stocktopus.config import Settings, get_settings
from stocktopus.db.engine import get_session as get_db_session
from stocktopus.db.models import Candle, FeatureSnapshot
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


# ── Config endpoint ───────────────────────────────────────────────────────────


class StrategyConfigOut(BaseModel):
    symbol: str
    timeframe: str
    entry_time: str
    exit_time: str
    max_daily_trades: int
    position_size_pct: float
    stop_loss_pct: float
    take_profit_pct: float
    require_regime: str | None
    min_llm_confidence: int | None


@router.get("/config", response_model=StrategyConfigOut)
async def strategy_config(
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> StrategyConfigOut:
    """Return current strategy configuration derived from settings."""
    strat = OpeningMomentumStrategy()
    return StrategyConfigOut(
        symbol="SPY",
        timeframe="5m",
        entry_time=getattr(strat, "entry_time", "09:35"),
        exit_time=getattr(strat, "exit_time", "15:55"),
        max_daily_trades=settings.max_trades_per_day,
        position_size_pct=round(settings.max_position_usd / 10_000 * 100, 2),
        stop_loss_pct=getattr(strat, "stop_loss_pct", 0.5),
        take_profit_pct=getattr(strat, "take_profit_pct", 1.0),
        require_regime=getattr(strat, "require_regime", None),
        min_llm_confidence=getattr(strat, "min_confidence", None),
    )


# ── Backtest endpoint ─────────────────────────────────────────────────────────


class BacktestRequest(BaseModel):
    symbol: str = "SPY"
    start: str  # ISO date: YYYY-MM-DD
    end: str  # ISO date: YYYY-MM-DD
    timeframe: str = "5m"


class BacktestTradeOut(BaseModel):
    entry_ts: str
    exit_ts: str | None
    direction: str
    entry_price: float
    exit_price: float | None
    pnl: float | None
    exit_reason: str


class BacktestMetricsOut(BaseModel):
    total_trades: int
    win_rate: float
    net_profit: float
    max_drawdown: float
    sharpe_ratio: float | None
    profit_factor: float | None
    avg_win: float
    avg_loss: float
    expectancy: float


class BacktestResponse(BaseModel):
    symbol: str
    start: str
    end: str
    metrics: BacktestMetricsOut
    trades: list[BacktestTradeOut]


@router.post("/backtest", response_model=BacktestResponse)
async def run_backtest(
    req: BacktestRequest,
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
) -> BacktestResponse:
    """Run a quick offline backtest against stored candle data."""


    from stocktopus.backtest.runner import BacktestRunner
    from stocktopus.features.models import Regime, TradeLean

    sym = req.symbol.upper()

    start_dt = datetime.fromisoformat(req.start).replace(tzinfo=UTC)
    end_dt = datetime.fromisoformat(req.end).replace(tzinfo=UTC)

    # Load intraday bars
    q_5m = (
        select(Candle)
        .where(
            Candle.symbol == sym,
            Candle.timeframe == req.timeframe,
            Candle.ts >= start_dt,
            Candle.ts < end_dt,
        )
        .order_by(Candle.ts)
    )
    rows_5m = (await session.execute(q_5m)).scalars().all()
    if not rows_5m:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No {req.timeframe} candle data for {sym} "
                f"in [{req.start}, {req.end}). Run ingestion first."
            ),
        )

    # Load daily bars
    q_1d = (
        select(Candle)
        .where(
            Candle.symbol == sym,
            Candle.timeframe == "1d",
            Candle.ts >= start_dt,
            Candle.ts < end_dt,
        )
        .order_by(Candle.ts)
    )
    rows_1d = (await session.execute(q_1d)).scalars().all()

    def to_df(rows: list) -> pd.DataFrame:
        return pd.DataFrame([
            {
                "ts": r.ts,
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "volume": r.volume,
                "symbol": r.symbol,
            }
            for r in rows
        ])

    intraday_df = to_df(rows_5m)
    daily_df = to_df(rows_1d) if rows_1d else None

    # Neutral regime assessment for all dates (no LLM budget spent in backtest)
    neutral = RegimeAssessment(
        regime=Regime.TRENDING_UP,
        lean=TradeLean.LONG,
        confidence=7,
        reasoning="Offline backtest — neutral regime assumed.",
        key_risks=[],
        invalidation="N/A — offline backtest uses a fixed neutral regime.",
    )
    regime_map = {
        d: neutral
        for d in pd.date_range(req.start, req.end, freq="D")
    }

    runner = BacktestRunner(
        symbol=sym,
        intraday_bars=intraday_df,
        daily_bars=daily_df,
        regime_map={k.date(): neutral for k in regime_map},
    )
    trades, metrics = runner.run()

    n_wins = sum(1 for t in trades if t.pnl and t.pnl > 0)
    n_losses = sum(1 for t in trades if t.pnl and t.pnl < 0)
    avg_win = sum(t.pnl for t in trades if t.pnl and t.pnl > 0) / max(1, n_wins)
    avg_loss = sum(t.pnl for t in trades if t.pnl and t.pnl < 0) / max(1, n_losses)

    return BacktestResponse(
        symbol=sym,
        start=req.start,
        end=req.end,
        metrics=BacktestMetricsOut(
            total_trades=metrics.total_trades,
            win_rate=round(metrics.win_rate, 4),
            net_profit=round(metrics.net_profit, 2),
            max_drawdown=round(metrics.max_drawdown_pct, 4),
            sharpe_ratio=metrics.sharpe_ratio,
            profit_factor=metrics.profit_factor,
            avg_win=round(avg_win, 2),
            avg_loss=round(avg_loss, 2),
            expectancy=round(metrics.expectancy, 4),
        ),
        trades=[
            BacktestTradeOut(
                entry_ts=t.entry_ts.isoformat(),
                exit_ts=t.exit_ts.isoformat() if t.exit_ts else None,
                direction=t.direction,
                entry_price=round(t.entry_price, 2),
                exit_price=round(t.exit_price, 2) if t.exit_price else None,
                pnl=round(t.pnl, 4) if t.pnl else None,
                exit_reason=t.exit_reason,
            )
            for t in trades
        ],
    )
