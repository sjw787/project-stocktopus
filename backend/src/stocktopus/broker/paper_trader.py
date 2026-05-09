"""Paper (and live) trading execution engine.

The PaperTrader orchestrates the full decision cycle:
  1. Fetch latest features from DB (or compute fresh)
  2. Get LLM regime assessment
  3. Run the strategy
  4. Run the risk filter
  5. If approved — place order, record in trade journal (paper_trades)
  6. Monitor open position for stop/take-profit, EOD exit

Designed to be called once per bar (e.g., every 5 minutes via the scheduler)
from the CLI or an APScheduler job.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from loguru import logger
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from stocktopus.broker.base import BrokerAdapter, OrderRequest, OrderSide
from stocktopus.config import get_settings
from stocktopus.db.models import FeatureSnapshot, PaperTrade, TradeRejection
from stocktopus.features.models import FeatureVector, RegimeAssessment
from stocktopus.llm.research_director import ResearchDirector
from stocktopus.risk.filter import FilterResult, RiskFilter
from stocktopus.strategies.base import StrategyContext
from stocktopus.strategies.opening_momentum import OpeningMomentumStrategy


class PaperTrader:
    """Orchestrates a single paper-trading decision cycle for one symbol.

    Parameters
    ----------
    broker:
        A BrokerAdapter (AlpacaBrokerAdapter in paper mode, or MockBrokerAdapter in tests).
    director:
        A configured ResearchDirector (LLM layer).
    session:
        An open async SQLAlchemy session.
    symbol:
        Ticker to trade (e.g. "SPY").
    max_position_usd:
        Maximum notional per open trade.
    """

    def __init__(
        self,
        broker: BrokerAdapter,
        director: ResearchDirector,
        session: AsyncSession,
        symbol: str = "SPY",
        max_position_usd: float = 50.0,
        max_daily_loss_usd: float = 25.0,
        max_trades_per_day: int = 5,
        dry_run: bool = False,
    ) -> None:
        self._broker = broker
        self._director = director
        self._session = session
        self._symbol = symbol.upper()
        self._dry_run = dry_run
        self._strategy = OpeningMomentumStrategy()
        self._risk = RiskFilter.from_settings(
            max_position_usd=max_position_usd,
            max_daily_loss_usd=max_daily_loss_usd,
            max_trades_per_day=max_trades_per_day,
        )

    async def _latest_features(self) -> FeatureVector | None:
        """Load the most recent feature snapshot for the symbol."""
        q = (
            select(FeatureSnapshot)
            .where(FeatureSnapshot.symbol == self._symbol)
            .order_by(desc(FeatureSnapshot.ts))
            .limit(1)
        )
        row = (await self._session.execute(q)).scalar_one_or_none()
        if row is None:
            return None
        return FeatureVector(**row.features)

    async def _get_open_position_qty(self) -> float:
        """Get current open qty from broker."""
        try:
            pos = await self._broker.get_position(self._symbol)
            return pos.qty if pos else 0.0
        except Exception:  # noqa: BLE001
            return 0.0

    async def _count_trades_today(self) -> int:
        """Count filled paper trades for today."""
        from sqlalchemy import text

        today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        result = await self._session.execute(
            text(
                "SELECT COUNT(*) FROM paper_trades WHERE symbol = :sym AND entry_ts >= :today"
            ),
            {"sym": self._symbol, "today": today_start},
        )
        return int(result.scalar_one() or 0)

    async def _daily_realized_pnl(self) -> float:
        """Sum today's realized P&L from paper_trades."""
        from sqlalchemy import text

        today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        result = await self._session.execute(
            text(
                "SELECT COALESCE(SUM(realized_pnl), 0) FROM paper_trades "
                "WHERE symbol = :sym AND exit_ts >= :today"
            ),
            {"sym": self._symbol, "today": today_start},
        )
        return float(result.scalar_one() or 0.0)

    async def _persist_rejection(self, ctx: StrategyContext, fr: FilterResult) -> None:
        """Write a TradeRejection audit record."""
        if fr.approved or not fr.rejections:
            return
        first = fr.rejections[0]
        rej = TradeRejection(
            id=str(uuid.uuid4()),
            ts=ctx.ts,
            symbol=self._symbol,
            strategy_name=self._strategy.name,
            strategy_version=self._strategy.version,
            check_name=first.check_name,
            reason=first.reason,
            check_results=[r.model_dump() for r in fr.results],
        )
        self._session.add(rej)
        await self._session.commit()

    async def _persist_trade_entry(
        self,
        ctx: StrategyContext,
        thesis: Any,
        order_id: str | None,
        regime: RegimeAssessment,
    ) -> str:
        """Persist a PaperTrade entry record. Returns the new trade ID."""
        trade_id = str(uuid.uuid4())
        trade = PaperTrade(
            id=trade_id,
            symbol=self._symbol,
            is_paper=self._broker.is_paper,
            entry_ts=ctx.ts,
            entry_price=thesis.entry_price,
            qty=max(1.0, float(int(get_settings().max_position_usd / thesis.entry_price))),
            direction=thesis.direction,
            stop_loss=thesis.stop_loss,
            take_profit=thesis.take_profit,
            entry_order_id=order_id,
            regime=regime.regime.value if hasattr(regime.regime, "value") else str(regime.regime),
            lean=regime.lean.value if hasattr(regime.lean, "value") else str(regime.lean),
            llm_confidence=regime.confidence,
            strategy_name=self._strategy.name,
            strategy_version=self._strategy.version,
            rationale=thesis.rationale if hasattr(thesis, "rationale") else None,
        )
        self._session.add(trade)
        await self._session.commit()
        logger.info("PaperTrade entry persisted", trade_id=trade_id)
        return trade_id

    async def tick(self) -> dict[str, Any]:
        """Run one decision cycle. Returns a status dict for logging/API."""
        ts = datetime.now(UTC)
        result: dict[str, Any] = {
            "ts": ts.isoformat(),
            "symbol": self._symbol,
            "action": "no_op",
            "reason": None,
        }

        # 1. Features
        fv = await self._latest_features()
        if fv is None:
            result["reason"] = "no_feature_snapshot"
            logger.warning("No feature snapshot — skipping tick", symbol=self._symbol)
            return result

        # 2. LLM regime
        try:
            regime: RegimeAssessment = await self._director.analyze(
                self._session, symbol=self._symbol
            )
        except RuntimeError as exc:
            result["reason"] = str(exc)
            logger.warning("LLM budget exceeded or error", error=str(exc))
            return result

        # 3. Current state
        open_qty = await self._get_open_position_qty()
        trades_today = await self._count_trades_today()
        daily_pnl = await self._daily_realized_pnl()

        ctx = StrategyContext(
            symbol=self._symbol,
            ts=ts,
            features=fv,
            regime=regime,
            open_position_qty=open_qty,
            daily_realized_pnl=daily_pnl,
            trades_today=trades_today,
        )

        # 4. Strategy signal
        thesis = self._strategy.evaluate(ctx)
        if thesis is None:
            result["reason"] = "no_strategy_signal"
            return result

        result["thesis"] = {
            "direction": thesis.direction,
            "entry": thesis.entry_price,
            "stop": thesis.stop_loss,
            "tp": thesis.take_profit,
        }

        # 5. Risk filter
        fr = self._risk.evaluate(ctx, thesis)
        if not fr.approved:
            await self._persist_rejection(ctx, fr)
            result["action"] = "rejected"
            result["reason"] = fr.rejections[0].reason if fr.rejections else "risk_blocked"
            return result

        # 6. Place order
        settings = get_settings()
        qty = max(1, int(settings.max_position_usd / thesis.entry_price))
        order_req = OrderRequest(
            symbol=self._symbol,
            side=OrderSide.BUY,
            qty=float(qty),
            client_order_id=str(uuid.uuid4()),
        )

        if self._dry_run:
            result["action"] = "dry_run_entry"
            result["qty"] = qty
            await self._persist_trade_entry(ctx, thesis, None, regime)
            logger.info("DRY RUN — would place order", symbol=self._symbol, qty=qty)
        else:
            order = await self._broker.place_order(order_req)
            trade_id = await self._persist_trade_entry(ctx, thesis, order.order_id, regime)
            result["action"] = "entry_placed"
            result["order_id"] = order.order_id
            result["trade_id"] = trade_id
            result["status"] = order.status
            logger.info(
                "Order placed",
                symbol=self._symbol,
                qty=qty,
                order_id=order.order_id,
                status=order.status,
            )

        return result

    async def kill_switch(self) -> list[str]:
        """Flatten all positions immediately. Returns list of order IDs placed."""
        logger.warning("KILL SWITCH ACTIVATED — closing all positions", symbol=self._symbol)
        results = await self._broker.close_all_positions()
        order_ids = [r.order_id for r in results]
        logger.warning("Kill switch complete", orders=order_ids)
        return order_ids

