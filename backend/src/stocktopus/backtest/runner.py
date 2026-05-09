"""Event-driven backtest runner for the Opening Momentum strategy.

Design:
- Iterates over 5-minute candle bars chronologically.
- At each bar, simulates feature computation and an LLM regime assessment
  (using the real strategy logic but with a stubbed/cached regime).
- Applies the RiskFilter before entering any trade.
- Fills are at the NEXT bar's open (realistic).
- Exits trigger on stop-loss or take-profit touch during the bar, or forced
  EOD exit at the close of the last bar of each session.
- Walk-forward splits enforced by caller (pass in/out-of-sample date ranges).

The runner does NOT make live LLM calls — it accepts a pre-computed
regime map `{date -> RegimeAssessment}` built offline. In practice you
would run `stocktopus analyze regime` over the history first.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import numpy as np
import pandas as pd
from loguru import logger

from stocktopus.backtest.friction import FrictionModel
from stocktopus.backtest.records import BacktestMetrics, BacktestTrade, ExitReason
from stocktopus.features.models import (
    FeatureVector,
    RegimeAssessment,
)
from stocktopus.risk.filter import RiskFilter
from stocktopus.strategies.base import StrategyContext
from stocktopus.strategies.opening_momentum import OpeningMomentumStrategy

# ── Constants ─────────────────────────────────────────────────────────────────

# Market hours in UTC (13:30–20:00 for ET summer offset)
_MARKET_OPEN_UTC = 13 * 60 + 30   # minutes since midnight
_MARKET_CLOSE_UTC = 20 * 60        # minutes since midnight
# Force exit 15 minutes before close to avoid last-second fills
_EOD_EXIT_CUTOFF = _MARKET_CLOSE_UTC - 15


def _bar_minutes(ts: datetime) -> int:
    return ts.hour * 60 + ts.minute


def _is_market_hours(ts: datetime) -> bool:
    m = _bar_minutes(ts)
    return _MARKET_OPEN_UTC <= m < _MARKET_CLOSE_UTC


# ── Feature computation from OHLCV bars ──────────────────────────────────────


def _compute_features(
    bars: pd.DataFrame,
    idx: int,
    daily_bars: pd.DataFrame | None = None,
) -> FeatureVector | None:
    """Compute a FeatureVector from the bar at `idx` in `bars`.

    `bars` must have columns: open, high, low, close, volume, ts (UTC datetime).
    `daily_bars` may be provided for SMA / gap computation; if None, SMAs are skipped.
    """
    if idx < 0 or idx >= len(bars):
        return None

    row = bars.iloc[idx]
    ts: datetime = row["ts"]

    # ── RVOL: relative volume vs trailing 20-bar average ──────────────────────
    start = max(0, idx - 20)
    avg_vol = bars.iloc[start:idx]["volume"].mean() if idx > 0 else float("nan")
    rvol = (
        (row["volume"] / avg_vol)
        if (avg_vol and not np.isnan(avg_vol) and avg_vol > 0)
        else None
    )

    # ── VWAP: simple running VWAP from session open ───────────────────────────
    session_date = ts.date()
    session_mask = pd.Series([b.date() == session_date for b in bars["ts"]])
    session_bars = bars[session_mask.values]
    if len(session_bars) > 0:
        typical = (session_bars["high"] + session_bars["low"] + session_bars["close"]) / 3
        vwap = (typical * session_bars["volume"]).sum() / session_bars["volume"].sum()
        above_vwap = bool(row["close"] > vwap)
    else:
        vwap = None
        above_vwap = None

    # ── Gap: close vs prior day close ────────────────────────────────────────
    gap_pct: float | None = None
    if daily_bars is not None and len(daily_bars) >= 2:
        day_ts = ts.date()
        prior_days = daily_bars[daily_bars["ts"].dt.date < day_ts]
        if len(prior_days) >= 1:
            prior_close = prior_days.iloc[-1]["close"]
            # Use intraday open as proxy for gap (open vs prior close)
            gap_pct = ((row["open"] - prior_close) / prior_close) * 100

    # ── Daily SMAs ────────────────────────────────────────────────────────────
    sma_20d = sma_50d = sma_200d = None
    if daily_bars is not None:
        day_ts = ts.date()
        hist = daily_bars[daily_bars["ts"].dt.date <= day_ts]["close"]
        if len(hist) >= 20:
            sma_20d = float(hist.iloc[-20:].mean())
        if len(hist) >= 50:
            sma_50d = float(hist.iloc[-50:].mean())
        if len(hist) >= 200:
            sma_200d = float(hist.iloc[-200:].mean())

    # ── ATR (14-bar) ──────────────────────────────────────────────────────────
    atr_14d: float | None = None
    atr_pct: float | None = None
    if idx >= 14:
        window = bars.iloc[idx - 14 : idx]
        highs = window["high"].values
        lows = window["low"].values
        prev_closes = bars.iloc[idx - 15 : idx - 1]["close"].values
        trs = [
            max(h - lo, abs(h - pc), abs(lo - pc))
            for h, lo, pc in zip(highs, lows, prev_closes, strict=False)
        ]
        atr_14d = float(np.mean(trs)) if trs else None
        atr_pct = (atr_14d / row["close"] * 100) if (atr_14d and row["close"] > 0) else None

    return FeatureVector(
        symbol=str(row.get("symbol", "SPY")),
        ts=ts,
        close=float(row["close"]),
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        volume=float(row["volume"]),
        vwap=float(vwap) if vwap is not None else None,
        above_vwap=above_vwap,
        rvol=float(rvol) if rvol is not None else None,
        gap_pct=float(gap_pct) if gap_pct is not None else None,
        sma_20d=sma_20d,
        sma_50d=sma_50d,
        sma_200d=sma_200d,
        atr_14d=atr_14d,
        atr_pct=atr_pct,
    )


# ── BacktestRunner ────────────────────────────────────────────────────────────


class BacktestRunner:
    """Event-driven backtest runner.

    Parameters
    ----------
    symbol:
        Ticker to backtest (e.g. "SPY").
    intraday_bars:
        DataFrame of 5-minute bars with columns: ts, open, high, low, close, volume.
        `ts` must be UTC-aware datetimes.
    daily_bars:
        DataFrame of 1-day bars for SMA / gap computation.
    regime_map:
        Mapping of date → RegimeAssessment. Use a fixed "bull" assessment for
        quick testing, or provide a pre-computed map from stored LLM logs.
    friction:
        FrictionModel instance. Defaults to realistic Alpaca model.
    initial_capital:
        Starting capital in USD.
    position_size_usd:
        Maximum notional per trade.
    risk_filter:
        Optional custom RiskFilter. If None, uses defaults from config.
    """

    def __init__(
        self,
        symbol: str,
        intraday_bars: pd.DataFrame,
        daily_bars: pd.DataFrame | None = None,
        regime_map: dict[date, RegimeAssessment] | None = None,
        friction: FrictionModel | None = None,
        initial_capital: float = 10_000.0,
        position_size_usd: float = 50.0,
        risk_filter: RiskFilter | None = None,
    ) -> None:
        self.symbol = symbol
        self._bars = intraday_bars.sort_values("ts").reset_index(drop=True)
        self._daily_bars = (
            daily_bars.sort_values("ts").reset_index(drop=True) if daily_bars is not None else None
        )
        self._regime_map = regime_map or {}
        self._friction = friction or FrictionModel.realistic_alpaca()
        self._capital = initial_capital
        self._initial_capital = initial_capital
        self._position_size_usd = position_size_usd
        self._strategy = OpeningMomentumStrategy()
        self._risk_filter = risk_filter or RiskFilter.from_settings(
            max_position_usd=position_size_usd
        )

    def _get_regime(self, ts: datetime) -> RegimeAssessment | None:
        """Look up the nearest prior regime assessment for the given timestamp."""
        d = ts.date()
        # Walk backwards up to 5 days to find a regime
        for delta in range(6):
            key = d - timedelta(days=delta)
            if key in self._regime_map:
                return self._regime_map[key]
        return None

    def run(self) -> tuple[list[BacktestTrade], BacktestMetrics]:
        """Run the backtest and return (trades, metrics)."""
        trades: list[BacktestTrade] = []
        capital = self._capital
        equity_curve: list[float] = [capital]

        # State
        in_trade = False
        entry_price: float = 0.0
        entry_ts: datetime = datetime.min.replace(tzinfo=UTC)
        entry_qty: float = 0.0
        stop_loss: float = 0.0
        take_profit: float = 0.0
        entry_friction: float = 0.0
        entry_regime: str = "unknown"
        entry_lean: str = "unknown"
        entry_confidence: int = 0
        trades_today: int = 0
        daily_pnl: float = 0.0
        current_day: date | None = None

        n_bars = len(self._bars)

        for i in range(n_bars):
            row = self._bars.iloc[i]
            ts: datetime = row["ts"]
            bar_date = ts.date()

            # Reset daily counters at the start of each new session
            if bar_date != current_day:
                trades_today = 0
                daily_pnl = 0.0
                current_day = bar_date

            if not _is_market_hours(ts):
                continue

            bar_minutes = _bar_minutes(ts)

            # ── Manage open position ──────────────────────────────────────────
            if in_trade:
                # Check SL/TP intra-bar: conservative — use high/low to detect touch
                sl_touched = row["low"] <= stop_loss
                tp_touched = row["high"] >= take_profit
                eod_exit = bar_minutes >= _EOD_EXIT_CUTOFF
                is_last_bar = (i == n_bars - 1)

                if sl_touched or tp_touched or eod_exit or is_last_bar:
                    # Determine exit price (next open if possible, else this bar)
                    if tp_touched and not sl_touched:
                        exit_price = take_profit
                        reason = ExitReason.TAKE_PROFIT
                    elif sl_touched and not tp_touched:
                        exit_price = stop_loss
                        reason = ExitReason.STOP_LOSS
                    elif sl_touched and tp_touched:
                        # Both touched — assume worst case (stop hit first)
                        exit_price = stop_loss
                        reason = ExitReason.STOP_LOSS
                    else:
                        # EOD / last bar — exit at close
                        exit_price = float(row["close"])
                        reason = ExitReason.TIME_EXIT

                    exit_friction = self._friction.exit_cost(exit_price, entry_qty)
                    gross = (exit_price - entry_price) * entry_qty
                    net = gross - entry_friction - exit_friction
                    capital += net

                    trade = BacktestTrade(
                        symbol=self.symbol,
                        entry_ts=entry_ts,
                        exit_ts=ts,
                        entry_price=entry_price,
                        exit_price=exit_price,
                        qty=entry_qty,
                        stop_loss=stop_loss,
                        take_profit=take_profit,
                        exit_reason=reason,
                        regime=entry_regime,
                        lean=entry_lean,
                        llm_confidence=entry_confidence,
                        entry_friction=entry_friction,
                        exit_friction=exit_friction,
                    )
                    trades.append(trade)
                    daily_pnl += net
                    trades_today += 1
                    equity_curve.append(capital)
                    in_trade = False

            # ── Evaluate new entry signal ─────────────────────────────────────
            if not in_trade:
                fv = _compute_features(self._bars, i, self._daily_bars)
                if fv is None:
                    continue

                regime = self._get_regime(ts)

                ctx = StrategyContext(
                    symbol=self.symbol,
                    ts=ts,
                    features=fv,
                    regime=regime,
                    open_position_qty=0.0,
                    daily_realized_pnl=daily_pnl,
                    trades_today=trades_today,
                )
                thesis = self._strategy.evaluate(ctx)
                if thesis is None:
                    continue

                filter_result = self._risk_filter.evaluate(ctx, thesis)
                if not filter_result.approved:
                    continue

                # Enter trade at NEXT bar open (realistic fill)
                if i + 1 >= n_bars:
                    continue
                next_row = self._bars.iloc[i + 1]
                fill_price = float(next_row["open"])
                qty = max(1, int(self._position_size_usd / fill_price))
                friction_in = self._friction.entry_cost(fill_price, qty)

                if friction_in > capital:
                    logger.debug("Insufficient capital for trade")
                    continue

                in_trade = True
                entry_price = fill_price
                entry_ts = next_row["ts"]
                entry_qty = float(qty)
                # Recalculate SL/TP relative to actual fill price
                stop_loss = round(
                    fill_price * (thesis.stop_loss / thesis.entry_price), 4
                )
                take_profit = round(
                    fill_price * (thesis.take_profit / thesis.entry_price), 4
                )
                entry_friction = friction_in
                entry_regime = str(regime.regime) if regime else "unknown"
                entry_lean = str(regime.lean) if regime else "unknown"
                entry_confidence = int(regime.confidence) if regime else 0

        metrics = _compute_metrics(
            trades=trades,
            equity_curve=equity_curve,
            initial_capital=self._initial_capital,
            final_capital=capital,
            symbol=self.symbol,
            bars=self._bars,
        )
        return trades, metrics


# ── Metrics computation ───────────────────────────────────────────────────────


def _compute_metrics(
    trades: list[BacktestTrade],
    equity_curve: list[float],
    initial_capital: float,
    final_capital: float,
    symbol: str,
    bars: pd.DataFrame,
) -> BacktestMetrics:
    start_date = bars.iloc[0]["ts"]
    end_date = bars.iloc[-1]["ts"]

    winners = [t for t in trades if t.is_winner]
    losers = [t for t in trades if not t.is_winner]

    gross_profit = sum(t.net_pnl for t in winners)
    gross_loss = sum(t.net_pnl for t in losers)
    total_friction = sum(t.entry_friction + t.exit_friction for t in trades)

    # Max drawdown
    equity = np.array(equity_curve, dtype=float)
    running_max = np.maximum.accumulate(equity)
    drawdowns = (running_max - equity) / running_max
    max_dd_pct = float(np.max(drawdowns) * 100) if len(drawdowns) > 1 else 0.0

    # Sharpe / Sortino (daily returns from equity curve, annualised)
    sharpe: float | None = None
    sortino: float | None = None
    if len(equity) > 2:
        returns = np.diff(equity) / equity[:-1]
        if returns.std() > 0:
            sharpe = float((returns.mean() / returns.std()) * np.sqrt(252))
        neg_returns = returns[returns < 0]
        if len(neg_returns) > 0 and neg_returns.std() > 0:
            sortino = float((returns.mean() / neg_returns.std()) * np.sqrt(252))

    # Per-regime breakdown
    regime_breakdown: dict[str, dict] = {}
    for t in trades:
        r = t.regime
        if r not in regime_breakdown:
            regime_breakdown[r] = {"trades": 0, "net_pnl": 0.0, "wins": 0}
        regime_breakdown[r]["trades"] += 1
        regime_breakdown[r]["net_pnl"] += t.net_pnl
        if t.is_winner:
            regime_breakdown[r]["wins"] += 1
    for r, data in regime_breakdown.items():
        n = data["trades"]
        regime_breakdown[r]["win_rate"] = round(data["wins"] / n, 4) if n > 0 else 0.0
        regime_breakdown[r]["net_pnl"] = round(data["net_pnl"], 2)

    return BacktestMetrics(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        final_capital=final_capital,
        total_trades=len(trades),
        winning_trades=len(winners),
        losing_trades=len(losers),
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        total_friction=total_friction,
        max_drawdown_pct=max_dd_pct,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        regime_breakdown=regime_breakdown,
    )
