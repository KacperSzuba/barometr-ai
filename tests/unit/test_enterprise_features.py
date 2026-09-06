"""Testy jednostkowe modułów F2-F5: Nowość, NER, Framing, Briefing, Samorząd, Sondaże, k>=50."""

import pytest
from pydantic import ValidationError

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
    RelationType,
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

    # Relacje pochodza wylacznie z jawnej konstrukcji czasownikowej i nios offsety fragmentu,
    # z ktorego wynikaja. Kolejnosc encji na liscie nie tworzy juz krawedzi.
    for relation in res.relations:
        evidence = text[relation.char_start : relation.char_end]
        assert evidence.startswith(relation.source_entity)
        assert evidence.endswith(relation.target_entity)
        assert relation.trigger in evidence


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


# --- Relacje NER: wyprowadzane z konstrukcji czasownikowej, nie z sąsiedztwa ---


def test_ner_relacja_z_jawnej_konstrukcji_czasownikowej() -> None:
    text = "Minister Adam Nowak powiadomił UOKiK."
    res = EntityExtractorService.extract_entities(NERRequest(text=text))

    assert len(res.relations) == 1
    relation = res.relations[0]
    assert relation.relation_type == RelationType.NOTIFIED
    assert relation.source_entity == "Minister Adam Nowak"
    assert relation.target_entity == "UOKiK"

    # Relacja bez zakotwiczenia jest nieodróżnialna od zgadniętej — offsety muszą wskazywać
    # fragment, z którego wynika, a `trigger` musi się w tym fragmencie faktycznie znajdować.
    evidence = text[relation.char_start : relation.char_end]
    assert evidence == "Minister Adam Nowak powiadomił UOKiK"
    assert relation.trigger in evidence


def test_ner_kierunek_relacji_wynika_z_szyku() -> None:
    res = EntityExtractorService.extract_entities(
        NERRequest(text="UOKiK nadzoruje KNF w zakresie rynku.")
    )
    assert [(r.source_entity, r.relation_type, r.target_entity) for r in res.relations] == [
        ("UOKiK", RelationType.REGULATES, "KNF")
    ]


def test_ner_nie_laczy_encji_z_dwoch_zdan() -> None:
    """Sąsiedztwo w tekście to nie relacja — to była właśnie odrzucona heurystyka."""
    res = EntityExtractorService.extract_entities(
        NERRequest(text="Sejm obradował do późna. Senat przyjął ustawę bez poprawek.")
    )
    assert len(res.entities) == 2
    assert res.relations == []


def test_ner_nie_zgaduje_podmiotu_w_zdaniu_wspolrzednym() -> None:
    """W „X złożył do Y oraz powiadomił Z" powiadamiającym jest X, nie sąsiadujący Y.

    Rozstrzygnięcie wymaga analizy składniowej, więc druga relacja nie powstaje — zamiast
    powstać z błędnym podmiotem.
    """
    res = EntityExtractorService.extract_entities(
        NERRequest(
            text=(
                "Minister Adam Nowak złożył wniosek do Sejm Rzeczypospolitej Polskiej "
                "oraz powiadomił UOKiK."
            )
        )
    )
    assert [(r.source_entity, r.relation_type, r.target_entity) for r in res.relations] == [
        ("Minister Adam Nowak", RelationType.SUBMITTED, "Sejm Rzeczypospolitej Polskiej")
    ]


def test_ner_nie_przekracza_granicy_zdania_skladowego() -> None:
    """Encja za przecinkiem należy do następnego zdania składowego, nie jest celem poprawki."""
    res = EntityExtractorService.extract_entities(
        NERRequest(
            text=(
                "Poseł Jan Kowalski zgłosił poprawkę do projektu, "
                "a Minister Anna Lis sprzeciwiła się KNF."
            )
        )
    )
    assert [(r.source_entity, r.relation_type, r.target_entity) for r in res.relations] == [
        ("Minister Anna Lis", RelationType.OPPOSES, "KNF")
    ]


# --- Publicystyka: gatunek rozpoznawany ze zwrotów, nie z podobieństwa wektorowego ---


