"""Endpointy dla sektora publicznego: sondaże i skrzynka obywatelska k>=50 (F5 Gov)."""

import asyncio

from fastapi import APIRouter

from barometr_ai.domain.enterprise_models import (
    CitizenFeedbackRequest,
    CitizenFeedbackResponse,
    PollsAggregateRequest,
    PollsAggregateResponse,
)
from barometr_ai.services.gov_analytics_service import GovAnalyticsService

router = APIRouter(tags=["Gov"])


@router.post(
    "/gov/polls",
    response_model=PollsAggregateResponse,
    summary="Agreguj sondaże z korektą house effects",
)
async def aggregate_polls(request: PollsAggregateRequest) -> PollsAggregateResponse:
    return await asyncio.to_thread(GovAnalyticsService.aggregate_polls, request)


@router.post(
    "/gov/feedback",
    response_model=CitizenFeedbackResponse,
    summary="Klastruj skrzynkę obywatelską z progiem k>=50",
)
async def process_feedback(request: CitizenFeedbackRequest) -> CitizenFeedbackResponse:
    return await asyncio.to_thread(GovAnalyticsService.process_citizen_feedback, request)
