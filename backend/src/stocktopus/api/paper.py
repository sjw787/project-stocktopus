"""Paper trading API endpoints.

GET  /api/paper/status  — Phase 8 gate progress (trades, regimes)
POST /api/paper/tick    — Trigger one decision cycle
POST /api/paper/kill    — Flatten all positions (kill switch)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from stocktopus.config import Settings, get_settings
from stocktopus.db.engine import get_session

paper_router = APIRouter(prefix="/api/paper", tags=["paper"])


@paper_router.get("/status")
async def paper_status(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, Any]:
    """Return Phase 8 gating progress plus live P&L summary."""
    total_result = await session.execute(
        text("SELECT COUNT(*) FROM paper_trades WHERE exit_ts IS NOT NULL")
    )
    total: int = total_result.scalar_one()

    regime_result = await session.execute(
        text(
            "SELECT regime, COUNT(*) as cnt FROM paper_trades "
            "WHERE exit_ts IS NOT NULL GROUP BY regime ORDER BY cnt DESC"
        )
    )
    regimes = [{"regime": r, "count": c} for r, c in regime_result.fetchall()]

    open_result = await session.execute(
        text("SELECT COUNT(*) FROM paper_trades WHERE exit_ts IS NULL")
    )
    open_positions: int = open_result.scalar_one()

    pnl_result = await session.execute(
        text(
            "SELECT "
            "  COALESCE(SUM(CASE WHEN exit_ts::date = CURRENT_DATE "
            "    THEN realized_pnl END), 0) AS daily, "
            "  COALESCE(SUM(realized_pnl), 0) AS total "
            "FROM paper_trades WHERE exit_ts IS NOT NULL AND realized_pnl IS NOT NULL"
        )
    )
    pnl_row = pnl_result.fetchone()
    daily_pnl = float(pnl_row[0]) if pnl_row else 0.0
    total_pnl = float(pnl_row[1]) if pnl_row else 0.0

    gate_passed = total >= 100 and len(regimes) >= 3

    return {
        "trades_completed": total,
        "regimes_seen": len(regimes),
        "regimes": regimes,
        "phase8_gate": gate_passed,
        "required_trades": 100,
        "required_regimes": 3,
        "open_positions": open_positions,
        "daily_pnl": daily_pnl,
        "total_pnl": total_pnl,
        "kill_switch_active": False,
    }


@paper_router.post("/tick")
async def paper_tick(
    symbol: str = "SPY",
    dry_run: bool = False,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> dict[str, Any]:
    """Trigger one paper-trading decision cycle.

    Returns the tick result dict with action, reason, thesis (if applicable),
    and order details (if an order was placed).
    """
    from stocktopus.broker.alpaca_adapter import AlpacaBrokerAdapter
    from stocktopus.broker.mock_adapter import MockBrokerAdapter
    from stocktopus.broker.paper_trader import PaperTrader
    from stocktopus.llm.anthropic_provider import AnthropicProvider
    from stocktopus.llm.openai_provider import OpenAIProvider
    from stocktopus.llm.research_director import ResearchDirector

    active = (settings.active_llm_provider or "openai").lower()
    if active == "anthropic" and settings.anthropic_api_key:
        llm = AnthropicProvider(api_key=settings.anthropic_api_key)
    elif settings.openai_api_key:
        llm = OpenAIProvider(api_key=settings.openai_api_key)
    else:
        raise HTTPException(status_code=503, detail="No LLM provider configured")

    director = ResearchDirector(llm=llm, daily_budget_usd=settings.llm_daily_budget_usd)

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

    return await trader.tick()


@paper_router.get("/drift")
async def paper_drift(
    days: int = 30,
    min_win_rate: float = 0.40,
    min_pf: float = 1.0,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, Any]:
    """Check live paper trade distribution against alarm thresholds."""
    from stocktopus.backtest.drift import DriftChecker

    checker = DriftChecker(
        min_win_rate=min_win_rate,
        min_profit_factor=min_pf,
        lookback_days=days,
    )
    status = await checker.check(session)
    m = status.live

    return {
        "checked_at": status.checked_at.isoformat(),
        "alarm_active": status.alarm_active,
        "alarm_reasons": status.alarm_reasons,
        "n_trades": m.n_trades,
        "win_rate": round(m.win_rate, 4),
        "avg_win": round(m.avg_win, 4),
        "avg_loss": round(m.avg_loss, 4),
        "profit_factor": round(m.profit_factor, 4) if m.profit_factor != float("inf") else None,
        "expectancy": round(m.expectancy, 4),
        "regimes_seen": m.regimes_seen,
        "thresholds": {
            "min_win_rate": min_win_rate,
            "min_profit_factor": min_pf,
            "lookback_days": days,
        },
    }


@paper_router.post("/kill")
async def paper_kill(
    symbol: str | None = None,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> dict[str, Any]:
    """Kill switch: flatten all paper positions (or a single symbol).

    Closes open paper_trades records in the DB (covers dry-run trades) and,
    if Alpaca credentials are present, also closes any live broker positions.
    """
    from datetime import UTC, datetime

    from sqlalchemy import select

    from stocktopus.db.models import PaperTrade

    now = datetime.now(UTC)

    # ── 1. Close open DB records ──────────────────────────────────────────────
    q = select(PaperTrade).where(PaperTrade.exit_ts.is_(None))
    if symbol:
        q = q.where(PaperTrade.symbol == symbol.upper())
    open_trades = (await session.execute(q)).scalars().all()

    db_closed = []
    for trade in open_trades:
        trade.exit_ts = now
        trade.exit_price = trade.entry_price  # use entry as exit (no live price at kill time)
        trade.realized_pnl = 0.0
        db_closed.append({"id": str(trade.id), "symbol": trade.symbol})

    if open_trades:
        await session.commit()

    # ── 2. Close Alpaca broker positions (live/paper brokerage) ───────────────
    broker_closed: list[dict[str, str]] = []
    if settings.alpaca_api_key and settings.alpaca_secret_key:
        from stocktopus.broker.alpaca_adapter import AlpacaBrokerAdapter

        broker = AlpacaBrokerAdapter(
            api_key=settings.alpaca_api_key,
            secret_key=settings.alpaca_secret_key,
            paper=True,
        )
        if symbol:
            result = await broker.close_position(symbol.upper())
            if result:
                broker_closed.append({"symbol": result.symbol, "order_id": result.order_id})
        else:
            results = await broker.close_all_positions()
            broker_closed = [{"symbol": r.symbol, "order_id": r.order_id} for r in results]

    return {
        "db_closed": db_closed,
        "broker_closed": broker_closed,
        "count": len(db_closed) + len(broker_closed),
    }


@paper_router.get("/trades")
async def paper_trades(
    limit: int = 50,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[dict[str, Any]]:
    """Return recent paper trade journal entries."""
    from sqlalchemy import desc, select

    from stocktopus.db.models import PaperTrade

    q = (
        select(PaperTrade)
        .order_by(desc(PaperTrade.entry_ts))
        .limit(limit)
    )
    rows = (await session.execute(q)).scalars().all()
    return [
        {
            "id": r.id,
            "symbol": r.symbol,
            "direction": r.direction,
            "qty": r.qty,
            "entry_price": r.entry_price,
            "exit_price": r.exit_price,
            "realized_pnl": float(r.realized_pnl) if r.realized_pnl is not None else None,
            "regime": r.regime,
            "entry_ts": r.entry_ts.isoformat(),
            "exit_ts": r.exit_ts.isoformat() if r.exit_ts else None,
            "status": "closed" if r.exit_ts else "open",
        }
        for r in rows
    ]
