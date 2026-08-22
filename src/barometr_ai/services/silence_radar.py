"""Radar Ciszy - detekcja anomalii braku pokrycia medialnego dla istotnych ustaw (F2)."""

from barometr_ai.domain.advanced_models import (
    LegislativeStage,
    SilenceRadarRequest,
    SilenceRadarResponse,
)


class SilenceRadarService:
    """Wykrywa akty prawne o wysokiej wadze merytorycznej, które przeszły bez rozgłosu."""

    @staticmethod
    def evaluate(request: SilenceRadarRequest) -> SilenceRadarResponse:
        # Baza oczekiwanych wzmianek: akt 80 pkt na etapie Sejmu powinien mieć min. 25-40 wzmianek
        stage_factor = 1.5 if request.stage in [LegislativeStage.SEJM_READING_3, LegislativeStage.ENACTED] else 1.0
        expected = round((request.relevance_score / 100.0) ** 2 * 35.0 * stage_factor, 1)

        gap = max(0.0, expected - request.actual_media_mentions)
        is_anomaly = (
            request.relevance_score >= 55.0
            and request.actual_media_mentions <= max(2, int(expected * 0.25))
        )

        if is_anomaly:
            explanation = (
                f"Wykryto anomalię: akt o wysokiej istotności ({request.relevance_score}/100) "
                f"posiada zaledwie {request.actual_media_mentions} wzmianek medialnych (oczekiwano ~{expected})."
            )
        else:
            explanation = "Pokrycie medialne odpowiada szacunkom modelowym."

        return SilenceRadarResponse(
            expected_mentions=expected,
            silence_gap=round(gap, 1),
            is_anomaly=is_anomaly,
            explanation=explanation,
        )