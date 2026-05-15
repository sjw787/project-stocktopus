"""AWS Lambda entrypoint for Stocktopus.

Routes:
  - EventBridge Scheduler events → scheduled task dispatcher
  - All other events              → Mangum HTTP proxy (FastAPI)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── Cold-start bootstrap ──────────────────────────────────────────────────────
# Fetch secrets from Secrets Manager and inject into os.environ before any
# application imports occur. Must run at module level (import time).
_bootstrap_done = False


def _bootstrap_secrets() -> None:
    """Load all secrets from Secrets Manager into os.environ on cold start.

    Reads DB credentials, API keys (OpenAI, Anthropic, Alpaca, Finnhub, NewsAPI)
    from Secrets Manager ARNs passed as Lambda env vars. Idempotent.
    """
    global _bootstrap_done
    if _bootstrap_done:
        return
    _bootstrap_done = True

    import json
    import os
    import urllib.parse

    from stocktopus.config import get_settings

    settings = get_settings()
    if not settings.lambda_runtime:
        return  # Local dev — all values come from .env

    import boto3
    client = boto3.client("secretsmanager")

    def _get(arn: str) -> dict:
        return json.loads(client.get_secret_value(SecretId=arn)["SecretString"])

    # DB credentials → DATABASE_URL
    if settings.db_secret_arn and settings.rds_proxy_endpoint:
        secret = _get(settings.db_secret_arn)
        password = urllib.parse.quote_plus(secret["password"])
        os.environ["DATABASE_URL"] = (
            f"postgresql+asyncpg://{secret['username']}:{password}"
            f"@{settings.rds_proxy_endpoint}:5432/{settings.db_name}"
        )

    # API keys
    _load_api_key(client, os.getenv("OPENAI_SECRET_ARN"), "OPENAI_API_KEY", "api_key")
    _load_api_key(client, os.getenv("ANTHROPIC_SECRET_ARN"), "ANTHROPIC_API_KEY", "api_key")
    _load_api_key(client, os.getenv("FINNHUB_SECRET_ARN"), "FINNHUB_API_KEY", "api_key")
    _load_api_key(client, os.getenv("NEWSAPI_SECRET_ARN"), "NEWSAPI_API_KEY", "api_key")

    alpaca_arn = os.getenv("ALPACA_SECRET_ARN")
    if alpaca_arn:
        alpaca = _get(alpaca_arn)
        os.environ["ALPACA_API_KEY"] = alpaca.get("api_key", "")
        os.environ["ALPACA_SECRET_KEY"] = alpaca.get("secret_key", "")

    get_settings.cache_clear()  # reload with injected values


def _load_api_key(client: Any, arn: str | None, env_var: str, field: str) -> None:
    if not arn:
        return
    try:
        import json
        secret = json.loads(client.get_secret_value(SecretId=arn)["SecretString"])
        import os
        os.environ[env_var] = secret.get(field, "")
    except Exception:
        logger.exception("Failed to load secret %s into %s", arn, env_var)


_bootstrap_secrets()

# Lazily initialized to avoid importing the full FastAPI app on cold start
# until we know it is an HTTP request (not a scheduled event).
_mangum_handler = None


def handler(event: dict[str, Any], context: Any) -> Any:
    """Lambda entrypoint — routes EventBridge Scheduler events or HTTP events."""
    if event.get("source") in ("aws.scheduler", "scheduler"):
        return _handle_scheduled_event(event, context)

    global _mangum_handler
    if _mangum_handler is None:
        from mangum import Mangum

        from stocktopus.main import create_app

        _mangum_handler = Mangum(create_app(), lifespan="off")

    # Python 3.12 no longer auto-creates an event loop in the main thread.
    # Mangum ≥0.17 uses asyncio.run() internally, but guard here for safety.
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    return _mangum_handler(event, context)


# ── Scheduled event dispatcher ────────────────────────────────────────────────


def _handle_scheduled_event(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Dispatch EventBridge Scheduler tasks by the `task` field in the event payload."""
    task = event.get("task")
    logger.info("Scheduled event: task=%s", task)

    if task == "ingestion_tick":
        return asyncio.run(_run_ingestion_tick())
    elif task == "paper_tick":
        return asyncio.run(_run_paper_tick())
    elif task == "backfill":
        return asyncio.run(_run_backfill(event))
    else:
        logger.warning("Unknown scheduled task: %s", task)
        return {"status": "error", "message": f"unknown task: {task}"}


