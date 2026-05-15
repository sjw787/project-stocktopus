"""Tests for the tax lot tracker, wash-sale detector, and report generator."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from stocktopus.tax import (
    HoldingPeriod,
    LotTracker,
    WashSaleDetector,
    WashSaleStatus,
    generate_8949_csv,
    generate_summary,
)

# ── WashSaleDetector ──────────────────────────────────────────────────────────


class TestWashSaleDetector:
    def test_no_buys_no_wash_sale(self) -> None:
        d = WashSaleDetector()
        assert not d.is_wash_sale("SPY", date(2024, 1, 10))

    def test_buy_before_sell_not_forward_wash_sale(self) -> None:
        d = WashSaleDetector()
        d.notify_buy("SPY", date(2024, 1, 1))
        # Buy was BEFORE sell — forward window doesn't fire
        assert not d.is_wash_sale("SPY", date(2024, 1, 10))

    def test_buy_within_30_days_after_sell_is_wash_sale(self) -> None:
        d = WashSaleDetector()
        sell = date(2024, 1, 10)
        d.notify_buy("SPY", sell + timedelta(days=15))
        assert d.is_wash_sale("SPY", sell)

    def test_buy_at_exactly_30_days_is_wash_sale(self) -> None:
        d = WashSaleDetector()
        sell = date(2024, 1, 1)
        d.notify_buy("SPY", sell + timedelta(days=30))
        assert d.is_wash_sale("SPY", sell)

    def test_buy_after_31_days_not_wash_sale(self) -> None:
        d = WashSaleDetector()
        sell = date(2024, 1, 1)
        d.notify_buy("SPY", sell + timedelta(days=31))
        assert not d.is_wash_sale("SPY", sell)

    def test_has_recent_loss_sell(self) -> None:
        d = WashSaleDetector()
        d.notify_sell("SPY", date(2024, 1, 1))
        assert d.has_recent_loss_sell("SPY", date(2024, 1, 25))
        assert not d.has_recent_loss_sell("SPY", date(2024, 2, 5))


# ── LotTracker: Basic FIFO ────────────────────────────────────────────────────


class TestLotTrackerFIFO:
    def test_buy_creates_open_lot(self) -> None:
        t = LotTracker()
        lot = t.record_buy("SPY", qty=10, price=500.0, trade_date=date(2024, 1, 1))
        assert lot.symbol == "SPY"
        assert lot.qty == 10
        assert lot.cost_basis == 500.0
        assert lot.is_open
        assert len(t.open_lots("SPY")) == 1

    def test_sell_closes_lot_fifo(self) -> None:
        t = LotTracker()
        t.record_buy("SPY", qty=10, price=500.0, trade_date=date(2024, 1, 1))
        result = t.record_sell("SPY", qty=10, price=510.0, trade_date=date(2024, 6, 1))
        assert len(t.open_lots("SPY")) == 0
        assert len(result.closed_lots) == 1
        assert result.raw_pnl == pytest.approx(100.0)  # 10 * (510-500)

    def test_partial_sell_splits_lot(self) -> None:
        t = LotTracker()
        t.record_buy("SPY", qty=10, price=500.0, trade_date=date(2024, 1, 1))
        result = t.record_sell("SPY", qty=3, price=510.0, trade_date=date(2024, 6, 1))
        assert len(result.closed_lots) == 1
        assert result.closed_lots[0].qty == 3
        open_lots = t.open_lots("SPY")
        assert len(open_lots) == 1
        assert open_lots[0].qty == 7

    def test_multiple_lots_consume_oldest_first(self) -> None:
        t = LotTracker()
        t.record_buy("SPY", qty=5, price=490.0, trade_date=date(2024, 1, 1))
        t.record_buy("SPY", qty=5, price=510.0, trade_date=date(2024, 3, 1))
        result = t.record_sell("SPY", qty=5, price=520.0, trade_date=date(2024, 6, 1))
        # Should consume the 490 lot first
        assert result.closed_lots[0].cost_basis == pytest.approx(490.0)
        assert result.raw_pnl == pytest.approx(150.0)  # 5 * (520-490)

    def test_unrealized_pnl(self) -> None:
        t = LotTracker()
        t.record_buy("SPY", qty=10, price=500.0, trade_date=date(2024, 1, 1))
        assert t.unrealized_pnl("SPY", 510.0) == pytest.approx(100.0)

    def test_stcg_on_close_only_short_term(self) -> None:
        t = LotTracker()
        # Short-term lot (30 days old)
        buy_date = date.today() - timedelta(days=30)
        t.record_buy("SPY", qty=5, price=490.0, trade_date=buy_date)
        # Long-term lot (400 days old)
        old_buy_date = date.today() - timedelta(days=400)
        t.record_buy("SPY", qty=5, price=450.0, trade_date=old_buy_date)

        stcg = t.stcg_on_close("SPY", 520.0)
        # Only 5 * (520-490) = 150 STCG
        assert stcg == pytest.approx(150.0)


# ── LotTracker: Holding Period ────────────────────────────────────────────────


class TestHoldingPeriod:
    def test_less_than_365_days_is_short_term(self) -> None:
        t = LotTracker()
        t.record_buy("SPY", qty=1, price=500.0, trade_date=date(2024, 1, 1))
        result = t.record_sell("SPY", qty=1, price=510.0, trade_date=date(2024, 6, 1))
        assert result.closed_lots[0].holding_period == HoldingPeriod.SHORT_TERM

    def test_365_days_is_long_term(self) -> None:
        t = LotTracker()
        buy = date(2024, 1, 1)
        sell = buy + timedelta(days=365)
        t.record_buy("SPY", qty=1, price=500.0, trade_date=buy)
        result = t.record_sell("SPY", qty=1, price=510.0, trade_date=sell)
        assert result.closed_lots[0].holding_period == HoldingPeriod.LONG_TERM

    def test_stcg_vs_ltcg_split(self) -> None:
        t = LotTracker()
        buy_short = date.today() - timedelta(days=30)
        buy_long = date.today() - timedelta(days=400)
        t.record_buy("SPY", qty=5, price=490.0, trade_date=buy_long)  # LTCG
        t.record_buy("SPY", qty=5, price=490.0, trade_date=buy_short)  # STCG
        result = t.record_sell("SPY", qty=10, price=510.0, trade_date=date.today())
        assert result.ltcg == pytest.approx(100.0)  # 5 * 20
        assert result.stcg == pytest.approx(100.0)  # 5 * 20


# ── LotTracker: Wash Sale ─────────────────────────────────────────────────────


class TestWashSaleIntegration:
    def test_loss_no_repurchase_not_wash_sale(self) -> None:
        t = LotTracker()
        t.record_buy("SPY", qty=10, price=500.0, trade_date=date(2024, 1, 1))
        result = t.record_sell("SPY", qty=10, price=490.0, trade_date=date(2024, 6, 1))
        assert not result.wash_sale_triggered
        assert result.closed_lots[0].wash_sale_status == WashSaleStatus.CLEAN

    def test_loss_with_repurchase_triggers_wash_sale(self) -> None:
        t = LotTracker()
        t.record_buy("SPY", qty=10, price=500.0, trade_date=date(2024, 1, 1))
        # Buy replacement shares 10 days after the planned sell
        sell_date = date(2024, 6, 1)
        replacement_date = sell_date + timedelta(days=10)
        t.record_buy("SPY", qty=10, price=495.0, trade_date=replacement_date)
        result = t.record_sell("SPY", qty=10, price=490.0, trade_date=sell_date)
        assert result.wash_sale_triggered
        assert result.closed_lots[0].wash_sale_status == WashSaleStatus.TRIGGERED

    def test_wash_sale_disallows_loss(self) -> None:
        t = LotTracker()
        t.record_buy("SPY", qty=10, price=500.0, trade_date=date(2024, 1, 1))
        sell_date = date(2024, 6, 1)
        t.record_buy("SPY", qty=10, price=495.0, trade_date=sell_date + timedelta(days=10))
        result = t.record_sell("SPY", qty=10, price=490.0, trade_date=sell_date)

        # Raw loss was -100 (10 * -10), but wash-sale disallows it
        assert result.raw_pnl == pytest.approx(-100.0)
        # Recognized PnL after disallowing the loss = 0 (loss added back)
        assert result.total_pnl == pytest.approx(0.0)


# ── Report ────────────────────────────────────────────────────────────────────


class TestReport:
    def test_generate_8949_csv_headers(self) -> None:
        t = LotTracker()
        t.record_buy("SPY", qty=5, price=500.0, trade_date=date(2024, 1, 1))
        t.record_sell("SPY", qty=5, price=510.0, trade_date=date(2024, 6, 1))
        csv_str = generate_8949_csv(t)
        assert "description" in csv_str
        assert "proceeds" in csv_str
        assert "gain_or_loss" in csv_str

    def test_generate_8949_csv_has_data_row(self) -> None:
        t = LotTracker()
        t.record_buy("SPY", qty=5, price=500.0, trade_date=date(2024, 1, 1))
        t.record_sell("SPY", qty=5, price=510.0, trade_date=date(2024, 6, 1))
        lines = generate_8949_csv(t).strip().split("\n")
        assert len(lines) == 2  # header + 1 data row

    def test_generate_summary_stcg_only(self) -> None:
        t = LotTracker()
        buy = date.today() - timedelta(days=30)
        t.record_buy("SPY", qty=10, price=500.0, trade_date=buy)
        t.record_sell("SPY", qty=10, price=510.0, trade_date=date.today())
        s = generate_summary(t)
        assert s["stcg"] == pytest.approx(100.0)
        assert s["ltcg"] == pytest.approx(0.0)

    def test_generate_summary_ltcg_only(self) -> None:
        t = LotTracker()
        buy = date.today() - timedelta(days=400)
        t.record_buy("SPY", qty=10, price=500.0, trade_date=buy)
        t.record_sell("SPY", qty=10, price=520.0, trade_date=date.today())
        s = generate_summary(t)
        assert s["ltcg"] == pytest.approx(200.0)
        assert s["stcg"] == pytest.approx(0.0)

    def test_generate_summary_wash_sale_disallowed(self) -> None:
        t = LotTracker()
        sell_date = date.today()
        t.record_buy("SPY", qty=10, price=500.0, trade_date=sell_date - timedelta(days=60))
        t.record_buy("SPY", qty=10, price=495.0, trade_date=sell_date + timedelta(days=5))
        t.record_sell("SPY", qty=10, price=490.0, trade_date=sell_date)
        s = generate_summary(t)
        assert s["wash_sale_disallowed"] > 0
