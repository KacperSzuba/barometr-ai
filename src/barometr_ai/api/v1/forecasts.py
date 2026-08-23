"""Kalibrowane prognozy wyniku procesu legislacyjnego (F3)."""

from fastapi import APIRouter, HTTPException, status

from barometr_ai.domain.advanced_models import ForecastRequest, ForecastResponse

router = APIRouter(tags=["Forecasts"])


@router.post(
    "/forecast",
    response_model=ForecastResponse,
    summary="Oszacuj prawdopodobieństwo uchwalenia ustawy",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    responses={501: {"description": "Funkcja niezaimplementowana"}},
)
async def generate_forecast(request: ForecastRequest) -> ForecastResponse:
    """Prognoza przejścia legislacyjnego — niezaimplementowana.

    Poprzednia implementacja zwracała jako `historical_base_rate` stałe wpisane w kod
    (0,82 dla projektów rządowych) oraz `brier_score_target` jako gdyby był zmierzoną
    kalibracją. Zadanie F3 wymaga częstości policzonych z 5-letniego backfillu i modelu
    kalibrowanego — a publiczny rejestr trafności prognoz rozliczy te liczby publicznie.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={
            "error": "NOT_IMPLEMENTED",
            "message": (
                "Prognozy legislacyjne nie są zaimplementowane. Endpoint zwracał wcześniej "
                "stałe podane jako częstości historyczne i został wyłączony do czasu "
                "policzenia base rates z danych backfillu."
            ),
            "spec_task": "F3 · Prognozy przejścia legislacyjnego",
        },
    )
