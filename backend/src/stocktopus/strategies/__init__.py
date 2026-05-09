"""Opening Momentum strategy package."""

from stocktopus.strategies.base import Strategy, StrategyContext
from stocktopus.strategies.opening_momentum import OpeningMomentumStrategy

__all__ = ["OpeningMomentumStrategy", "Strategy", "StrategyContext"]
