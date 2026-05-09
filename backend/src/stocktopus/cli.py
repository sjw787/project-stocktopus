"""Stocktopus CLI — ingestion commands and utilities.

Usage:
    uv run stocktopus ingest backfill --symbol SPY --from 2022-01-01
    uv run stocktopus ingest quality  --symbol SPY --from 2022-01-01 --to 2024-01-01
"""

import asyncio
import sys
from datetime import UTC, date, datetime

import click

from stocktopus.config import get_settings
from stocktopus.db.engine import AsyncSessionFactory
from stocktopus.features.snapshot import backfill_market_context_signals, compute_and_persist
from stocktopus.ingestion.alpaca_market_data import AlpacaMarketData
from stocktopus.ingestion.candle_ingest import backfill
from stocktopus.ingestion.context_ingest import snapshot_market_context
from stocktopus.ingestion.quality import check_candle_quality
from stocktopus.ingestion.yahoo_market_data import YahooFinanceMarketData
from stocktopus.logging_config import configure_logging
from stocktopus.universe import DEFAULT_UNIVERSE


@click.group()
def cli() -> None:
    """Stocktopus management CLI."""
    configure_logging()


@cli.group()
def ingest() -> None:
    """Data ingestion commands."""


@ingest.command("backfill")
@click.option("--symbol", required=True, help="Ticker symbol (e.g. SPY)")
@click.option(
    "--from",
    "from_date",
    required=True,
    metavar="YYYY-MM-DD",
    help="Start date for backfill",
)
@click.option(
    "--to",
    "to_date",
    default=None,
    metavar="YYYY-MM-DD",
    help="End date (default: today)",
)
@click.option(
    "--timeframe",
    "-tf",
    multiple=True,
    default=["1m", "5m", "1d"],
    show_default=True,
    help="Timeframes to fetch (can be repeated)",
)
@click.option("--qqq-enabled", is_flag=True, default=False, help="Allow QQQ symbol")
@click.option(
    "--provider",
    type=click.Choice(["alpaca", "yahoo"], case_sensitive=False),
    default="yahoo",
    show_default=True,
    help="Data provider. 'yahoo' is free and requires no credentials.",
)
def backfill_cmd(
    symbol: str,
    from_date: str,
    to_date: str | None,
    timeframe: tuple[str, ...],
    qqq_enabled: bool,
    provider: str,
) -> None:
    """Backfill historical candles for a symbol."""
    settings = get_settings()

    DEFAULT_UNIVERSE.validate_symbol(symbol.upper(), qqq_enabled=qqq_enabled)

    start = datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=UTC)
    end = (
        datetime.strptime(to_date, "%Y-%m-%d").replace(tzinfo=UTC)
        if to_date
        else datetime.now(tz=UTC)
    )

    if provider == "alpaca":
        data_provider = AlpacaMarketData(
            api_key=settings.alpaca_api_key,
            secret_key=settings.alpaca_secret_key,
            data_feed=settings.alpaca_data_feed,
        )
    else:
        data_provider = YahooFinanceMarketData()

    async def _run() -> None:
        async with AsyncSessionFactory() as session:
            results = await backfill(
                session,
                data_provider,
                symbol=symbol.upper(),
                start=start,
                end=end,
                timeframes=list(timeframe),
            )
        for tf, count in results.items():
            click.echo(f"  {tf}: {count} rows inserted")

    click.echo(
        f"Backfilling {symbol.upper()} from {from_date} to {to_date or 'today'} via {provider}..."
    )
    asyncio.run(_run())
    click.echo("Done.")


@ingest.command("quality")
@click.option("--symbol", required=True, help="Ticker symbol")
@click.option("--from", "from_date", required=True, metavar="YYYY-MM-DD")
@click.option("--to", "to_date", required=True, metavar="YYYY-MM-DD")
@click.option("--timeframe", "-tf", default="1m", show_default=True)
def quality_cmd(symbol: str, from_date: str, to_date: str, timeframe: str) -> None:
    """Run data quality checks on stored candles."""
    start = date.fromisoformat(from_date)
    end = date.fromisoformat(to_date)

    async def _run() -> None:
        async with AsyncSessionFactory() as session:
            report = await check_candle_quality(session, symbol.upper(), timeframe, start, end)
        click.echo(f"\nQuality report for {report.symbol} {report.timeframe}")
        click.echo(f"  Period:             {report.start} → {report.end}")
        click.echo(f"  Expected sessions:  {report.expected_sessions}")
        click.echo(f"  Sessions with data: {report.sessions_with_data}")
        click.echo(f"  Missing sessions:   {len(report.missing_sessions)}")
        if report.missing_sessions:
            for d in report.missing_sessions[:10]:
                click.echo(f"    - {d}")
            if len(report.missing_sessions) > 10:
                click.echo(f"    ... and {len(report.missing_sessions) - 10} more")
        click.echo(f"  OHLC violations:    {report.ohlc_violations}")
        click.echo(f"  Bar count issues:   {report.bar_count_violations}")
        click.echo(f"  Negative volumes:   {report.negative_volume_count}")
        status = "✓ PASSED" if report.passed else "✗ FAILED"
        click.echo(f"\n  {status}")
        if not report.passed:
            sys.exit(1)

    asyncio.run(_run())


