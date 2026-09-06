"""Kompletny agregator wszystkich tras API v1 (F0 - F5)."""

from fastapi import APIRouter

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

api_v1_router.include_router(health.router)
api_v1_router.include_router(embeddings.router)
api_v1_router.include_router(classification.router)
api_v1_router.include_router(clustering.router)
api_v1_router.include_router(pipeline.router)
api_v1_router.include_router(summaries.router)
api_v1_router.include_router(scoring.router)
api_v1_router.include_router(radar.router)
api_v1_router.include_router(diffs.router)
api_v1_router.include_router(forecasts.router)
api_v1_router.include_router(novelty.router)
api_v1_router.include_router(ner.router)
api_v1_router.include_router(framing.router)
api_v1_router.include_router(briefings.router)
api_v1_router.include_router(local.router)
api_v1_router.include_router(gov.router)
api_v1_router.include_router(usage.router)
