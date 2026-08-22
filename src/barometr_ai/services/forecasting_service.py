"""Kalibrowany silnik prognoz prawdopodobieństwa uchwalenia ustawy (F3)."""

from barometr_ai.domain.advanced_models import (
    ForecastRequest,
    ForecastResponse,
    LegislativeStage,
)

BASE_RATES_BY_SPONSOR: dict[str, float] = {
    "GOVERNMENT": 0.82,
    "DEPUTIES": 0.18,
    "SENATE": 0.25,
    "CITIZENS": 0.08,
}

STAGE_COMPLETION_PROBABILITIES: dict[LegislativeStage, float] = {
    LegislativeStage.GOV_WORK: 0.70,
    LegislativeStage.CONSULTATIONS: 0.75,
    LegislativeStage.SEJM_READING_1: 0.80,
    LegislativeStage.SEJM_COMMITTEE: 0.86,
    LegislativeStage.SEJM_READING_3: 0.95,
    LegislativeStage.SENATE: 0.97,
    LegislativeStage.PRESIDENT_SIGN: 0.99,
    LegislativeStage.ENACTED: 1.0,
}


class ForecastingService:
    """Prognozuje wynik legislacyjny w oparciu o częstości historyczne (Base Rates) i Brier Score."""

    @staticmethod
    def forecast(request: ForecastRequest) -> ForecastResponse:
        base_rate = BASE_RATES_BY_SPONSOR.get(request.sponsor_type.upper(), 0.50)
        stage_rate = STAGE_COMPLETION_PROBABILITIES.get(request.stage, 0.75)

        # Wycena wpływu etapu i wnioskodawcy
        prob = (base_rate * 0.40) + (stage_rate * 0.60)

        # Kara za utknięcie w etapie (> 180 dni)
        if request.days_in_current_stage > 180:
            prob *= 0.85

        if not request.governing_coalition_support:
            prob *= 0.20

        prob = min(0.99, max(0.01, prob))

        # Pasmo niepewności (Confidence Interval)
        margin = 0.06 if prob > 0.80 or prob < 0.20 else 0.10
        ci_low = max(0.0, prob - margin)
        ci_high = min(1.0, prob + margin)

        return ForecastResponse(
            enactment_probability=round(prob, 2),
            confidence_interval=(round(ci_low, 2), round(ci_high, 2)),
            historical_base_rate=round(base_rate, 2),
            brier_score_target=0.12,
            explanation=(
                f"Prognoza oparta na wnioskodawcy ({request.sponsor_type}: {base_rate*100:.0f}% szans historycznych) "
                f"oraz zaawansowaniu etapu ({request.stage.value})."
            ),
        )