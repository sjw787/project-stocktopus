"""Concrete pre-trade risk checks.

Each check is a single-responsibility class that takes a StrategyContext +
TradeThesis and returns a RiskResult. Add new checks here and register them
in RiskFilter.
"""

from __future__ import annotations

from stocktopus.features.models import TradeDirection, TradeThesis
from stocktopus.risk.base import RiskCheck, RiskResult, RiskVerdict
from stocktopus.strategies.base import StrategyContext

# ── 1. Position size ──────────────────────────────────────────────────────────


class PositionSizeCheck(RiskCheck):
    """Block trades where notional value exceeds max_position_usd."""

    def __init__(self, max_position_usd: float) -> None:
        self._max = max_position_usd

    @property
    def name(self) -> str:
        return "position_size"

    def run(self, ctx: StrategyContext, thesis: TradeThesis) -> RiskResult:
        # Estimate qty from max position / entry price (round down).
        if thesis.entry_price <= 0:
            return RiskResult(
                check_name=self.name,
                verdict=RiskVerdict.FAILED,
                reason="Entry price is zero or negative.",
            )
        qty = self._max / thesis.entry_price
        notional = qty * thesis.entry_price
        if notional > self._max:
            return RiskResult(
                check_name=self.name,
                verdict=RiskVerdict.FAILED,
                reason=f"Notional ${notional:.2f} exceeds max ${self._max:.2f}.",
                details={"notional": notional, "max_position_usd": self._max},
            )
        return RiskResult(
            check_name=self.name,
            verdict=RiskVerdict.PASSED,
            details={"qty": round(qty, 4), "notional": round(notional, 2)},
        )


# ── 2. Daily loss ─────────────────────────────────────────────────────────────


class DailyLossCheck(RiskCheck):
    """Block trades if today's realized losses already exceed max_daily_loss_usd."""

    def __init__(self, max_daily_loss_usd: float) -> None:
        self._max = max_daily_loss_usd

    @property
    def name(self) -> str:
        return "daily_loss"

    def run(self, ctx: StrategyContext, thesis: TradeThesis) -> RiskResult:
        loss = -ctx.daily_realized_pnl  # positive means we've lost money
        if loss >= self._max:
            return RiskResult(
                check_name=self.name,
                verdict=RiskVerdict.FAILED,
                reason=(f"Daily loss ${loss:.2f} has reached the ${self._max:.2f} limit. No further trades today."),
                details={"daily_loss": loss, "max_daily_loss_usd": self._max},
            )
        return RiskResult(
            check_name=self.name,
            verdict=RiskVerdict.PASSED,
            details={"daily_loss": round(loss, 2), "remaining": round(self._max - loss, 2)},
        )


# ── 3. Max trades per day ─────────────────────────────────────────────────────


class MaxDailyTradesCheck(RiskCheck):
    """Block trades after max_trades_per_day trades have been placed today."""

    def __init__(self, max_trades_per_day: int) -> None:
        self._max = max_trades_per_day

    @property
    def name(self) -> str:
        return "max_daily_trades"

    def run(self, ctx: StrategyContext, thesis: TradeThesis) -> RiskResult:
        if ctx.trades_today >= self._max:
            return RiskResult(
                check_name=self.name,
                verdict=RiskVerdict.FAILED,
                reason=f"Max trades/day ({self._max}) reached ({ctx.trades_today} placed).",
                details={"trades_today": ctx.trades_today, "max": self._max},
            )
        return RiskResult(
            check_name=self.name,
            verdict=RiskVerdict.PASSED,
            details={"trades_today": ctx.trades_today, "remaining": self._max - ctx.trades_today},
        )


# ── 4. No overnight holds ─────────────────────────────────────────────────────