# ── Ingestion tick ─────────────────────────────────────────────────────────────


async def _run_ingestion_tick() -> dict[str, Any]:
    """Run a candle ingestion tick for all configured symbols if the schedule is enabled."""
    if not await _schedule_enabled("ingestion"):
        logger.info("Ingestion schedule disabled — skipping")
        return {"status": "skipped", "reason": "schedule disabled"}

    from datetime import datetime, timedelta, timezone

    from stocktopus.config import get_settings
    from stocktopus.db.engine import AsyncSessionFactory
    from stocktopus.ingestion.candle_ingest import backfill

    settings = get_settings()
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=2)

    # Choose provider based on Alpaca key availability
    if settings.alpaca_api_key:
        from stocktopus.ingestion.alpaca_market_data import AlpacaMarketData

        provider = AlpacaMarketData(
            api_key=settings.alpaca_api_key,
            secret_key=settings.alpaca_secret_key,
            feed=settings.alpaca_data_feed or None,
        )
    else:
        from stocktopus.ingestion.yahoo_market_data import YahooFinanceMarketData

        provider = YahooFinanceMarketData()

    results: dict[str, Any] = {}
    async with AsyncSessionFactory() as session:
        for symbol in settings.allowed_symbols:
            counts = await backfill(session, provider=provider, symbol=symbol, start=start, end=now)
            await session.commit()
            results[symbol] = counts

    logger.info("Ingestion tick complete: %s", results)
    return {"status": "ok", "task": "ingestion_tick", "results": results}


# ── Historical backfill ────────────────────────────────────────────────────────


async def _run_backfill(event: dict[str, Any]) -> dict[str, Any]:
    """Run a full historical candle backfill.

    Event fields:
      symbol   – ticker (e.g. "SPY"); defaults to all allowed_symbols
      from_date – ISO date string "YYYY-MM-DD"; default: 1 year ago
      to_date   – ISO date string "YYYY-MM-DD"; default: today
      provider  – "alpaca" | "yahoo"; default: "alpaca" if key present, else "yahoo"
    """
    from datetime import datetime, timedelta, timezone

    from stocktopus.config import get_settings
    from stocktopus.db.engine import AsyncSessionFactory
    from stocktopus.ingestion.candle_ingest import backfill

    settings = get_settings()
    now = datetime.now(timezone.utc)

    from_str = event.get("from_date")
    to_str = event.get("to_date")
    start = datetime.strptime(from_str, "%Y-%m-%d").replace(tzinfo=timezone.utc) if from_str else now - timedelta(days=365)
    end = datetime.strptime(to_str, "%Y-%m-%d").replace(tzinfo=timezone.utc) if to_str else now

    symbols_raw = event.get("symbol")
    symbols = [symbols_raw.upper()] if symbols_raw else [s.upper() for s in settings.allowed_symbols]

    timeframes = event.get("timeframes", ["1m", "5m", "1d"])
    provider_name = event.get("provider", "alpaca" if settings.alpaca_api_key else "yahoo")
    if provider_name == "alpaca" and settings.alpaca_api_key:
        from stocktopus.ingestion.alpaca_market_data import AlpacaMarketData
        provider = AlpacaMarketData(
            api_key=settings.alpaca_api_key,
            secret_key=settings.alpaca_secret_key,
            feed=settings.alpaca_data_feed or None,
        )
    else:
        from stocktopus.ingestion.yahoo_market_data import YahooFinanceMarketData
        provider = YahooFinanceMarketData()

    results: dict[str, Any] = {}
    async with AsyncSessionFactory() as session:
        for symbol in symbols:
            logger.info("Backfilling %s from %s to %s via %s", symbol, start.date(), end.date(), provider_name)
            counts = await backfill(session, provider=provider, symbol=symbol, start=start, end=end, timeframes=timeframes)
            await session.commit()
            results[symbol] = counts
            logger.info("Backfill %s complete: %s", symbol, counts)

    return {"status": "ok", "task": "backfill", "results": results}


