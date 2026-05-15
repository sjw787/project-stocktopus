"""Research Director — orchestrates LLM-based regime assessment for a symbol.

Flow:
  1. Load latest FeatureSnapshot from DB (or use supplied FeatureVector).
  2. Optionally gather recent news headlines from news_events.
  3. Optionally include tax context (wash-sale, STCG/LTCG) if trade_lots exist.
  4. Render the versioned prompt template.
  5. Call LLM, parse JSON → RegimeAssessment, retry up to MAX_RETRIES on bad output.
  6. Track cost against daily budget circuit breaker.
  7. Persist LLMLog to DB for replay and audit.

The caller decides which LLMProvider to inject (OpenAI or Anthropic); this module
is provider-agnostic.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from stocktopus.db.models import FeatureSnapshot, LLMLog, NewsEvent, TradeLot
from stocktopus.features.models import FeatureVector, RegimeAssessment
from stocktopus.providers.llm import LLMMessage, LLMProvider

if TYPE_CHECKING:
    pass

MAX_RETRIES = 3
PROMPT_VERSION = "v1"


def _load_prompt_template() -> str:
    path = Path(__file__).resolve()
    # Local layout:  .../backend/src/stocktopus/llm/research_director.py
    #   parents[3] = .../backend/  →  backend/prompts/research_director/v1.md
    # Lambda layout: /var/task/stocktopus/llm/research_director.py
    #   parents[2] = /var/task/        →  /var/task/prompts/research_director/v1.md
    for depth in (3, 2, 4):
        candidate = path.parents[depth] / "prompts" / "research_director" / "v1.md"
        if candidate.exists():
            return candidate.read_text()
    raise FileNotFoundError(
        f"prompt template not found; tried parents[2..4] of {path}"
    )


_PROMPT_TEMPLATE = _load_prompt_template()


def _strip_json_fences(text: str) -> str:
    """Remove markdown code fences if the model wrapped its JSON output."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _parse_regime_assessment(raw: str) -> RegimeAssessment:
    """Parse and validate raw JSON string into a RegimeAssessment."""
    cleaned = _strip_json_fences(raw)
    data = json.loads(cleaned)
    return RegimeAssessment(**data)