@ingest.command("context")
@click.option(
    "--at",
    "at_time",
    default=None,
    metavar="YYYY-MM-DDTHH:MM:SSZ",
    help="Snapshot timestamp (default: now)",
)
def context_cmd(at_time: str | None) -> None:
    """Snapshot current broad-market context (breadth proxies, VIX, sector ETFs)."""
    settings = get_settings()

    ts = (
        datetime.fromisoformat(at_time.rstrip("Z")).replace(tzinfo=UTC)
        if at_time
        else datetime.now(tz=UTC)
    )

    provider = AlpacaMarketData(
        api_key=settings.alpaca_api_key,
        secret_key=settings.alpaca_secret_key,
        data_feed=settings.alpaca_data_feed,
    )

    async def _run() -> None:
        async with AsyncSessionFactory() as session:
            row = await snapshot_market_context(session, provider, ts)
        if row:
            click.echo(f"  ts:        {row.ts}")
            click.echo(f"  SPY:       {row.spy_price}")
            click.echo(f"  VIX:       {row.vix}")
            click.echo(f"  QQQ:       {row.qqq_price}  IWM: {row.iwm_price}  DIA: {row.dia_price}")
            click.echo(f"  XLK: {row.xlk}  XLF: {row.xlf}  XLE: {row.xle}")
            click.echo(f"  gap_pct:   {row.spy_gap_pct}")
        else:
            click.echo("  (duplicate snapshot — row already exists for this timestamp)")

    click.echo(f"Snapshotting market context at {ts.isoformat()}...")
    asyncio.run(_run())
    click.echo("Done.")


@cli.group()
def features() -> None:
    """Feature computation commands."""


@features.command("compute")
@click.option("--symbol", default="SPY", show_default=True, help="Ticker symbol")
@click.option(
    "--at",
    "at_ts",
    default=None,
    metavar="YYYY-MM-DDTHH:MM:SS",
    help="Timestamp to compute at (default: now UTC)",
)
def compute_features_cmd(symbol: str, at_ts: str | None) -> None:
    """Compute and persist a feature snapshot for SYMBOL at a given timestamp."""

    ts: datetime | None = None
    if at_ts:
        ts = datetime.fromisoformat(at_ts).replace(tzinfo=UTC)

    async def _run() -> None:
        async with AsyncSessionFactory() as session:
            fv = await compute_and_persist(session, symbol, ts=ts)
        click.echo(f"Symbol:      {fv.symbol}  ts: {fv.ts.isoformat()}")
        click.echo(f"Close:       {fv.close:.4f}")
        click.echo(f"SMA20d:      {fv.sma_20d}  SMA50d: {fv.sma_50d}  SMA200d: {fv.sma_200d}")
        click.echo(
            f"ATR(14d):    {fv.atr_14d}  ({fv.atr_pct:.2f}%)"
            if fv.atr_pct
            else f"ATR(14d): {fv.atr_14d}"
        )
        click.echo(f"VWAP:        {fv.vwap}  above={fv.above_vwap}")
        click.echo(f"RVOL:        {fv.rvol}")
        click.echo(f"Trend(1d):   {fv.trend_1d}  gap%: {fv.gap_pct}")

    asyncio.run(_run())


@features.command("backfill-context")
@click.option("--symbol", default="SPY", show_default=True, help="Ticker symbol")
@click.option(
    "--batch",
    default=500,
    show_default=True,
    type=int,
    help="Rows per batch",
)
def backfill_context_cmd(symbol: str, batch: int) -> None:
    """Back-fill spy_above_vwap and spy_trend_1d on existing market_context rows."""

    async def _run() -> None:
        total = 0
        while True:
            async with AsyncSessionFactory() as session:
                n = await backfill_market_context_signals(session, symbol, batch_size=batch)
            if n == 0:
                break
            total += n
            click.echo(f"  updated {total} rows so far...")
        click.echo(f"Done. Total rows updated: {total}")

    asyncio.run(_run())


def main() -> None:
    cli()


# ── db commands ────────────────────────────────────────────────────────────────


@cli.group()
def db() -> None:
    """Database maintenance commands."""


_PURGEABLE_TABLES = {
    "candles": "candles",
    "feature_snapshots": "feature_snapshots",
    "llm_logs": "llm_logs",
    "market_context": "market_context",
    "news_events": "news_events",
    "trade_lots": "trade_lots",
    "trade_rejections": "trade_rejections",
    "paper_trades": "paper_trades",
}


@db.command("status")
def db_status_cmd() -> None:
    """Show row counts for all data tables."""
    from sqlalchemy import text

    _STATUS_TABLES = [
        "candles",
        "feature_snapshots",
        "llm_logs",
        "market_context",
        "news_events",
        "trade_lots",
        "trade_rejections",
        "paper_trades",
    ]

    async def _run() -> None:
        async with AsyncSessionFactory() as session:
            click.echo(f"{'Table':<24} {'Rows':>10}")
            click.echo("-" * 36)
            for tbl in _STATUS_TABLES:
                result = await session.execute(text(f"SELECT COUNT(*) FROM {tbl}"))  # noqa: S608
                count = result.scalar_one()
                click.echo(f"{tbl:<24} {count:>10,}")

    asyncio.run(_run())


