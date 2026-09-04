"""Testy orkiestratora kaskady kosztowej L1 → L2 → L3."""

import pytest

from barometr_ai.core.config import Settings
from barometr_ai.domain.advanced_models import LegislativeStage
from barometr_ai.domain.pipeline_models import PipelineDocument, PipelineRequest
from barometr_ai.services.cascade_service import (
    SKIP_BELOW_THRESHOLD,
    SKIP_BUDGET,
    SKIP_OUTSIDE_TOP_N,
    SKIP_TOO_SHORT,
    CascadeService,
)
from barometr_ai.services.clustering_service import ClusteringService
from barometr_ai.services.cost_tracker_service import CostTrackerService
from barometr_ai.services.relevance_scorer import RelevanceScorerService
from barometr_ai.services.summarizer_service import SummarizerService

#: Treść musi przekroczyć MIN_SUMMARIZABLE_LENGTH, żeby klaster w ogóle wszedł do L3.
AKT_ENERGIA = (
    "Sejm przyjął ustawę o cenach maksymalnych energii elektrycznej na rok 2026. "
    "Nowe taryfy obejmą gospodarstwa domowe oraz małe i średnie przedsiębiorstwa."
)
AKT_ZDROWIE = (
    "Ministerstwo Zdrowia ogłosiło nową listę leków refundowanych obowiązującą od kwietnia. "
    "Na wykazie znalazły się terapie onkologiczne finansowane dotąd w programach lekowych."
)
AKT_ODPADY = (
    "Rada Ministrów przyjęła rozporządzenie w sprawie gospodarowania odpadami komunalnymi. "
    "Nowe stawki opłat zaczną obowiązywać w gminach od początku przyszłego kwartału."
)


def build_cascade(
    embedder, *, daily_budget: int = 1_000_000
) -> tuple[CascadeService, CostTrackerService]:
    """Kaskada na adapterze zastępczym — deterministyczna, bez sieci i bez kosztu."""
    from barometr_ai.adapters.heuristic_llm_adapter import HeuristicLLMAdapter

    settings = Settings(_env_file=None)
    cost_tracker = CostTrackerService(daily_budget=daily_budget)
    cascade = CascadeService(
        clustering=ClusteringService(embedder=embedder),
        scorer=RelevanceScorerService(),
        summarizer=SummarizerService(
            llm=HeuristicLLMAdapter(), cost_tracker=cost_tracker, settings=settings
        ),
        cost_tracker=cost_tracker,
    )
    return cascade, cost_tracker


async def test_rozmiar_klastra_zasila_scoring(embedder) -> None:
    """Sedno kaskady: akt opisany przez wiele redakcji jest istotniejszy niż opisany raz.
    Tej informacji nie ma żaden pojedynczy dokument — wie ją dopiero warstwa L1."""
    cascade, _ = build_cascade(embedder)

    docs = [
        # Trzy przedruki tego samego aktu — po deduplikacji jeden klaster o trzech członkach.
        PipelineDocument(id="e1", content=AKT_ENERGIA, stage=LegislativeStage.SEJM_READING_3),
        PipelineDocument(
            id="e2", content=AKT_ENERGIA.upper(), stage=LegislativeStage.SEJM_READING_3
        ),
        PipelineDocument(
            id="e3", content=AKT_ENERGIA.replace(".", " ;"), stage=LegislativeStage.SEJM_READING_3
        ),
        # Ten sam etap legislacyjny, ale tylko jedno źródło.
        PipelineDocument(id="z1", content=AKT_ZDROWIE, stage=LegislativeStage.SEJM_READING_3),
    ]

    response = await cascade.run(PipelineRequest(documents=docs, top_n=5, cluster_threshold=0.95))

    by_representative = {c.representative_document_id: c for c in response.clusters}
    energia = by_representative["e1"]
    zdrowie = by_representative["z1"]

    assert len(energia.member_document_ids) == 3
    assert len(zdrowie.member_document_ids) == 1
    # Wszystkie czynniki poza zasięgiem źródeł są identyczne, więc różnica wyniku bierze się
    # wyłącznie z rozmiaru klastra.
    assert energia.relevance.total_score > zdrowie.relevance.total_score


