"""Strategy interface and shared context model.

Every strategy implements `Strategy.evaluate(ctx) -> Optional[TradeThesis]`.
The risk filter runs *after* the strategy, so strategies should not do their own
risk checks — keep them focused on signal generation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from stocktopus.features.models import FeatureVector, RegimeAssessment, TradeThesis


class StrategyContext(BaseModel):
    """All inputs available to a strategy at decision time."""

    symbol: str
    ts: datetime

    # Feature snapshot (required)
    features: FeatureVector

    # LLM regime assessment (None → fail closed in risk filter)
    regime: RegimeAssessment | None = None

    # Recent news headlines (last N hours)
    news_headlines: list[str] = Field(default_factory=list)

    # Current open positions for this symbol (qty > 0 = long, < 0 = short)
    open_position_qty: float = 0.0
    open_position_avg_price: float | None = None

    # Today's realized P&L so far (for daily loss check)
    daily_realized_pnl: float = 0.0

    # Number of trades placed today
    trades_today: int = 0

    # Extra context for forward compat
    extra: dict[str, Any] = Field(default_factory=dict)


class Strategy(ABC):
    """Abstract base for all trading strategies.

    Strategies are *signal generators only* — they do not enforce risk limits.
    The risk filter layer wraps every strategy call.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable strategy name (e.g., 'opening_momentum')."""
        ...

    @property
    @abstractmethod
    def version(self) -> str:
        """Version string (e.g., 'v1')."""
        ...

    @abstractmethod
    def evaluate(self, ctx: StrategyContext) -> TradeThesis | None:
        """Evaluate the strategy and return a TradeThesis, or None to pass."""
        ...
