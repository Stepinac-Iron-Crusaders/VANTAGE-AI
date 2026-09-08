from functools import lru_cache
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "vantage-frc"
    environment: str = "development"
    debug: bool = True
    log_level: str = "INFO"

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/vantage",
        description="PostgreSQL async connection URL",
    )
    database_pool_size: int = 20
    database_max_overflow: int = 10

    # Redis
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL for caching and pub/sub",
    )

    # The Blue Alliance API
    tba_api_key: Optional[str] = Field(default=None, description="TBA API key")
    tba_base_url: str = "https://www.thebluealliance.com/api/v3"
    tba_rate_limit: int = 10  # requests per second

    # Statbotics API
    statbotics_base_url: str = "https://api.statbotics.io/v3"
    statbotics_rate_limit: int = 5  # requests per second

    # Google Gemini API
    gemini_api_key: Optional[str] = Field(default=None, description="Gemini API key")
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_model: str = "gemini-3.6-flash"
    gemini_temperature: float = 0.2
    gemini_max_tokens: int = 8192

    # Data Pipeline
    pipeline_batch_size: int = 100
    pipeline_max_retries: int = 3
    pipeline_retry_delay: float = 1.0
    historical_seasons: list[int] = Field(
        default_factory=lambda: [2022, 2023, 2024, 2025],
        description="Seasons to ingest for historical data",
    )

    # Scouting
    scouting_max_concurrent_matches: int = 4
    scouting_gpu_memory_fraction: float = 0.8

    # Manager/Strategy
    manager_model: str = "gpt-4o"
    manager_temperature: float = 0.1
    manager_max_tokens: int = 4000


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()