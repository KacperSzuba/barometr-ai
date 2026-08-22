"""FastAPI application factory and main entrypoint."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from barometr_ai.api.exception_handlers import register_exception_handlers
from barometr_ai.api.v1.router import api_v1_router
from barometr_ai.core.config import get_settings
from barometr_ai.core.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Lifespan context manager for startup and shutdown events."""
    setup_logging()
    yield


def create_app() -> FastAPI:
    """Application factory."""
    settings = get_settings()

    app = FastAPI(
        title="Barometr AI Service",
        description="Bezstanowy serwis inferencyjny i NLP platformy Barometr z rygorystyczną proweniencją.",
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    register_exception_handlers(app)
    app.include_router(api_v1_router)

    return app


app = create_app()