@db.command("purge")
@click.option(
    "--table",
    type=click.Choice([*_PURGEABLE_TABLES, "all"], case_sensitive=False),
    required=True,
    help="Table to truncate, or 'all' to truncate every data table.",
)
@click.option(
    "--symbol",
    default=None,
    help="Limit purge to this symbol (only honoured for 'candles' and 'feature_snapshots').",
)
@click.option("--yes", is_flag=True, default=False, help="Skip confirmation prompt.")
def db_purge_cmd(table: str, symbol: str | None, yes: bool) -> None:
    """Truncate one or all data tables.

    \b
    Examples:
        stocktopus db purge --table all --yes
        stocktopus db purge --table candles --symbol SPY
    """
    from sqlalchemy import text

    tables = list(_PURGEABLE_TABLES.keys()) if table == "all" else [table]

    summary = ", ".join(tables) + (f"  (symbol={symbol})" if symbol else "")
    if not yes:
        click.confirm(f"Purge data from: {summary}?", abort=True)

    async def _run() -> None:
        async with AsyncSessionFactory() as session:
            for t in tables:
                sql = (
                    f"DELETE FROM {t} WHERE symbol = :sym"
                    if (symbol and t in ("candles", "feature_snapshots"))
                    else f"TRUNCATE TABLE {t} RESTART IDENTITY CASCADE"
                )
                sym_tables = ("candles", "feature_snapshots")
                params = {"sym": symbol} if (symbol and t in sym_tables) else {}
                result = await session.execute(text(sql), params)
                rows = result.rowcount if sql.startswith("DELETE") else "all"
                click.echo(f"  {t}: purged {rows} rows")
            await session.commit()

    asyncio.run(_run())
    click.echo("Done.")


# ── Analyze (LLM regime assessment) ─────────────────────────────────────────


@cli.group()
def analyze() -> None:
    """LLM-powered regime analysis commands."""


@analyze.command("regime")
@click.option("--symbol", default="SPY", show_default=True, help="Ticker symbol")
@click.option(
    "--provider",
    type=click.Choice(["openai", "anthropic"], case_sensitive=False),
    default=None,
    help="LLM provider (defaults to ACTIVE_LLM_PROVIDER in settings)",
)
@click.option("--model", default=None, help="Override model name")
@click.option("--snapshot-id", default=None, help="Specific feature_snapshot UUID to analyze")
def analyze_regime_cmd(
    symbol: str,
    provider: str | None,
    model: str | None,
    snapshot_id: str | None,
) -> None:
    """Run LLM regime assessment for a symbol using its latest feature snapshot."""
    from stocktopus.llm.anthropic_provider import AnthropicProvider
    from stocktopus.llm.openai_provider import OpenAIProvider
    from stocktopus.llm.research_director import ResearchDirector

    settings = get_settings()
    active = (provider or settings.active_llm_provider).lower()

    if active == "anthropic":
        if not settings.anthropic_api_key:
            click.echo("ERROR: ANTHROPIC_API_KEY not set in .env", err=True)
            sys.exit(1)
        llm = AnthropicProvider(api_key=settings.anthropic_api_key)
    else:
        if not settings.openai_api_key:
            click.echo("ERROR: OPENAI_API_KEY not set in .env", err=True)
            sys.exit(1)
        llm = OpenAIProvider(api_key=settings.openai_api_key)

    director = ResearchDirector(
        llm=llm,
        daily_budget_usd=settings.llm_daily_budget_usd,
        model=model,
    )

    async def _run() -> None:
        async with AsyncSessionFactory() as session:
            assessment = await director.analyze(
                session, symbol=symbol.upper(), feature_snapshot_id=snapshot_id
            )
        click.echo(f"\nRegime Assessment for {symbol.upper()}")
        click.echo("=" * 40)
        click.echo(f"  Regime:     {assessment.regime}")
        click.echo(f"  Lean:       {assessment.lean}")
        click.echo(f"  Confidence: {assessment.confidence}/10")
        click.echo(f"  Model:      {assessment.model_used}")
        click.echo(f"  Cost:       ${assessment.input_tokens * 0.0000015:.5f} (approx)")
        click.echo(f"\nReasoning:\n{assessment.reasoning}")
        click.echo("\nKey Risks:")
        for risk in assessment.key_risks:
            click.echo(f"  • {risk}")
        click.echo(f"\nInvalidation:\n  {assessment.invalidation}")

    asyncio.run(_run())


# ── Strategy (signal evaluation) ─────────────────────────────────────────────


@cli.group()
def strategy() -> None:
    """Trading strategy commands."""


