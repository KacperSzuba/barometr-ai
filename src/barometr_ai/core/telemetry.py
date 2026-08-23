"""OpenTelemetry: ślady HTTP, metryki tokenów i identyfikator wspólny z backendem.

Kontrakt między językami to W3C Trace Context (`traceparent`). Nagłówek `X-Trace-Id`
jest mostem dla backendu, który jeszcze nie wysyła `traceparent`: 32 znaki hex, bez myślników
(akceptujemy też UUID). Pusty `OTEL_EXPORTER_OTLP_ENDPOINT` zostawia ślady w procesie
— logi nadal niosą `trace_id` — i nie próbuje eksportu do nieistniejącego collectora.
"""

from __future__ import annotations

import logging
import re
import secrets
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.propagate import set_global_textmap
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from barometr_ai.core.config import Settings

logger = logging.getLogger(__name__)

_TRACE_ID_HEX = re.compile(r"^[0-9a-f]{32}$")
_SILENT_PATHS = frozenset({"/v1/health", "/v1/ready"})
_UNTRACED_URLS = "/v1/health,/v1/ready,/docs,/redoc,/openapi.json"

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

_initialized = False
_export_enabled = False


def normalize_trace_id(raw: str) -> str | None:
    """Zwraca 32-znakowy hex albo None, gdy wartość nie nadaje się na W3C trace-id."""
    candidate = raw.strip().lower().replace("-", "")
    if not _TRACE_ID_HEX.fullmatch(candidate) or candidate == "0" * 32:
        return None
    return candidate


def current_trace_id() -> str | None:
    """Aktualny trace-id albo None, gdy nie ma aktywnego, poprawnego spanu."""
    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return None
    return format(context.trace_id, "032x")


def current_span_id() -> str | None:
    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return None
    return format(context.span_id, "016x")


def get_tracer(name: str) -> trace.Tracer:
    return trace.get_tracer(name)


def record_tokens(*, client_id: str, tokens: int, model_version: str) -> None:
    """Licznik zużycia tokenów. Działa także bez collectora (NoOp / SDK w pamięci)."""
    if tokens <= 0:
        return
    metrics.get_meter("barometr_ai").create_counter(
        "barometr.ai.tokens",
        unit="{token}",
        description="Zużycie tokenów warstwy generatywnej per klient",
    ).add(tokens, {"client_id": client_id, "model_version": model_version})


def setup_telemetry(settings: Settings) -> None:
    """Jednorazowa inicjalizacja providera. Kolejne wywołania są no-op."""
    global _initialized, _export_enabled
    if _initialized:
        return

    resource = Resource.create(
        {
            "service.name": settings.otel_service_name,
            "service.version": settings.app_version,
            "deployment.environment": settings.app_env,
        }
    )
    provider = TracerProvider(resource=resource)
    endpoint = settings.otel_exporter_otlp_endpoint.strip()
    if endpoint:
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=_signal_endpoint(endpoint, "traces")))
        )
        meter_reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=_signal_endpoint(endpoint, "metrics"))
        )
        metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[meter_reader]))
        _export_enabled = True
        logger.info("Eksport OTLP włączony", extra={"endpoint": endpoint})
    else:
        metrics.set_meter_provider(MeterProvider(resource=resource))
        _export_enabled = False

    trace.set_tracer_provider(provider)
    set_global_textmap(TraceContextTextMapPropagator())
    _initialized = True


def instrument_fastapi_app(app: Any) -> None:
    """Instrumentacja HTTP. Wywoływana dla każdej instancji aplikacji (także w testach)."""
    FastAPIInstrumentor.instrument_app(app, excluded_urls=_UNTRACED_URLS)


def flush_telemetry() -> None:
    """Wypycha bufor eksportu. Bez collectora nie robi nic kosztownego."""
    if not _export_enabled:
        return
    provider = trace.get_tracer_provider()
    force_flush = getattr(provider, "force_flush", None)
    if callable(force_flush):
        force_flush(timeout_millis=2000)


def _signal_endpoint(base: str, signal: str) -> str:
    trimmed = base.rstrip("/")
    suffix = f"/v1/{signal}"
    if trimmed.endswith(suffix):
        return trimmed
    return f"{trimmed}{suffix}"


def _header_map(headers: list[tuple[bytes, bytes]]) -> dict[bytes, bytes]:
    return {key.lower(): value for key, value in headers}


def _inject_traceparent(headers: list[tuple[bytes, bytes]]) -> list[tuple[bytes, bytes]]:
    mapped = _header_map(headers)
    if b"traceparent" in mapped:
        return headers
    raw = mapped.get(b"x-trace-id")
    if raw is None:
        return headers
    try:
        normalized = normalize_trace_id(raw.decode("ascii"))
    except UnicodeDecodeError:
        return headers
    if normalized is None:
        return headers
    parent_span = secrets.token_hex(8)
    traceparent = f"00-{normalized}-{parent_span}-01"
    return [*headers, (b"traceparent", traceparent.encode("ascii"))]


class TraceHeaderMiddleware:
    """Zewnętrzna warstwa: `X-Trace-Id` → `traceparent` oraz zwrotka identyfikatora śladu."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = _inject_traceparent(list(scope.get("headers", [])))
        scope = {**scope, "headers": headers}
        method = scope.get("method", "")
        path = scope.get("path", "")
        status_code = 0

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message.get("status", 0))
                trace_id = current_trace_id()
                if trace_id is not None:
                    response_headers = list(message.get("headers", []))
                    response_headers.append((b"x-trace-id", trace_id.encode("ascii")))
                    span_id = current_span_id()
                    if span_id is not None:
                        flags = (
                            "01"
                            if trace.get_current_span().get_span_context().trace_flags.sampled
                            else "00"
                        )
                        traceresponse = f"00-{trace_id}-{span_id}-{flags}"
                        response_headers.append((b"traceresponse", traceresponse.encode("ascii")))
                    message = {**message, "headers": response_headers}
            await send(message)

        await self.app(scope, receive, send_wrapper)
        if path not in _SILENT_PATHS:
            logger.info(
                "request",
                extra={"http_method": method, "http_path": path, "http_status": status_code},
            )
