"""Application settings validated with Pydantic Settings."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Immutable application settings loaded from environment or .env file."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "barometr-ai"
    app_version: str = "0.1.0"
    app_env: str = Field(default="development", description="development | staging | production")
    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)

    # Modele i wersje
    embedding_model_name: str = Field(default="sdadas/mmlw-retrieval-roberta-large")
    embedding_dimension: int = Field(default=1024)
    model_version: str = Field(default="v1.0.0")
    prompt_version: str = Field(default="v1.0.0")

    # Budżet i limity
    daily_token_budget: int = Field(default=1_000_000)
    cost_alert_threshold: float = Field(default=0.8)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached singleton for application settings."""
    return Settings()
