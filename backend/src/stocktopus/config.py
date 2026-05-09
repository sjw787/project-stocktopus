from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    env: str = "development"
    app_name: str = "stocktopus"

    # Database
    database_url: str = "postgresql+asyncpg://stocktopus:stocktopus_dev@localhost:5432/stocktopus"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # LLM Providers
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    active_llm_provider: str = "openai"  # "openai" | "anthropic"

    # Alpaca
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_base_url: str = "https://paper-api.alpaca.markets"
    # Data feed: "iex" for legacy free accounts; "sip" for paid; leave blank to let
    # Alpaca pick the right default for the account type (recommended for new accounts).
    alpaca_data_feed: str = ""

    # News Providers
    finnhub_api_key: str = ""
    newsapi_api_key: str = ""

    # Budget / Cost Controls
    llm_daily_budget_usd: float = 5.00
    data_monthly_budget_usd: float = 50.00

    # Trading Safety Caps (Phase 9)
    max_position_usd: float = 50.0
    max_daily_loss_usd: float = 25.0
    max_trades_per_day: int = 5
    no_overnight_holds: bool = True
    no_leverage: bool = True

    # Universe
    allowed_symbols: list[str] = Field(default=["SPY"])

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def is_test(self) -> bool:
        return self.env == "test"


@lru_cache
def get_settings() -> Settings:
    return Settings()
