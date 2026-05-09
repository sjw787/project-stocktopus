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
from stocktopus.ingestion.alpaca_market_data import AlpacaMarketData
from stocktopus.ingestion.candle_ingest import backfill
from stocktopus.ingestion.context_ingest import snapshot_market_context
from stocktopus.ingestion.quality import check_candle_quality
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
def backfill_cmd(
    symbol: str,
    from_date: str,
    to_date: str | None,
    timeframe: tuple[str, ...],
    qqq_enabled: bool,
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

    provider = AlpacaMarketData(
        api_key=settings.alpaca_api_key,
        secret_key=settings.alpaca_secret_key,
    )

    async def _run() -> None:
        async with AsyncSessionFactory() as session:
            results = await backfill(
                session,
                provider,
                symbol=symbol.upper(),
                start=start,
                end=end,
                timeframes=list(timeframe),
            )
        for tf, count in results.items():
            click.echo(f"  {tf}: {count} rows inserted")

    click.echo(f"Backfilling {symbol.upper()} from {from_date} to {to_date or 'today'}...")
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


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
