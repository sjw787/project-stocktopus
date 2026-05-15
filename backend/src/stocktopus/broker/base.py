"""Broker adapter interface.

All broker adapters (paper, live, mock) implement this interface.
The execution layer only calls these methods — never the broker SDK directly.
This makes swapping paper→live a config change, not a code change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TRAILING_STOP = "trailing_stop"


class OrderStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class OrderRequest:
    """All the information needed to place a single order."""

    symbol: str
    side: OrderSide
    qty: float
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None
    stop_price: float | None = None
    time_in_force: str = "day"
    client_order_id: str | None = None  # for idempotency / dedup


@dataclass
class OrderResult:
    """Broker's response to an order submission."""

    order_id: str
    client_order_id: str | None
    symbol: str
    side: OrderSide
    qty: float
    filled_qty: float
    filled_avg_price: float | None
    status: OrderStatus
    submitted_at: datetime
    filled_at: datetime | None
    raw: dict[str, Any]  # raw broker payload for audit


@dataclass
class Position:
    """An open position as reported by the broker."""

    symbol: str
    qty: float  # positive = long, negative = short
    avg_entry_price: float
    current_price: float
    unrealized_pnl: float
    market_value: float


class BrokerAdapter(ABC):
    """Abstract broker adapter interface."""

    @abstractmethod
    async def place_order(self, req: OrderRequest) -> OrderResult:
        """Submit an order to the broker."""
        ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order. Returns True if successfully cancelled."""
        ...

    @abstractmethod
    async def get_position(self, symbol: str) -> Position | None:
        """Get the current open position for a symbol, or None if flat."""
        ...

    @abstractmethod
    async def get_all_positions(self) -> list[Position]:
        """Get all open positions."""
        ...

    @abstractmethod
    async def get_account_equity(self) -> float:
        """Get total account equity in USD."""
        ...

    @abstractmethod
    async def close_position(self, symbol: str) -> OrderResult | None:
        """Flatten the position in `symbol` with a market order. Returns None if already flat."""
        ...

    @abstractmethod
    async def close_all_positions(self) -> list[OrderResult]:
        """Flatten all open positions (kill switch)."""
        ...

    @property
    @abstractmethod
    def is_paper(self) -> bool:
        """True if this adapter is connected to a paper trading account."""
        ...
