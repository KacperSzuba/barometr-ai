"""Endpoint wielopoziomowych briefingów (F3)."""

from fastapi import APIRouter

from barometr_ai.domain.enterprise_models import BriefingRequest, BriefingResponse
from barometr_ai.services.multi_briefing_service import MultiBriefingService

router = APIRouter(tags=["Briefings"])


@router.post("/briefing", response_model=BriefingResponse, summary="Generuj wielomiesięczny briefing tematyczny")
async def generate_briefing(request: BriefingRequest) -> BriefingResponse:
    return MultiBriefingService.generate_briefing(request)