async def _run_paper_tick() -> dict[str, Any]:
    """Run a paper trading tick for all configured symbols if the schedule is enabled."""
    if not await _schedule_enabled("paper"):
        logger.info("Paper trading schedule disabled — skipping")
        return {"status": "skipped", "reason": "schedule disabled"}

    from stocktopus.broker.alpaca_adapter import AlpacaBrokerAdapter
    from stocktopus.broker.mock_adapter import MockBrokerAdapter
    from stocktopus.broker.paper_trader import PaperTrader
    from stocktopus.config import get_settings
    from stocktopus.db.engine import AsyncSessionFactory
    from stocktopus.llm.anthropic_provider import AnthropicProvider
    from stocktopus.llm.openai_provider import OpenAIProvider
    from stocktopus.llm.research_director import ResearchDirector

    settings = get_settings()

    active = (settings.active_llm_provider or "openai").lower()
    if active == "anthropic" and settings.anthropic_api_key:
        llm = AnthropicProvider(api_key=settings.anthropic_api_key, default_model=settings.llm_model)
    elif settings.openai_api_key:
        llm = OpenAIProvider(api_key=settings.openai_api_key, default_model=settings.llm_model)
    else:
        logger.error("No LLM provider configured — cannot run paper tick")
        return {"status": "error", "message": "no LLM provider configured"}

    director = ResearchDirector(llm=llm, daily_budget_usd=settings.llm_daily_budget_usd)

    broker = (
        AlpacaBrokerAdapter(
            api_key=settings.alpaca_api_key,
            secret_key=settings.alpaca_secret_key,
            paper=True,
        )
        if settings.alpaca_api_key
        else MockBrokerAdapter()
    )

    tick_results: list[dict[str, Any]] = []
    async with AsyncSessionFactory() as session:
        for symbol in settings.allowed_symbols:
            trader = PaperTrader(
                broker=broker,
                director=director,
                session=session,
                symbol=symbol.upper(),
                max_position_usd=settings.max_position_usd,
                max_daily_loss_usd=settings.max_daily_loss_usd,
                max_trades_per_day=settings.max_trades_per_day,
                dry_run=False,
            )
            result = await trader.tick()
            tick_results.append({"symbol": symbol, **result})

    logger.info("Paper tick complete: %s", tick_results)
    return {"status": "ok", "task": "paper_tick", "results": tick_results}


# ── DynamoDB feature-flag helper ───────────────────────────────────────────────


async def _schedule_enabled(schedule_name: str) -> bool:
    """Return True if the given schedule is enabled in DynamoDB.

    Falls back to True when SETTINGS_TABLE_NAME is not set (local / non-Lambda env).
    Uses asyncio.to_thread so the sync boto3 call does not block the event loop.
    """
    import os

    table_name = os.getenv("SETTINGS_TABLE_NAME")
    if not table_name:
        return True

    def _get_flag() -> bool:
        import boto3

        ddb = boto3.resource("dynamodb")
        table = ddb.Table(table_name)
        try:
            resp = table.get_item(Key={"pk": "schedule", "sk": schedule_name})
            item = resp.get("Item", {})
            return bool(item.get("enabled", True))
        except Exception:
            logger.exception("Failed to read schedule flag for %s; defaulting to enabled", schedule_name)
            return True

    return await asyncio.to_thread(_get_flag)