async def test_top_n_zaweza_wejscie_do_warstwy_platnej(embedder) -> None:
    """Model widzi wyłącznie top-N. Reszta wraca z jawnym powodem, a nie znika."""
    cascade, _ = build_cascade(embedder)
    docs = [
        PipelineDocument(id="a", content=AKT_ENERGIA, stage=LegislativeStage.ENACTED),
        PipelineDocument(id="b", content=AKT_ZDROWIE, stage=LegislativeStage.SEJM_COMMITTEE),
        PipelineDocument(id="c", content=AKT_ODPADY, stage=LegislativeStage.GOV_WORK),
    ]

    response = await cascade.run(PipelineRequest(documents=docs, top_n=1, cluster_threshold=0.95))

    assert response.summarized_count == 1
    assert len(response.summaries) == 1
    assert response.clusters_formed == 3
    # Wszystkie trzy klastry są raportowane, mimo że streszczony został jeden.
    assert len(response.clusters) == 3

    wybrane = [c for c in response.clusters if c.selected_for_summary]
    pominiete = [c for c in response.clusters if not c.selected_for_summary]
    assert len(wybrane) == 1
    assert wybrane[0].representative_document_id == "a"  # najwyższy etap = najwyższy wynik
    assert all(c.skip_reason == SKIP_OUTSIDE_TOP_N for c in pominiete)


async def test_klastry_posortowane_malejaco_po_istotnosci(embedder) -> None:
    cascade, _ = build_cascade(embedder)
    docs = [
        PipelineDocument(id="niski", content=AKT_ODPADY, stage=LegislativeStage.GOV_WORK),
        PipelineDocument(id="wysoki", content=AKT_ENERGIA, stage=LegislativeStage.ENACTED),
        PipelineDocument(id="sredni", content=AKT_ZDROWIE, stage=LegislativeStage.SEJM_COMMITTEE),
    ]

    response = await cascade.run(PipelineRequest(documents=docs, top_n=5, cluster_threshold=0.95))

    wyniki = [c.relevance.total_score for c in response.clusters]
    assert wyniki == sorted(wyniki, reverse=True)
    assert [c.representative_document_id for c in response.clusters] == [
        "wysoki",
        "sredni",
        "niski",
    ]


async def test_prog_istotnosci_odcina_przed_top_n(embedder) -> None:
    """`min_relevance` działa przed miejscem w rankingu — akt na wczesnym etapie nie trafia
    do modelu nawet wtedy, gdy nikt inny nie kandyduje."""
    cascade, _ = build_cascade(embedder)
    docs = [
        PipelineDocument(id="a", content=AKT_ENERGIA, stage=LegislativeStage.ENACTED),
        PipelineDocument(id="b", content=AKT_ODPADY, stage=LegislativeStage.GOV_WORK),
    ]

    response = await cascade.run(
        PipelineRequest(documents=docs, top_n=10, min_relevance=40.0, cluster_threshold=0.95)
    )

    odciete = [c for c in response.clusters if c.skip_reason == SKIP_BELOW_THRESHOLD]
    assert odciete, "akt na etapie prac rządowych powinien wypaść poniżej progu 40"
    assert all(c.relevance.total_score < 40.0 for c in odciete)
    assert response.summarized_count == len(response.clusters) - len(odciete)


async def test_budzet_zaweza_n_zamiast_wywracac_zadanie(embedder) -> None:
    """Wyczerpany budżet nie może kończyć się błędem całego żądania: to, co policzone,
    jest poprawnym wynikiem, a reszta wraca z powodem.

    Budżet 1800 tokenów mieści dokładnie dwa z trzech streszczeń (jedno kosztuje ok. 830),
    więc test sprawdza faktyczne *zawężenie* N, a nie sytuację, w której nie powstaje nic.
    """
    cascade, cost_tracker = build_cascade(embedder, daily_budget=1800)
    docs = [
        PipelineDocument(id="a", content=AKT_ENERGIA, stage=LegislativeStage.ENACTED),
        PipelineDocument(id="b", content=AKT_ZDROWIE, stage=LegislativeStage.SENATE),
        PipelineDocument(id="c", content=AKT_ODPADY, stage=LegislativeStage.SEJM_COMMITTEE),
    ]

    response = await cascade.run(PipelineRequest(documents=docs, top_n=3, cluster_threshold=0.95))

    assert response.summarized_count == 2
    assert response.budget_exhausted is True
    assert cost_tracker.tokens_today <= 1800  # bramka stoi przed wywołaniem, nie po nim

    zablokowane = [c for c in response.clusters if c.skip_reason == SKIP_BUDGET]
    assert len(zablokowane) == 1
    # Odcięty został najmniej istotny klaster, a nie przypadkowy: kaskada streszcza
    # w kolejności istotności, więc budżet zabiera zawsze od dołu rankingu.
    assert zablokowane[0].representative_document_id == "c"
    assert zablokowane[0].relevance.total_score == min(
        c.relevance.total_score for c in response.clusters
    )