def test_novelty_rozpoznaje_publicystyke(mock_embedder) -> None:
    detector = NoveltyDetectorService(mock_embedder)
    res = detector.evaluate_novelty(
        NoveltyRequest(
            new_text="Moim zdaniem ustawa o cenach energii jest źle napisana i nie pomoże nikomu.",
            history_texts=["Sejm uchwalił ustawę o cenach energii elektrycznej."],
        )
    )

    assert res.classification == NoveltyType.COMMENTARY
    assert res.is_suppressed is False
    # Decyzja musi być audytowalna: trafiony zwrot ma być widoczny w opisie metody.
    assert "moim zdaniem" in res.method


def test_novelty_recykling_ma_pierwszenstwo_przed_publicystyka(mock_embedder) -> None:
    """Duplikat jest ukrywany niezależnie od gatunku — bezpiecznikiem jest powtórzenie."""
    powtorzony = "Moim zdaniem ustawa o cenach energii jest chybiona."
    detector = NoveltyDetectorService(mock_embedder)
    res = detector.evaluate_novelty(NoveltyRequest(new_text=powtorzony, history_texts=[powtorzony]))

    assert res.classification == NoveltyType.RECYCLED
    assert res.is_suppressed is True


def test_novelty_tekst_sprawozdawczy_nie_jest_publicystyka(mock_embedder) -> None:
    detector = NoveltyDetectorService(mock_embedder)
    res = detector.evaluate_novelty(
        NoveltyRequest(
            new_text="Sejm uchwalił dziś ustawę o cenach maksymalnych energii elektrycznej.",
            history_texts=["Rada Ministrów przyjęła rozporządzenie o odpadach komunalnych."],
        )
    )

    assert res.classification == NoveltyType.NEW_EVENT
    assert "brak zwrotów opiniujących" in res.method


def test_novelty_publicystyka_bez_historii(mock_embedder) -> None:
    """Brak historii nie znaczy „nowe zdarzenie", jeśli tekst jest jawnie opinią."""
    detector = NoveltyDetectorService(mock_embedder)
    res = detector.evaluate_novelty(
        NoveltyRequest(
            new_text="Zdaniem autora projekt ustawy nie rozwiązuje problemu.", history_texts=[]
        )
    )

    assert res.classification == NoveltyType.COMMENTARY
    assert res.highest_similarity == 0.0


def test_skrzynka_nie_myli_oceny_z_cenami() -> None:
    """Regresja: rdzeń „cen" dopasowywany podciągiem trafiał w „Ocena", więc zgłoszenie
    o szkole lądowało w obszarze kosztów energii."""
    messages = [
        FeedbackItem(id=f"o_{i}", message="Ocena pracy szkoły jest niska.") for i in range(60)
    ]
    res = GovAnalyticsService.process_citizen_feedback(
        CitizenFeedbackRequest(messages=messages, min_k_threshold=50)
    )

    assert [cluster.topic for cluster in res.clusters] == ["Edukacja i opieka przedszkolna"]


def test_skrzynka_wrzuca_nieznany_temat_do_kosza() -> None:
    messages = [
        FeedbackItem(id=f"s_{i}", message="Scena kulturalna w gminie zamiera.") for i in range(60)
    ]
    res = GovAnalyticsService.process_citizen_feedback(
        CitizenFeedbackRequest(messages=messages, min_k_threshold=50)
    )

    assert [cluster.topic for cluster in res.clusters] == ["Inne sprawy lokalne"]


def test_framing_nie_liczy_trafien_wewnatrz_wyrazu() -> None:
    """Regresja: „cen" trafiało w „ocena", a „dane" w „oddane"/„sprzedane", więc materiał
    o ocenie skutków regulacji dostawał ramę kosztów życia."""
    res = StakeholderFramingService.analyze_framing(
        FramingAnalysisRequest(
            cluster_id="cluster_regresja",
            articles=[
                {
                    "outlet": "Serwis A",
                    "title": "Ocena skutków nowej regulacji",
                    "content": "Ocena wypadla pomyslnie.",
                },
                {
                    "outlet": "Serwis B",
                    "title": "Sprzedane mieszkania",
                    "content": "Oddane lokale w nowym budynku.",
                },
            ],
        )
    )

    assert [outlet.framing_signal_count for outlet in res.outlets] == [0, 0]
    assert all(outlet.dominant_framing is None for outlet in res.outlets)
    assert res.unclassified_count == 2


