"""Testy jednostkowe silnika klastrowania i deduplikacji strumienia."""

import pytest

from barometr_ai.core.exceptions import InvalidDocumentBatchError
from barometr_ai.domain.models import ClusterRequest, DocumentItem
from barometr_ai.ports.embedder import InputType
from barometr_ai.services.clustering_service import (
    MAX_DOCUMENTS,
    ClusteringService,
    content_fingerprint,
)

DEPESZA = (
    "Sejm przyjął ustawę o cenach maksymalnych energii elektrycznej na rok 2026. "
    "Nowe taryfy obejmą gospodarstwa domowe oraz małe i średnie przedsiębiorstwa. "
    "Rekompensaty dla sprzedawców energii wypłaca Zarządca Rozliczeń na wniosek."
)


class _StubEmbedder:
    """Embedder o zadanych z góry wektorach — pozwala testować logikę klastrowania
    bez zależności od tego, co akurat uzna model semantyczny."""

    def __init__(self, vectors: dict[str, list[float]], dimension: int = 3) -> None:
        self._vectors = vectors
        self._dimension = dimension
        self.calls: list[list[str]] = []

    @property
    def model_name(self) -> str:
        return "stub"

    @property
    def model_version(self) -> str:
        return "stub@v0"

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_texts(
        self,
        texts: list[str],
        normalize: bool = True,
        *,
        input_type: InputType = "passage",
    ) -> list[list[float]]:
        self.calls.append(list(texts))
        return [self._vectors[text] for text in texts]


@pytest.fixture
def clustering_service(embedder) -> ClusteringService:
    return ClusteringService(embedder=embedder)


@pytest.mark.model
def test_cluster_deduplication(clustering_service: ClusteringService) -> None:
    docs = [
        DocumentItem(
            id="d1",
            content="Sejm przyjął ustawę o cenach maksymalnych energii elektrycznej na rok 2026.",
        ),
        DocumentItem(
            id="d2",
            content="sejm przyjął ustawę o cenach maksymalnych energii elektrycznej na rok 2026.",
        ),  # Dokładny duplikat (różne wielkości liter)
        DocumentItem(
            id="d3", content="Ustawa o zamrożeniu cen prądu i energii przegłosowana przez Sejm."
        ),  # Bliski semantyczny duplikat
        DocumentItem(
            id="d4", content="Nowe zasady ochrony zwierząt i parków krajobrazowych wchodzą w życie."
        ),  # Inny temat
    ]

    request = ClusterRequest(documents=docs, threshold=0.55)
    response = clustering_service.cluster_documents(request)

    assert response.total_processed == 4
    assert len(response.clusters) == 2  # 2 klastry: energia (d1, d2, d3) i przyroda (d4)
    assert response.reduction_rate == 0.50  # 4 dokumenty zredukowane do 2 klastrów (50% redukcji)
    assert response.exact_duplicates_removed == 1  # d2 to przedruk d1 znak w znak


@pytest.mark.model
def test_wynik_nie_zalezy_od_kolejnosci_wejscia(clustering_service: ClusteringService) -> None:
    """Zachłanne przypisanie do pierwszego dokumentu dawało tu inny podział po odwróceniu
    listy. Aglomeracja łączy globalnie najpodobniejszą parę, więc podział jest ten sam."""
    docs = [
        DocumentItem(id="a", content="Sejm uchwalił nowe stawki podatku akcyzowego na paliwa."),
        DocumentItem(id="b", content="Nowelizacja akcyzy na paliwa przyjęta przez Sejm."),
        DocumentItem(id="c", content="Podatek akcyzowy od paliw silnikowych zostanie podniesiony."),
        DocumentItem(id="d", content="Ministerstwo Zdrowia ogłasza listę leków refundowanych."),
        DocumentItem(id="e", content="Nowe leki refundowane trafią na listę Ministerstwa Zdrowia."),
    ]

    forward = clustering_service.cluster_documents(ClusterRequest(documents=docs, threshold=0.60))
    backward = clustering_service.cluster_documents(
        ClusterRequest(documents=list(reversed(docs)), threshold=0.60)
    )

    def podzial(response) -> set[frozenset[str]]:
        return {frozenset(group.member_document_ids) for group in response.clusters}

    assert podzial(forward) == podzial(backward)
    # Identyfikatory wynikają ze składu klastra, więc też muszą się zgadzać.
    assert {g.cluster_id for g in forward.clusters} == {g.cluster_id for g in backward.clusters}
    assert [g.representative_document_id for g in forward.clusters] == [
        g.representative_document_id for g in backward.clusters
    ]


def test_odcisk_znosi_interpunkcje_i_wielkosc_liter() -> None:
    """Przedruk różniący się wyłącznie interpunkcją i wielkością liter to ten sam materiał.
    To jedyne rozluźnienie względem porównania znak w znak, jakie jest bezsporne."""
    assert content_fingerprint(DEPESZA) == content_fingerprint(
        DEPESZA.upper().replace(".", " ;").replace(",", "")
    )


def test_odcisk_rozroznia_negacje() -> None:
    """Sedno decyzji z ADR 0003: „obejmą" i „nie obejmą" to dokumenty o przeciwnym
    znaczeniu. Każda metoda progowa na pokryciu leksykalnym scala je (Jaccard 0,955),
    dlatego warstwy near-duplicate tu nie ma. Odcisk dokładny je rozdziela."""
    assert content_fingerprint(DEPESZA) != content_fingerprint(
        DEPESZA.replace("obejmą", "nie obejmą")
    )


