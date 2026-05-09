"""Pure-function feature computation from OHLCV candle data.

All functions operate on plain Python lists/floats so they can be used
anywhere — CLI, background jobs, backtests, unit tests — without a DB
session.  No side effects, no I/O.

Candle dicts are expected to have keys: open, high, low, close, volume, vwap.
Lists are always oldest-first (ascending timestamp order).
"""

from __future__ import annotations

from typing import NamedTuple


class OHLCVBar(NamedTuple):
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: float | None = None


# ── Simple Moving Average ──────────────────────────────────────────────────────


def sma(closes: list[float], period: int) -> float | None:
    """SMA of the last `period` closes.  Returns None if insufficient data."""
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def sma_series(closes: list[float], period: int) -> list[float | None]:
    """Full SMA series aligned to `closes`. First (period-1) values are None."""
    result: list[float | None] = [None] * (period - 1)
    for i in range(period - 1, len(closes)):
        result.append(sum(closes[i - period + 1 : i + 1]) / period)
    return result


# ── Average True Range (ATR-14) ────────────────────────────────────────────────


def _true_ranges(bars: list[OHLCVBar]) -> list[float]:
    trs: list[float] = []
    for i, bar in enumerate(bars):
        if i == 0:
            trs.append(bar.high - bar.low)
        else:
            prev_close = bars[i - 1].close
            trs.append(
                max(
                    bar.high - bar.low,
                    abs(bar.high - prev_close),
                    abs(bar.low - prev_close),
                )
            )
    return trs


def atr(bars: list[OHLCVBar], period: int = 14) -> float | None:
    """Wilder-smoothed ATR.  Requires at least `period + 1` bars."""
    if len(bars) < period + 1:
        return None
    trs = _true_ranges(bars)
    # Seed with simple average of first `period` true ranges.
    smoothed = sum(trs[:period]) / period
    for tr in trs[period:]:
        smoothed = (smoothed * (period - 1) + tr) / period
    return smoothed


# ── Relative Volume (RVOL) ────────────────────────────────────────────────────


def rvol(
    current_volume: float,
    historical_volumes: list[float],
) -> float | None:
    """RVOL = current bar volume / average of same-period volumes on prior days.

    `historical_volumes` should be volumes for the same intraday bar across
    recent sessions (e.g. the 9:35 bar for the past 20 days).
    Returns None if historical_volumes is empty.
    """
    if not historical_volumes:
        return None
    avg = sum(historical_volumes) / len(historical_volumes)
    return current_volume / avg if avg > 0 else None


# ── VWAP ──────────────────────────────────────────────────────────────────────


def vwap(bars: list[OHLCVBar]) -> float | None:
    """Intraday VWAP computed from all bars supplied (cumulative).

    Uses (H+L+C)/3 as the typical price for each bar.
    Returns None if bars is empty or total volume is zero.
    """
    if not bars:
        return None
    total_pv = sum(((b.high + b.low + b.close) / 3) * b.volume for b in bars)
    total_vol = sum(b.volume for b in bars)
    return total_pv / total_vol if total_vol > 0 else None


def spy_above_vwap(bars: list[OHLCVBar]) -> bool | None:
    """True when the latest bar's close is above intraday VWAP.

    Returns None if VWAP cannot be computed (no bars / zero volume).
    """
    vwap_val = vwap(bars)
    if vwap_val is None or not bars:
        return None
    return bars[-1].close > vwap_val


# ── Trend classification ───────────────────────────────────────────────────────


def spy_trend(
    closes: list[float],
    short_period: int = 20,
    long_period: int = 50,
) -> str | None:
    """Classify 1-day trend as 'up', 'down', or 'flat'.

    'up'   — close > SMA(short) > SMA(long)
    'down' — close < SMA(short) < SMA(long)
    'flat' — anything else

    Returns None if there are insufficient candles.
    """
    short_ma = sma(closes, short_period)
    long_ma = sma(closes, long_period)
    if short_ma is None or long_ma is None or not closes:
        return None
    last = closes[-1]
    if last > short_ma > long_ma:
        return "up"
    if last < short_ma < long_ma:
        return "down"
    return "flat"


# ── Gap % ─────────────────────────────────────────────────────────────────────


def gap_pct(current_open: float, prev_close: float) -> float | None:
    """Gap percentage between the current session open and prior close."""
    if prev_close <= 0:
        return None
    return (current_open - prev_close) / prev_close * 100