@strategy.command("evaluate")
@click.option("--symbol", default="SPY", show_default=True, help="Ticker symbol")
@click.option(
    "--provider",
    type=click.Choice(["openai", "anthropic"], case_sensitive=False),
    default=None,
    help="LLM provider (defaults to ACTIVE_LLM_PROVIDER in settings)",
)
@click.option("--model", default=None, help="Override model name")
@click.option("--snapshot-id", default=None, help="Specific feature_snapshot UUID to analyze")
def strategy_evaluate_cmd(
    symbol: str,
    provider: str | None,
    model: str | None,
    snapshot_id: str | None,
) -> None:
    """Evaluate opening momentum strategy signal for a symbol.

    Runs the full pipeline: features → LLM regime → strategy signal → risk filter.
    Prints the TradeThesis if a signal is generated, or explains why no trade was taken.
    """

    from sqlalchemy import desc, select

    from stocktopus.db.models import FeatureSnapshot
    from stocktopus.features.models import FeatureVector
    from stocktopus.llm.anthropic_provider import AnthropicProvider
    from stocktopus.llm.openai_provider import OpenAIProvider
    from stocktopus.llm.research_director import ResearchDirector
    from stocktopus.risk.filter import RiskFilter
    from stocktopus.strategies.base import StrategyContext
    from stocktopus.strategies.opening_momentum import OpeningMomentumStrategy

    settings = get_settings()
    active = (provider or settings.active_llm_provider).lower()

    if active == "anthropic":
        if not settings.anthropic_api_key:
            click.echo("ERROR: ANTHROPIC_API_KEY not set in .env", err=True)
            sys.exit(1)
        llm = AnthropicProvider(api_key=settings.anthropic_api_key)
    else:
        if not settings.openai_api_key:
            click.echo("ERROR: OPENAI_API_KEY not set in .env", err=True)
            sys.exit(1)
        llm = OpenAIProvider(api_key=settings.openai_api_key)

    director = ResearchDirector(
        llm=llm,
        daily_budget_usd=settings.llm_daily_budget_usd,
        model=model,
    )
    strat = OpeningMomentumStrategy()
    risk = RiskFilter.from_settings(
        max_position_usd=settings.max_position_usd,
        max_daily_loss_usd=settings.max_daily_loss_usd,
        max_trades_per_day=settings.max_trades_per_day,
    )

    async def _run() -> None:
        async with AsyncSessionFactory() as session:
            # 1. Get LLM regime assessment (reuses cached if recent)
            assessment = await director.analyze(
                session, symbol=symbol.upper(), feature_snapshot_id=snapshot_id
            )

            # 2. Load latest feature snapshot
            q = (
                select(FeatureSnapshot)
                .where(FeatureSnapshot.symbol == symbol.upper())
                .order_by(desc(FeatureSnapshot.ts))
                .limit(1)
            )
            row = (await session.execute(q)).scalar_one_or_none()
            if row is None:
                click.echo(f"No feature snapshots found for {symbol.upper()}.", err=True)
                return

            fv = FeatureVector(**row.features)

            # 3. Build context and run strategy
            ctx = StrategyContext(
                symbol=symbol.upper(),
                ts=row.ts,
                features=fv,
                regime=assessment,
            )
            thesis = strat.evaluate(ctx)

        click.echo(f"\nStrategy Evaluation for {symbol.upper()}")
        click.echo("=" * 44)

        if thesis is None:
            click.echo("  Signal: NO TRADE — entry conditions not met.")
            click.echo(f"  Regime: {assessment.regime} / {assessment.lean} "
                       f"@ {assessment.confidence}/10")
            return

        # 4. Run risk filter
        filter_result = risk.evaluate(ctx, thesis)

        if filter_result.approved:
            click.echo("  Signal:     TRADE SIGNAL ✓")
        else:
            click.echo("  Signal:     BLOCKED by risk filter ✗")

        click.echo(f"  Direction:  {thesis.direction}")
        click.echo(f"  Entry:      ${thesis.entry_price:.2f}")
        click.echo(f"  Stop:       ${thesis.stop_loss:.2f}")
        click.echo(f"  Take-Profit:${thesis.take_profit:.2f}")
        click.echo(f"  R/R:        {thesis.risk_reward:.2f}x" if thesis.risk_reward else "")
        click.echo(f"\nRationale:\n  {thesis.rationale}")

        if not filter_result.approved:
            click.echo("\nRisk Rejections:")
            for r in filter_result.rejections:
                click.echo(f"  ✗ [{r.check_name}] {r.reason}")

    asyncio.run(_run())


# ── Backtest ──────────────────────────────────────────────────────────────────


@cli.group()
def backtest() -> None:
    """Backtesting commands."""


