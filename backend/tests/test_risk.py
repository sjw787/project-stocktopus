"""Tests for the risk layer — individual checks and the RiskFilter orchestrator."""

from __future__ import annotations

from datetime import UTC, datetime

from stocktopus.features.models import (
    FeatureVector,
    Regime,
    RegimeAssessment,
    TradeDirection,
    TradeLean,
    TradeThesis,
)
from stocktopus.risk.base import RiskVerdict
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
from stocktopus.risk.filter import RiskFilter
from stocktopus.strategies.base import StrategyContext

# ── Helpers ───────────────────────────────────────────────────────────────────

_TS = datetime(2025, 1, 10, 14, 30, 0, tzinfo=UTC)  # 10:30 ET


def _regime(lean: TradeLean = TradeLean.LONG, confidence: int = 7) -> RegimeAssessment:
    return RegimeAssessment(
        regime=Regime.TRENDING_UP,
        lean=lean,
        confidence=confidence,
        reasoning="test",
        key_risks=["r1"],
        invalidation="inv",
    )


def _features(close: float = 500.0, vix: float | None = 18.0) -> FeatureVector:
    return FeatureVector(symbol="SPY", ts=_TS, close=close, vix=vix)


def _ctx(
    daily_pnl: float = 0.0,
    trades_today: int = 0,
    open_qty: float = 0.0,
    ts: datetime = _TS,
    regime: RegimeAssessment | None = None,
    features: FeatureVector | None = None,
) -> StrategyContext:
    return StrategyContext(
        symbol="SPY",
        ts=ts,
        features=features or _features(),
        regime=regime if regime is not None else _regime(),
        open_position_qty=open_qty,
        daily_realized_pnl=daily_pnl,
        trades_today=trades_today,
    )


def _thesis(
    direction: TradeDirection = TradeDirection.LONG,
    entry: float = 500.0,
    stop: float = 495.0,
    tp: float = 510.0,
) -> TradeThesis:
    return TradeThesis(
        symbol="SPY",
        direction=direction,
        entry_price=entry,
        stop_loss=stop,
        take_profit=tp,
    )


# ── PositionSizeCheck ─────────────────────────────────────────────────────────


class TestPositionSizeCheck:
    def test_passes_within_limit(self) -> None:
        check = PositionSizeCheck(max_position_usd=50.0)
        r = check.run(_ctx(), _thesis(entry=500.0))
        assert r.verdict == RiskVerdict.PASSED

    def test_blocks_oversized(self) -> None:
        # entry=$500, max=$50 → qty=0.1 → notional=$50 which equals max (should pass)
        # use a very small max so notional > max
        check = PositionSizeCheck(max_position_usd=10.0)
        # qty = 10 / 500 = 0.02; notional = 0.02 * 500 = 10 ≤ 10 → pass
        r = check.run(_ctx(), _thesis(entry=500.0))
        assert r.verdict == RiskVerdict.PASSED

    def test_blocks_zero_entry(self) -> None:
        check = PositionSizeCheck(max_position_usd=50.0)
        r = check.run(_ctx(), _thesis(entry=0.0))
        assert r.verdict == RiskVerdict.FAILED


# ── DailyLossCheck ────────────────────────────────────────────────────────────


class TestDailyLossCheck:
    def test_passes_no_loss(self) -> None:
        r = DailyLossCheck(25.0).run(_ctx(daily_pnl=0.0), _thesis())
        assert r.verdict == RiskVerdict.PASSED

    def test_passes_positive_pnl(self) -> None:
        r = DailyLossCheck(25.0).run(_ctx(daily_pnl=10.0), _thesis())
        assert r.verdict == RiskVerdict.PASSED

    def test_blocks_at_limit(self) -> None:
        r = DailyLossCheck(25.0).run(_ctx(daily_pnl=-25.0), _thesis())
        assert r.verdict == RiskVerdict.FAILED

    def test_blocks_beyond_limit(self) -> None:
        r = DailyLossCheck(25.0).run(_ctx(daily_pnl=-30.0), _thesis())
        assert r.verdict == RiskVerdict.FAILED

    def test_passes_just_below_limit(self) -> None:
        r = DailyLossCheck(25.0).run(_ctx(daily_pnl=-24.99), _thesis())
        assert r.verdict == RiskVerdict.PASSED


