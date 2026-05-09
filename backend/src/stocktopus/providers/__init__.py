"""Provider interfaces — pluggable adapters for all external services."""

from stocktopus.providers.broker import (
    BrokerProvider,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
)
from stocktopus.providers.llm import LLMMessage, LLMProvider, LLMResponse
from stocktopus.providers.market_data import Candle, MarketDataProvider
from stocktopus.providers.news import NewsArticle, NewsCategory, NewsProvider
from stocktopus.providers.secrets import EnvSecretsProvider, SecretsProvider

__all__ = [
    "BrokerProvider",
    "Order",
    "OrderSide",
    "OrderStatus",
    "OrderType",
    "Position",
    "LLMMessage",
    "LLMProvider",
    "LLMResponse",
    "Candle",
    "MarketDataProvider",
    "NewsArticle",
    "NewsCategory",
    "NewsProvider",
    "EnvSecretsProvider",
    "SecretsProvider",
]
