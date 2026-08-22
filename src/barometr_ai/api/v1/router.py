"""Aggregator for v1 API routers."""

from fastapi import APIRouter

from barometr_ai.api.v1 import classification, clustering, embeddings, health, summaries

api_v1_router = APIRouter(prefix="/v1")

api_v1_router.include_router(health.router)
api_v1_router.include_router(embeddings.router)
api_v1_router.include_router(classification.router)
api_v1_router.include_router(clustering.router)
api_v1_router.include_router(summaries.router)
