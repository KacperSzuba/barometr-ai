"""Global exception handlers mapping domain errors to clean HTTP responses."""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from barometr_ai.core.exceptions import (
    BarometrAIError,
    BudgetExceededError,
    ModelInferenceError,
    ProvenanceViolationError,
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
