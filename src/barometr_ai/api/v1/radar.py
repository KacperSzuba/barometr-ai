"""Radar Ciszy - detekcja anomalii braku pokrycia medialnego (F2)."""

from fastapi import APIRouter

from barometr_ai.domain.advanced_models import SilenceRadarRequest, SilenceRadarResponse
from barometr_ai.services.silence_radar import SilenceRadarService

router = APIRouter(tags=["Radar"])


@router.post(
    "/radar",
    response_model=SilenceRadarResponse,
    summary="Oceń anomalię pokrycia medialnego (Radar Ciszy)",
)
async def evaluate_silence_radar(request: SilenceRadarRequest) -> SilenceRadarResponse:
    # Bez `asyncio.to_thread` świadomie: cała praca to mediana po `peer_media_mentions`,
    # czyli sortowanie krótkiej listy liczb dostarczonej w żądaniu.
    return SilenceRadarService.evaluate(request)
