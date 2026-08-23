"""Endpoint detekcji nowości vs recykling (F2)."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends

from barometr_ai.api.dependencies import get_novelty_detector
from barometr_ai.domain.enterprise_models import NoveltyRequest, NoveltyResponse
from barometr_ai.services.novelty_detector import NoveltyDetectorService

router = APIRouter(tags=["Novelty"])


@router.post(
    "/novelty", response_model=NoveltyResponse, summary="Oceń stopień nowości tekstu vs historia"
)
async def evaluate_novelty(
    request: NoveltyRequest,
    detector: Annotated[NoveltyDetectorService, Depends(get_novelty_detector)],
) -> NoveltyResponse:
    return await asyncio.to_thread(detector.evaluate_novelty, request)
