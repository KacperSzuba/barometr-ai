"""FastAPI application factory and main entrypoint."""

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from barometr_ai.api.dependencies import get_embedder, get_llm
from barometr_ai.api.exception_handlers import register_exception_handlers
from barometr_ai.api.v1.router import api_v1_router
from barometr_ai.core.config import get_settings
from barometr_ai.core.logging import setup_logging
from barometr_ai.core.telemetry import (
    TraceHeaderMiddleware,
    flush_telemetry,
    instrument_fastapi_app,
    setup_telemetry,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Lifespan context manager for startup and shutdown events.

    Modele ładujemy przy starcie, nie przy pierwszym żądaniu. Wcześniej inicjalizacja ONNX
    działa się w trakcie obsługi requestu, więc pierwszy użytkownik po deployu płacił
    kilkanaście sekund latencji, a healthcheck raportował gotowość zanim cokolwiek istniało.
    """
    settings = get_settings()
    logger.info("Start serwisu", extra={"app": settings.app_name, "environment": settings.app_env})

    await asyncio.to_thread(get_embedder)
    llm = get_llm()
    if not llm.is_generative:
        logger.warning(
            "Warstwa generatywna działa w trybie zastępczym — odpowiedzi mają is_generative=false"
        )

    logger.info("Modele gotowe")
    yield
    logger.info("Zatrzymanie serwisu")
    flush_telemetry()


def create_app() -> FastAPI:
    """Application factory."""
    settings = get_settings()
    setup_telemetry(settings)
    setup_logging()

    app = FastAPI(
        title="Barometr AI Service",
        description=(
            "Bezstanowy serwis inferencyjny i NLP platformy Barometr z rygorystyczną proweniencją."
        ),
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    register_exception_handlers(app)
    app.include_router(api_v1_router)
    instrument_fastapi_app(app)
    # Ostatnie add_middleware = najbardziej zewnętrzna warstwa: X-Trace-Id → traceparent
    # musi być widoczne dla instrumentacji HTTP.
    app.add_middleware(TraceHeaderMiddleware)

    return app


app = create_app()
