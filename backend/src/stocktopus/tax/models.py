"""Tax lot tracking — US federal STCG/LTCG + wash-sale detection.

This module tracks realized P&L by lot for US federal tax purposes:
- Short-term capital gain (STCG): held < 365 days
- Long-term capital gain (LTCG): held ≥ 365 days
- Wash-sale: selling at a loss and rebuying within ±30 days

This is NOT tax advice. It surfaces tax-aware signals to the risk filter
and generates a Form 8949-style CSV for review by a tax professional.

See docs/tax.md for the full disclaimer and methodology.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any


class HoldingPeriod(StrEnum):
    SHORT_TERM = "short_term"   # < 365 days, taxed as ordinary income
    LONG_TERM = "long_term"     # ≥ 365 days, lower rate


class WashSaleStatus(StrEnum):
    CLEAN = "clean"                  # No wash-sale issue
    POTENTIAL = "potential"          # Pending — within look-ahead window
    TRIGGERED = "triggered"          # Wash-sale rule applied, loss disallowed


@dataclass
class TaxLot:
    """A single purchased lot of shares."""

    lot_id: str
    symbol: str
    buy_date: date
    qty: float
    cost_basis: float          # per share
    is_paper: bool = True      # False = real money lot

    # Set when the lot is sold
    sell_date: date | None = None
    sell_price: float | None = None
    wash_sale_status: WashSaleStatus = WashSaleStatus.CLEAN
    disallowed_loss: float = 0.0   # wash-sale disallowed amount (per share)

    @property
    def is_open(self) -> bool:
        return self.sell_date is None

    @property
    def holding_days(self) -> int:
        end = self.sell_date or date.today()
        return (end - self.buy_date).days

    @property
    def holding_period(self) -> HoldingPeriod:
        return HoldingPeriod.LONG_TERM if self.holding_days >= 365 else HoldingPeriod.SHORT_TERM

    @property
    def realized_pnl_per_share(self) -> float | None:
        if self.sell_price is None:
            return None
        return self.sell_price - self.cost_basis

    @property
    def realized_pnl_total(self) -> float | None:
        pnl = self.realized_pnl_per_share
        if pnl is None:
            return None
        return (pnl + self.disallowed_loss) * self.qty  # disallowed_loss reduces recognized loss

    def to_8949_row(self) -> dict[str, Any]:
        """Produce a Form 8949 row for this lot."""
        proceeds = (self.sell_price or 0.0) * self.qty
        basis = self.cost_basis * self.qty
        gain_loss = proceeds - basis
        adjustment = self.disallowed_loss * self.qty  # positive = adds back disallowed loss
        return {
            "description": f"{self.qty} sh {self.symbol}",
            "date_acquired": self.buy_date.isoformat(),
            "date_sold": self.sell_date.isoformat() if self.sell_date else "",
            "proceeds": round(proceeds, 2),
            "cost_or_basis": round(basis, 2),
            "adjustment_code": "W" if self.wash_sale_status == WashSaleStatus.TRIGGERED else "",
            "adjustment_amount": round(adjustment, 2),
            "gain_or_loss": round(gain_loss + adjustment, 2),
            "holding_period": self.holding_period.value,
        }
