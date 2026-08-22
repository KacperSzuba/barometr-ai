"""Structured logging configuration."""

import logging
import sys

from barometr_ai.core.config import get_settings


def setup_logging() -> None:
    """Configure root logger with clean standard formatting."""
    settings = get_settings()
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )
