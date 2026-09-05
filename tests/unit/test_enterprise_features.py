"""Testy jednostkowe modułów F2-F5: Nowość, NER, Framing, Briefing, Samorząd, Sondaże, k>=50."""

import pytest

from barometr_ai.domain.enterprise_models import (
    CitizenFeedbackRequest,
    FeedbackItem,
    FramingAnalysisRequest,
    FramingType,
    LocalDocType,
    LocalParseRequest,
    NERRequest,
    NoveltyRequest,
    NoveltyType,
    PollItem,
    PollsAggregateRequest,
)
from barometr_ai.services.entity_extractor import EntityExtractorService
from barometr_ai.services.framing_analyzer import StakeholderFramingService
from barometr_ai.services.gov_analytics_service import GovAnalyticsService
from barometr_ai.services.local_parser_service import LocalDocumentParserService
from barometr_ai.services.novelty_detector import NoveltyDetectorService


@pytest.mark.model
def test_novelty_detector_recycled_and_new(embedder) -> None:
    detector = NoveltyDetectorService(embedder)

    # 1. Dokładne powtórzenie znanych faktów -> RECYCLED
    req_recycled = NoveltyRequest(
        new_text="Sejm przyjął wczoraj ustawę o obniżeniu podatku PIT dla przedsiębiorców.",
        history_texts=[
            "Wczoraj Sejm uchwalił ustawę obniżającą stawki podatku dochodowego PIT dla firm."
        ],
    )
    res_recycled = detector.evaluate_novelty(req_recycled)
    assert res_recycled.classification in [NoveltyType.RECYCLED, NoveltyType.ELABORATION]

    # 2. Zupełnie nowy fakt -> NEW_EVENT
    req_new = NoveltyRequest(
        new_text="Katastrofa ekologiczna w dorzeczu Odry: wykryto obecność toksycznych alg.",
        history_texts=["Sejm obraduje nad zmianami w kodeksie spółek handlowych."],
    )
    res_new = detector.evaluate_novelty(req_new)
    assert res_new.classification == NoveltyType.NEW_EVENT
    assert res_new.is_suppressed is False


def test_ner_extraction() -> None:
    text = "Minister Adam Nowak złożył wniosek do Sejm Rzeczypospolitej Polskiej oraz powiadomił UOKiK."
    res = EntityExtractorService.extract_entities(NERRequest(text=text))

    entity_names = [e.name for e in res.entities]
    assert any("Minister Adam Nowak" in n for n in entity_names)
    assert any("Sejm" in n for n in entity_names)

    # Offsety musza wskazywac faktyczne miejsce wystapienia encji w tekscie.
    for entity in res.entities:
        assert text[entity.char_start : entity.char_end] == entity.name

    # Relacja zgadnieta z kolejnosci encji byla zmyslona. Do czasu rozstrzygania
    # tozsamosci i analizy zdania lista pozostaje pusta - patrz P1 w audycie.
    assert res.relations == []


def test_ner_matches_abbreviated_title() -> None:
    """Regresja: wzorzec wymagal tytulu i dokladnie dwoch czlonow, wiec gubil 'min. Nowak'."""
    res = EntityExtractorService.extract_entities(
        NERRequest(text="Jak podal min. Nowak, projekt trafi do Sejmu w przyszlym tygodniu.")
    )
    assert any("Nowak" in e.name for e in res.entities)


def test_framing_analysis() -> None:
    req = FramingAnalysisRequest(
        cluster_id="cluster_44",
        articles=[
            {
                "outlet": "Gazeta Finansowa",
                "title": "Nowy podatek uderzy w ceny i portfele Polaków",
                "content": "Koszty życia wzrosną.",
            },
            {
                "outlet": "Dziennik Prawny",
                "title": "Sejm przyjął ustawę: zobacz procedurę i terminy",
                "content": "Głosowanie i vacatio legis.",
            },
        ],
    )
    res = StakeholderFramingService.analyze_framing(req)
    assert len(res.outlets) == 2
    assert res.outlets[0].dominant_framing == FramingType.COST_OF_LIVING
    assert res.outlets[1].dominant_framing == FramingType.PROCEDURAL
    assert res.framing_diversity_score > 0.0


def test_local_document_parser() -> None:
    bip_mpzp = "Uchwała Nr XII/88/2026 Rady Gminy w sprawie miejscowego planu zagospodarowania przestrzennego (MPZP)."
    res = LocalDocumentParserService.parse_document(
        LocalParseRequest(bip_text=bip_mpzp, gmina_teryt="146501")
    )
    assert res.doc_type == LocalDocType.MPZP
    assert res.is_spatial_planning is True
    assert res.resolution_number is not None


def test_gov_polls_and_citizen_feedback_privacy() -> None:
    # 1. Sondaże
    polls_req = PollsAggregateRequest(
        polls=[
            PollItem(
                pollster="IBRiS",
                sample_size=1100,
                date="2026-08-01",
                results={"Partia A": 34.5, "Partia B": 31.0},
            ),
            PollItem(
                pollster="CBOS",
                sample_size=1000,
                date="2026-08-10",
                results={"Partia A": 36.0, "Partia B": 29.5},
            ),
        ]
    )
    res_polls = GovAnalyticsService.aggregate_polls(polls_req)
    assert "Partia A" in res_polls.pooled_average
    assert "IBRiS" in res_polls.house_effects

    # 2. Skrzynka z bezpiecznikiem k >= 50
    # Tworzymy 60 wiadomości o energii (spełnia k >= 50) i 10 o edukacji (poniżej progu k=50)
    messages = [
        FeedbackItem(id=f"e_{i}", message="Wysokie ceny prądu i energii.") for i in range(60)
    ]
    messages.extend([FeedbackItem(id=f"s_{i}", message="Brak miejsc w szkole.") for i in range(10)])

    fb_req = CitizenFeedbackRequest(messages=messages, min_k_threshold=50)
    res_fb = GovAnalyticsService.process_citizen_feedback(fb_req)

    # Tylko klastry z count >= 50 są ujawniane
    assert len(res_fb.clusters) == 1
    assert res_fb.clusters[0].count == 60
    assert res_fb.suppressed_count_below_k == 10  # 10 wiadomości zostało bezpiecznie wstrzymanych
