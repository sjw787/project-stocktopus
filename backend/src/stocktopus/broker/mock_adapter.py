"""Mock broker adapter for testing.

Returns deterministic fill prices based on the order side and a configurable
slippage. Maintains an in-memory position ledger.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from stocktopus.broker.base import (
    BrokerAdapter,
    OrderRequest,
    OrderResult,
    OrderSide,
    OrderStatus,
    Position,
)


class MockBrokerAdapter(BrokerAdapter):
    """In-memory broker for testing — no network calls."""

    def __init__(
        self,
        initial_equity: float = 100_000.0,
        fill_price: float | None = None,
        slippage_bps: float = 0.0,
    ) -> None:
        self._equity = initial_equity
        self._fill_price = fill_price  # if set, all orders fill at this price
        self._slippage_bps = slippage_bps
        self._positions: dict[str, Position] = {}
        self.orders: list[OrderResult] = []  # full history

    @property
    def is_paper(self) -> bool:
        return True  # mock is always "paper"

    def _simulate_fill(self, req: OrderRequest) -> float:
        base = self._fill_price or 500.0
        slip = base * (self._slippage_bps / 10_000)
        return base + slip if req.side == OrderSide.BUY else base - slip

    async def place_order(self, req: OrderRequest) -> OrderResult:
        fill_price = self._simulate_fill(req)
        now = datetime.now(UTC)
        result = OrderResult(
            order_id=str(uuid.uuid4()),
            client_order_id=req.client_order_id,
            symbol=req.symbol,
            side=req.side,
            qty=req.qty,
            filled_qty=req.qty,
            filled_avg_price=fill_price,
            status=OrderStatus.FILLED,
            submitted_at=now,
            filled_at=now,
            raw={},
        )
        self.orders.append(result)

        # Update position ledger
        pos = self._positions.get(req.symbol)
        if req.side == OrderSide.BUY:
            if pos is None:
                self._positions[req.symbol] = Position(
                    symbol=req.symbol,
                    qty=req.qty,
                    avg_entry_price=fill_price,
                    current_price=fill_price,
                    unrealized_pnl=0.0,
                    market_value=fill_price * req.qty,
                )
            else:
                total_qty = pos.qty + req.qty
                avg = (pos.avg_entry_price * pos.qty + fill_price * req.qty) / total_qty
                self._positions[req.symbol] = Position(
                    symbol=req.symbol,
                    qty=total_qty,
                    avg_entry_price=avg,
                    current_price=fill_price,
                    unrealized_pnl=0.0,
                    market_value=fill_price * total_qty,
                )
        else:  # SELL
            if pos is not None:
                new_qty = pos.qty - req.qty
                if new_qty <= 0:
                    del self._positions[req.symbol]
                    pnl = (fill_price - pos.avg_entry_price) * req.qty
                    self._equity += pnl
                else:
                    self._positions[req.symbol] = Position(
                        symbol=req.symbol,
                        qty=new_qty,
                        avg_entry_price=pos.avg_entry_price,
                        current_price=fill_price,
                        unrealized_pnl=(fill_price - pos.avg_entry_price) * new_qty,
                        market_value=fill_price * new_qty,
                    )
        return result

    async def cancel_order(self, order_id: str) -> bool:
        return True  # mock always succeeds

    async def get_position(self, symbol: str) -> Position | None:
        return self._positions.get(symbol)

    async def get_all_positions(self) -> list[Position]:
        return list(self._positions.values())

    async def get_account_equity(self) -> float:
        return self._equity

    async def close_position(self, symbol: str) -> OrderResult | None:
        pos = await self.get_position(symbol)
        if pos is None:
            return None
        side = OrderSide.SELL if pos.qty > 0 else OrderSide.BUY
        return await self.place_order(
            OrderRequest(symbol=symbol, side=side, qty=abs(pos.qty))
        )

    async def close_all_positions(self) -> list[OrderResult]:
        symbols = list(self._positions.keys())
        results = []
        for sym in symbols:
            r = await self.close_position(sym)
            if r:
                results.append(r)
        return results
