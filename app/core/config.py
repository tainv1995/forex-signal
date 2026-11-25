from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.enums import MarketDataProviderType, StrategyName
from app.core.strategy_weights import DEFAULT_STRATEGY_WEIGHTS


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"

    symbol: str = "XAUUSD"
    signal_id_prefix: str = "GOLD"

    database_url: str = "postgresql+asyncpg://gold:gold@localhost:5432/goldbot"
    redis_url: str = "redis://localhost:6379/0"

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_admin_user_ids: str = ""
    telegram_show_metadata: bool = True
    telegram_enabled: bool = True
    telegram_symbol_label: str = "GOLD"
    telegram_max_retries: int = 3
    telegram_poll_timeout_seconds: int = 30

    report_time: str = "23:55"
    report_timezone: str = "Asia/Ho_Chi_Minh"

    watch_signal_confidence: float = 0.68
    min_signal_confidence: float = 0.75
    strong_signal_confidence: float = 0.82
    very_strong_signal_confidence: float = 0.90
    reversal_signal_confidence: float = 0.82
    invalidation_confidence_floor: float = 0.35

    min_method_agreement: float = 0.5
    strong_method_agreement: float = 0.7

    signal_cooldown_minutes: int = 20
    max_signals_per_hour: int = 3

    min_rr: float = 1.5

    primary_timeframe: str = "M15"
    analysis_interval_seconds: int = 60
    tracking_interval_seconds: int = 15
    entry_max_chase_atr_mult: float = 1.3
    entry_expiry_minutes: int = 120

    strategy_weights: dict[StrategyName, float] = Field(
        default_factory=lambda: dict(DEFAULT_STRATEGY_WEIGHTS)
    )

    market_data_provider: MarketDataProviderType = MarketDataProviderType.MOCK
    tradingview_symbol: str = "OANDA:XAUUSD"
    tradingview_webhook_secret: str = ""

    mock_base_price: float = 2650.0

    oanda_api_key: str = ""
    oanda_account_id: str = ""
    oanda_environment: str = "practice"
    oanda_instrument: str = "XAU_USD"

    twelvedata_api_key: str = ""
    twelvedata_symbol: str = "XAU/USD"

    paper_mode: bool = True
    signal_generation_enabled: bool = True

    log_level: str = "INFO"
    log_json: bool = False

    @property
    def telegram_admin_ids(self) -> list[int]:
        return [int(uid.strip()) for uid in self.telegram_admin_user_ids.split(",") if uid.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