async def _get_daily_cost(session: AsyncSession) -> float:
    """Sum LLM costs for today from llm_logs."""
    today_start = datetime.now(tz=UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    result = await session.execute(
        select(func.coalesce(func.sum(LLMLog.cost_usd), 0.0)).where(
            LLMLog.ts >= today_start
        )
    )
    return float(result.scalar_one())


async def _get_news_summary(session: AsyncSession, hours: int = 4) -> str:
    """Return a bullet-list of recent news headlines."""
    cutoff = datetime.now(tz=UTC) - timedelta(hours=hours)
    rows = (
        await session.execute(
            select(NewsEvent.headline, NewsEvent.published_at, NewsEvent.categories)
            .where(NewsEvent.published_at >= cutoff)
            .order_by(NewsEvent.published_at.desc())
            .limit(10)
        )
    ).all()

    if not rows:
        return "No recent news available."

    lines = []
    for headline, pub_at, categories in rows:
        cats = ", ".join(categories) if categories else ""
        time_str = pub_at.strftime("%H:%M ET") if pub_at else ""
        tag = f" [{cats}]" if cats else ""
        lines.append(f"- {time_str}{tag} {headline}")
    return "\n".join(lines)


async def _get_tax_context(session: AsyncSession, symbol: str) -> str:
    """Return a brief tax-awareness note based on open lots."""
    rows = (
        await session.execute(
            select(TradeLot)
            .where(TradeLot.symbol == symbol, TradeLot.exit_date.is_(None))
            .order_by(TradeLot.entry_date.asc())
            .limit(5)
        )
    ).scalars().all()

    if not rows:
        return "No open lots. No wash-sale or STCG concerns."

    now = datetime.now(tz=UTC)
    lines = ["Open lots:"]
    for lot in rows:
        days_held = (now - lot.entry_date).days if lot.entry_date else 0
        status = "LTCG-eligible" if days_held >= 365 else f"STCG ({days_held}d held)"
        lines.append(f"  - {lot.qty} shares @ ${lot.cost_basis:.2f} [{status}]")

    # Wash-sale warning: recently closed lots within 30 days
    wash_cutoff = now - timedelta(days=30)
    recent_losses = (
        await session.execute(
            select(func.count()).where(
                TradeLot.symbol == symbol,
                TradeLot.exit_date >= wash_cutoff,
                TradeLot.realized_pnl < 0,
            )
        )
    ).scalar_one()

    if recent_losses:
        lines.append(
            f"⚠ Wash-sale risk: {recent_losses} loss(es) closed in the last 30 days. "
            f"A new {symbol} purchase within 30 days of a loss would trigger wash-sale rules."
        )

    return "\n".join(lines)


class ResearchDirector:
    """Orchestrates LLM-based regime assessment for a symbol.

    Usage::

        provider = OpenAIProvider(api_key=settings.openai_api_key)
        director = ResearchDirector(provider, daily_budget_usd=5.0)
        assessment = await director.analyze(session, symbol="SPY")
    """

    def __init__(
        self,
        llm: LLMProvider,
        daily_budget_usd: float = 5.0,
        model: str | None = None,
    ) -> None:
        self._llm = llm
        self._daily_budget = daily_budget_usd
        self._model = model

    async def analyze(
        self,
        session: AsyncSession,
        symbol: str,
        feature_snapshot_id: str | None = None,
    ) -> RegimeAssessment:
        """Run a full LLM regime analysis for symbol.

        Args:
            session: Active async DB session.
            symbol: Ticker symbol (e.g., "SPY").
            feature_snapshot_id: Optional specific snapshot UUID. If None, uses latest.

        Returns:
            Validated RegimeAssessment.

        Raises:
            RuntimeError: If daily budget exceeded or all retries exhausted.
        """
        # ── Budget guard ──────────────────────────────────────────────────────
        daily_cost = await _get_daily_cost(session)
        if daily_cost >= self._daily_budget:
            raise RuntimeError(
                f"Daily LLM budget of ${self._daily_budget:.2f} exceeded "
                f"(spent ${daily_cost:.2f} today). No further calls allowed."
            )

        # ── Load feature snapshot ─────────────────────────────────────────────
        if feature_snapshot_id:
            snap = (
                await session.execute(
                    select(FeatureSnapshot).where(FeatureSnapshot.id == feature_snapshot_id)
                )
            ).scalar_one_or_none()
        else:
            snap = (
                await session.execute(
                    select(FeatureSnapshot)
                    .where(FeatureSnapshot.symbol == symbol.upper())
                    .order_by(FeatureSnapshot.ts.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

        if snap is None:
            raise RuntimeError(
                f"No feature snapshot found for {symbol}. "
                "Run `stocktopus features compute --symbol {symbol}` first."
            )

        fv_data = {k: v for k, v in snap.features.items() if k not in ("symbol", "ts")}
        fv = FeatureVector(**fv_data, symbol=symbol, ts=snap.ts)

        # ── Context gathering ─────────────────────────────────────────────────
        news_summary = await _get_news_summary(session)
        tax_context = await _get_tax_context(session, symbol)

        now_et = datetime.now(UTC)  # simplified — treat UTC as close enough for now
        market_status = "open" if 13 <= now_et.hour < 20 else "closed"

        # ── Render prompt ─────────────────────────────────────────────────────
        features_json = json.dumps(fv.model_dump(mode="json"), indent=2)
        user_prompt = _PROMPT_TEMPLATE.format(
            features_json=features_json,
            news_summary=news_summary,
            tax_context=tax_context,
            current_time_et=now_et.strftime("%Y-%m-%d %H:%M"),
            market_status=market_status,
        )

        messages = [LLMMessage(role="user", content=user_prompt)]

        # ── LLM call with retry ───────────────────────────────────────────────
        assessment: RegimeAssessment | None = None
        last_error: str = ""
        raw_response: str = ""
        llm_response = None

        for attempt in range(1, MAX_RETRIES + 1):
            logger.debug(
                "Calling LLM for regime assessment",
                symbol=symbol,
                attempt=attempt,
                snapshot_id=snap.id,
            )
            try:
                llm_response = await self._llm.complete(
                    messages=messages,
                    model=self._model,
                    response_schema=RegimeAssessment.model_json_schema(),
                    temperature=0.2,
                )
                raw_response = llm_response.content
                assessment = _parse_regime_assessment(raw_response)
                break
            except (json.JSONDecodeError, ValidationError, KeyError) as exc:
                last_error = str(exc)
                logger.warning(
                    "LLM returned malformed JSON",
                    attempt=attempt,
                    error=last_error,
                    raw=raw_response[:200],
                )
                # Append correction request for next attempt.
                messages = [
                    LLMMessage(role="user", content=user_prompt),
                    LLMMessage(role="assistant", content=raw_response),
                    LLMMessage(
                        role="user",
                        content=(
                            f"Your previous response was not valid JSON conforming to the schema. "
                            f"Error: {last_error}. Please respond with valid JSON only."
                        ),
                    ),
                ]

        # ── Persist LLM log ───────────────────────────────────────────────────
        parsed_ok = assessment is not None
        log_entry = LLMLog(
            ts=datetime.now(tz=UTC),
            symbol=symbol.upper(),
            prompt_version=PROMPT_VERSION,
            model=llm_response.model if llm_response else "",
            user_prompt=user_prompt,
            raw_response=raw_response,
            parsed_ok=parsed_ok,
            regime_assessment=assessment.model_dump(mode="json") if assessment else None,
            feature_snapshot_id=snap.id,
            prompt_tokens=llm_response.prompt_tokens if llm_response else 0,
            completion_tokens=llm_response.completion_tokens if llm_response else 0,
            cost_usd=llm_response.cost_usd if llm_response else 0.0,
            latency_ms=llm_response.latency_ms if llm_response else 0,
            retry_count=MAX_RETRIES if not parsed_ok else 0,
        )
        session.add(log_entry)
        await session.commit()

        if not parsed_ok:
            raise RuntimeError(
                f"LLM failed to return a valid RegimeAssessment after {MAX_RETRIES} attempts. "
                f"Last error: {last_error}"
            )

        # Populate audit metadata from llm_response.
        assert assessment is not None
        assessment.prompt_version = PROMPT_VERSION
        assessment.model_used = llm_response.model  # type: ignore[union-attr]
        assessment.input_tokens = llm_response.prompt_tokens  # type: ignore[union-attr]
        assessment.output_tokens = llm_response.completion_tokens  # type: ignore[union-attr]
        assessment.latency_ms = llm_response.latency_ms  # type: ignore[union-attr]

        logger.info(
            "Regime assessment complete",
            symbol=symbol,
            regime=assessment.regime,
            lean=assessment.lean,
            confidence=assessment.confidence,
            cost_usd=llm_response.cost_usd,  # type: ignore[union-attr]
        )
        return assessment
