"""Strukturalne logi JSON z `trace_id` z aktualnego spanu OpenTelemetry."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

if sys.version_info >= (3, 12):
    from typing import override
else:  # pragma: no cover - ścieżka wyłącznie dla Pythona 3.11
    # typing.override to PEP 698, dostępne dopiero od 3.12; na 3.11 sam import
    # `from typing import override` wywala ImportError przy starcie aplikacji.
    from typing_extensions import override

from barometr_ai.core.config import get_settings
from barometr_ai.core.telemetry import current_span_id, current_trace_id

_RESERVED_LOG_ATTRS = frozenset(
    {
        "args",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "span_id",
        "taskName",
        "thread",
        "threadName",
        "trace_id",
    }
)


class TraceContextFilter(logging.Filter):
    """Dokleja identyfikatory śladu do rekordu, żeby formatter nie musiał znać OTel.

    Filtr musi wisieć na **handlerze**, nie na loggerze. Logger stosuje swoje filtry wyłącznie
    do rekordów zalogowanych bezpośrednio na nim; rekordy propagowane z loggerów potomnych
    trafiają prosto do jego handlerów, z pominięciem filtrów. Ponieważ cały kod aplikacji woła
    `logging.getLogger(__name__)`, filtr na rootcie nie zadziałałby dla żadnej linii logu.
    """

    @override
    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = current_trace_id()
        record.span_id = current_span_id()
        return True


class JsonLogFormatter(logging.Formatter):
    """Jedna linia JSON na zdarzenie — format, którego oczekuje Loki."""

    @override
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": getattr(record, "trace_id", None),
            "span_id": getattr(record, "span_id", None),
        }
        for key, value in record.__dict__.items():
            if key in _RESERVED_LOG_ATTRS or key.startswith("_"):
                continue
            payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging() -> None:
    """Konfiguruje root logger. `force=True`, bo uvicorn zdąży dołożyć własne handlery."""
    settings = get_settings()
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLogFormatter())
    # Na handlerze, nie na loggerze — patrz docstring TraceContextFilter.
    handler.addFilter(TraceContextFilter())

    root = logging.getLogger()
    root.handlers.clear()
    # Filtr z poprzedniej konfiguracji zostałby na rootcie i nic by nie robił poza myleniem.
    root.filters = [item for item in root.filters if not isinstance(item, TraceContextFilter)]
    root.addHandler(handler)
    root.setLevel(log_level)
