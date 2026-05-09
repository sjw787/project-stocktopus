"""Features package — pure-function feature computation from stored candles."""

from stocktopus.features.compute import (
    OHLCVBar,
    atr,
    gap_pct,
    rvol,
    sma,
    sma_series,
    spy_trend,
)
from stocktopus.features.compute import (
    spy_above_vwap as compute_spy_above_vwap,
)
from stocktopus.features.compute import (
    vwap as compute_vwap,
)
from stocktopus.features.models import (
    FeatureVector,
    Regime,
    RegimeAssessment,
    TradeLean,
    TradeThesis,
)

__all__ = [
    "OHLCVBar",
    "FeatureVector",
    "Regime",
    "RegimeAssessment",
    "TradeLean",
    "TradeThesis",
    "atr",
    "compute_spy_above_vwap",
    "compute_vwap",
    "gap_pct",
    "rvol",
    "sma",
    "sma_series",
    "spy_trend",
]
