"""Kalibrowane prognozy wyniku procesu legislacyjnego (F3)."""

from fastapi import APIRouter

from barometr_ai.domain.advanced_models import ForecastRequest, ForecastResponse
from barometr_ai.services.forecasting_service import ForecastingService

router = APIRouter(tags=["Forecasts"])


@router.post("/forecast", response_model=ForecastResponse, summary="Oszacuj prawdopodobieństwo uchwalenia ustawy")
async def generate_forecast(request: ForecastRequest) -> ForecastResponse:
    return ForecastingService.forecast(request)