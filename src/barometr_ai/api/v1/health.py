"""Health and readiness probe endpoints."""

from typing import Any

from fastapi import APIRouter, Response, status

from barometr_ai.api.dependencies import get_embedder, get_llm
from barometr_ai.core.config import get_settings

router = APIRouter(tags=["Health"])


@router.get("/health", summary="Liveness probe")
async def health_check() -> dict[str, str | bool]:
    """Serwis odpowiada. Nie mówi nic o gotowości modeli — od tego jest /ready."""
    settings = get_settings()
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.app_env,
        "stateless": True,
    }


@router.get("/ready", summary="Readiness probe — stan załadowanych modeli")
async def readiness_check(response: Response) -> dict[str, Any]:
    """Zwraca 503 dopóki modele nie są gotowe.

    Rozdzielenie liveness od readiness jest konieczne: wcześniej `/health` zwracał "ok"
    zanim jakikolwiek model istniał, więc orkiestrator kierował ruch do poda, który
    wywracał się na pierwszym żądaniu (wymóg F0: "health check i stan modeli").
    """
    settings = get_settings()
    components: dict[str, Any] = {}
    ready = True

    try:
        embedder = get_embedder()
        components["embedder"] = {
            "ready": True,
            "model": embedder.model_name,
            "model_version": embedder.model_version,
            "dimension": embedder.dimension,
        }
    except Exception as exc:  # noqa: BLE001 — readiness raportuje każdą awarię ładowania
        ready = False
        components["embedder"] = {"ready": False, "error": str(exc)}

    try:
        llm = get_llm()
        components["llm"] = {
            "ready": True,
            "model": llm.model_name,
            "model_version": llm.model_version,
            "generative": llm.is_generative,
        }
        if not llm.is_generative:
            components["llm"]["note"] = (
                "Adapter zastępczy — streszczenia nie pochodzą z modelu językowego."
            )
    except Exception as exc:  # noqa: BLE001
        ready = False
        components["llm"] = {"ready": False, "error": str(exc)}

    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {"ready": ready, "environment": settings.app_env, "components": components}
