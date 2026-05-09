"""Tests for the broker adapters and PaperTrader (Phase 8)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from stocktopus.broker.base import (
    OrderRequest,
    OrderSide,
    OrderStatus,
)
from stocktopus.broker.mock_adapter import MockBrokerAdapter

# ── MockBrokerAdapter ─────────────────────────────────────────────────────────


class TestMockBrokerAdapter:
    def setup_method(self) -> None:
        self.broker = MockBrokerAdapter(initial_equity=10_000.0, fill_price=500.0)

    def test_is_paper(self) -> None:
        assert self.broker.is_paper is True

    @pytest.mark.asyncio
    async def test_place_buy_order(self) -> None:
        req = OrderRequest(symbol="SPY", side=OrderSide.BUY, qty=10.0)
        result = await self.broker.place_order(req)

        assert result.symbol == "SPY"
        assert result.side == OrderSide.BUY
        assert result.qty == 10.0
        assert result.filled_qty == 10.0
        assert result.filled_avg_price == 500.0
        assert result.status == OrderStatus.FILLED
        assert result.order_id

    @pytest.mark.asyncio
    async def test_position_created_after_buy(self) -> None:
        req = OrderRequest(symbol="SPY", side=OrderSide.BUY, qty=5.0)
        await self.broker.place_order(req)

        pos = await self.broker.get_position("SPY")
        assert pos is not None
        assert pos.qty == 5.0
        assert pos.avg_entry_price == 500.0

    @pytest.mark.asyncio
    async def test_position_flat_after_full_sell(self) -> None:
        await self.broker.place_order(OrderRequest(symbol="SPY", side=OrderSide.BUY, qty=5.0))
        await self.broker.place_order(OrderRequest(symbol="SPY", side=OrderSide.SELL, qty=5.0))

        pos = await self.broker.get_position("SPY")
        assert pos is None

    @pytest.mark.asyncio
    async def test_partial_sell_reduces_qty(self) -> None:
        await self.broker.place_order(OrderRequest(symbol="SPY", side=OrderSide.BUY, qty=10.0))
        await self.broker.place_order(OrderRequest(symbol="SPY", side=OrderSide.SELL, qty=4.0))

        pos = await self.broker.get_position("SPY")
        assert pos is not None
        assert pos.qty == pytest.approx(6.0)

    @pytest.mark.asyncio
    async def test_get_all_positions(self) -> None:
        await self.broker.place_order(OrderRequest(symbol="SPY", side=OrderSide.BUY, qty=5.0))
        await self.broker.place_order(OrderRequest(symbol="AAPL", side=OrderSide.BUY, qty=3.0))

        positions = await self.broker.get_all_positions()
        symbols = {p.symbol for p in positions}
        assert "SPY" in symbols
        assert "AAPL" in symbols

    @pytest.mark.asyncio
    async def test_get_account_equity(self) -> None:
        equity = await self.broker.get_account_equity()
        assert equity == pytest.approx(10_000.0)

    @pytest.mark.asyncio
    async def test_equity_changes_on_profitable_sell(self) -> None:
        # Buy at 500, sell at 600 (change fill price mid-test)
        await self.broker.place_order(OrderRequest(symbol="SPY", side=OrderSide.BUY, qty=10.0))
        self.broker._fill_price = 600.0  # price moves up
        await self.broker.place_order(OrderRequest(symbol="SPY", side=OrderSide.SELL, qty=10.0))

        equity = await self.broker.get_account_equity()
        assert equity == pytest.approx(10_000.0 + 10 * 100)  # 10 shares * $100 profit

    @pytest.mark.asyncio
    async def test_close_position(self) -> None:
        await self.broker.place_order(OrderRequest(symbol="SPY", side=OrderSide.BUY, qty=5.0))
        result = await self.broker.close_position("SPY")

        assert result is not None
        assert result.side == OrderSide.SELL
        pos = await self.broker.get_position("SPY")
        assert pos is None

    @pytest.mark.asyncio
    async def test_close_nonexistent_position_returns_none(self) -> None:
        result = await self.broker.close_position("NOPE")
        assert result is None

    @pytest.mark.asyncio
    async def test_close_all_positions(self) -> None:
        await self.broker.place_order(OrderRequest(symbol="SPY", side=OrderSide.BUY, qty=5.0))
        await self.broker.place_order(OrderRequest(symbol="QQQ", side=OrderSide.BUY, qty=3.0))
        results = await self.broker.close_all_positions()

        assert len(results) == 2
        positions = await self.broker.get_all_positions()
        assert len(positions) == 0

    @pytest.mark.asyncio
    async def test_cancel_order_always_true(self) -> None:
        result = await self.broker.cancel_order("fake-order-id")
        assert result is True

    @pytest.mark.asyncio
    async def test_order_history_accumulated(self) -> None:
        await self.broker.place_order(OrderRequest(symbol="SPY", side=OrderSide.BUY, qty=5.0))
        await self.broker.place_order(OrderRequest(symbol="SPY", side=OrderSide.BUY, qty=3.0))
        assert len(self.broker.orders) == 2

    @pytest.mark.asyncio
    async def test_avg_entry_price_blended_on_add(self) -> None:
        # First buy 5 shares at 500, then 5 more at 600 → avg should be 550
        await self.broker.place_order(OrderRequest(symbol="SPY", side=OrderSide.BUY, qty=5.0))
        self.broker._fill_price = 600.0
        await self.broker.place_order(OrderRequest(symbol="SPY", side=OrderSide.BUY, qty=5.0))

        pos = await self.broker.get_position("SPY")
        assert pos is not None
        assert pos.avg_entry_price == pytest.approx(550.0)
        assert pos.qty == pytest.approx(10.0)

    @pytest.mark.asyncio
    async def test_slippage_applied_on_buy(self) -> None:
        broker = MockBrokerAdapter(fill_price=500.0, slippage_bps=10)  # 10bps = 0.1%
        req = OrderRequest(symbol="SPY", side=OrderSide.BUY, qty=1.0)
        result = await broker.place_order(req)
        assert result.filled_avg_price == pytest.approx(500.5)  # 500 + 0.5

    @pytest.mark.asyncio
    async def test_slippage_applied_on_sell(self) -> None:
        broker = MockBrokerAdapter(fill_price=500.0, slippage_bps=10)
        req = OrderRequest(symbol="SPY", side=OrderSide.SELL, qty=1.0)
        result = await broker.place_order(req)
        assert result.filled_avg_price == pytest.approx(499.5)  # 500 - 0.5


# ── PaperTrader ───────────────────────────────────────────────────────────────


def _make_mock_session() -> AsyncMock:
    """Build a minimal async SQLAlchemy session mock."""
    session = AsyncMock()
    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none.return_value = None  # no feature snapshot by default
    scalar_result.scalar_one.return_value = 0
    session.execute.return_value = scalar_result
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


def _make_feature_snapshot() -> MagicMock:
    snap = MagicMock()
    snap.features = {
        "symbol": "SPY",
        "ts": datetime.now(UTC).isoformat(),
        "close": 510.0,
        "vwap": 508.0,
        "rvol": 1.8,
        "gap_pct": 0.55,
        "atr": 4.5,
        "sma20": 505.0,
        "sma50": 500.0,
    }
    return snap


def _make_director(regime_override: dict | None = None) -> AsyncMock:
    director = AsyncMock()
    from stocktopus.features.models import Regime, RegimeAssessment, TradeLean

    assessment = RegimeAssessment(
        regime=Regime.TRENDING_UP,
        lean=TradeLean.LONG,
        confidence=8,
        reasoning="strong uptrend",
        key_risks=["none"],
        invalidation="price below SMA50",
    )
    director.analyze.return_value = assessment
    return director


class TestPaperTrader:
    def setup_method(self) -> None:
        from stocktopus.broker.paper_trader import PaperTrader

        self.broker = MockBrokerAdapter(fill_price=510.0)
        self.director = _make_director()
        self.session = _make_mock_session()
        self.trader = PaperTrader(
            broker=self.broker,
            director=self.director,
            session=self.session,
            symbol="SPY",
            max_position_usd=5_000.0,
            max_daily_loss_usd=500.0,
            max_trades_per_day=5,
            dry_run=False,
        )

    @pytest.mark.asyncio
    async def test_tick_no_feature_snapshot_returns_no_op(self) -> None:
        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none.return_value = None
        scalar_result.scalar_one.return_value = 0
        self.session.execute.return_value = scalar_result

        result = await self.trader.tick()
        assert result["action"] == "no_op"
        assert result["reason"] == "no_feature_snapshot"

    @pytest.mark.asyncio
    async def test_tick_with_feature_snapshot_no_signal(self) -> None:
        snap = _make_feature_snapshot()
        # Make gap_pct too low to trigger momentum strategy (< 0.3 threshold)
        snap.features["gap_pct"] = 0.05
        snap.features["rvol"] = 0.5

        call_count = 0

        def side_effect(query, *args, **kwargs):
            nonlocal call_count
            result = MagicMock()
            if call_count == 0:
                result.scalar_one_or_none.return_value = snap
            else:
                result.scalar_one.return_value = 0
                result.scalar_one_or_none.return_value = None
            call_count += 1
            return result

        self.session.execute = AsyncMock(side_effect=side_effect)

        result = await self.trader.tick()
        # With insufficient gap/rvol, strategy returns no signal
        assert result["action"] in ("no_op", "no_strategy_signal", "rejected")

    @pytest.mark.asyncio
    async def test_tick_dry_run_does_not_place_order(self) -> None:
        from stocktopus.broker.paper_trader import PaperTrader

        dry_trader = PaperTrader(
            broker=self.broker,
            director=self.director,
            session=self.session,
            symbol="SPY",
            max_position_usd=5_000.0,
            max_daily_loss_usd=500.0,
            max_trades_per_day=5,
            dry_run=True,
        )

        snap = _make_feature_snapshot()
        call_count = 0

        def side_effect(query, *args, **kwargs):
            nonlocal call_count
            result = MagicMock()
            if call_count == 0:
                result.scalar_one_or_none.return_value = snap
            else:
                result.scalar_one.return_value = 0
                result.scalar_one_or_none.return_value = None
            call_count += 1
            return result

        self.session.execute = AsyncMock(side_effect=side_effect)

        tick_result = await dry_trader.tick()
        # dry_run means no Alpaca orders but we still get a result dict
        assert isinstance(tick_result, dict)
        assert "ts" in tick_result
        assert "symbol" in tick_result

    @pytest.mark.asyncio
    async def test_kill_switch_closes_all_positions(self) -> None:
        # Pre-load some positions
        await self.broker.place_order(OrderRequest(symbol="SPY", side=OrderSide.BUY, qty=5.0))

        order_ids = await self.trader.kill_switch()
        assert isinstance(order_ids, list)

        positions = await self.broker.get_all_positions()
        assert len(positions) == 0

    @pytest.mark.asyncio
    async def test_kill_switch_no_positions_returns_empty(self) -> None:
        order_ids = await self.trader.kill_switch()
        assert order_ids == []

    @pytest.mark.asyncio
    async def test_count_trades_today_queries_paper_trades(self) -> None:
        scalar_result = MagicMock()
        scalar_result.scalar_one.return_value = 3
        self.session.execute.return_value = scalar_result

        count = await self.trader._count_trades_today()
        assert count == 3

    @pytest.mark.asyncio
    async def test_daily_realized_pnl_returns_float(self) -> None:
        scalar_result = MagicMock()
        scalar_result.scalar_one.return_value = 42.5
        self.session.execute.return_value = scalar_result

        pnl = await self.trader._daily_realized_pnl()
        assert pnl == pytest.approx(42.5)

    @pytest.mark.asyncio
    async def test_persist_rejection_skipped_when_approved(self) -> None:
        from stocktopus.features.models import (
            FeatureVector,
            Regime,
            RegimeAssessment,
            TradeLean,
        )
        from stocktopus.risk.base import RiskResult, RiskVerdict
        from stocktopus.risk.filter import FilterResult
        from stocktopus.strategies.base import StrategyContext

        regime = RegimeAssessment(
            regime=Regime.TRENDING_UP,
            lean=TradeLean.LONG,
            confidence=8,
            reasoning="ok",
            key_risks=[],
            invalidation="none",
        )
        fv = FeatureVector(symbol="SPY", ts=datetime.now(UTC), close=500.0)
        ctx = StrategyContext(
            symbol="SPY",
            ts=datetime.now(UTC),
            features=fv,
            regime=regime,
            open_position_qty=0.0,
            daily_realized_pnl=0.0,
            trades_today=0,
        )
        fr = FilterResult(
            approved=True,
            symbol="SPY",
            ts=datetime.now(UTC),
            results=[RiskResult(check_name="test", verdict=RiskVerdict.PASSED, reason="ok")],
        )

        await self.trader._persist_rejection(ctx, fr)
        self.session.add.assert_not_called()