async def test_zerowy_budzet_nie_wywoluje_modelu(embedder) -> None:
    """Bramka stoi przed wywołaniem, nie po nim — przy zerowym budżecie model nie rusza."""
    cascade, _ = build_cascade(embedder, daily_budget=1)
    docs = [
        PipelineDocument(id="a", content=AKT_ENERGIA, stage=LegislativeStage.ENACTED),
        PipelineDocument(id="b", content=AKT_ZDROWIE, stage=LegislativeStage.SENATE),
    ]

    response = await cascade.run(PipelineRequest(documents=docs, top_n=2, cluster_threshold=0.95))

    assert response.summaries == []
    assert response.total_tokens == 0
    assert response.budget_exhausted is True
    # Brak streszczeń nie uprawnia do deklarowania, że cokolwiek wygenerował model.
    assert response.is_generative is False


async def test_za_krotki_reprezentant_wraca_z_powodem(embedder) -> None:
    """Kontrakt `SummarizeRequest` wymaga 50 znaków. Krótszy dokument nie może wywracać
    całej kaskady ani cicho znikać."""
    cascade, _ = build_cascade(embedder)
    docs = [
        PipelineDocument(id="krotki", content="Ustawa przyjęta.", stage=LegislativeStage.ENACTED),
        PipelineDocument(id="pelny", content=AKT_ENERGIA, stage=LegislativeStage.ENACTED),
    ]

    response = await cascade.run(PipelineRequest(documents=docs, top_n=5, cluster_threshold=0.95))

    krotki = next(c for c in response.clusters if c.representative_document_id == "krotki")
    assert krotki.skip_reason == SKIP_TOO_SHORT
    assert krotki.selected_for_summary is False
    assert response.summarized_count == 1


async def test_kazdy_dokument_jest_rozliczony(embedder) -> None:
    """Niezmiennik kaskady: żaden dokument wejściowy nie może zniknąć — albo jest w klastrze
    streszczonym, albo w pominiętym z podanym powodem."""
    cascade, _ = build_cascade(embedder)
    docs = [
        PipelineDocument(id=f"d{i}", content=tresc, stage=LegislativeStage.SEJM_COMMITTEE)
        for i, tresc in enumerate([AKT_ENERGIA, AKT_ZDROWIE, AKT_ODPADY, AKT_ENERGIA.upper()])
    ]

    response = await cascade.run(PipelineRequest(documents=docs, top_n=1, cluster_threshold=0.95))

    rozliczone = {mid for c in response.clusters for mid in c.member_document_ids}
    assert rozliczone == {d.id for d in docs}
    assert all(c.selected_for_summary or c.skip_reason is not None for c in response.clusters), (
        "klaster pominięty bez powodu to cicha strata dokumentu"
    )


async def test_redukcja_wolumenu_liczona_wobec_wejscia(embedder) -> None:
    cascade, _ = build_cascade(embedder)
    docs = [
        PipelineDocument(id=f"d{i}", content=tresc, stage=LegislativeStage.ENACTED)
        for i, tresc in enumerate([AKT_ENERGIA, AKT_ZDROWIE, AKT_ODPADY, AKT_ENERGIA.upper()])
    ]

    response = await cascade.run(PipelineRequest(documents=docs, top_n=1, cluster_threshold=0.95))

    assert response.total_documents == 4
    assert response.summarized_count == 1
    assert response.volume_reduction_rate == pytest.approx(0.75)
