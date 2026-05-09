"""Wash-sale rule detector.

IRS wash-sale rule: if you sell a security at a loss and buy substantially
identical shares within 30 days before or after the sale, the loss is disallowed
and added to the cost basis of the replacement shares.

We only flag the 30-day look-ahead window (buy within 30 days AFTER the sale).
We do NOT handle look-back (buy before sale) as that would require future data.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

WASH_SALE_WINDOW = timedelta(days=30)


class WashSaleDetector:
    """Tracks buy and sell dates per symbol to detect wash-sale violations.

    Usage:
        - Call ``notify_sell(symbol, date)`` when recording a loss sale.
        - Call ``notify_buy(symbol, date)`` when recording a buy.
        - Call ``is_wash_sale(symbol, sell_date)`` to check if a sell triggers the rule.
    """

    def __init__(self) -> None:
        # symbol → sorted list of (buy_date,)
        self._buys: dict[str, list[date]] = defaultdict(list)
        # symbol → sorted list of sell_dates with losses
        self._loss_sells: dict[str, list[date]] = defaultdict(list)

    def notify_buy(self, symbol: str, trade_date: date) -> None:
        self._buys[symbol].append(trade_date)

    def notify_sell(self, symbol: str, trade_date: date) -> None:
        self._loss_sells[symbol].append(trade_date)

    def is_wash_sale(self, symbol: str, sell_date: date) -> bool:
        """Return True if there is a buy within 30 days after this loss sale.

        Note: look-back (buy before sell) also triggers wash-sale in real life,
        but this detector only covers the forward window since we process
        transactions chronologically.
        """
        window_end = sell_date + WASH_SALE_WINDOW
        return any(
            sell_date < buy_date <= window_end
            for buy_date in self._buys.get(symbol, [])
        )

    def has_recent_loss_sell(self, symbol: str, before_date: date) -> bool:
        """Return True if there was a loss sell within 30 days before *before_date*.

        Used by the risk filter to raise the edge bar before initiating a new
        buy that would create a wash-sale situation.
        """
        window_start = before_date - WASH_SALE_WINDOW
        return any(
            window_start <= sell_date < before_date
            for sell_date in self._loss_sells.get(symbol, [])
        )
