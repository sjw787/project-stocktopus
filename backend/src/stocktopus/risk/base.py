"""Risk check interface and result models.

Every pre-trade check implements `RiskCheck.run(ctx, thesis) -> RiskResult`.
The RiskFilter orchestrates all checks; a single FAILED result blocks the trade.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from stocktopus.features.models import TradeThesis
from stocktopus.strategies.base import StrategyContext


class RiskVerdict(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    WARNED = "warned"  # trade allowed but with a logged warning


class RiskResult(BaseModel):
    """Outcome of a single risk check."""

    check_name: str
    verdict: RiskVerdict
    reason: str = ""
    details: dict[str, Any] = {}

    @property
    def blocked(self) -> bool:
        return self.verdict == RiskVerdict.FAILED


class RiskCheck(ABC):
    """Abstract pre-trade risk check."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def run(self, ctx: StrategyContext, thesis: TradeThesis) -> RiskResult: ...
