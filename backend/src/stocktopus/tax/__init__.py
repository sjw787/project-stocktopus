"""Tax package — lot tracking, wash-sale detection, Form 8949 export."""

from stocktopus.tax.lots import LotTracker, SaleResult
from stocktopus.tax.models import HoldingPeriod, TaxLot, WashSaleStatus
from stocktopus.tax.report import generate_8949_csv, generate_summary
from stocktopus.tax.wash_sale import WashSaleDetector

__all__ = [
    "LotTracker",
    "SaleResult",
    "TaxLot",
    "HoldingPeriod",
    "WashSaleStatus",
    "WashSaleDetector",
    "generate_8949_csv",
    "generate_summary",
]