@backtest.command("run")
@click.option("--symbol", default="SPY", show_default=True, help="Ticker symbol")
@click.option(
    "--from",
    "from_date",
    required=True,
    metavar="YYYY-MM-DD",
    help="Backtest start date (inclusive)",
)
@click.option(
    "--to",
    "to_date",
    default=None,
    metavar="YYYY-MM-DD",
    help="Backtest end date (inclusive, default: today)",
)
@click.option("--capital", default=10_000.0, show_default=True, help="Initial capital USD")
@click.option(
    "--position-size",
    default=50.0,
    show_default=True,
    help="Max notional per trade USD",
)
@click.option(
    "--friction",
    type=click.Choice(["realistic", "zero"], case_sensitive=False),
    default="realistic",
    show_default=True,
    help="Friction model",
)
@click.option(
    "--out-dir",
    default="runs",
    show_default=True,
    help="Directory to write report artifacts",
)
@click.option("--no-html", is_flag=True, default=False, help="Skip HTML report generation")
def backtest_run_cmd(
    symbol: str,
    from_date: str,
    to_date: str | None,
    capital: float,
    position_size: float,
    friction: str,
    out_dir: str,
    no_html: bool,
) -> None:
    """Run an event-driven backtest of the opening momentum strategy.

    \b
    Examples:
        stocktopus backtest run --symbol SPY --from 2024-01-01
        stocktopus backtest run --symbol SPY --from 2023-01-01 --to 2024-01-01 --capital 5000
    """
    import json
    import uuid
    from datetime import UTC, timedelta
    from pathlib import Path

    import pandas as pd
    from sqlalchemy import select

    from stocktopus.backtest.friction import FrictionModel
    from stocktopus.backtest.report import render_report
    from stocktopus.backtest.runner import BacktestRunner
    from stocktopus.db.models import Candle, LLMLog
    from stocktopus.features.models import Regime, TradeLean

    start_dt = datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=UTC)
    end_dt = (
        datetime.strptime(to_date, "%Y-%m-%d").replace(tzinfo=UTC)
        if to_date
        else datetime.now(UTC)
    )
    sym = symbol.upper()
    run_id = str(uuid.uuid4())[:8]

    friction_model = (
        FrictionModel.realistic_alpaca() if friction == "realistic" else FrictionModel.zero()
    )

    click.echo(f"Backtest: {sym}  {from_date} → {to_date or 'today'}")
    click.echo(f"Capital: ${capital:,.0f}  |  Position size: ${position_size:.0f}")
    click.echo(f"Friction: {friction}  |  Run ID: {run_id}")
    click.echo()

    async def _run() -> None:
        async with AsyncSessionFactory() as session:
            # ── Load 5m intraday candles ──────────────────────────────────────
            q5m = (
                select(Candle)
                .where(
                    Candle.symbol == sym,
                    Candle.timeframe == "5m",
                    Candle.ts >= start_dt,
                    Candle.ts <= end_dt,
                )
                .order_by(Candle.ts)
            )
            rows_5m = (await session.execute(q5m)).scalars().all()
            if not rows_5m:
                click.echo(
                    f"ERROR: No 5m candles for {sym} in the given date range.\n"
                    "Run: stocktopus ingest backfill --symbol SPY --from YYYY-MM-DD --timeframe 5m",
                    err=True,
                )
                return

            bars_5m = pd.DataFrame(
                [
                    {
                        "symbol": c.symbol,
                        "ts": c.ts,
                        "open": c.open,
                        "high": c.high,
                        "low": c.low,
                        "close": c.close,
                        "volume": c.volume,
                    }
                    for c in rows_5m
                ]
            )
            click.echo(f"Loaded {len(bars_5m):,} 5m bars")

            # ── Load 1d candles for SMA/gap ───────────────────────────────────
            q1d = (
                select(Candle)
                .where(
                    Candle.symbol == sym,
                    Candle.timeframe == "1d",
                    Candle.ts <= end_dt,
                )
                .order_by(Candle.ts)
            )
            rows_1d = (await session.execute(q1d)).scalars().all()
            bars_1d: pd.DataFrame | None = None
            if rows_1d:
                bars_1d = pd.DataFrame(
                    [
                        {
                            "ts": c.ts,
                            "open": c.open,
                            "high": c.high,
                            "low": c.low,
                            "close": c.close,
                            "volume": c.volume,
                        }
                        for c in rows_1d
                    ]
                )
                click.echo(f"Loaded {len(bars_1d):,} 1d bars")

            # ── Build regime map from stored LLM logs ─────────────────────────
            q_llm = (
                select(LLMLog)
                .where(
                    LLMLog.symbol == sym,
                    LLMLog.parsed_ok.is_(True),
                    LLMLog.ts >= start_dt,
                    LLMLog.ts <= end_dt,
                )
                .order_by(LLMLog.ts)
            )
            llm_rows = (await session.execute(q_llm)).scalars().all()

            from stocktopus.features.models import RegimeAssessment
            regime_map: dict = {}
            for row in llm_rows:
                if row.regime_assessment:
                    try:
                        ra = RegimeAssessment(**row.regime_assessment)
                        regime_map[row.ts.date()] = ra
                    except Exception:  # noqa: BLE001
                        pass

            if not regime_map:
                click.echo(
                    "WARNING: No LLM regime assessments found for this period.\n"
                    "Using a default TRENDING_UP / LONG / confidence=7 assessment for all bars.\n"
                    "Run `stocktopus analyze regime` to populate real assessments.",
                    err=True,
                )
                # Build synthetic regime map so backtest still runs
                cur = start_dt.date()
                end_d = end_dt.date()
                default_ra = RegimeAssessment(
                    regime=Regime.TRENDING_UP,
                    lean=TradeLean.LONG,
                    confidence=7,
                    reasoning="Default synthetic regime for backtest",
                    key_risks=["no llm data"],
                    invalidation="N/A",
                )
                while cur <= end_d:
                    regime_map[cur] = default_ra
                    cur += timedelta(days=1)

        # ── Run backtest ──────────────────────────────────────────────────────
        click.echo(f"\nRunning backtest with {len(regime_map)} regime assessment(s)...")
        runner = BacktestRunner(
            symbol=sym,
            intraday_bars=bars_5m,
            daily_bars=bars_1d,
            regime_map=regime_map,
            friction=friction_model,
            initial_capital=capital,
            position_size_usd=position_size,
        )
        trades, metrics = runner.run()

        # ── Print summary ─────────────────────────────────────────────────────
        click.echo()
        click.echo("=" * 50)
        click.echo(f"  Net Return:    {metrics.total_return_pct:+.2f}%")
        click.echo(f"  Total Trades:  {metrics.total_trades}")
        click.echo(f"  Win Rate:      {metrics.win_rate * 100:.1f}%")
        pf = metrics.profit_factor
        click.echo(f"  Profit Factor: {f'{pf:.2f}' if pf else 'N/A'}")
        click.echo(f"  Expectancy:    ${metrics.expectancy:+.2f} / trade")
        click.echo(f"  Max Drawdown:  -{metrics.max_drawdown_pct:.2f}%")
        sr = metrics.sharpe_ratio
        click.echo(f"  Sharpe Ratio:  {f'{sr:.2f}' if sr else 'N/A'}")
        click.echo(f"  Total Friction:${metrics.total_friction:.2f}")
        click.echo("=" * 50)

        if metrics.regime_breakdown:
            click.echo("\nPer-Regime Breakdown:")
            for regime, data in sorted(metrics.regime_breakdown.items()):
                click.echo(
                    f"  {regime:<20} trades={data['trades']:>3}  "
                    f"wr={data['win_rate']*100:>5.1f}%  "
                    f"pnl=${data['net_pnl']:>+8.2f}"
                )

        # ── Write artifacts ───────────────────────────────────────────────────
        if not no_html:
            run_dir = Path(out_dir) / run_id
            run_dir.mkdir(parents=True, exist_ok=True)

            report_path = run_dir / "report.html"
            equity_values = [capital]
            for t in trades:
                equity_values.append(equity_values[-1] + t.net_pnl)
            render_report(
                metrics=metrics,
                trades=trades,
                equity_curve=equity_values,
                run_id=run_id,
                output_path=report_path,
            )

            metrics_path = run_dir / "metrics.json"
            metrics_path.write_text(json.dumps(metrics.to_dict(), indent=2))

            trades_path = run_dir / "trades.json"
            trades_path.write_text(json.dumps([t.to_dict() for t in trades], indent=2))

            click.echo(f"\nArtifacts written to: {run_dir}/")
            click.echo(f"  Open: {report_path}")

    asyncio.run(_run())


