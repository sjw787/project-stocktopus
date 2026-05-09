"""Smoke tests for provider interface contracts and model validation."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from stocktopus.providers.broker import Order, OrderSide, OrderStatus, OrderType, Position
from stocktopus.providers.llm import LLMMessage, LLMResponse
from stocktopus.providers.market_data import Candle
from stocktopus.providers.news import NewsArticle, NewsCategory
from stocktopus.providers.secrets import EnvSecretsProvider

# ── Secrets ───────────────────────────────────────────────────────────────────


def test_env_secrets_missing_key() -> None:
    provider = EnvSecretsProvider()
    with pytest.raises(KeyError):
        provider.get("NONEXISTENT_SECRET_XYZ_123")


def test_env_secrets_default_fallback() -> None:
    provider = EnvSecretsProvider()
    assert provider.get_or_default("NONEXISTENT_SECRET_XYZ_123", "fallback") == "fallback"


def test_env_secrets_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_SECRET_KEY", "supersecret")
    provider = EnvSecretsProvider()
    assert provider.get("TEST_SECRET_KEY") == "supersecret"


# ── Market Data ───────────────────────────────────────────────────────────────


def test_candle_model_full() -> None:
    candle = Candle(
        symbol="SPY",
        timeframe="1m",
        ts=datetime(2024, 1, 2, 9, 31, tzinfo=UTC),
        open=470.0,
        high=470.5,
        low=469.8,
        close=470.3,
        volume=1_200_000,
        vwap=470.15,
    )
    assert candle.symbol == "SPY"
    assert candle.vwap == 470.15


def test_candle_model_no_vwap() -> None:
    candle = Candle(
        symbol="SPY",
        timeframe="5m",
        ts=datetime(2024, 1, 2, 9, 35, tzinfo=UTC),
        open=470.0,
        high=471.0,
        low=469.5,
        close=470.8,
        volume=2_500_000,
    )
    assert candle.vwap is None


# ── News ──────────────────────────────────────────────────────────────────────


def test_news_article_model() -> None:
    article = NewsArticle(
        id="abc123",
        headline="Fed holds rates steady",
        source="reuters",
        url="https://reuters.com/article/abc123",
        published_at=datetime(2024, 1, 2, 14, 0, tzinfo=UTC),
        symbols=["SPY"],
        categories=[NewsCategory.FED],
    )
    assert NewsCategory.FED in article.categories
    assert article.sentiment_score is None


def test_news_category_values() -> None:
    assert NewsCategory.FED == "fed"
    assert NewsCategory.CPI_NFP == "cpi_nfp"
    assert NewsCategory.MACRO == "macro"


# ── LLM ───────────────────────────────────────────────────────────────────────


def test_llm_message_model() -> None:
    msg = LLMMessage(role="user", content="Is the market trending?")
    assert msg.role == "user"
    assert msg.content == "Is the market trending?"


def test_llm_response_model() -> None:
    resp = LLMResponse(
        content='{"regime": "trending"}',
        model="gpt-4o",
        prompt_tokens=100,
        completion_tokens=50,
        cost_usd=0.002,
    )
    assert resp.cost_usd == 0.002
    assert resp.prompt_tokens + resp.completion_tokens == 150


# ── Broker ────────────────────────────────────────────────────────────────────


def test_order_side_str_values() -> None:
    assert OrderSide.BUY == "buy"
    assert OrderSide.SELL == "sell"


def test_order_type_str_values() -> None:
    assert OrderType.MARKET == "market"
    assert OrderType.STOP_LIMIT == "stop_limit"


def test_order_model() -> None:
    order = Order(
        id="ord_abc123",
        symbol="SPY",
        side=OrderSide.BUY,
        type=OrderType.MARKET,
        qty=Decimal("10"),
        status=OrderStatus.FILLED,
        filled_qty=Decimal("10"),
        filled_avg_price=Decimal("470.25"),
        created_at=datetime(2024, 1, 2, 9, 31, tzinfo=UTC),
    )
    assert order.filled_avg_price == Decimal("470.25")
    assert order.status == OrderStatus.FILLED


def test_position_model() -> None:
    pos = Position(
        symbol="SPY",
        qty=Decimal("10"),
        avg_entry_price=Decimal("470.00"),
        current_price=Decimal("472.50"),
        unrealized_pnl=Decimal("25.00"),
        side="long",
    )
    assert pos.unrealized_pnl == Decimal("25.00")
