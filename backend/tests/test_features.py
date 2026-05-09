"""Unit tests for features/compute.py — pure functions, no DB required."""


import pytest

from stocktopus.features.compute import (
    OHLCVBar,
    atr,
    gap_pct,
    rvol,
    sma,
    sma_series,
    spy_above_vwap,
    spy_trend,
    vwap,
)

# ── Helpers ────────────────────────────────────────────────────────────────────


def _bar(close: float, high: float | None = None, low: float | None = None) -> OHLCVBar:
    hi = high if high is not None else close + 1
    lo = low if low is not None else close - 1
    return OHLCVBar(open=close, high=hi, low=lo, close=close, volume=1_000_000.0)


# ── SMA ────────────────────────────────────────────────────────────────────────


class TestSMA:
    def test_basic(self):
        closes = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert sma(closes, 3) == pytest.approx(4.0)

    def test_full_window(self):
        closes = [10.0, 20.0, 30.0]
        assert sma(closes, 3) == pytest.approx(20.0)

    def test_insufficient_data_returns_none(self):
        assert sma([1.0, 2.0], 5) is None

    def test_exact_window(self):
        assert sma([5.0, 5.0, 5.0, 5.0, 5.0], 5) == pytest.approx(5.0)

    def test_series_length(self):
        closes = list(range(1, 6))  # [1, 2, 3, 4, 5]
        series = sma_series(closes, 3)
        assert len(series) == 5
        assert series[0] is None
        assert series[1] is None
        assert series[2] == pytest.approx(2.0)
        assert series[4] == pytest.approx(4.0)


# ── ATR ────────────────────────────────────────────────────────────────────────


class TestATR:
    def test_insufficient_bars(self):
        bars = [_bar(100.0)] * 5
        assert atr(bars, 14) is None  # needs period + 1

    def test_flat_market(self):
        # All bars have high=101, low=99 → TR = 2 always
        bars = [_bar(100.0, high=101.0, low=99.0)] * 20
        result = atr(bars, 14)
        assert result == pytest.approx(2.0, rel=0.01)

    def test_result_positive(self):
        import random

        random.seed(42)
        bars = [_bar(100.0 + random.gauss(0, 1)) for _ in range(30)]
        result = atr(bars, 14)
        assert result is not None
        assert result > 0


# ── RVOL ───────────────────────────────────────────────────────────────────────


class TestRVOL:
    def test_no_history(self):
        assert rvol(1000.0, []) is None

    def test_average_volume(self):
        # Current vol equals average → RVOL = 1.0
        hist = [1000.0] * 20
        assert rvol(1000.0, hist) == pytest.approx(1.0)

    def test_elevated(self):
        hist = [1000.0] * 20
        assert rvol(2000.0, hist) == pytest.approx(2.0)

    def test_zero_average(self):
        assert rvol(1000.0, [0.0, 0.0]) is None


# ── VWAP ───────────────────────────────────────────────────────────────────────


class TestVWAP:
    def test_empty(self):
        assert vwap([]) is None

    def test_single_bar(self):
        bar = OHLCVBar(open=100, high=110, low=90, close=105, volume=1000)
        # typical price = (110+90+105)/3 = 101.666…
        result = vwap([bar])
        assert result == pytest.approx((110 + 90 + 105) / 3)

    def test_uniform_price(self):
        bars = [OHLCVBar(open=100, high=100, low=100, close=100, volume=500)] * 5
        assert vwap(bars) == pytest.approx(100.0)

    def test_volume_weighted(self):
        b1 = OHLCVBar(open=100, high=100, low=100, close=100, volume=100)  # tp=100
        b2 = OHLCVBar(open=200, high=200, low=200, close=200, volume=100)  # tp=200
        # vwap = (100*100 + 200*100) / 200 = 150
        assert vwap([b1, b2]) == pytest.approx(150.0)

    def test_zero_volume(self):
        bars = [OHLCVBar(open=100, high=110, low=90, close=105, volume=0)]
        assert vwap(bars) is None


class TestSpyAboveVWAP:
    def test_above(self):
        bars = [OHLCVBar(open=100, high=100, low=100, close=100, volume=100)] * 3
        # Last bar close = 110 > vwap(100)
        bars.append(OHLCVBar(open=110, high=110, low=110, close=110, volume=100))
        assert spy_above_vwap(bars) is True

    def test_below(self):
        bars = [OHLCVBar(open=100, high=100, low=100, close=100, volume=1000)] * 3
        bars.append(OHLCVBar(open=90, high=90, low=90, close=90, volume=10))
        result = spy_above_vwap(bars)
        assert result is not None
        assert result is False

    def test_empty(self):
        assert spy_above_vwap([]) is None


# ── Trend ──────────────────────────────────────────────────────────────────────


class TestSpyTrend:
    def _uptrend_closes(self) -> list[float]:
        # SMA20 > SMA50 required; close > SMA20
        base = list(range(1, 51))  # 1…50, ascending so SMA20=41.5, SMA50=25.5
        return [float(x) for x in base]

    def test_uptrend(self):
        closes = self._uptrend_closes()
        # close=50 > SMA20=41.5 > SMA50=25.5 → "up"
        assert spy_trend(closes, 20, 50) == "up"

    def test_downtrend(self):
        closes = [float(x) for x in range(50, 0, -1)]
        # close=1 < SMA20 < SMA50 → "down"
        assert spy_trend(closes, 20, 50) == "down"

    def test_flat(self):
        # All same price → SMAs equal close → "flat"
        closes = [100.0] * 60
        assert spy_trend(closes, 20, 50) == "flat"

    def test_insufficient_data(self):
        assert spy_trend([100.0] * 10, 20, 50) is None


# ── Gap % ─────────────────────────────────────────────────────────────────────


class TestGapPct:
    def test_positive_gap(self):
        assert gap_pct(105.0, 100.0) == pytest.approx(5.0)

    def test_negative_gap(self):
        assert gap_pct(95.0, 100.0) == pytest.approx(-5.0)

    def test_zero_prev_close(self):
        assert gap_pct(100.0, 0.0) is None

    def test_no_gap(self):
        assert gap_pct(100.0, 100.0) == pytest.approx(0.0)