class NoOvernightCheck(RiskCheck):
    """Block new trades when there are fewer than min_minutes_to_close minutes left.

    Prevents opening positions that can't be closed by market close.
    """

    def __init__(self, min_minutes_to_close: int = 65) -> None:
        self._min_minutes = min_minutes_to_close

    @property
    def name(self) -> str:
        return "no_overnight"

    def run(self, ctx: StrategyContext, thesis: TradeThesis) -> RiskResult:
        ts = ctx.ts
        # Market close UTC = 20:00 (16:00 ET)
        close_utc_minutes = 20 * 60
        ts_utc_minutes = ts.hour * 60 + ts.minute
        minutes_to_close = close_utc_minutes - ts_utc_minutes
        if minutes_to_close < self._min_minutes:
            return RiskResult(
                check_name=self.name,
                verdict=RiskVerdict.FAILED,
                reason=(
                    f"Only {minutes_to_close}m to market close; "
                    f"need at least {self._min_minutes}m to avoid overnight hold."
                ),
                details={
                    "minutes_to_close": minutes_to_close,
                    "min_required": self._min_minutes,
                },
            )
        return RiskResult(
            check_name=self.name,
            verdict=RiskVerdict.PASSED,
            details={"minutes_to_close": minutes_to_close},
        )


# ── 5. Volatility ceiling (VIX) ──────────────────────────────────────────────


class VolatilityCeilingCheck(RiskCheck):
    """Warn (or block) when VIX is above the configured ceiling."""

    def __init__(self, vix_warn: float = 30.0, vix_block: float = 40.0) -> None:
        self._warn = vix_warn
        self._block = vix_block

    @property
    def name(self) -> str:
        return "volatility_ceiling"

    def run(self, ctx: StrategyContext, thesis: TradeThesis) -> RiskResult:
        vix = ctx.features.vix
        if vix is None:
            return RiskResult(
                check_name=self.name,
                verdict=RiskVerdict.WARNED,
                reason="VIX data unavailable — proceeding without volatility check.",
            )
        if vix >= self._block:
            return RiskResult(
                check_name=self.name,
                verdict=RiskVerdict.FAILED,
                reason=f"VIX {vix:.1f} at or above hard block threshold {self._block:.1f}.",
                details={"vix": vix, "block": self._block},
            )
        if vix >= self._warn:
            return RiskResult(
                check_name=self.name,
                verdict=RiskVerdict.WARNED,
                reason=f"VIX {vix:.1f} elevated (warn threshold {self._warn:.1f}).",
                details={"vix": vix, "warn": self._warn},
            )
        return RiskResult(check_name=self.name, verdict=RiskVerdict.PASSED, details={"vix": vix})


# ── 6. LLM assessment required ────────────────────────────────────────────────


class LLMAssessmentRequiredCheck(RiskCheck):
    """Fail closed if no valid LLM regime assessment is present."""

    @property
    def name(self) -> str:
        return "llm_assessment_required"

    def run(self, ctx: StrategyContext, thesis: TradeThesis) -> RiskResult:
        if ctx.regime is None:
            return RiskResult(
                check_name=self.name,
                verdict=RiskVerdict.FAILED,
                reason="No LLM regime assessment present. Failing closed — no new trades allowed.",
            )
        return RiskResult(
            check_name=self.name,
            verdict=RiskVerdict.PASSED,
            details={"regime": ctx.regime.regime, "confidence": ctx.regime.confidence},
        )


# ── 7. Long-only guard ────────────────────────────────────────────────────────


class LongOnlyCheck(RiskCheck):
    """Block short trades when long_only mode is enabled."""

    def __init__(self, long_only: bool = True) -> None:
        self._long_only = long_only

    @property
    def name(self) -> str:
        return "long_only"

    def run(self, ctx: StrategyContext, thesis: TradeThesis) -> RiskResult:
        if self._long_only and thesis.direction == TradeDirection.SHORT:
            return RiskResult(
                check_name=self.name,
                verdict=RiskVerdict.FAILED,
                reason="Short trades are not allowed in long-only mode.",
            )
        return RiskResult(check_name=self.name, verdict=RiskVerdict.PASSED)


# ── 8. No duplicate position ──────────────────────────────────────────────────


class NoDuplicatePositionCheck(RiskCheck):
    """Block new entries when a position in the same symbol is already open."""

    @property
    def name(self) -> str:
        return "no_duplicate_position"

    def run(self, ctx: StrategyContext, thesis: TradeThesis) -> RiskResult:
        if abs(ctx.open_position_qty) > 0:
            return RiskResult(
                check_name=self.name,
                verdict=RiskVerdict.FAILED,
                reason=(
                    f"Already holding {ctx.open_position_qty} shares of {ctx.symbol}. "
                    "Close existing position before entering a new one."
                ),
                details={"open_qty": ctx.open_position_qty},
            )
        return RiskResult(check_name=self.name, verdict=RiskVerdict.PASSED)
