"""Testy jednostkowe zaawansowanych funkcji: Scoring, Radar Ciszy, Legal Diff."""

from barometr_ai.domain.advanced_models import (
    LegalDiffRequest,
    LegislativeStage,
    ScoreRequest,
    SilenceRadarRequest,
)
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
    """Akt o wysokiej randze z 1 wzmianką przy medianie 30 dla porównywalnych -> anomalia."""
    req = SilenceRadarRequest(
        relevance_score=85.0,
        actual_media_mentions=1,
        stage=LegislativeStage.SEJM_READING_3,
        peer_media_mentions=[24, 28, 30, 33, 41, 52],
    )
    res = SilenceRadarService.evaluate(req)
    assert res.is_anomaly is True
    assert res.expected_mentions == 31.5  # mediana zbioru porównawczego
    assert res.silence_gap == 30.5
    assert "Anomalia" in res.explanation


def test_silence_radar_needs_peer_baseline() -> None:
    """Bez zbioru porównawczego nie ma z czym porównać — wynik musi być pusty, nie zgadnięty.

    Poprzednia wersja liczyła oczekiwane pokrycie ze wzoru zamkniętego z dwiema stałymi
    wpisanymi w kod, więc zwracała "anomalię" nie mając żadnej historii.
    """
    req = SilenceRadarRequest(
        relevance_score=85.0,
        actual_media_mentions=1,
        stage=LegislativeStage.SEJM_READING_3,
    )
    res = SilenceRadarService.evaluate(req)
    assert res.is_anomaly is False
    assert res.expected_mentions is None
    assert res.silence_gap is None
    assert "Za mało aktów porównywalnych" in res.explanation


def test_silence_radar_ignores_low_relevance_acts() -> None:
    """Filtr istotności: bez niego lista tonie w drobiazgach (punkt 4 zadania F2)."""
    req = SilenceRadarRequest(
        relevance_score=20.0,
        actual_media_mentions=0,
        stage=LegislativeStage.SEJM_READING_3,
        peer_media_mentions=[24, 28, 30, 33, 41, 52],
    )
    assert SilenceRadarService.evaluate(req).is_anomaly is False


def test_legal_diff_with_rcl_consultation_correlation() -> None:
    version_a = (
        "Art. 1. Ustawa o ochronie danych.\nArt. 2. Kary finansowe wynoszą do 10 000 000 zł."
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


def test_radar_nie_zglasza_anomalii_gdy_mediana_pokrycia_jest_zerowa() -> None:
    """Regresja: `actual <= 0 * ANOMALY_RATIO` było prawdziwe dla każdego aktu bez wzmianek.

    Jeżeli akty porównywalne też nie miały pokrycia, brak wzmianek jest normą, a nie ciszą
    wokół tego jednego aktu — nie ma oczekiwania, wobec którego dałoby się mierzyć lukę.
    """
    res = SilenceRadarService.evaluate(
        SilenceRadarRequest(
            relevance_score=90.0,
            actual_media_mentions=0,
            stage=LegislativeStage.SEJM_READING_3,
            peer_media_mentions=[0, 0, 0, 0, 0],
        )
    )

    assert res.is_anomaly is False
    assert res.expected_mentions == 0.0
    # Luka bez oczekiwania jest niepoliczalna — `None`, a nie zero sugerujące brak różnicy.
    assert res.silence_gap is None


def test_radar_wykrywa_cisze_przy_realnym_pokryciu_porownywalnych() -> None:
    res = SilenceRadarService.evaluate(
        SilenceRadarRequest(
            relevance_score=90.0,
            actual_media_mentions=1,
            stage=LegislativeStage.SEJM_READING_3,
            peer_media_mentions=[10, 12, 14, 20, 30],
        )
    )

    assert res.is_anomaly is True
    assert res.expected_mentions == 14.0
    assert res.silence_gap == 13.0
