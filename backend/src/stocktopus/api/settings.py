"""Read-only settings endpoint — exposes non-sensitive runtime configuration.

GET  /api/settings  → Returns trading mode, LLM provider/model, budget caps, risk limits, etc.
PATCH /api/settings → Updates editable fields, persists to the appropriate settings store
                      (.env for local dev, DynamoDB for Lambda/production).

Never exposes API keys, DB URLs, or other secrets.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from stocktopus.config import Settings, get_settings
from stocktopus.settings_store import (
    ScheduleFlagsRepository,
    get_settings_repository,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])
admin_router = APIRouter(prefix="/api/admin", tags=["admin"])

# Models available per provider (kept in sync with llm/provider files)
OPENAI_MODELS = [
    "gpt-5-mini",
    "gpt-5.4-nano-2026-03-17",
    "gpt-5.2-pro",
    "gpt-5.4-pro",
    "gpt-5.5",
    "gpt-5.5-2026-04-23",
]
ANTHROPIC_MODELS = [
    "claude-3-5-haiku-20241022",
    "claude-3-5-sonnet-20241022",
    "claude-3-opus-20240229",
    "claude-3-haiku-20240307",
]


# ── Response / request schemas ─────────────────────────────────────────────────


class AppSettingsOut(BaseModel):
    trading_mode: str
    active_llm_provider: str
    llm_model: str
    llm_daily_budget_usd: float
    max_position_usd: float
    max_daily_loss_usd: float
    max_trades_per_day: int
    clock_offset_hours: int
    allowed_symbols: list[str]
    no_overnight_holds: bool
    no_leverage: bool
    openai_models: list[str]
    anthropic_models: list[str]


class AppSettingsUpdate(BaseModel):
    active_llm_provider: str | None = None
    llm_model: str | None = None
    llm_daily_budget_usd: float | None = None
    max_position_usd: float | None = None
    max_daily_loss_usd: float | None = None
    max_trades_per_day: int | None = None
    clock_offset_hours: int | None = None


class ScheduleFlagsOut(BaseModel):
    ingestion: bool
    paper: bool


class ScheduleFlagsUpdate(BaseModel):
    ingestion: bool | None = None
    paper: bool | None = None


# ── Helpers ────────────────────────────────────────────────────────────────────


def _settings_to_out(s: Settings) -> AppSettingsOut:
    return AppSettingsOut(
        trading_mode=s.trading_mode,
        active_llm_provider=s.active_llm_provider,
        llm_model=s.llm_model,
        llm_daily_budget_usd=s.llm_daily_budget_usd,
        max_position_usd=s.max_position_usd,
        max_daily_loss_usd=s.max_daily_loss_usd,
        max_trades_per_day=s.max_trades_per_day,
        clock_offset_hours=s.clock_offset_hours,
        allowed_symbols=s.allowed_symbols,
        no_overnight_holds=s.no_overnight_holds,
        no_leverage=s.no_leverage,
        openai_models=OPENAI_MODELS,
        anthropic_models=ANTHROPIC_MODELS,
    )


# ── Settings endpoints ─────────────────────────────────────────────────────────


@router.get("", response_model=AppSettingsOut)
async def get_app_settings(
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> AppSettingsOut:
    """Return current non-sensitive runtime settings."""
    return _settings_to_out(settings)


@router.patch("", response_model=AppSettingsOut)
async def update_app_settings(
    body: AppSettingsUpdate,
) -> AppSettingsOut:
    """Persist editable settings and reload the settings cache."""
    repo = get_settings_repository()
    store_updates: dict[str, str] = {}

    if body.active_llm_provider is not None:
        allowed = {"openai", "anthropic"}
        if body.active_llm_provider.lower() not in allowed:
            raise HTTPException(status_code=422, detail=f"active_llm_provider must be one of {allowed}")
        store_updates["ACTIVE_LLM_PROVIDER"] = body.active_llm_provider.lower()

    if body.llm_model is not None:
        store_updates["LLM_MODEL"] = body.llm_model

    if body.llm_daily_budget_usd is not None:
        if body.llm_daily_budget_usd < 0:
            raise HTTPException(status_code=422, detail="llm_daily_budget_usd must be >= 0")
        store_updates["LLM_DAILY_BUDGET_USD"] = str(body.llm_daily_budget_usd)

    if body.max_position_usd is not None:
        if body.max_position_usd <= 0:
            raise HTTPException(status_code=422, detail="max_position_usd must be > 0")
        store_updates["MAX_POSITION_USD"] = str(body.max_position_usd)

    if body.max_daily_loss_usd is not None:
        if body.max_daily_loss_usd <= 0:
            raise HTTPException(status_code=422, detail="max_daily_loss_usd must be > 0")
        store_updates["MAX_DAILY_LOSS_USD"] = str(body.max_daily_loss_usd)

    if body.max_trades_per_day is not None:
        if body.max_trades_per_day < 1:
            raise HTTPException(status_code=422, detail="max_trades_per_day must be >= 1")
        store_updates["MAX_TRADES_PER_DAY"] = str(body.max_trades_per_day)

    if body.clock_offset_hours is not None:
        store_updates["CLOCK_OFFSET_HOURS"] = str(body.clock_offset_hours)

    for key, value in store_updates.items():
        await repo.set(key, value)

    get_settings.cache_clear()
    return _settings_to_out(get_settings())


# ── Admin schedule-flag endpoints ──────────────────────────────────────────────


@admin_router.get("/schedules", response_model=ScheduleFlagsOut)
async def get_schedule_flags() -> ScheduleFlagsOut:
    """Return current enabled/disabled state of scheduled EventBridge tasks."""
    flags_repo = ScheduleFlagsRepository()
    flags = await flags_repo.get_all()
    return ScheduleFlagsOut(
        ingestion=flags.get("ingestion", True),
        paper=flags.get("paper", True),
    )


@admin_router.put("/schedules", response_model=ScheduleFlagsOut)
async def update_schedule_flags(body: ScheduleFlagsUpdate) -> ScheduleFlagsOut:
    """Enable or disable scheduled EventBridge tasks without redeploying."""
    flags_repo = ScheduleFlagsRepository()

    if body.ingestion is not None:
        await flags_repo.set("ingestion", body.ingestion)
    if body.paper is not None:
        await flags_repo.set("paper", body.paper)

    flags = await flags_repo.get_all()
    return ScheduleFlagsOut(
        ingestion=flags.get("ingestion", True),
        paper=flags.get("paper", True),
    )
