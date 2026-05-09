"""Trade records and metrics produced by a backtest run."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class ExitReason(StrEnum):
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    TIME_EXIT = "time_exit"      # end-of-day or max-hold forced exit
    SIGNAL_EXIT = "signal_exit"  # strategy reversed


@dataclass
class BacktestTrade:
    """A single completed round-trip trade in a backtest."""

    symbol: str
    entry_ts: datetime
    exit_ts: datetime
    entry_price: float
    exit_price: float
    qty: float
    stop_loss: float
    take_profit: float
    exit_reason: ExitReason

    # Regime at entry (from simulated LLM assessment)
    regime: str = "unknown"
    lean: str = "unknown"
    llm_confidence: int = 0

    # Friction
    entry_friction: float = 0.0
    exit_friction: float = 0.0

    @property
    def gross_pnl(self) -> float:
        return (self.exit_price - self.entry_price) * self.qty

    @property
    def net_pnl(self) -> float:
        return self.gross_pnl - self.entry_friction - self.exit_friction

    @property
    def is_winner(self) -> bool:
        return self.net_pnl > 0

    @property
    def hold_minutes(self) -> float:
        return (self.exit_ts - self.entry_ts).total_seconds() / 60

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "entry_ts": self.entry_ts.isoformat(),
            "exit_ts": self.exit_ts.isoformat(),
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "qty": self.qty,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "exit_reason": self.exit_reason,
            "regime": self.regime,
            "lean": self.lean,
            "llm_confidence": self.llm_confidence,
            "gross_pnl": round(self.gross_pnl, 4),
            "net_pnl": round(self.net_pnl, 4),
            "entry_friction": round(self.entry_friction, 4),
            "exit_friction": round(self.exit_friction, 4),
            "hold_minutes": round(self.hold_minutes, 1),
            "is_winner": self.is_winner,
        }


@dataclass
class BacktestMetrics:
    """Aggregated performance metrics for a completed backtest."""

    symbol: str
    start_date: datetime
    end_date: datetime
    initial_capital: float
    final_capital: float

    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0

    gross_profit: float = 0.0
    gross_loss: float = 0.0
    total_friction: float = 0.0

    max_drawdown_pct: float = 0.0
    sharpe_ratio: float | None = None
    sortino_ratio: float | None = None

    # Per-regime breakdown: regime_name → {trades, net_pnl, win_rate}
    regime_breakdown: dict[str, dict] = field(default_factory=dict)

    @property
    def net_profit(self) -> float:
        return self.final_capital - self.initial_capital

    @property
    def total_return_pct(self) -> float:
        return (self.net_profit / self.initial_capital) * 100

    @property
    def win_rate(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return self.winning_trades / self.total_trades

    @property
    def profit_factor(self) -> float | None:
        if self.gross_loss == 0:
            return None
        return abs(self.gross_profit) / abs(self.gross_loss)

    @property
    def expectancy(self) -> float:
        """Average net P&L per trade."""
        if self.total_trades == 0:
            return 0.0
        return self.net_profit / self.total_trades

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "initial_capital": self.initial_capital,
            "final_capital": round(self.final_capital, 2),
            "net_profit": round(self.net_profit, 2),
            "total_return_pct": round(self.total_return_pct, 3),
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": round(self.win_rate, 4),
            "profit_factor": round(self.profit_factor, 3) if self.profit_factor else None,
            "expectancy": round(self.expectancy, 4),
            "gross_profit": round(self.gross_profit, 2),
            "gross_loss": round(self.gross_loss, 2),
            "total_friction": round(self.total_friction, 4),
            "max_drawdown_pct": round(self.max_drawdown_pct, 3),
            "sharpe_ratio": round(self.sharpe_ratio, 3) if self.sharpe_ratio else None,
            "sortino_ratio": round(self.sortino_ratio, 3) if self.sortino_ratio else None,
            "regime_breakdown": self.regime_breakdown,
        }
