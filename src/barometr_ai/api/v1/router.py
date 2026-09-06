"""Kompletny agregator wszystkich tras API v1 (F0 - F5)."""

from fastapi import APIRouter

from barometr_ai.api.dependencies import ServiceKeyDep
from barometr_ai.api.v1 import (
    briefings,
    classification,
    clustering,
    diffs,
    embeddings,
    forecasts,
    framing,
    gov,
    health,
    local,
    ner,
    novelty,
    pipeline,
    radar,
    scoring,
    summaries,
    usage,
)

api_v1_router = APIRouter(prefix="/v1")

# Sondy zdrowia zostają otwarte: orkiestrator, który musi znać stan kontenera, nie ma jak
# przedstawić sekretu, a jedyne, co stąd wychodzi, to gotowość modeli. Wszystko poniżej
# kosztuje tokeny albo niesie treść żądania i przechodzi przez `require_service_key`.
api_v1_router.include_router(health.router)

_inference_routers = (
    embeddings.router,
    classification.router,
    clustering.router,
    pipeline.router,
    summaries.router,
    scoring.router,
    radar.router,
    diffs.router,
    forecasts.router,
    novelty.router,
    ner.router,
    framing.router,
    briefings.router,
    local.router,
    gov.router,
    usage.router,
)

for _router in _inference_routers:
    api_v1_router.include_router(_router, dependencies=[ServiceKeyDep])