# ── Paper trading ─────────────────────────────────────────────────────────────


@cli.group()
def paper() -> None:
    """Paper trading commands."""


@paper.command("tick")
@click.option("--symbol", default="SPY", show_default=True, help="Ticker symbol")
@click.option(
    "--provider",
    type=click.Choice(["openai", "anthropic"], case_sensitive=False),
    default=None,
)
@click.option("--dry-run", is_flag=True, default=False, help="Log signal but don't place orders")
def paper_tick_cmd(symbol: str, provider: str | None, dry_run: bool) -> None:
    """Run one paper-trading decision tick for a symbol.

    Fetches latest features, gets LLM regime, evaluates strategy and risk filter,
    and places a paper order via Alpaca if conditions are met.

    \b
    Example:
        stocktopus paper tick --symbol SPY
        stocktopus paper tick --symbol SPY --dry-run
    """
    import json

    from stocktopus.broker.alpaca_adapter import AlpacaBrokerAdapter
    from stocktopus.broker.paper_trader import PaperTrader
    from stocktopus.llm.anthropic_provider import AnthropicProvider
    from stocktopus.llm.openai_provider import OpenAIProvider
    from stocktopus.llm.research_director import ResearchDirector

    settings = get_settings()
    active = (provider or settings.active_llm_provider).lower()

    if active == "anthropic":
        if not settings.anthropic_api_key:
            click.echo("ERROR: ANTHROPIC_API_KEY not set", err=True)
            sys.exit(1)
        llm = AnthropicProvider(api_key=settings.anthropic_api_key)
    else:
        if not settings.openai_api_key:
            click.echo("ERROR: OPENAI_API_KEY not set", err=True)
            sys.exit(1)
        llm = OpenAIProvider(api_key=settings.openai_api_key)

    if (not settings.alpaca_api_key or not settings.alpaca_secret_key) and not dry_run:
        click.echo("ERROR: ALPACA_API_KEY / ALPACA_SECRET_KEY not set", err=True)
        sys.exit(1)

    director = ResearchDirector(llm=llm, daily_budget_usd=settings.llm_daily_budget_usd)

    async def _run() -> None:
        from stocktopus.broker.mock_adapter import MockBrokerAdapter

        async with AsyncSessionFactory() as session:
            if dry_run or not settings.alpaca_api_key:
                broker = MockBrokerAdapter()
            else:
                broker = AlpacaBrokerAdapter(
                    api_key=settings.alpaca_api_key,
                    secret_key=settings.alpaca_secret_key,
                    paper=True,
                )

            trader = PaperTrader(
                broker=broker,
                director=director,
                session=session,
                symbol=symbol.upper(),
                max_position_usd=settings.max_position_usd,
                max_daily_loss_usd=settings.max_daily_loss_usd,
                max_trades_per_day=settings.max_trades_per_day,
                dry_run=dry_run,
            )
            result = await trader.tick()

        click.echo(json.dumps(result, indent=2, default=str))

    asyncio.run(_run())