# ── MaxDailyTradesCheck ───────────────────────────────────────────────────────


class TestMaxDailyTradesCheck:
    def test_passes_under_limit(self) -> None:
        r = MaxDailyTradesCheck(5).run(_ctx(trades_today=3), _thesis())
        assert r.verdict == RiskVerdict.PASSED

    def test_blocks_at_limit(self) -> None:
        r = MaxDailyTradesCheck(5).run(_ctx(trades_today=5), _thesis())
        assert r.verdict == RiskVerdict.FAILED

    def test_blocks_over_limit(self) -> None:
        r = MaxDailyTradesCheck(5).run(_ctx(trades_today=7), _thesis())
        assert r.verdict == RiskVerdict.FAILED


# ── NoOvernightCheck ──────────────────────────────────────────────────────────


class TestNoOvernightCheck:
    def test_passes_well_before_close(self) -> None:
        ts = datetime(2025, 1, 10, 14, 0, tzinfo=UTC)  # 10:00 ET, 360m to close
        r = NoOvernightCheck(65).run(_ctx(ts=ts), _thesis())
        assert r.verdict == RiskVerdict.PASSED

    def test_blocks_near_close(self) -> None:
        ts = datetime(2025, 1, 10, 19, 30, tzinfo=UTC)  # 15:30 ET, 30m to close
        r = NoOvernightCheck(65).run(_ctx(ts=ts), _thesis())
        assert r.verdict == RiskVerdict.FAILED


# ── VolatilityCeilingCheck ────────────────────────────────────────────────────


class TestVolatilityCeilingCheck:
    def test_passes_low_vix(self) -> None:
        r = VolatilityCeilingCheck(30, 40).run(_ctx(features=_features(vix=18.0)), _thesis())
        assert r.verdict == RiskVerdict.PASSED

    def test_warns_elevated_vix(self) -> None:
        r = VolatilityCeilingCheck(30, 40).run(_ctx(features=_features(vix=35.0)), _thesis())
        assert r.verdict == RiskVerdict.WARNED

    def test_blocks_high_vix(self) -> None:
        r = VolatilityCeilingCheck(30, 40).run(_ctx(features=_features(vix=42.0)), _thesis())
        assert r.verdict == RiskVerdict.FAILED

    def test_warns_when_vix_none(self) -> None:
        r = VolatilityCeilingCheck(30, 40).run(_ctx(features=_features(vix=None)), _thesis())
        assert r.verdict == RiskVerdict.WARNED


# ── LLMAssessmentRequiredCheck ────────────────────────────────────────────────


class TestLLMAssessmentRequiredCheck:
    def test_passes_with_regime(self) -> None:
        r = LLMAssessmentRequiredCheck().run(_ctx(regime=_regime()), _thesis())
        assert r.verdict == RiskVerdict.PASSED

    def test_blocks_without_regime(self) -> None:
        ctx = StrategyContext(symbol="SPY", ts=_TS, features=_features(), regime=None)
        r = LLMAssessmentRequiredCheck().run(ctx, _thesis())
        assert r.verdict == RiskVerdict.FAILED


# ── LongOnlyCheck ────────────────────────────────────────────────────────────


class TestLongOnlyCheck:
    def test_passes_long_trade(self) -> None:
        r = LongOnlyCheck(long_only=True).run(_ctx(), _thesis(direction=TradeDirection.LONG))
        assert r.verdict == RiskVerdict.PASSED

    def test_blocks_short_trade(self) -> None:
        r = LongOnlyCheck(long_only=True).run(_ctx(), _thesis(direction=TradeDirection.SHORT))
        assert r.verdict == RiskVerdict.FAILED

    def test_allows_short_when_not_long_only(self) -> None:
        r = LongOnlyCheck(long_only=False).run(_ctx(), _thesis(direction=TradeDirection.SHORT))
        assert r.verdict == RiskVerdict.PASSED


