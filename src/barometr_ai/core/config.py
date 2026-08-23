"""Application settings validated with Pydantic Settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Rodziny modeli embeddingowych wymagające prefiksów instrukcyjnych na wejściu.
# Pominięcie prefiksu w modelach E5 mierzalnie pogarsza jakość wyszukiwania.
E5_MODEL_MARKERS = ("e5-",)


class Settings(BaseSettings):
    """Immutable application settings loaded from environment or .env file.

    `extra="forbid"` jest świadomą decyzją: nieznana zmienna środowiskowa ma wywrócić start
    serwisu, a nie zniknąć po cichu. Klucz API wpisany pod błędną nazwą to awaria, którą
    trzeba zobaczyć przy deployu, a nie przy pierwszym wywołaniu modelu.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
        case_sensitive=False,
        frozen=True,
    )

    app_name: str = "barometr-ai"
    app_version: str = "0.1.0"
    app_env: Literal["development", "staging", "production"] = "development"
    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000, ge=1, le=65535)
    workers: int = Field(default=1, ge=1)

    # --- Warstwa L1: lokalne embeddingi ---
    embedding_model_name: str = Field(
        default="intfloat/multilingual-e5-large",
        description="Nazwa modelu FastEmbed. Musi być obsługiwana przez zainstalowaną wersję fastembed.",
    )
    embedding_dimension: int = Field(default=1024, ge=1)
    embedding_device: Literal["cpu", "cuda"] = Field(default="cpu")
    embedding_batch_size: int = Field(default=32, ge=1)
    embedding_model_version: str = Field(
        default="multilingual-e5-large@v1",
        description="Wersja wektorów. Zmiana wymusza przeliczenie całego indeksu pgvector.",
    )

    # --- Warstwa L3: model generatywny ---
    anthropic_api_key: str = Field(
        default="", description="Pusty klucz = degradacja do adaptera heurystycznego"
    )
    llm_model: str = Field(default="claude-opus-5")
    llm_effort: Literal["low", "medium", "high", "xhigh", "max"] = Field(default="low")
    llm_max_output_tokens: int = Field(default=4096, ge=1)
    llm_timeout_seconds: float = Field(default=120.0, gt=0)
    llm_max_retries: int = Field(default=2, ge=0)
    llm_regeneration_attempts: int = Field(
        default=2,
        ge=0,
        le=5,
        description="Ile razy ponawiać sekcje odrzucone przez walidator proweniencji",
    )

    # --- Budżet i limity ---
    daily_token_budget: int = Field(default=1_000_000, ge=1)
    cost_alert_threshold: float = Field(default=0.8, gt=0.0, le=1.0)

    # --- Telemetria ---
    otel_exporter_otlp_endpoint: str = Field(default="")
    otel_service_name: str = Field(default="barometr-ai")

    @property
    def embedding_needs_e5_prefix(self) -> bool:
        """True dla rodziny E5, która wymaga prefiksów `query: ` / `passage: `."""
        return any(marker in self.embedding_model_name.lower() for marker in E5_MODEL_MARKERS)

    @property
    def llm_enabled(self) -> bool:
        """True gdy skonfigurowano dostawcę modelu generatywnego."""
        return bool(self.anthropic_api_key)

    @model_validator(mode="after")
    def _require_llm_in_production(self) -> "Settings":
        """Produkcja bez klucza API oznaczałaby ciche podanie heurystyki jako wyniku modelu."""
        if self.app_env == "production" and not self.anthropic_api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY jest wymagany przy APP_ENV=production — "
                "adapter heurystyczny nie jest dopuszczalny jako źródło streszczeń produkcyjnych."
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached singleton for application settings."""
    return Settings()
