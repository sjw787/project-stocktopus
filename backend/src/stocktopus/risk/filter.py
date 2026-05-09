"""RiskFilter — orchestrates all pre-trade checks.

Usage::

    filter = RiskFilter.from_settings(settings)
    result = filter.evaluate(ctx, thesis)
    if result.approved:
        # proceed to execution
    else:
        # log result.rejections and abort
"""

from __future__ import annotations

from datetime import datetime

from loguru import logger
from pydantic import BaseModel

from stocktopus.features.models import TradeThesis
from stocktopus.risk.base import RiskCheck, RiskResult, RiskVerdict
from stocktopus.risk.checks import (
    DailyLossCheck,
    LLMAssessmentRequiredCheck,
    LongOnlyCheck,
    MaxDailyTradesCheck,
    NoDuplicatePositionCheck,
    NoOvernightCheck,
    PositionSizeCheck,
    VolatilityCeilingCheck,
)
from stocktopus.strategies.base import StrategyContext


class FilterResult(BaseModel):
    """Aggregated result from the RiskFilter."""

    approved: bool
    results: list[RiskResult]
    symbol: str
    ts: datetime

    @property
    def rejections(self) -> list[RiskResult]:
        return [r for r in self.results if r.blocked]

    @property
    def warnings(self) -> list[RiskResult]:
        return [r for r in self.results if r.verdict == RiskVerdict.WARNED]

    def summary(self) -> str:
        if self.approved:
            warns = len(self.warnings)
            return f"APPROVED ({"no warnings" if not warns else f"{warns} warning(s)"})"
        reasons = "; ".join(r.reason for r in self.rejections)
        return f"REJECTED: {reasons}"


class RiskFilter:
    """Runs a configurable ordered list of RiskChecks against a proposed trade.

    Checks run in order; the first FAILED result short-circuits the rest
    for speed (all results up to the failure are still returned).
    """

    def __init__(self, checks: list[RiskCheck], short_circuit: bool = True) -> None:
        self._checks = checks
        self._short_circuit = short_circuit

    @classmethod
    def from_settings(
        cls,
        max_position_usd: float = 50.0,
        max_daily_loss_usd: float = 25.0,
        max_trades_per_day: int = 5,
        no_overnight: bool = True,
        long_only: bool = True,
        vix_warn: float = 30.0,
        vix_block: float = 40.0,
        min_minutes_to_close: int = 65,
    ) -> RiskFilter:
        """Build a RiskFilter with the standard check stack from settings values."""
        checks: list[RiskCheck] = [
            LLMAssessmentRequiredCheck(),
            LongOnlyCheck(long_only=long_only),
            NoDuplicatePositionCheck(),
            PositionSizeCheck(max_position_usd),
            DailyLossCheck(max_daily_loss_usd),
            MaxDailyTradesCheck(max_trades_per_day),
            VolatilityCeilingCheck(vix_warn=vix_warn, vix_block=vix_block),
        ]
        if no_overnight:
            checks.append(NoOvernightCheck(min_minutes_to_close=min_minutes_to_close))
        return cls(checks=checks)

    def evaluate(self, ctx: StrategyContext, thesis: TradeThesis) -> FilterResult:
        """Run all checks and return an aggregated FilterResult."""
        results: list[RiskResult] = []
        approved = True

        for check in self._checks:
            result = check.run(ctx, thesis)
            results.append(result)

            if result.blocked:
                approved = False
                logger.warning(
                    "Trade blocked by risk check",
                    check=check.name,
                    reason=result.reason,
                    symbol=ctx.symbol,
                )
                if self._short_circuit:
                    break
            elif result.verdict == RiskVerdict.WARNED:
                logger.warning(
                    "Risk warning",
                    check=check.name,
                    reason=result.reason,
                    symbol=ctx.symbol,
                )

        fr = FilterResult(
            approved=approved,
            results=results,
            symbol=ctx.symbol,
            ts=ctx.ts,
        )

        if approved:
            logger.info("Trade approved by risk filter", symbol=ctx.symbol)
        else:
            logger.info(
                "Trade rejected by risk filter",
                symbol=ctx.symbol,
                rejections=[r.reason for r in fr.rejections],
            )

        return fr