@paper.command("kill")
@click.option("--symbol", default=None, help="Symbol to flatten (default: all)")
@click.option("--yes", is_flag=True, default=False)
def paper_kill_cmd(symbol: str | None, yes: bool) -> None:
    """KILL SWITCH — flatten all open paper positions immediately."""
    from stocktopus.broker.alpaca_adapter import AlpacaBrokerAdapter

    settings = get_settings()
    if not settings.alpaca_api_key:
        click.echo("ERROR: ALPACA_API_KEY not set", err=True)
        sys.exit(1)

    if not yes:
        click.confirm("Flatten ALL paper positions?", abort=True)

    broker = AlpacaBrokerAdapter(
        api_key=settings.alpaca_api_key,
        secret_key=settings.alpaca_secret_key,
        paper=True,
    )

    async def _run() -> None:
        if symbol:
            result = await broker.close_position(symbol.upper())
            if result:
                click.echo(f"Closed {symbol.upper()}: order {result.order_id}")
            else:
                click.echo(f"No open position for {symbol.upper()}")
        else:
            results = await broker.close_all_positions()
            for r in results:
                click.echo(f"Closed {r.symbol}: order {r.order_id}")
            if not results:
                click.echo("No open positions to close.")

    asyncio.run(_run())


@paper.command("status")
def paper_status_cmd() -> None:
    """Show Phase 8 gating progress: trades, regimes covered."""
    from sqlalchemy import text

    async def _run() -> None:
        async with AsyncSessionFactory() as session:
            # Total completed trades
            total = (
                await session.execute(
                    text("SELECT COUNT(*) FROM paper_trades WHERE exit_ts IS NOT NULL")
                )
            ).scalar_one()

            # Regimes covered
            regimes = (
                await session.execute(
                    text(
                        "SELECT regime, COUNT(*) as cnt FROM paper_trades "
                        "WHERE exit_ts IS NOT NULL GROUP BY regime ORDER BY cnt DESC"
                    )
                )
            ).fetchall()

            click.echo("\nPhase 8 Gate Progress")
            click.echo("=" * 40)
            click.echo(f"  Completed trades:  {total:>4} / 100 required")
            click.echo(f"  Regimes covered:   {len(regimes):>4} / 3 required")
            click.echo()
            click.echo(f"{'Regime':<24} {'Trades':>6}")
            click.echo("-" * 32)
            for regime, cnt in regimes:
                click.echo(f"  {regime:<22} {cnt:>6}")
            click.echo()

            if total >= 100 and len(regimes) >= 3:
                click.echo("✅  Phase 8 gate PASSED — ready for Phase 9!")
            else:
                remaining_trades = max(0, 100 - total)
                remaining_regimes = max(0, 3 - len(regimes))
                click.echo(
                    f"⏳  Not ready: need {remaining_trades} more trades, "
                    f"{remaining_regimes} more regime(s)"
                )

    asyncio.run(_run())


@paper.command("drift")
@click.option("--days", default=30, show_default=True, help="Lookback window in calendar days")
@click.option("--min-win-rate", default=0.40, show_default=True)
@click.option("--min-pf", default=1.0, show_default=True, help="Min profit factor")
def paper_drift_cmd(days: int, min_win_rate: float, min_pf: float) -> None:
    """Check live paper trade distribution against alarm thresholds.

    \b
    Example:
        stocktopus paper drift --days 30
        stocktopus paper drift --min-win-rate 0.45 --min-pf 1.2
    """
    from stocktopus.backtest.drift import DriftChecker

    checker = DriftChecker(
        min_win_rate=min_win_rate,
        min_profit_factor=min_pf,
        lookback_days=days,
    )

    async def _run() -> None:
        async with AsyncSessionFactory() as session:
            status = await checker.check(session)
            m = status.live

            click.echo("\nDrift Check")
            click.echo("=" * 44)
            click.echo(f"  Lookback:         {days} days")
            click.echo(f"  Sample trades:    {m.n_trades}")
            click.echo()
            if m.n_trades == 0:
                click.echo("  No completed trades in window.")
            else:
                click.echo(f"  Win rate:         {m.win_rate:.1%}  (threshold ≥{min_win_rate:.1%})")
                click.echo(f"  Profit factor:    {m.profit_factor:.2f}  (threshold ≥{min_pf:.2f})")
                click.echo(f"  Expectancy:       ${m.expectancy:.2f} / trade")
                click.echo(f"  Avg win:          ${m.avg_win:.2f}")
                click.echo(f"  Avg loss:         ${m.avg_loss:.2f}")
                click.echo(f"  Regimes seen:     {', '.join(m.regimes_seen) or 'none'}")
            click.echo()

            if status.alarm_active:
                click.echo(f"🚨  ALARM: {'; '.join(status.alarm_reasons)}")
                click.echo("    Consider pausing new entries until distribution recovers.")
            elif m.n_trades < 10:
                click.echo("⏳  Insufficient data — need ≥10 completed trades.")
            else:
                click.echo("✅  Distribution within acceptable thresholds.")

    asyncio.run(_run())


