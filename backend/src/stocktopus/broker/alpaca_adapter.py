"""Alpaca broker adapter (paper and live).

Uses the alpaca-py SDK. The same adapter works for both paper and live trading —
the only difference is the `base_url` passed to TradingClient.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide as AlpacaOrderSide
from alpaca.trading.enums import TimeInForce
from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest
from loguru import logger

from stocktopus.broker.base import (
    BrokerAdapter,
    OrderRequest,
    OrderResult,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
)

_STATUS_MAP: dict[str, OrderStatus] = {
    "new": OrderStatus.ACCEPTED,
    "partially_filled": OrderStatus.PARTIALLY_FILLED,
    "filled": OrderStatus.FILLED,
    "done_for_day": OrderStatus.CANCELLED,
    "canceled": OrderStatus.CANCELLED,
    "cancelled": OrderStatus.CANCELLED,
    "expired": OrderStatus.EXPIRED,
    "replaced": OrderStatus.CANCELLED,
    "pending_cancel": OrderStatus.PENDING,
    "pending_replace": OrderStatus.PENDING,
    "accepted": OrderStatus.ACCEPTED,
    "pending_new": OrderStatus.PENDING,
    "accepted_for_bidding": OrderStatus.ACCEPTED,
    "stopped": OrderStatus.CANCELLED,
    "rejected": OrderStatus.REJECTED,
    "suspended": OrderStatus.REJECTED,
    "calculated": OrderStatus.ACCEPTED,
}


def _map_status(raw_status: str) -> OrderStatus:
    return _STATUS_MAP.get(raw_status.lower(), OrderStatus.PENDING)


class AlpacaBrokerAdapter(BrokerAdapter):
    """Alpaca paper or live broker adapter."""

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        paper: bool = True,
    ) -> None:
        self._paper = paper
        self._client = TradingClient(
            api_key=api_key,
            secret_key=secret_key,
            paper=paper,
        )

    @property
    def is_paper(self) -> bool:
        return self._paper

    def _build_order_result(self, order: Any) -> OrderResult:
        raw = order.model_dump() if hasattr(order, "model_dump") else dict(order)
        filled_at = getattr(order, "filled_at", None)
        submitted = getattr(order, "submitted_at", datetime.now(UTC))
        return OrderResult(
            order_id=str(order.id),
            client_order_id=str(getattr(order, "client_order_id", "")),
            symbol=str(order.symbol),
            side=OrderSide(str(order.side).lower().replace("ordersideenum.", "")),
            qty=float(getattr(order, "qty", 0) or 0),
            filled_qty=float(getattr(order, "filled_qty", 0) or 0),
            filled_avg_price=(
                float(order.filled_avg_price) if getattr(order, "filled_avg_price", None) else None
            ),
            status=_map_status(str(getattr(order, "status", "pending"))),
            submitted_at=submitted if isinstance(submitted, datetime) else datetime.now(UTC),
            filled_at=filled_at if isinstance(filled_at, datetime) else None,
            raw={k: str(v) for k, v in raw.items()},
        )

    async def place_order(self, req: OrderRequest) -> OrderResult:
        logger.info(
            "Placing order",
            symbol=req.symbol,
            side=req.side,
            qty=req.qty,
            type=req.order_type,
            paper=self._paper,
        )
        side = AlpacaOrderSide.BUY if req.side == OrderSide.BUY else AlpacaOrderSide.SELL
        tif = TimeInForce.DAY

        if req.order_type == OrderType.MARKET:
            order_req = MarketOrderRequest(
                symbol=req.symbol,
                qty=req.qty,
                side=side,
                time_in_force=tif,
                client_order_id=req.client_order_id or str(uuid.uuid4()),
            )
        elif req.order_type == OrderType.LIMIT and req.limit_price:
            order_req = LimitOrderRequest(
                symbol=req.symbol,
                qty=req.qty,
                side=side,
                limit_price=req.limit_price,
                time_in_force=tif,
                client_order_id=req.client_order_id or str(uuid.uuid4()),
            )
        else:
            order_req = MarketOrderRequest(
                symbol=req.symbol,
                qty=req.qty,
                side=side,
                time_in_force=tif,
                client_order_id=req.client_order_id or str(uuid.uuid4()),
            )

        order = self._client.submit_order(order_data=order_req)
        result = self._build_order_result(order)
        logger.info("Order submitted", order_id=result.order_id, status=result.status)
        return result

    async def cancel_order(self, order_id: str) -> bool:
        try:
            self._client.cancel_order_by_id(order_id)
            return True
        except Exception as exc:
            logger.warning("Failed to cancel order", order_id=order_id, error=str(exc))
            return False

    async def get_position(self, symbol: str) -> Position | None:
        try:
            pos = self._client.get_open_position(symbol)
            return Position(
                symbol=str(pos.symbol),
                qty=float(pos.qty),
                avg_entry_price=float(pos.avg_entry_price),
                current_price=float(pos.current_price or 0),
                unrealized_pnl=float(pos.unrealized_pl or 0),
                market_value=float(pos.market_value or 0),
            )
        except Exception:  # noqa: BLE001
            return None

    async def get_all_positions(self) -> list[Position]:
        positions = self._client.get_all_positions()
        return [
            Position(
                symbol=str(p.symbol),
                qty=float(p.qty),
                avg_entry_price=float(p.avg_entry_price),
                current_price=float(p.current_price or 0),
                unrealized_pnl=float(p.unrealized_pl or 0),
                market_value=float(p.market_value or 0),
            )
            for p in positions
        ]

    async def get_account_equity(self) -> float:
        account = self._client.get_account()
        return float(account.equity or 0)

    async def close_position(self, symbol: str) -> OrderResult | None:
        pos = await self.get_position(symbol)
        if pos is None:
            return None
        side = OrderSide.SELL if pos.qty > 0 else OrderSide.BUY
        return await self.place_order(
            OrderRequest(symbol=symbol, side=side, qty=abs(pos.qty))
        )

    async def close_all_positions(self) -> list[OrderResult]:
        results: list[OrderResult] = []
        positions = await self.get_all_positions()
        for pos in positions:
            result = await self.close_position(pos.symbol)
            if result:
                results.append(result)
        return results
