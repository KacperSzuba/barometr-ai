"""Scoring istotności i pilności aktu prawnego (F1)."""

from fastapi import APIRouter

from barometr_ai.domain.advanced_models import ScoreRequest, ScoreResponse
from barometr_ai.services.relevance_scorer import RelevanceScorerService

router = APIRouter(tags=["Scoring"])


@router.post("/score", response_model=ScoreResponse, summary="Oblicz wynik istotności aktu prawnego")
async def calculate_score(request: ScoreRequest) -> ScoreResponse:
    return RelevanceScorerService.calculate_score(request)