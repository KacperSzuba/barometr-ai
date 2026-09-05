"""Testy strukturalnego logowania i korelacji ze śladem OpenTelemetry.

Kontrakt z backendem opiera się na tym, że każda linia logu niesie `trace_id` tego samego
żądania. Linia bez niego jest nie do skorelowania, a formatter wypisuje wtedy `null` bez
żadnego błędu — awaria jest więc cicha i tylko test może ją złapać.
"""

import io
import json
import logging

import pytest
from opentelemetry import trace

from barometr_ai.core.config import Settings
from barometr_ai.core.logging import JsonLogFormatter, TraceContextFilter, setup_logging
from barometr_ai.core.telemetry import setup_telemetry


@pytest.fixture
def captured_logs() -> io.StringIO:
    """Konfiguruje logowanie tak jak aplikacja i przechwytuje strumień handlera."""
    setup_telemetry(Settings(_env_file=None))
    setup_logging()
    buffer = io.StringIO()
    logging.getLogger().handlers[0].stream = buffer  # type: ignore[attr-defined]
    return buffer


def _lines(buffer: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in buffer.getvalue().strip().splitlines() if line]


def test_log_z_loggera_potomnego_niesie_trace_id(captured_logs: io.StringIO) -> None:
    """Regresja: filtr wisiał na loggerze root, więc nie dotykał rekordów propagowanych.

    Logger stosuje własne filtry tylko do rekordów zalogowanych bezpośrednio na nim. Cały kod
    aplikacji woła `logging.getLogger(__name__)`, więc każda linia logu wychodziła
    z `trace_id: null` — po cichu, bo formatter czyta atrybut przez `getattr(..., None)`.
    """
    with trace.get_tracer("test").start_as_current_span("span-testowy"):
        logging.getLogger("barometr_ai.services.cokolwiek").info("zdarzenie z serwisu")

    entries = _lines(captured_logs)
    assert len(entries) == 1
    assert entries[0]["logger"] == "barometr_ai.services.cokolwiek"
    assert isinstance(entries[0]["trace_id"], str)
    assert len(str(entries[0]["trace_id"])) == 32
    assert isinstance(entries[0]["span_id"], str)


def test_log_poza_spanem_ma_puste_identyfikatory(captured_logs: io.StringIO) -> None:
    """Brak aktywnego spanu to `null`, a nie zmyślony identyfikator."""
    logging.getLogger("barometr_ai.services.cokolwiek").info("zdarzenie bez sladu")

    entry = _lines(captured_logs)[0]
    assert entry["trace_id"] is None
    assert entry["span_id"] is None


def test_setup_logging_nie_zostawia_filtra_na_rootcie(captured_logs: io.StringIO) -> None:
    """Filtr na loggerze nic nie robi poza myleniem czytającego konfigurację."""
    root = logging.getLogger()
    assert not any(isinstance(item, TraceContextFilter) for item in root.filters)
    assert any(isinstance(item, TraceContextFilter) for item in root.handlers[0].filters)


def test_ponowne_setup_logging_nie_mnozy_handlerow(captured_logs: io.StringIO) -> None:
    """Uvicorn dokłada własne handlery — konfiguracja musi być idempotentna."""
    setup_logging()
    setup_logging()
    assert len(logging.getLogger().handlers) == 1


def test_pola_extra_trafiaja_do_json(captured_logs: io.StringIO) -> None:
    logging.getLogger("barometr_ai.api.v1.test").info(
        "request", extra={"http_status": 200, "http_path": "/v1/usage"}
    )

    entry = _lines(captured_logs)[0]
    assert entry["http_status"] == 200
    assert entry["http_path"] == "/v1/usage"
    assert entry["message"] == "request"


def test_formatter_serializuje_wyjatek() -> None:
    formatter = JsonLogFormatter()
    try:
        raise ValueError("blad testowy")
    except ValueError:
        record = logging.LogRecord(
            name="barometr_ai.test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="awaria",
            args=(),
            exc_info=logging.sys.exc_info(),  # type: ignore[attr-defined]
        )
        payload = json.loads(formatter.format(record))

    assert payload["level"] == "ERROR"
    assert "ValueError: blad testowy" in payload["exception"]
