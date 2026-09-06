"""Endpoint analizy framingu medialnego (F3)."""

import asyncio

from fastapi import APIRouter

from barometr_ai.domain.enterprise_models import FramingAnalysisRequest, FramingAnalysisResponse
from barometr_ai.services.framing_analyzer import StakeholderFramingService

router = APIRouter(tags=["Framing"])


@router.post(
    "/framing",
    response_model=FramingAnalysisResponse,
    summary="Analiza ramy narracyjnej w redakcjach",
)
async def analyze_framing(request: FramingAnalysisRequest) -> FramingAnalysisResponse:
    return await asyncio.to_thread(StakeholderFramingService.analyze_framing, request)