if __name__ == "__main__":
    main()


# ── live ─────────────────────────────────────────────────────────────────────


@cli.group()
def live() -> None:
    """Phase 9: real-money trading commands (use with extreme caution)."""


@live.command("promote")
@click.option(
    "--confirm-key-1",
    required=True,
    metavar="LIVE",
    help='First confirmation key — type the literal word "LIVE"',
)
@click.option(
    "--confirm-key-2",
    required=True,
    metavar="IUNDERSTAND",
    help='Second confirmation key — type the literal phrase "IUNDERSTAND"',
)
def live_promote_cmd(confirm_key_1: str, confirm_key_2: str) -> None:
    """Promote to LIVE trading mode (Phase 9 gate).

    Requires two explicit confirmation flags and Phase 8 gate clearance.
    This writes TRADING_MODE=live to the .env file — which causes the
    broker adapter to use Alpaca's live endpoint on next startup.

    \b
    Prerequisites:
        - Phase 8 gate cleared (100 completed paper trades, 3+ regimes)
        - Drift alarm must be INACTIVE
        - Alpaca live API credentials must be set

    \b
    Example:
        stocktopus live promote --confirm-key-1 LIVE --confirm-key-2 IUNDERSTAND
    """
    from pathlib import Path

    if confirm_key_1 != "LIVE":
        click.echo('❌  --confirm-key-1 must be exactly "LIVE"', err=True)
        raise SystemExit(1)
    if confirm_key_2 != "IUNDERSTAND":
        click.echo('❌  --confirm-key-2 must be exactly "IUNDERSTAND"', err=True)
        raise SystemExit(1)

    from stocktopus.backtest.drift import DriftChecker

    async def _run() -> None:
        async with AsyncSessionFactory() as session:
            # Phase 8 gate check
            from sqlalchemy import text

            result = await session.execute(
                text(
                    "SELECT COUNT(*) FROM paper_trades WHERE exit_ts IS NOT NULL"
                )
            )
            completed = result.scalar() or 0

            regime_result = await session.execute(
                text(
                    "SELECT COUNT(DISTINCT regime) FROM paper_trades WHERE exit_ts IS NOT NULL"
                )
            )
            regimes = regime_result.scalar() or 0

            if completed < 100:
                click.echo(
                    f"❌  Phase 8 gate not cleared: only {completed}/100 completed trades.",
                    err=True,
                )
                raise SystemExit(1)

            if regimes < 3:
                click.echo(
                    f"❌  Phase 8 gate not cleared: only {regimes}/3 distinct regimes.",
                    err=True,
                )
                raise SystemExit(1)

            # Drift alarm check
            checker = DriftChecker()
            drift_status = await checker.check(session)
            if drift_status.alarm_active:
                click.echo(
                    f"❌  Drift alarm is active: {'; '.join(drift_status.alarm_reasons)}",
                    err=True,
                )
                click.echo("    Resolve distribution issues before going live.", err=True)
                raise SystemExit(1)

        # Write TRADING_MODE=live to .env
        env_path = Path(".env")
        if env_path.exists():
            lines = env_path.read_text().splitlines()
            replaced = False
            new_lines = []
            for line in lines:
                if line.startswith("TRADING_MODE="):
                    new_lines.append("TRADING_MODE=live")
                    replaced = True
                else:
                    new_lines.append(line)
            if not replaced:
                new_lines.append("TRADING_MODE=live")
            env_path.write_text("\n".join(new_lines) + "\n")
        else:
            env_path.write_text("TRADING_MODE=live\n")

        click.echo()
        click.echo("🟢  Trading mode promoted to LIVE.")
        click.echo("    Restart the server to apply. Max position: $50 | Max daily loss: $25.")
        click.echo("    To revert: set TRADING_MODE=paper in .env and restart.")

    asyncio.run(_run())


@live.command("status")
def live_status_cmd() -> None:
    """Show current trading mode and live safety caps."""
    from stocktopus.config import get_settings

    s = get_settings()
    mode = s.trading_mode.upper()
    color = "green" if s.trading_mode == "paper" else "red"
    click.echo()
    click.echo(f"  Trading mode:     {click.style(mode, fg=color, bold=True)}")
    click.echo(f"  Max position:     ${s.max_position_usd:.2f}")
    click.echo(f"  Max daily loss:   ${s.max_daily_loss_usd:.2f}")
    click.echo(f"  Max trades/day:   {s.max_trades_per_day}")
    click.echo(f"  No overnight:     {s.no_overnight_holds}")
    click.echo(f"  No leverage:      {s.no_leverage}")
    click.echo()
