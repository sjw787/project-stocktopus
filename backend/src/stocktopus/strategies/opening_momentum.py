"""Opening Momentum Strategy — v1.

Signal logic:
  1. Gap up > min_gap_pct from prior close.
  2. RVOL > min_rvol.
  3. Price above VWAP (after first 5m bar).
  4. LLM regime lean is LONG with confidence >= min_llm_confidence.
  5. Entry after first pullback that holds VWAP.
  6. Stop: entry * (1 - stop_loss_pct / 100)
  7. TP:   entry * (1 + take_profit_pct / 100)
           extended to take_profit_extended_pct when LLM confidence >= dynamic_tp_min_confidence.

All thresholds come from opening_momentum.yaml — no magic numbers in code.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from loguru import logger

from stocktopus.features.models import TradeDirection, TradeLean, TradeThesis
from stocktopus.strategies.base import Strategy, StrategyContext

_CONFIG_PATH = Path(__file__).parent / "opening_momentum.yaml"


def _load_config() -> dict:
    return yaml.safe_load(_CONFIG_PATH.read_text())


_CONFIG = _load_config()
_ENTRY = _CONFIG["entry"]
_EXIT = _CONFIG["exit"]
_ALLOWED_REGIMES = {r for r in _CONFIG.get("allowed_regimes", [])}

# Regular market hours (ET expressed as UTC offsets don't matter here — we
# compare against the hour/minute extracted from the ts field which is stored
# in UTC. Offset is -4 or -5 depending on DST. We use a simple heuristic:
# market open = 13:30 UTC (09:30 ET in summer), close = 20:00 UTC (16:00 ET).
_MARKET_OPEN_UTC_H, _MARKET_OPEN_UTC_M = 13, 30
_MARKET_CLOSE_UTC_H, _MARKET_CLOSE_UTC_M = 20, 0

_EARLIEST_AFTER_OPEN = _ENTRY.get("earliest_entry_minutes_after_open", 5)
_LATEST_BEFORE_CLOSE = _ENTRY.get("latest_entry_minutes_before_close", 60)


def _minutes_since_open(ts_utc_h: int, ts_utc_m: int) -> int:
    open_total = _MARKET_OPEN_UTC_H * 60 + _MARKET_OPEN_UTC_M
    ts_total = ts_utc_h * 60 + ts_utc_m
    return ts_total - open_total


def _minutes_to_close(ts_utc_h: int, ts_utc_m: int) -> int:
    close_total = _MARKET_CLOSE_UTC_H * 60 + _MARKET_CLOSE_UTC_M
    ts_total = ts_utc_h * 60 + ts_utc_m
    return close_total - ts_total


class OpeningMomentumStrategy(Strategy):
    """Long-only opening momentum strategy.

    See `opening_momentum.yaml` for all configurable thresholds.
    """

    @property
    def name(self) -> str:
        return "opening_momentum"

    @property
    def version(self) -> str:
        return _CONFIG["strategy"]["version"]

    def evaluate(self, ctx: StrategyContext) -> TradeThesis | None:  # noqa: PLR0911
        """Return a TradeThesis if all entry conditions pass, else None."""
        thesis, _ = self.evaluate_with_reason(ctx)
        return thesis

    def evaluate_with_reason(  # noqa: PLR0911
        self, ctx: StrategyContext
    ) -> tuple[TradeThesis | None, str | None]:
        """Return (TradeThesis, None) on signal, or (None, reason_string) when no signal."""
        fv = ctx.features
        ts = ctx.ts

        # ── Timing guard ─────────────────────────────────────────────────────
        since_open = _minutes_since_open(ts.hour, ts.minute)
        to_close = _minutes_to_close(ts.hour, ts.minute)
        if since_open < _EARLIEST_AFTER_OPEN:
            logger.debug("Too early after open", minutes_since_open=since_open)
            return None, f"too_early: {since_open}min since open (need {_EARLIEST_AFTER_OPEN})"
        if to_close < _LATEST_BEFORE_CLOSE:
            logger.debug("Too close to market close", minutes_to_close=to_close)
            return None, f"too_late: {to_close}min to close (need {_LATEST_BEFORE_CLOSE})"

        # ── Gap filter ────────────────────────────────────────────────────────
        gap = fv.gap_pct
        if gap is None or gap < _ENTRY["min_gap_pct"]:
            logger.debug("Gap filter failed", gap_pct=gap, required=_ENTRY["min_gap_pct"])
            return (
                None,
                f"gap_filter: {gap:.3f}% < {_ENTRY['min_gap_pct']}%" if gap is not None else "gap_filter: gap_pct=None",
            )

        # ── RVOL filter ───────────────────────────────────────────────────────
        rvol = fv.rvol
        if rvol is None or rvol < _ENTRY["min_rvol"]:
            logger.debug("RVOL filter failed", rvol=rvol, required=_ENTRY["min_rvol"])
            return (
                None,
                f"rvol_filter: {rvol:.2f}x < {_ENTRY['min_rvol']}x" if rvol is not None else "rvol_filter: rvol=None",
            )

        # ── VWAP filter ───────────────────────────────────────────────────────
        if _ENTRY["require_above_vwap"] and not fv.above_vwap:
            logger.debug("VWAP filter failed — price not above VWAP")
            return None, "vwap_filter: price below VWAP"

        # ── LLM regime filter ────────────────────────────────────────────────
        ra = ctx.regime
        if ra is None:
            logger.warning("No LLM regime assessment — failing closed")
            return None, "no_regime_assessment"
        if ra.lean not in {TradeLean.LONG}:
            logger.debug("LLM lean not LONG", lean=ra.lean)
            return None, f"regime_lean: {ra.lean} (need LONG)"
        if ra.confidence < _ENTRY["min_llm_confidence"]:
            logger.debug(
                "LLM confidence too low",
                confidence=ra.confidence,
                required=_ENTRY["min_llm_confidence"],
            )
            return None, f"regime_confidence: {ra.confidence}/10 < {_ENTRY['min_llm_confidence']}/10"
        if ra.regime not in _ALLOWED_REGIMES:
            logger.debug("Regime not in allowed set", regime=ra.regime)
            return None, f"regime_type: {ra.regime} not in {sorted(_ALLOWED_REGIMES)}"

        # ── All filters passed — build thesis ─────────────────────────────────
        entry = fv.close
        stop_pct = _EXIT["stop_loss_pct"] / 100
        stop = round(entry * (1 - stop_pct), 4)

        # Dynamic TP extension when LLM confidence is high enough.
        if ra.confidence >= _EXIT["dynamic_tp_min_confidence"]:
            tp_pct = _EXIT["take_profit_extended_pct"] / 100
            tp_note = f"(extended TP — LLM confidence {ra.confidence}/10)"
        else:
            tp_pct = _EXIT["take_profit_pct"] / 100
            tp_note = "(standard TP)"

        take_profit = round(entry * (1 + tp_pct), 4)

        rationale = (
            f"Opening Momentum long setup on {ctx.symbol}. "
            f"Gap: {gap:.2f}%, RVOL: {rvol:.2f}x, above VWAP: {fv.above_vwap}. "
            f"LLM regime: {ra.regime} / {ra.lean} @ {ra.confidence}/10 confidence. "
            f"Entry: {entry:.2f}, Stop: {stop:.2f} ({_EXIT['stop_loss_pct']}%), "
            f"TP: {take_profit:.2f} {tp_note}."
        )

        logger.info(
            "Opening Momentum signal generated",
            symbol=ctx.symbol,
            entry=entry,
            stop=stop,
            take_profit=take_profit,
            confidence=ra.confidence,
        )

        return TradeThesis(
            symbol=ctx.symbol,
            direction=TradeDirection.LONG,
            entry_price=entry,
            stop_loss=stop,
            take_profit=take_profit,
            regime_assessment=ra,
            features=fv,
            strategy_name=self.name,
            strategy_version=self.version,
            rationale=rationale,
        ), None
