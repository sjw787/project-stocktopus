"""Drift alarm: compare live paper trade distribution vs backtest expectations.

Computes key metrics over the most recent N completed paper trades, then compares
against configurable thresholds. If divergence exceeds the alarm threshold, the
drift alarm fires and auto-pauses new entries.

Typical use:
    checker = DriftChecker.from_settings()
    status  = await checker.check(session)
    if status.alarm_active:
        # pause trading
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class DriftMetrics:
    """Computed distribution metrics over a sample of trades."""

    n_trades: int
    win_rate: float  # fraction 0–1
    avg_win: float  # USD
    avg_loss: float  # USD (negative)
    profit_factor: float
    expectancy: float  # USD per trade
    regimes_seen: list[str] = field(default_factory=list)

    @property
    def is_sufficient(self) -> bool:
        return self.n_trades >= 10


@dataclass
class DriftStatus:
    """Result of a drift check run."""

    live: DriftMetrics
    alarm_active: bool
    alarm_reasons: list[str]
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    # Configurable baselines used in this check
    baseline_win_rate: float = 0.0
    baseline_profit_factor: float = 0.0

    def summary(self) -> str:
        if not self.live.is_sufficient:
            return f"Insufficient data ({self.live.n_trades} trades, need ≥10)"
        if self.alarm_active:
            return f"ALARM — {'; '.join(self.alarm_reasons)}"
        return (
            f"OK — win_rate={self.live.win_rate:.1%}  "
            f"PF={self.live.profit_factor:.2f}  "
            f"expect=${self.live.expectancy:.2f}"
        )


class DriftChecker:
    """Computes live vs baseline drift and raises alarms.

    Parameters
    ----------
    min_win_rate:
        Alarm if live win rate drops below this fraction. Default 0.40.
    min_profit_factor:
        Alarm if live profit factor drops below this ratio. Default 1.0 (breakeven).
    lookback_days:
        Only consider trades from the last N days. Default 30.
    sample_size:
        Maximum number of recent completed trades to include. Default 50.
    """

    def __init__(
        self,
        min_win_rate: float = 0.40,
        min_profit_factor: float = 1.0,
        lookback_days: int = 30,
        sample_size: int = 50,
    ) -> None:
        self._min_win_rate = min_win_rate
        self._min_profit_factor = min_profit_factor
        self._lookback_days = lookback_days
        self._sample_size = sample_size

    @classmethod
    def from_settings(cls) -> DriftChecker:
        from stocktopus.config import get_settings

        s = get_settings()
        return cls(
            min_win_rate=getattr(s, "drift_min_win_rate", 0.40),
            min_profit_factor=getattr(s, "drift_min_profit_factor", 1.0),
            lookback_days=getattr(s, "drift_lookback_days", 30),
        )

    async def _fetch_metrics(self, session: AsyncSession) -> DriftMetrics:
        cutoff = datetime.now(UTC) - timedelta(days=self._lookback_days)
        rows = await session.execute(
            text(
                """
                SELECT realized_pnl, regime
                FROM paper_trades
                WHERE exit_ts IS NOT NULL
                  AND exit_ts >= :cutoff
                ORDER BY exit_ts DESC
                LIMIT :limit
                """
            ),
            {"cutoff": cutoff, "limit": self._sample_size},
        )
        trades = rows.fetchall()

        if not trades:
            return DriftMetrics(
                n_trades=0,
                win_rate=0.0,
                avg_win=0.0,
                avg_loss=0.0,
                profit_factor=0.0,
                expectancy=0.0,
            )

        pnls = [float(r.realized_pnl or 0) for r in trades]
        regimes = list({r.regime for r in trades if r.regime})

        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        win_rate = len(wins) / len(pnls)
        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0

        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        expectancy = sum(pnls) / len(pnls)

        return DriftMetrics(
            n_trades=len(pnls),
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            profit_factor=profit_factor,
            expectancy=expectancy,
            regimes_seen=regimes,
        )

    async def check(self, session: AsyncSession) -> DriftStatus:
        """Run a drift check and return the status."""
        metrics = await self._fetch_metrics(session)
        alarm_reasons: list[str] = []

        if metrics.is_sufficient:
            if metrics.win_rate < self._min_win_rate:
                alarm_reasons.append(f"win_rate {metrics.win_rate:.1%} < threshold {self._min_win_rate:.1%}")
            if metrics.profit_factor < self._min_profit_factor:
                alarm_reasons.append(
                    f"profit_factor {metrics.profit_factor:.2f} < threshold {self._min_profit_factor:.2f}"
                )

        alarm_active = bool(alarm_reasons)
        if alarm_active:
            logger.warning(
                "Drift alarm fired",
                n_trades=metrics.n_trades,
                win_rate=metrics.win_rate,
                profit_factor=metrics.profit_factor,
                reasons=alarm_reasons,
            )

        return DriftStatus(
            live=metrics,
            alarm_active=alarm_active,
            alarm_reasons=alarm_reasons,
            baseline_win_rate=self._min_win_rate,
            baseline_profit_factor=self._min_profit_factor,
        )
