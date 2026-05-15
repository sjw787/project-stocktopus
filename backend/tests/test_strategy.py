"""Tests for the OpeningMomentumStrategy signal logic.

All tests use synthetic StrategyContext / FeatureVector instances — no DB required.
"""

from __future__ import annotations

from datetime import UTC, datetime

from stocktopus.features.models import (
    FeatureVector,
    Regime,
    RegimeAssessment,
    TradeDirection,
    TradeLean,
)
from stocktopus.strategies.base import StrategyContext
from stocktopus.strategies.opening_momentum import OpeningMomentumStrategy

# ── Fixtures ──────────────────────────────────────────────────────────────────

# 10:00 ET → 14:00 UTC (within the allowed window)
_TS_IN_WINDOW = datetime(2025, 1, 10, 14, 0, 0, tzinfo=UTC)

# 09:31 ET → 13:31 UTC (just 1 minute after open — too early by default)
_TS_TOO_EARLY = datetime(2025, 1, 10, 13, 31, 0, tzinfo=UTC)

# 15:30 ET → 19:30 UTC (only 30m to close — blocked by default config)
_TS_TOO_LATE = datetime(2025, 1, 10, 19, 30, 0, tzinfo=UTC)


def _regime(
    lean: TradeLean = TradeLean.LONG,
    confidence: int = 7,
    regime: Regime = Regime.TRENDING_UP,
) -> RegimeAssessment:
    return RegimeAssessment(
        regime=regime,
        lean=lean,
        confidence=confidence,
        reasoning="Test regime",
        key_risks=["test risk"],
        invalidation="test invalidation",
    )


def _features(
    close: float = 580.0,
    gap_pct: float = 0.8,
    rvol: float = 2.5,
    above_vwap: bool = True,
    vix: float | None = 18.0,
) -> FeatureVector:
    return FeatureVector(
        symbol="SPY",
        ts=_TS_IN_WINDOW,
        close=close,
        gap_pct=gap_pct,
        rvol=rvol,
        above_vwap=above_vwap,
        vix=vix,
    )


def _ctx(
    ts: datetime = _TS_IN_WINDOW,
    features: FeatureVector | None = None,
    regime: RegimeAssessment | None = None,
) -> StrategyContext:
    return StrategyContext(
        symbol="SPY",
        ts=ts,
        features=features or _features(),
        regime=regime if regime is not None else _regime(),
    )


# ── Tests ──────────────────────────────────────────────────────────────────────


class TestOpeningMomentumStrategy:
    strategy = OpeningMomentumStrategy()

    def test_all_conditions_met_returns_thesis(self) -> None:
        thesis = self.strategy.evaluate(_ctx())
        assert thesis is not None
        assert thesis.direction == TradeDirection.LONG
        assert thesis.symbol == "SPY"
        assert thesis.entry_price == 580.0
        assert thesis.stop_loss < thesis.entry_price
        assert thesis.take_profit > thesis.entry_price

    def test_strategy_name_and_version(self) -> None:
        assert self.strategy.name == "opening_momentum"
        assert self.strategy.version  # non-empty string

    def test_too_early_after_open_returns_none(self) -> None:
        thesis = self.strategy.evaluate(_ctx(ts=_TS_TOO_EARLY))
        assert thesis is None

    def test_too_close_to_close_returns_none(self) -> None:
        thesis = self.strategy.evaluate(_ctx(ts=_TS_TOO_LATE))
        assert thesis is None

    def test_gap_below_minimum_returns_none(self) -> None:
        thesis = self.strategy.evaluate(_ctx(features=_features(gap_pct=0.1)))
        assert thesis is None

    def test_gap_none_returns_none(self) -> None:
        thesis = self.strategy.evaluate(_ctx(features=_features(gap_pct=None)))
        assert thesis is None

    def test_rvol_below_minimum_returns_none(self) -> None:
        thesis = self.strategy.evaluate(_ctx(features=_features(rvol=0.9)))
        assert thesis is None

    def test_rvol_none_returns_none(self) -> None:
        thesis = self.strategy.evaluate(_ctx(features=_features(rvol=None)))
        assert thesis is None

    def test_below_vwap_returns_none(self) -> None:
        thesis = self.strategy.evaluate(_ctx(features=_features(above_vwap=False)))
        assert thesis is None

    def test_no_regime_assessment_returns_none(self) -> None:
        ctx = StrategyContext(symbol="SPY", ts=_TS_IN_WINDOW, features=_features(), regime=None)
        assert self.strategy.evaluate(ctx) is None

    def test_lean_not_long_returns_none(self) -> None:
        thesis = self.strategy.evaluate(_ctx(regime=_regime(lean=TradeLean.NO_TRADE)))
        assert thesis is None

    def test_lean_short_returns_none(self) -> None:
        thesis = self.strategy.evaluate(_ctx(regime=_regime(lean=TradeLean.SHORT)))
        assert thesis is None

    def test_low_llm_confidence_returns_none(self) -> None:
        # Default min_llm_confidence in YAML is 6 — confidence of 4 should fail
        thesis = self.strategy.evaluate(_ctx(regime=_regime(confidence=4)))
        assert thesis is None

    def test_disallowed_regime_returns_none(self) -> None:
        thesis = self.strategy.evaluate(_ctx(regime=_regime(regime=Regime.HIGH_VOLATILITY, lean=TradeLean.LONG)))
        assert thesis is None

    def test_risk_reward_is_positive(self) -> None:
        thesis = self.strategy.evaluate(_ctx())
        assert thesis is not None
        assert thesis.risk_reward is not None
        assert thesis.risk_reward > 0

    def test_dynamic_tp_extension_at_high_confidence(self) -> None:
        """High LLM confidence should produce a larger take_profit."""
        low_conf_thesis = self.strategy.evaluate(_ctx(regime=_regime(confidence=6)))
        high_conf_thesis = self.strategy.evaluate(_ctx(regime=_regime(confidence=9)))
        assert low_conf_thesis is not None
        assert high_conf_thesis is not None
        assert high_conf_thesis.take_profit >= low_conf_thesis.take_profit

    def test_rationale_contains_key_info(self) -> None:
        thesis = self.strategy.evaluate(_ctx())
        assert thesis is not None
        assert "SPY" in thesis.rationale
        assert "Gap" in thesis.rationale
        assert "RVOL" in thesis.rationale
