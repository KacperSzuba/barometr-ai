"""Endpoint wielopoziomowych briefingów (F3)."""

from fastapi import APIRouter, HTTPException, status

from barometr_ai.domain.enterprise_models import BriefingRequest, BriefingResponse

router = APIRouter(tags=["Briefings"])


@router.post(
    "/briefing",
    response_model=BriefingResponse,
    summary="Generuj wielomiesięczny briefing tematyczny",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    responses={501: {"description": "Funkcja niezaimplementowana"}},
)
async def generate_briefing(request: BriefingRequest) -> BriefingResponse:
    """Wielopoziomowa synteza tematu — niezaimplementowana.

    Poprzednia implementacja zwracała stałą oś czasu z zaszytymi datami, numerem druku
    sejmowego i liczbą uwag, niezależnie od wejścia. W produkcie, którego obietnicą jest
    weryfikowalna proweniencja, zmyślona chronologia jest gorsza niż brak funkcji.
    Zadanie F3 wymaga: mapa chronologiczna → streszczenia cząstkowe → synteza, z proweniencją
    zachowaną na każdym poziomie.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={
            "error": "NOT_IMPLEMENTED",
            "message": (
                "Briefing wielopoziomowy nie jest zaimplementowany. Endpoint zwracał wcześniej "
                "dane zmyślone i został wyłączony do czasu implementacji syntezy z proweniencją."
            ),
            "spec_task": "F3 · Briefing na życzenie",
        },
    )
