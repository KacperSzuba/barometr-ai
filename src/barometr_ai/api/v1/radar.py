"""Radar Ciszy - detekcja anomalii braku pokrycia medialnego (F2)."""

from fastapi import APIRouter

from barometr_ai.domain.advanced_models import SilenceRadarRequest, SilenceRadarResponse
from barometr_ai.services.silence_radar import SilenceRadarService

router = APIRouter(tags=["Radar"])


@router.post("/radar", response_model=SilenceRadarResponse, summary="Oceń anomalię pokrycia medialnego (Radar Ciszy)")
async def evaluate_silence_radar(request: SilenceRadarRequest) -> SilenceRadarResponse:
    return SilenceRadarService.evaluate(request)