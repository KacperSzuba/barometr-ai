"""Health and readiness probe endpoints."""

from fastapi import APIRouter

from barometr_ai.core.config import get_settings

router = APIRouter(tags=["Health"])


@router.get("/health", summary="Liveness and readiness probe")
async def health_check() -> dict[str, str | bool]:
    settings = get_settings()
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.app_env,
        "stateless": True,
    }