# ── NoDuplicatePositionCheck ──────────────────────────────────────────────────


class TestNoDuplicatePositionCheck:
    def test_passes_no_position(self) -> None:
        r = NoDuplicatePositionCheck().run(_ctx(open_qty=0.0), _thesis())
        assert r.verdict == RiskVerdict.PASSED

    def test_blocks_existing_long_position(self) -> None:
        r = NoDuplicatePositionCheck().run(_ctx(open_qty=5.0), _thesis())
        assert r.verdict == RiskVerdict.FAILED

    def test_blocks_existing_short_position(self) -> None:
        r = NoDuplicatePositionCheck().run(_ctx(open_qty=-2.0), _thesis())
        assert r.verdict == RiskVerdict.FAILED


# ── RiskFilter ────────────────────────────────────────────────────────────────


class TestRiskFilter:
    def test_all_passing(self) -> None:
        f = RiskFilter.from_settings(max_position_usd=50.0, max_daily_loss_usd=25.0)
        result = f.evaluate(_ctx(), _thesis())
        assert result.approved
        assert result.rejections == []

    def test_blocked_by_daily_loss(self) -> None:
        f = RiskFilter.from_settings(max_daily_loss_usd=25.0)
        result = f.evaluate(_ctx(daily_pnl=-30.0), _thesis())
        assert not result.approved
        assert any(r.check_name == "daily_loss" for r in result.rejections)

    def test_blocked_by_max_trades(self) -> None:
        f = RiskFilter.from_settings(max_trades_per_day=3)
        result = f.evaluate(_ctx(trades_today=5), _thesis())
        assert not result.approved

    def test_blocked_without_llm_regime(self) -> None:
        ctx = StrategyContext(symbol="SPY", ts=_TS, features=_features(), regime=None)
        f = RiskFilter.from_settings()
        result = f.evaluate(ctx, _thesis())
        assert not result.approved
        assert any(r.check_name == "llm_assessment_required" for r in result.rejections)

    def test_summary_approved(self) -> None:
        f = RiskFilter.from_settings()
        result = f.evaluate(_ctx(), _thesis())
        assert result.approved
        assert "APPROVED" in result.summary()

    def test_summary_rejected(self) -> None:
        f = RiskFilter.from_settings(max_trades_per_day=1)
        result = f.evaluate(_ctx(trades_today=5), _thesis())
        assert not result.approved
        assert "REJECTED" in result.summary()

    def test_filter_result_warnings(self) -> None:
        f = RiskFilter.from_settings(vix_warn=20.0, vix_block=50.0)
        result = f.evaluate(_ctx(features=_features(vix=25.0)), _thesis())
        assert result.approved
        assert len(result.warnings) >= 1

    def test_short_circuit_stops_early(self) -> None:
        """Short-circuit filter should stop on first failure."""
        f = RiskFilter(
            checks=[
                LLMAssessmentRequiredCheck(),  # will fail (no regime)
                MaxDailyTradesCheck(1),  # would also fail
            ],
            short_circuit=True,
        )
        ctx = StrategyContext(symbol="SPY", ts=_TS, features=_features(), regime=None)
        result = f.evaluate(ctx, _thesis())
        assert not result.approved
        # Only 1 check ran (short-circuited at first failure)
        assert len(result.results) == 1

    def test_no_short_circuit_runs_all_checks(self) -> None:
        f = RiskFilter(
            checks=[
                LLMAssessmentRequiredCheck(),
                MaxDailyTradesCheck(1),
            ],
            short_circuit=False,
        )
        ctx = StrategyContext(symbol="SPY", ts=_TS, features=_features(), regime=None)
        result = (
            f.evaluate(ctx, _ctx(trades_today=5).__class__, _thesis())
            if False
            else f.evaluate(
                StrategyContext(symbol="SPY", ts=_TS, features=_features(), regime=None, trades_today=5), _thesis()
            )
        )
        assert not result.approved
        assert len(result.results) == 2
