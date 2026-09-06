"""Unit tests for config and settings."""

import pytest
from pydantic import ValidationError

from barometr_ai.core.config import Settings, get_settings


def test_settings_load_defaults():
    settings = get_settings()
    assert settings.app_name == "barometr-ai"
    assert settings.app_version == "0.1.0"
    assert settings.port == 8000


def test_backend_redis_bez_adresu_wywraca_start() -> None:
    """Cicha degradacja do licznika per proces byłaby limitem, którego nikt nie pilnuje."""
    with pytest.raises(ValidationError, match="REDIS_URL"):
        Settings(_env_file=None, token_budget_backend="redis", redis_url="")


def test_wiele_workerow_na_liczniku_w_pamieci_wywraca_start() -> None:
    """WORKERS=2 przy backendzie `memory` to po cichu dwukrotność deklarowanego budżetu."""
    with pytest.raises(ValidationError, match="TOKEN_BUDGET_BACKEND"):
        Settings(_env_file=None, workers=2, token_budget_backend="memory")


def test_wiele_workerow_jest_dozwolone_na_wspoldzielonym_liczniku() -> None:
    settings = Settings(
        _env_file=None,
        workers=4,
        token_budget_backend="redis",
        redis_url="redis://localhost:6379/0",
    )
    assert settings.workers == 4
    assert settings.token_budget_backend == "redis"


def test_domyslny_backend_to_licznik_w_pamieci() -> None:
    assert Settings(_env_file=None).token_budget_backend == "memory"


def test_produkcja_bez_klucza_serwisowego_wywraca_start() -> None:
    """Serwis nie zna użytkowników — bez klucza broni go wyłącznie założenie o sieci."""
    with pytest.raises(ValidationError, match="SERVICE_API_KEY"):
        Settings(
            _env_file=None, app_env="production", anthropic_api_key="sk-test", service_api_key=""
        )


def test_klucz_serwisowy_wlacza_bramke() -> None:
    assert Settings(_env_file=None).service_authentication_enabled is False
    assert Settings(_env_file=None, service_api_key="sekret").service_authentication_enabled is True