# --- Sondaże: waga świeżości i kotwica zaniku ---


def _poll(pollster: str, day: str, value: float, sample: int = 1000) -> PollItem:
    return PollItem(pollster=pollster, sample_size=sample, date=day, results={"X": value})


def test_half_life_days_wplywa_na_srednia() -> None:
    """Regresja: parametr był w kontrakcie i nie był czytany przez nic.

    Sondaż sprzed siedmiu miesięcy ważył dokładnie tyle co wczorajszy, niezależnie od
    zadeklarowanego okresu połowicznego zaniku.
    """
    polls = [_poll("A", "2026-01-01", 30.0), _poll("B", "2026-08-01", 40.0)]

    krotki = GovAnalyticsService.aggregate_polls(
        PollsAggregateRequest(polls=polls, half_life_days=1)
    ).pooled_average["X"]
    dlugi = GovAnalyticsService.aggregate_polls(
        PollsAggregateRequest(polls=polls, half_life_days=3650)
    ).pooled_average["X"]

    # Krótki okres połowiczny gasi stary sondaż, długi sprowadza wynik do średniej po próbie.
    assert krotki > dlugi
    assert krotki == pytest.approx(40.0, abs=0.1)
    assert dlugi == pytest.approx(35.0, abs=0.2)


def test_waga_polowieje_dokladnie_po_okresie_polowicznego_zaniku() -> None:
    """Sondaż starszy o `half_life_days` waży połowę — sprawdzone na policzalnym wejściu."""
    polls = [_poll("A", "2026-08-01", 0.0), _poll("B", "2026-08-11", 30.0)]

    res = GovAnalyticsService.aggregate_polls(PollsAggregateRequest(polls=polls, half_life_days=10))

    # Wagi 0,5 i 1,0 → (0*0,5 + 30*1,0) / 1,5 = 20,0
    assert res.pooled_average["X"] == pytest.approx(20.0, abs=0.01)
    assert "zanik wykładniczy świeżości" in res.methodology_note


def test_wynik_nie_zalezy_od_daty_wywolania() -> None:
    """Kotwicą jest najnowszy sondaż w zestawie, nie „dziś" — inaczej wynik zmieniałby się sam.

    Serwis jest bezstanowy i backend cache'uje po żądaniu; zegar w wzorze wywracałby jedno
    i drugie.
    """
    polls = [_poll("A", "2020-01-01", 30.0), _poll("B", "2020-01-15", 40.0)]
    stare = GovAnalyticsService.aggregate_polls(PollsAggregateRequest(polls=polls))

    przesuniete = [_poll("A", "2026-01-01", 30.0), _poll("B", "2026-01-15", 40.0)]
    nowe = GovAnalyticsService.aggregate_polls(PollsAggregateRequest(polls=przesuniete))

    # Ten sam odstęp między sondażami daje ten sam wynik, niezależnie od bezwzględnych dat.
    assert stare.pooled_average == nowe.pooled_average


def test_prog_k_ponizej_minimum_jest_odrzucany_na_kontrakcie() -> None:
    """Regresja: próg poniżej 50 przechodził walidację żądania, a bezpiecznik domykał dopiero
    walidator odpowiedzi — czyli błąd klienta wracał jako 500 zamiast czytelnego odrzucenia."""
    with pytest.raises(ValidationError):
        CitizenFeedbackRequest(
            messages=[FeedbackItem(id="x", message="Pojedyncze zgloszenie.")],
            min_k_threshold=1,
        )


def test_prog_k_wolno_podniesc() -> None:
    """Klient może żądać ostrzejszej ochrony, nigdy słabszej."""
    request = CitizenFeedbackRequest(
        messages=[FeedbackItem(id="x", message="Zgloszenie.")], min_k_threshold=200
    )
    assert request.min_k_threshold == 200


def test_niepoprawna_data_sondazu_jest_odrzucana() -> None:
    """Data steruje wagą, więc zapis nie do sparsowania musi paść na granicy kontraktu."""
    with pytest.raises(ValidationError):
        PollItem(pollster="A", sample_size=1000, date="wczoraj", results={"X": 30.0})
