"""Broker provider — pluggable adapter for order execution and account management."""

from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class Order(BaseModel):
    id: str
    symbol: str
    side: OrderSide
    type: OrderType
    qty: Decimal
    filled_qty: Decimal = Decimal(0)
    filled_avg_price: Decimal | None = None
    status: OrderStatus
    created_at: datetime


class Position(BaseModel):
    symbol: str
    qty: Decimal
    avg_entry_price: Decimal
    current_price: Decimal
    unrealized_pnl: Decimal
    side: str  # "long" | "short"


class BrokerProvider(ABC):
    """Abstract provider for order execution and account management.

    Implementations: AlpacaBroker (Phase 8, paper → live).
    Always connect to paper mode unless explicitly promoted to live (Phase 9).
    """

    @abstractmethod
    async def submit_order(
        self,
        symbol: str,
        side: OrderSide,
        qty: Decimal,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Decimal | None = None,
        stop_price: Decimal | None = None,
        client_order_id: str | None = None,
    ) -> Order:
        """Submit an order. Raises on rejection."""
        ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> None:
        """Cancel a pending order."""
        ...

    @abstractmethod
    async def get_order(self, order_id: str) -> Order:
        """Fetch the current state of an order."""
        ...

    @abstractmethod
    async def get_positions(self) -> list[Position]:
        """Return all open positions."""
        ...

    @abstractmethod
    async def get_buying_power(self) -> Decimal:
        """Return available buying power."""
        ...

    @property
    @abstractmethod
    def is_paper(self) -> bool:
        """True if connected to a paper trading account."""
        ...
