"""Testy jednostkowe zaawansowanych funkcji: Scoring, Radar Ciszy, Legal Diff, Prognozy."""

from barometr_ai.domain.advanced_models import (
    ForecastRequest,
    LegalDiffRequest,
    LegislativeStage,
    ScoreRequest,
    SilenceRadarRequest,
)
from barometr_ai.services.forecasting_service import ForecastingService
from barometr_ai.services.legal_diff_service import LegalDiffService
from barometr_ai.services.relevance_scorer import RelevanceScorerService
from barometr_ai.services.silence_radar import SilenceRadarService


def test_relevance_scorer_critical_urgency() -> None:
    req = ScoreRequest(
        stage=LegislativeStage.SEJM_READING_3,
        pkd_overlap_count=3,
        sources_count=5,
        diff_chars_changed=4000,
        has_hard_deadline=True,
    )
    res = RelevanceScorerService.calculate_score(req)
    assert res.total_score >= 75.0
    assert res.urgency_level == "CRITICAL"
    assert len(res.explanations) == 5


def test_silence_radar_detects_anomaly() -> None:
    # Akt o wysokiej randze (85/100) na etapie uchwalenia, a wzmianek tylko 1 -> anomalia
    req = SilenceRadarRequest(
        relevance_score=85.0,
        actual_media_mentions=1,
        stage=LegislativeStage.SEJM_READING_3,
    )
    res = SilenceRadarService.evaluate(req)
    assert res.is_anomaly is True
    assert res.silence_gap > 20.0
    assert "Wykryto anomalię" in res.explanation


def test_legal_diff_with_rcl_consultation_correlation() -> None:
    version_a = (
        "Art. 1. Ustawa o ochronie danych.\n"
        "Art. 2. Kary finansowe wynoszą do 10 000 000 zł."
    )
    version_b = (
        "Art. 1. Ustawa o ochronie danych.\n"
        "Art. 2. Kary finansowe wynoszą do 2 000 000 zł."  # Zmiana kwoty
    )
    comments = [
        {
            "id": "rcl_001",
            "article_ref": "Art. 2.",
            "text": "Wnosimy o obniżenie maksymalnych kar finansowych z 10 mln do 2 mln zł ze względu na MŚP.",
            "submitter": "Polska Izba Gospodarcza",
        }
    ]

    req = LegalDiffRequest(
        version_a_text=version_a,
        version_b_text=version_b,
        consultation_comments=comments,
    )
    res = LegalDiffService.compare_and_correlate(req)

    assert len(res.changes) == 1
    diff = res.changes[0]
    assert diff.article_ref == "Art. 2."
    assert diff.change_type == "MODIFIED"
    assert diff.consultation_comment_id == "rcl_001"
    assert diff.consultation_submitter == "Polska Izba Gospodarcza"
    assert diff.correlation_confidence is not None


def test_forecasting_service_probabilities() -> None:
    # Rządowy projekt w 3 czytaniu z poparciem koalicji -> bardzo wysoka szansa uchwalenia
    req_gov = ForecastRequest(
        stage=LegislativeStage.SEJM_READING_3,
        sponsor_type="GOVERNMENT",
        days_in_current_stage=14,
        governing_coalition_support=True,
    )
    res_gov = ForecastingService.forecast(req_gov)
    assert res_gov.enactment_probability >= 0.85
    assert res_gov.confidence_interval[0] < res_gov.enactment_probability <= res_gov.confidence_interval[1]

    # Obywatelski projekt bez poparcia koalicji -> niska szansa
    req_cit = ForecastRequest(
        stage=LegislativeStage.SEJM_READING_1,
        sponsor_type="CITIZENS",
        days_in_current_stage=200,
        governing_coalition_support=False,
    )
    res_cit = ForecastingService.forecast(req_cit)
    assert res_cit.enactment_probability < 0.20