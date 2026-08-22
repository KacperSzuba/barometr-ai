"""Wytłumaczalny model scoringu istotności aktów prawnych (Wymóg F1)."""

from barometr_ai.domain.advanced_models import (
    LegislativeStage,
    ScoreExplanation,
    ScoreRequest,
    ScoreResponse,
)

STAGE_WEIGHTS: dict[LegislativeStage, float] = {
    LegislativeStage.GOV_WORK: 10.0,
    LegislativeStage.CONSULTATIONS: 15.0,
    LegislativeStage.SEJM_READING_1: 18.0,
    LegislativeStage.SEJM_COMMITTEE: 22.0,
    LegislativeStage.SEJM_READING_3: 32.0,
    LegislativeStage.SENATE: 34.0,
    LegislativeStage.PRESIDENT_SIGN: 35.0,
    LegislativeStage.ENACTED: 35.0,
}


class RelevanceScorerService:
    """Liniowy, w pełni wytłumaczalny model obliczania istotności i pilności regulacji."""

    @staticmethod
    def calculate_score(request: ScoreRequest) -> ScoreResponse:
        explanations: list[ScoreExplanation] = []

        # 1. Waga etapu legislacyjnego (0-35 pkt)
        stage_contrib = STAGE_WEIGHTS.get(request.stage, 10.0)
        explanations.append(
            ScoreExplanation(
                factor="Etap procesu legislacyjnego",
                weight=35.0,
                contribution=round(stage_contrib, 1),
            )
        )

        # 2. Dopasowanie do profilu PKD (0-25 pkt)
        pkd_contrib = min(25.0, request.pkd_overlap_count * 8.0)
        explanations.append(
            ScoreExplanation(
                factor="Dopasowanie do profilu branżowego / PKD",
                weight=25.0,
                contribution=round(pkd_contrib, 1),
            )
        )

        # 3. Zasięg źródeł / prędkość narastania (0-15 pkt)
        sources_contrib = min(15.0, (request.sources_count - 1) * 3.0 + 3.0)
        explanations.append(
            ScoreExplanation(
                factor="Zasięg źródeł i powiązań",
                weight=15.0,
                contribution=round(sources_contrib, 1),
            )
        )

        # 4. Skala zmian w treści (diff size) (0-15 pkt)
        diff_contrib = min(15.0, (request.diff_chars_changed / 2000.0) * 15.0)
        explanations.append(
            ScoreExplanation(
                factor="Wielkość modyfikacji treści",
                weight=15.0,
                contribution=round(diff_contrib, 1),
            )
        )

        # 5. Twardy termin (0-10 pkt)
        deadline_contrib = 10.0 if request.has_hard_deadline else 0.0
        explanations.append(
            ScoreExplanation(
                factor="Obecność twardego terminu konsultacji/vacatio",
                weight=10.0,
                contribution=round(deadline_contrib, 1),
            )
        )

        total = sum(e.contribution for e in explanations)
        total_score = min(100.0, max(0.0, total))

        if total_score >= 75.0:
            urgency = "CRITICAL"
        elif total_score >= 50.0:
            urgency = "HIGH"
        elif total_score >= 30.0:
            urgency = "MEDIUM"
        else:
            urgency = "LOW"

        return ScoreResponse(
            total_score=round(total_score, 1),
            urgency_level=urgency,
            explanations=explanations,
            model_version="linear-relevance-v1.0",
        )