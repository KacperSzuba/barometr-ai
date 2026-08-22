"""Testy jednostkowe silnika klastrowania i deduplikacji strumienia."""

import pytest

from barometr_ai.adapters.fastembed_adapter import FastEmbedAdapter
from barometr_ai.domain.models import ClusterRequest, DocumentItem
from barometr_ai.services.clustering_service import ClusteringService


@pytest.fixture(scope="module")
def clustering_service() -> ClusteringService:
    embedder = FastEmbedAdapter()
    return ClusteringService(embedder=embedder)


def test_cluster_deduplication(clustering_service: ClusteringService) -> None:
    docs = [
        DocumentItem(id="d1", content="Sejm przyjął ustawę o cenach maksymalnych energii elektrycznej na rok 2026."),
        DocumentItem(id="d2", content="sejm przyjął ustawę o cenach maksymalnych energii elektrycznej na rok 2026."),  # Dokładny duplikat (różne wielkości liter)
        DocumentItem(id="d3", content="Ustawa o zamrożeniu cen prądu i energii przegłosowana przez Sejm."),  # Bliski semantyczny duplikat
        DocumentItem(id="d4", content="Nowe zasady ochrony zwierząt i parków krajobrazowych wchodzą w życie."),  # Inny temat
    ]

    request = ClusterRequest(documents=docs, threshold=0.55)
    response = clustering_service.cluster_documents(request)

    assert response.total_processed == 4
    assert len(response.clusters) == 2  # 2 klastry: energia (d1, d2, d3) i przyroda (d4)
    assert response.reduction_rate == 0.50  # 4 dokumenty zredukowane do 2 klastrów (50% redukcji)