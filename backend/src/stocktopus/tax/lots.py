"""FIFO lot tracker for realized P&L and wash-sale detection.

Tracks open lots per symbol in FIFO order. When a sell is recorded,
lots are consumed from oldest first.
"""

from __future__ import annotations

import uuid
from collections import defaultdict, deque
from datetime import date
from typing import NamedTuple

from stocktopus.tax.models import TaxLot, WashSaleStatus
from stocktopus.tax.wash_sale import WashSaleDetector


class SaleResult(NamedTuple):
    """Result of recording a sale."""

    closed_lots: list[TaxLot]
    total_pnl: float          # recognized gain/loss after disallowed amounts
    raw_pnl: float            # before wash-sale adjustment
    stcg: float               # short-term gain component
    ltcg: float               # long-term gain component
    wash_sale_triggered: bool


class LotTracker:
    """FIFO lot tracker with wash-sale detection.

    Not thread-safe. For concurrent use, wrap in an async lock.
    """

    def __init__(self, is_paper: bool = True) -> None:
        # symbol → deque[TaxLot] in FIFO order (oldest first)
        self._open: dict[str, deque[TaxLot]] = defaultdict(deque)
        # All closed lots (history)
        self._closed: list[TaxLot] = []
        self._is_paper = is_paper
        self._wash_detector = WashSaleDetector()

    # ── Recording trades ──────────────────────────────────────────────────────

    def record_buy(
        self,
        symbol: str,
        qty: float,
        price: float,
        trade_date: date | None = None,
    ) -> TaxLot:
        """Record a buy and return the created lot."""
        lot = TaxLot(
            lot_id=str(uuid.uuid4()),
            symbol=symbol,
            buy_date=trade_date or date.today(),
            qty=qty,
            cost_basis=price,
            is_paper=self._is_paper,
        )
        self._open[symbol].append(lot)
        self._wash_detector.notify_buy(symbol, trade_date or date.today())
        return lot

    def record_sell(
        self,
        symbol: str,
        qty: float,
        price: float,
        trade_date: date | None = None,
    ) -> SaleResult:
        """Consume FIFO lots and return a SaleResult."""
        sell_date = trade_date or date.today()
        queue = self._open[symbol]
        remaining = qty
        closed: list[TaxLot] = []

        while remaining > 0 and queue:
            lot = queue[0]
            consume = min(lot.qty, remaining)

            if consume < lot.qty:
                # Partial fill — split the lot
                partial = TaxLot(
                    lot_id=lot.lot_id + "_partial",
                    symbol=symbol,
                    buy_date=lot.buy_date,
                    qty=consume,
                    cost_basis=lot.cost_basis,
                    is_paper=self._is_paper,
                )
                lot.qty -= consume
                lot = partial
            else:
                queue.popleft()

            lot.sell_date = sell_date
            lot.sell_price = price

            # Wash-sale check
            raw_pnl = (price - lot.cost_basis) * lot.qty
            if raw_pnl < 0 and self._wash_detector.is_wash_sale(symbol, sell_date):
                lot.wash_sale_status = WashSaleStatus.TRIGGERED
                lot.disallowed_loss = -(price - lot.cost_basis)  # per share, positive

            closed.append(lot)
            self._closed.append(lot)
            remaining -= consume

        # Aggregate results
        total_raw = sum(
            (lot.sell_price - lot.cost_basis) * lot.qty for lot in closed  # type: ignore[operator]
        )
        total_recognized = sum(lot.realized_pnl_total or 0.0 for lot in closed)
        stcg = sum(
            lot.realized_pnl_total or 0.0
            for lot in closed
            if lot.holding_days < 365
        )
        ltcg = sum(
            lot.realized_pnl_total or 0.0
            for lot in closed
            if lot.holding_days >= 365
        )
        wash_sale_triggered = any(
            lot.wash_sale_status == WashSaleStatus.TRIGGERED for lot in closed
        )

        self._wash_detector.notify_sell(symbol, sell_date)
        return SaleResult(
            closed_lots=closed,
            total_pnl=total_recognized,
            raw_pnl=total_raw,
            stcg=stcg,
            ltcg=ltcg,
            wash_sale_triggered=wash_sale_triggered,
        )

    # ── Queries ───────────────────────────────────────────────────────────────

    def open_lots(self, symbol: str | None = None) -> list[TaxLot]:
        if symbol:
            return list(self._open.get(symbol, deque()))
        return [lot for q in self._open.values() for lot in q]

    def closed_lots(self, symbol: str | None = None) -> list[TaxLot]:
        if symbol:
            return [lot for lot in self._closed if lot.symbol == symbol]
        return list(self._closed)

    def unrealized_pnl(self, symbol: str, current_price: float) -> float:
        return sum(
            (current_price - lot.cost_basis) * lot.qty
            for lot in self._open.get(symbol, deque())
        )

    def stcg_on_close(self, symbol: str, current_price: float) -> float:
        """Estimated STCG if all open lots for symbol were closed today."""
        return sum(
            (current_price - lot.cost_basis) * lot.qty
            for lot in self._open.get(symbol, deque())
            if lot.holding_days < 365
        )