def test_odcisk_rozroznia_zmieniony_przedmiot_regulacji() -> None:
    """Ten sam szablon depeszy z podmienionym przedmiotem regulacji ma pokrycie leksykalne
    0,878 — wyżej niż niejeden prawdziwy przedruk. Nie wolno go scalić na poziomie L1."""
    assert content_fingerprint(DEPESZA) != content_fingerprint(
        DEPESZA.replace("energii elektrycznej", "wody pitnej")
    )


def test_gotowe_embeddingi_pomijaja_inferencje() -> None:
    """Backend trzyma wektory w pgvector. Dokument, który je niesie, nie może wywoływać
    modelu — pole `embedding` było wcześniej ignorowane."""
    embedder = _StubEmbedder(vectors={})
    docs = [
        DocumentItem(id="a", content="pierwszy", embedding=[1.0, 0.0, 0.0]),
        DocumentItem(id="b", content="drugi", embedding=[0.98, 0.199, 0.0]),
        DocumentItem(id="c", content="trzeci", embedding=[0.0, 0.0, 1.0]),
    ]

    response = ClusteringService(embedder=embedder).cluster_documents(
        ClusterRequest(documents=docs, threshold=0.90)
    )

    assert embedder.calls == []  # żadnej inferencji
    assert {frozenset(g.member_document_ids) for g in response.clusters} == {
        frozenset({"a", "b"}),
        frozenset({"c"}),
    }


def test_liczy_tylko_brakujace_wektory() -> None:
    """Wsad mieszany: jeden dokument z gotowym wektorem, jeden bez."""
    embedder = _StubEmbedder(vectors={"bez wektora": [0.0, 1.0, 0.0]})
    docs = [
        DocumentItem(id="a", content="z wektorem", embedding=[1.0, 0.0, 0.0]),
        DocumentItem(id="b", content="bez wektora"),
    ]

    ClusteringService(embedder=embedder).cluster_documents(
        ClusterRequest(documents=docs, threshold=0.90)
    )

    assert embedder.calls == [["bez wektora"]]


def test_odrzuca_wektor_o_zlym_wymiarze() -> None:
    embedder = _StubEmbedder(vectors={})
    docs = [
        DocumentItem(id="a", content="pierwszy", embedding=[1.0, 0.0, 0.0]),
        DocumentItem(id="b", content="drugi", embedding=[1.0, 0.0]),
    ]

    with pytest.raises(InvalidDocumentBatchError) as excinfo:
        ClusteringService(embedder=embedder).cluster_documents(
            ClusterRequest(documents=docs, threshold=0.90)
        )

    assert excinfo.value.details["expected_dimension"] == 3
    assert excinfo.value.details["received_dimension"] == 2


def test_odrzuca_wsad_ponad_limit() -> None:
    """Serwis nie próbkuje po cichu — cichy sampling zafałszowałby reduction_rate."""
    embedder = _StubEmbedder(vectors={})
    docs = [DocumentItem(id=f"d{i}", content=f"tresc {i}") for i in range(MAX_DOCUMENTS + 1)]

    with pytest.raises(InvalidDocumentBatchError) as excinfo:
        ClusteringService(embedder=embedder).cluster_documents(
            ClusterRequest(documents=docs, threshold=0.80)
        )

    assert excinfo.value.details["limit"] == MAX_DOCUMENTS
    assert embedder.calls == []  # limit sprawdzany przed inferencją


def test_spojnosc_liczona_wobec_centroidu() -> None:
    """`cohesion_score` to średni kosinus członków do centroidu. Poprzednia wersja
    uśredniała podobieństwa do pierwszego dokumentu i zawsze doliczała sztuczną jedynkę."""
    embedder = _StubEmbedder(vectors={})
    docs = [
        DocumentItem(id="a", content="pierwszy", embedding=[1.0, 0.0, 0.0]),
        DocumentItem(id="b", content="drugi", embedding=[0.0, 1.0, 0.0]),
    ]

    response = ClusteringService(embedder=embedder).cluster_documents(
        ClusterRequest(documents=docs, threshold=0.0)
    )

    assert len(response.clusters) == 1
    # Dwa wektory prostopadłe: centroid leży w połowie, kosinus do każdego to cos(45°).
    assert response.clusters[0].cohesion_score == pytest.approx(0.707, abs=1e-3)


def test_identyfikator_klastra_stabilny_dla_tego_samego_skladu() -> None:
    """Identyfikator ma być kluczem cache'u kaskady, więc nie może zależeć od tego, który
    dokument wypadł reprezentantem ani od kolejności w żądaniu."""
    embedder = _StubEmbedder(vectors={})
    wektory = {"a": [1.0, 0.0, 0.0], "b": [0.99, 0.141, 0.0], "c": [0.0, 0.0, 1.0]}
    docs = [DocumentItem(id=k, content=k, embedding=v) for k, v in wektory.items()]

    service = ClusteringService(embedder=embedder)
    pierwszy = service.cluster_documents(ClusterRequest(documents=docs, threshold=0.90))
    drugi = service.cluster_documents(
        ClusterRequest(documents=list(reversed(docs)), threshold=0.90)
    )

    assert [g.cluster_id for g in pierwszy.clusters] == [g.cluster_id for g in drugi.clusters]


def test_klastrowanie_jednego_dokumentu_jest_dobrze_okreslone() -> None:
    """Jeden dokument to jeden klaster o jednym członku i zerowej redukcji."""
    embedder = _StubEmbedder(vectors={DEPESZA: [1.0, 0.0, 0.0]})
    response = ClusteringService(embedder=embedder).cluster_documents(
        ClusterRequest(documents=[DocumentItem(id="d1", content=DEPESZA)])
    )

    assert len(response.clusters) == 1
    assert response.clusters[0].member_document_ids == ["d1"]
    assert response.total_processed == 1
    assert response.reduction_rate == 0.0
    assert response.exact_duplicates_removed == 0
