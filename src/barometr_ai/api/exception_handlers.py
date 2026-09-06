"""Global exception handlers mapping domain errors to clean HTTP responses."""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from barometr_ai.core.exceptions import (
    BarometrAIError,
    BudgetExceededError,
    ModelInferenceError,
    ProvenanceViolationError,
    ServiceAuthenticationError,
)
from barometr_ai.core.telemetry import current_trace_id

logger = logging.getLogger(__name__)


def _error_payload(code: str, exc: BarometrAIError) -> dict[str, object]:
    payload: dict[str, object] = {
        "error": code,
        "message": str(exc),
        "details": exc.details,
    }
    trace_id = current_trace_id()
    if trace_id is not None:
        payload["trace_id"] = trace_id
    return payload


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ProvenanceViolationError)
    async def provenance_violation_handler(
        request: Request, exc: ProvenanceViolationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_error_payload("PROVENANCE_VIOLATION", exc),
        )

    @app.exception_handler(ServiceAuthenticationError)
    async def service_authentication_handler(
        request: Request, exc: ServiceAuthenticationError
    ) -> JSONResponse:
        """401 w tej samej kopercie co reszta błędów — klient ma jeden parser, nie dwa.

        Ścieżka trafia do logu, bo powtarzające się odmowy na jednym endpoincie to albo
        źle skonfigurowany klucz po stronie backendu, albo skanowanie z zewnątrz.
        """
        logger.warning("Odmowa dostępu do serwisu", extra={"path": request.url.path})
        return JSONResponse(
            status_code=401,
            content=_error_payload("UNAUTHORIZED", exc),
        )

    @app.exception_handler(BudgetExceededError)
    async def budget_exceeded_handler(request: Request, exc: BudgetExceededError) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content=_error_payload("BUDGET_EXCEEDED", exc),
        )

    @app.exception_handler(ModelInferenceError)
    async def model_inference_handler(request: Request, exc: ModelInferenceError) -> JSONResponse:
        # 502: awaria leży u dostawcy modelu albo w konfiguracji serwisu, nie w żądaniu klienta.
        logger.error("Awaria inferencji", extra={"path": request.url.path, "details": exc.details})
        return JSONResponse(
            status_code=502,
            content=_error_payload("MODEL_INFERENCE_FAILED", exc),
        )

    @app.exception_handler(BarometrAIError)
    async def barometr_error_handler(request: Request, exc: BarometrAIError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content=_error_payload("DOMAIN_ERROR", exc),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        """Ostatnia siatka: awaria spoza hierarchii domenowej nadal musi być do skorelowania.

        Bez tego nieprzewidziany wyjątek wraca jako gołe 500 bez `trace_id`, więc zgłoszenie
        od klienta nie ma jak trafić do konkretnego żądania w logach. Treść wyjątku nie idzie
        do odpowiedzi — trafia do logu razem z identyfikatorem śladu.
        """
        logger.exception(
            "Nieobsłużona awaria",
            extra={"path": request.url.path, "exception_type": type(exc).__name__},
        )
        payload: dict[str, object] = {
            "error": "INTERNAL_ERROR",
            "message": "Wewnętrzna awaria serwisu.",
        }
        trace_id = current_trace_id()
        if trace_id is not None:
            payload["trace_id"] = trace_id
        return JSONResponse(status_code=500, content=payload)
