"""Global exception handlers mapping domain errors to clean HTTP responses."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from barometr_ai.core.exceptions import (
    BarometrAIError,
    BudgetExceededError,
    ProvenanceViolationError,
)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ProvenanceViolationError)
    async def provenance_violation_handler(request: Request, exc: ProvenanceViolationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"error": "PROVENANCE_VIOLATION", "message": str(exc), "details": exc.details},
        )

    @app.exception_handler(BudgetExceededError)
    async def budget_exceeded_handler(request: Request, exc: BudgetExceededError) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={"error": "BUDGET_EXCEEDED", "message": str(exc), "details": exc.details},
        )

    @app.exception_handler(BarometrAIError)
    async def barometr_error_handler(request: Request, exc: BarometrAIError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"error": "DOMAIN_ERROR", "message": str(exc), "details": exc.details},
        )
