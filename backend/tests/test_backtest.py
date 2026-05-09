"""Tests for the backtesting harness — friction, records, and runner logic."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pandas as pd
import pytest

from stocktopus.backtest.friction import FrictionModel
from stocktopus.backtest.records import BacktestMetrics, BacktestTrade, ExitReason
from stocktopus.backtest.runner import BacktestRunner, _compute_features
from stocktopus.features.models import Regime, RegimeAssessment, TradeLean

# ── FrictionModel ──────────────────────────────────────────────────────────────


class TestFrictionModel:
    def test_zero_model_no_costs(self) -> None:
        f = FrictionModel.zero()
        assert f.entry_cost(500.0, 1.0) == 0.0
        assert f.exit_cost(510.0, 1.0) == 0.0
        assert f.total_round_trip(500.0, 510.0, 1.0) == 0.0

    def test_realistic_model_positive_costs(self) -> None:
        f = FrictionModel.realistic_alpaca()
        assert f.entry_cost(500.0, 1.0) > 0
        assert f.exit_cost(510.0, 1.0) > 0

    def test_slippage_scales_with_notional(self) -> None:
        f = FrictionModel(slippage_bps=2.0)
        cost_100 = f.entry_cost(100.0, 1.0)
        cost_200 = f.entry_cost(200.0, 1.0)
        assert cost_200 == pytest.approx(cost_100 * 2, rel=0.01)

    def test_exit_includes_sec_fee(self) -> None:
        f = FrictionModel(slippage_bps=0, sec_fee_rate=0.01, finra_taf_rate=0, finra_taf_cap=0)
        cost = f.exit_cost(100.0, 1.0)
        assert cost == pytest.approx(1.0, rel=0.001)

    def test_finra_taf_capped(self) -> None:
        f = FrictionModel(slippage_bps=0, sec_fee_rate=0, finra_taf_rate=1.0, finra_taf_cap=5.0)
        # 10 shares × $1/share = $10, but capped at $5
        assert f.exit_cost(100.0, 10.0) == pytest.approx(5.0)

    def test_round_trip_is_entry_plus_exit(self) -> None:
        f = FrictionModel.realistic_alpaca()
        assert f.total_round_trip(500.0, 510.0, 2.0) == pytest.approx(
            f.entry_cost(500.0, 2.0) + f.exit_cost(510.0, 2.0)
        )


# ── BacktestTrade ─────────────────────────────────────────────────────────────


class TestBacktestTrade:
    def _trade(
        self,
        entry: float = 500.0,
        exit_price: float = 510.0,
        qty: float = 1.0,
        entry_friction: float = 0.0,
        exit_friction: float = 0.0,
        reason: ExitReason = ExitReason.TAKE_PROFIT,
    ) -> BacktestTrade:
        base = datetime(2025, 1, 10, 14, 0, tzinfo=UTC)
        return BacktestTrade(
            symbol="SPY",
            entry_ts=base,
            exit_ts=base + timedelta(minutes=30),
            entry_price=entry,
            exit_price=exit_price,
            qty=qty,
            stop_loss=entry * 0.99,
            take_profit=entry * 1.02,
            exit_reason=reason,
            entry_friction=entry_friction,
            exit_friction=exit_friction,
        )

    def test_gross_pnl_winner(self) -> None:
        t = self._trade(entry=500.0, exit_price=510.0, qty=2.0)
        assert t.gross_pnl == pytest.approx(20.0)

    def test_gross_pnl_loser(self) -> None:
        t = self._trade(entry=500.0, exit_price=495.0, qty=2.0)
        assert t.gross_pnl == pytest.approx(-10.0)

    def test_net_pnl_deducts_friction(self) -> None:
        t = self._trade(
            entry=500.0, exit_price=510.0, qty=1.0,
            entry_friction=1.0, exit_friction=2.0,
        )
        assert t.net_pnl == pytest.approx(7.0)

    def test_is_winner(self) -> None:
        assert self._trade(exit_price=510.0).is_winner
        assert not self._trade(exit_price=490.0).is_winner

    def test_hold_minutes(self) -> None:
        t = self._trade()
        assert t.hold_minutes == pytest.approx(30.0)

    def test_to_dict_keys(self) -> None:
        d = self._trade().to_dict()
        assert "entry_ts" in d
        assert "net_pnl" in d
        assert "exit_reason" in d


# ── BacktestMetrics ────────────────────────────────────────────────────────────


class TestBacktestMetrics:
    def _metrics(
        self,
        initial: float = 10_000.0,
        final: float = 10_100.0,
        total: int = 10,
        wins: int = 6,
        gross_profit: float = 200.0,
        gross_loss: float = -100.0,
    ) -> BacktestMetrics:
        base = datetime(2025, 1, 2, tzinfo=UTC)
        return BacktestMetrics(
            symbol="SPY",
            start_date=base,
            end_date=base + timedelta(days=90),
            initial_capital=initial,
            final_capital=final,
            total_trades=total,
            winning_trades=wins,
            losing_trades=total - wins,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
        )

    def test_win_rate(self) -> None:
        m = self._metrics(total=10, wins=6)
        assert m.win_rate == pytest.approx(0.6)

    def test_win_rate_zero_trades(self) -> None:
        m = self._metrics(total=0, wins=0)
        assert m.win_rate == 0.0

    def test_profit_factor(self) -> None:
        m = self._metrics(gross_profit=200.0, gross_loss=-100.0)
        assert m.profit_factor == pytest.approx(2.0)

    def test_profit_factor_none_when_no_losses(self) -> None:
        m = self._metrics(gross_loss=0.0)
        assert m.profit_factor is None

    def test_expectancy(self) -> None:
        m = self._metrics(initial=10_000.0, final=10_100.0, total=10)
        assert m.expectancy == pytest.approx(10.0)

    def test_total_return_pct(self) -> None:
        m = self._metrics(initial=10_000.0, final=11_000.0)
        assert m.total_return_pct == pytest.approx(10.0)

    def test_to_dict_contains_required_keys(self) -> None:
        d = self._metrics().to_dict()
        for k in ["win_rate", "profit_factor", "expectancy", "max_drawdown_pct", "total_trades"]:
            assert k in d


# ── _compute_features ─────────────────────────────────────────────────────────


def _make_bars(n: int = 50, base_price: float = 500.0) -> pd.DataFrame:
    """Generate synthetic 5-minute bars starting at 13:30 UTC."""
    base = datetime(2025, 1, 10, 13, 30, tzinfo=UTC)
    rows = []
    price = base_price
    for i in range(n):
        close = price + (i % 7 - 3) * 0.5
        rows.append(
            {
                "symbol": "SPY",
                "ts": base + timedelta(minutes=5 * i),
                "open": close - 0.1,
                "high": close + 0.3,
                "low": close - 0.3,
                "close": close,
                "volume": 10_000 + i * 100,
            }
        )
        price = close
    return pd.DataFrame(rows)


class TestComputeFeatures:
    def test_returns_none_for_invalid_index(self) -> None:
        bars = _make_bars(10)
        assert _compute_features(bars, -1) is None
        assert _compute_features(bars, 100) is None

    def test_returns_feature_vector(self) -> None:
        bars = _make_bars(30)
        fv = _compute_features(bars, 20)
        assert fv is not None
        assert fv.symbol == "SPY"
        assert fv.close > 0

    def test_rvol_computed_after_20_bars(self) -> None:
        bars = _make_bars(30)
        fv = _compute_features(bars, 25)
        assert fv is not None
        assert fv.rvol is not None

    def test_vwap_computed(self) -> None:
        bars = _make_bars(20)
        fv = _compute_features(bars, 10)
        assert fv is not None
        assert fv.vwap is not None

    def test_atr_computed_after_14_bars(self) -> None:
        bars = _make_bars(30)
        fv = _compute_features(bars, 20)
        assert fv is not None
        assert fv.atr_14d is not None


# ── BacktestRunner integration ────────────────────────────────────────────────


def _default_regime() -> RegimeAssessment:
    return RegimeAssessment(
        regime=Regime.TRENDING_UP,
        lean=TradeLean.LONG,
        confidence=7,
        reasoning="test",
        key_risks=["r1"],
        invalidation="inv",
    )


def _regime_map(bars: pd.DataFrame) -> dict:
    """Provide the same regime for every date in the bar range."""
    dates = {row["ts"].date() for _, row in bars.iterrows()}
    ra = _default_regime()
    return {d: ra for d in dates}


class TestBacktestRunner:
    def test_runner_returns_trades_and_metrics(self) -> None:
        bars = _make_bars(n=200)
        runner = BacktestRunner(
            symbol="SPY",
            intraday_bars=bars,
            regime_map=_regime_map(bars),
            friction=FrictionModel.zero(),
            initial_capital=10_000.0,
            position_size_usd=500.0,
        )
        trades, metrics = runner.run()
        assert isinstance(trades, list)
        assert metrics.total_trades >= 0
        assert metrics.initial_capital == 10_000.0

    def test_metrics_trade_count_matches_trades_list(self) -> None:
        bars = _make_bars(n=200)
        runner = BacktestRunner(
            symbol="SPY",
            intraday_bars=bars,
            regime_map=_regime_map(bars),
            friction=FrictionModel.zero(),
            initial_capital=10_000.0,
            position_size_usd=500.0,
        )
        trades, metrics = runner.run()
        assert metrics.total_trades == len(trades)

    def test_no_trades_with_empty_regime_map(self) -> None:
        """No regime assessments → risk filter blocks every trade (llm_required)."""
        bars = _make_bars(n=100)
        runner = BacktestRunner(
            symbol="SPY",
            intraday_bars=bars,
            regime_map={},  # no regime
            friction=FrictionModel.zero(),
            initial_capital=10_000.0,
            position_size_usd=500.0,
        )
        trades, metrics = runner.run()
        assert metrics.total_trades == 0

    def test_zero_friction_gives_larger_pnl_than_realistic(self) -> None:
        bars = _make_bars(n=200)
        rmap = _regime_map(bars)

        runner_zero = BacktestRunner(
            symbol="SPY",
            intraday_bars=bars,
            regime_map=rmap,
            friction=FrictionModel.zero(),
            initial_capital=10_000.0,
            position_size_usd=500.0,
        )
        _, m_zero = runner_zero.run()

        runner_real = BacktestRunner(
            symbol="SPY",
            intraday_bars=bars,
            regime_map=rmap,
            friction=FrictionModel.realistic_alpaca(),
            initial_capital=10_000.0,
            position_size_usd=500.0,
        )
        _, m_real = runner_real.run()

        # Net return with realistic friction ≤ zero-friction (friction reduces PnL)
        assert m_real.net_profit <= m_zero.net_profit


# ── DriftChecker ──────────────────────────────────────────────────────────────


class TestDriftChecker:
    """Tests for the live vs backtest drift alarm."""

    def _make_session(self, rows: list[dict]) -> AsyncMock:
        from unittest.mock import MagicMock

        session = AsyncMock()

        class FakeRow:
            def __init__(self, realized_pnl: float, regime: str) -> None:
                self.realized_pnl = realized_pnl
                self.regime = regime

        fake_rows = [FakeRow(r["pnl"], r.get("regime", "trending_up")) for r in rows]
        execute_result = MagicMock()
        execute_result.fetchall.return_value = fake_rows
        session.execute.return_value = execute_result
        return session

    @pytest.mark.asyncio
    async def test_no_trades_returns_zero_metrics(self) -> None:
        from stocktopus.backtest.drift import DriftChecker

        checker = DriftChecker()
        session = self._make_session([])
        status = await checker.check(session)

        assert status.live.n_trades == 0
        assert not status.alarm_active

    @pytest.mark.asyncio
    async def test_good_distribution_no_alarm(self) -> None:
        from stocktopus.backtest.drift import DriftChecker

        # 6 wins of $10, 4 losses of $5 → win_rate=60%, PF=3.0
        rows = [{"pnl": 10.0, "regime": "trending_up"}] * 6 + [
            {"pnl": -5.0, "regime": "ranging"}
        ] * 4
        checker = DriftChecker(min_win_rate=0.40, min_profit_factor=1.0)
        session = self._make_session(rows)
        status = await checker.check(session)

        assert not status.alarm_active
        assert status.live.win_rate == pytest.approx(0.60)
        assert status.live.profit_factor > 1.0

    @pytest.mark.asyncio
    async def test_low_win_rate_fires_alarm(self) -> None:
        from stocktopus.backtest.drift import DriftChecker

        # 3 wins, 7 losses → win_rate = 30%, below 40% threshold
        rows = [{"pnl": 10.0, "regime": "trending_up"}] * 3 + [
            {"pnl": -5.0, "regime": "ranging"}
        ] * 7
        checker = DriftChecker(min_win_rate=0.40, min_profit_factor=1.0)
        session = self._make_session(rows)
        status = await checker.check(session)

        assert status.alarm_active
        assert any("win_rate" in r for r in status.alarm_reasons)

    @pytest.mark.asyncio
    async def test_low_profit_factor_fires_alarm(self) -> None:
        from stocktopus.backtest.drift import DriftChecker

        # 5 wins of $2, 5 losses of $8 → PF = 10/40 = 0.25
        rows = [{"pnl": 2.0, "regime": "trending_up"}] * 5 + [
            {"pnl": -8.0, "regime": "ranging"}
        ] * 5
        checker = DriftChecker(min_win_rate=0.30, min_profit_factor=1.0)
        session = self._make_session(rows)
        status = await checker.check(session)

        assert status.alarm_active
        assert any("profit_factor" in r for r in status.alarm_reasons)

    @pytest.mark.asyncio
    async def test_insufficient_data_no_alarm(self) -> None:
        from stocktopus.backtest.drift import DriftChecker

        # Only 5 trades — below the 10-trade minimum
        rows = [{"pnl": -5.0, "regime": "trending_up"}] * 5  # terrible but below min
        checker = DriftChecker(min_win_rate=0.50, min_profit_factor=2.0)
        session = self._make_session(rows)
        status = await checker.check(session)

        assert not status.alarm_active  # insufficient data, no alarm
        assert not status.live.is_sufficient

    @pytest.mark.asyncio
    async def test_summary_returns_string(self) -> None:
        from stocktopus.backtest.drift import DriftChecker

        rows = [{"pnl": 10.0, "regime": "trending_up"}] * 6 + [
            {"pnl": -5.0, "regime": "ranging"}
        ] * 4
        checker = DriftChecker()
        session = self._make_session(rows)
        status = await checker.check(session)

        summary = status.summary()
        assert isinstance(summary, str)
        assert len(summary) > 0

    @pytest.mark.asyncio
    async def test_regimes_extracted_correctly(self) -> None:
        from stocktopus.backtest.drift import DriftChecker

        rows = (
            [{"pnl": 5.0, "regime": "trending_up"}] * 4
            + [{"pnl": 5.0, "regime": "ranging"}] * 4
            + [{"pnl": -2.0, "regime": "high_volatility"}] * 2
        )
        checker = DriftChecker()
        session = self._make_session(rows)
        status = await checker.check(session)

        assert set(status.live.regimes_seen) == {"trending_up", "ranging", "high_volatility"}
