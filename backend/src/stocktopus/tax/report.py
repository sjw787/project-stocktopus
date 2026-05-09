"""Form 8949-style CSV report generator.

Produces a CSV that mirrors Part I (short-term) and Part II (long-term)
of IRS Form 8949. This output is NOT a substitute for professional tax advice
and must be reviewed before filing.

See docs/tax.md for the full disclaimer and methodology.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from stocktopus.tax.lots import LotTracker


FORM_8949_COLUMNS = [
    "description",
    "date_acquired",
    "date_sold",
    "proceeds",
    "cost_or_basis",
    "adjustment_code",
    "adjustment_amount",
    "gain_or_loss",
    "holding_period",
]


def generate_8949_csv(
    tracker: LotTracker,
    symbol: str | None = None,
    tax_year: int | None = None,
) -> str:
    """Generate a Form 8949-style CSV from closed lots.

    Args:
        tracker: LotTracker with closed lot history
        symbol: Optionally filter to one symbol
        tax_year: Optionally filter to lots sold in a specific year

    Returns:
        CSV string with headers.
    """
    lots = tracker.closed_lots(symbol=symbol)

    if tax_year:
        lots = [lot for lot in lots if lot.sell_date and lot.sell_date.year == tax_year]

    # Sort: short-term first, then by sell date
    lots = sorted(
        lots,
        key=lambda lot: (0 if lot.holding_days < 365 else 1, lot.sell_date or date.min),
    )

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=FORM_8949_COLUMNS)
    writer.writeheader()

    for lot in lots:
        if lot.sell_date is None:
            continue
        writer.writerow(lot.to_8949_row())

    return buf.getvalue()


def generate_summary(
    tracker: LotTracker,
    tax_year: int | None = None,
) -> dict[str, float]:
    """Return aggregate STCG and LTCG totals for the given year."""
    lots = tracker.closed_lots()
    if tax_year:
        lots = [lot for lot in lots if lot.sell_date and lot.sell_date.year == tax_year]

    stcg = sum(
        lot.realized_pnl_total or 0.0
        for lot in lots
        if lot.holding_days < 365
    )
    ltcg = sum(
        lot.realized_pnl_total or 0.0
        for lot in lots
        if lot.holding_days >= 365
    )
    total_proceeds = sum((lot.sell_price or 0.0) * lot.qty for lot in lots)
    total_basis = sum(lot.cost_basis * lot.qty for lot in lots)
    wash_disallowed = sum(lot.disallowed_loss * lot.qty for lot in lots)

    return {
        "stcg": round(stcg, 2),
        "ltcg": round(ltcg, 2),
        "total_gain_loss": round(stcg + ltcg, 2),
        "total_proceeds": round(total_proceeds, 2),
        "total_basis": round(total_basis, 2),
        "wash_sale_disallowed": round(wash_disallowed, 2),
    }
