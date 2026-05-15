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
# In Lambda, fetch the DB password from Secrets Manager and inject DATABASE_URL
# into the process environment before any database imports occur.
# Must run at module level (import time) — before Mangum/FastAPI are initialised.
_bootstrap_done = False


def _bootstrap_db_credentials() -> None:
    """Fetch Aurora credentials from Secrets Manager and set DATABASE_URL.

    Only executes when the required Lambda env vars are present.
    Idempotent — called once per cold start; subsequent warm invocations skip it.
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
    if not (settings.lambda_runtime and settings.db_secret_arn and settings.rds_proxy_endpoint):
        return  # Local dev — DATABASE_URL already set via .env

    import boto3

    client = boto3.client("secretsmanager")
    secret = json.loads(
        client.get_secret_value(SecretId=settings.db_secret_arn)["SecretString"]
    )
    username = secret["username"]
    password = urllib.parse.quote_plus(secret["password"])  # encode special chars
    url = (
        f"postgresql+asyncpg://{username}:{password}"
        f"@{settings.rds_proxy_endpoint}:5432/{settings.db_name}"
    )
    os.environ["DATABASE_URL"] = url
    get_settings.cache_clear()  # reload settings with the new DATABASE_URL


_bootstrap_db_credentials()

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


# ── Paper trading tick ─────────────────────────────────────────────────────────


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
