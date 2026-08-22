"""Unit tests for config and settings."""

from barometr_ai.core.config import get_settings


def test_settings_load_defaults():
    settings = get_settings()
    assert settings.app_name == "barometr-ai"
    assert settings.app_version == "0.1.0"
    assert settings.port == 8000
