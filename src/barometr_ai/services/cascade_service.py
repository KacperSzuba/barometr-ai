"""Orkiestrator kaskady kosztowej: L1 klastrowanie → L2 scoring → top-N → L3 streszczenia.

Do tej pory warstwy istniały jako osobne endpointy, a łączenie ich było po stronie backendu.
Kaskada opisana w ARCHITECTURE.md żyła więc w dokumentacji, nie w kodzie — nic nie wybierało
top-N i nic nie przekazywało wyniku klastrowania do streszczania.

Sedno przepływu jest w dwóch miejscach:

* **Rozmiar klastra zasila scoring.** `sources_count` w modelu istotności to liczba
  dokumentów w klastrze, a nie liczba podana z zewnątrz. Akt opisany przez dwanaście
  redakcji jest istotniejszy niż ten sam akt opisany raz — i dopiero L1 to wie.
* **Budżet zawęża N, zamiast wywracać żądanie.** Przed każdym wywołaniem modelu sprawdzamy
  `can_afford`. Klaster, który się nie mieści, wraca z `skip_reason`, a nie znika po cichu.

Serwis pozostaje bezstanowy (ADR 0001): nie ma tu cache'u streszczeń. `cluster_id` jest
wyprowadzony ze składu klastra, więc ten sam zestaw dokumentów daje ten sam identyfikator
między wywołaniami i to backend może po nim cache'ować.
"""

import asyncio
import logging

from barometr_ai.core.exceptions import BudgetExceededError
from barometr_ai.domain.advanced_models import ScoreRequest, ScoreResponse
from barometr_ai.domain.models import (
    ClusterGroup,
    ClusterRequest,
    DocumentItem,
    SummarizeRequest,
    SummarizeResponse,
)
from barometr_ai.domain.pipeline_models import (
    PipelineDocument,
    PipelineRequest,
    PipelineResponse,
    RankedCluster,
)
from barometr_ai.services.clustering_service import ClusteringService
from barometr_ai.services.cost_tracker_service import CostTrackerService
from barometr_ai.services.relevance_scorer import RelevanceScorerService
from barometr_ai.services.summarizer_service import SummarizerService

logger = logging.getLogger(__name__)

#: Minimalna długość treści przyjmowana przez `SummarizeRequest`. Klaster, którego
#: reprezentant jest krótszy, nie ma czego streszczać — wraca z jawnym powodem.
MIN_SUMMARIZABLE_LENGTH = 50

SKIP_BELOW_THRESHOLD = "istotność poniżej progu min_relevance"
SKIP_OUTSIDE_TOP_N = "poza top-N"
SKIP_BUDGET = "dzienny budżet tokenów wyczerpany"
SKIP_TOO_SHORT = f"treść reprezentanta krótsza niż {MIN_SUMMARIZABLE_LENGTH} znaków"


class CascadeService:
    """Spina trzy warstwy w jedno przejście, tak żeby model widział tylko top-N klastrów."""

    def __init__(
        self,
        *,
        clustering: ClusteringService,
        scorer: RelevanceScorerService,
        summarizer: SummarizerService,
        cost_tracker: CostTrackerService,
    ) -> None:
        self._clustering = clustering
        self._scorer = scorer
        self._summarizer = summarizer
        self._cost_tracker = cost_tracker

    async def run(
        self, request: PipelineRequest, *, client_id: str = "unknown"
    ) -> PipelineResponse:
        """Przepuszcza wsad przez kaskadę i zwraca streszczenia wyłącznie dla top-N klastrów."""
        by_id = {document.id: document for document in request.documents}

        # --- L1: klastrowanie. Inferencja embeddingów jest CPU-bound, więc poza pętlą zdarzeń.
        cluster_response = await asyncio.to_thread(
            self._clustering.cluster_documents,
            ClusterRequest(
                documents=[
                    DocumentItem(id=doc.id, content=doc.content, embedding=doc.embedding)
                    for doc in request.documents
                ],
                threshold=request.cluster_threshold,
            ),
        )

        # --- L2: scoring istotności każdego klastra, malejąco.
        scored = [(group, self._score_cluster(group, by_id)) for group in cluster_response.clusters]
        scored.sort(key=lambda pair: (-pair[1].total_score, pair[0].cluster_id))

        # --- Wybór top-N: próg istotności, potem miejsce w rankingu.
        planned: list[tuple[ClusterGroup, str | None]] = []
        admitted = 0
        for group, score in scored:
            if score.total_score < request.min_relevance:
                planned.append((group, SKIP_BELOW_THRESHOLD))
            elif admitted >= request.top_n:
                planned.append((group, SKIP_OUTSIDE_TOP_N))
            else:
                planned.append((group, None))
                admitted += 1

        # --- L3: streszczenia w kolejności istotności, do wyczerpania budżetu.
        summaries: list[SummarizeResponse] = []
        decisions: list[str | None] = []
        budget_exhausted = False

        for group, skip in planned:
            if skip is not None:
                decisions.append(skip)
                continue

            representative = by_id[group.representative_document_id]
            if len(representative.content) < MIN_SUMMARIZABLE_LENGTH:
                decisions.append(SKIP_TOO_SHORT)
                continue

            # Bramka budżetu *przed* wywołaniem: zawęża N zamiast wywracać żądanie w połowie.
            # `SummarizerService` sprawdza to samo u siebie — tu chodzi o to, żeby do modelu
            # nie poszło nic, czego nie stać, a nie o reagowanie na wyjątek po fakcie.
            estimated_tokens = self._summarizer.estimate_request_tokens(representative.content)
            if budget_exhausted or not self._cost_tracker.can_afford(estimated_tokens):
                budget_exhausted = True
                decisions.append(SKIP_BUDGET)
                continue

            try:
                summary = await self._summarizer.summarize(
                    SummarizeRequest(
                        document_id=representative.id,
                        content=representative.content,
                        max_sentences=request.max_sentences,
                        target_audience=request.target_audience,
                    ),
                    client_id=client_id,
                )
            except BudgetExceededError:
                # Budżet zamyka kaskadę, ale nie wywraca żądania: to, co już policzone,
                # jest poprawnym wynikiem, a pominięte klastry niosą jawny powód.
                logger.warning(
                    "Kaskada zatrzymana przez budżet tokenów",
                    extra={"cluster_id": group.cluster_id, "client_id": client_id},
                )
                budget_exhausted = True
                decisions.append(SKIP_BUDGET)
                continue

            summaries.append(summary)
            decisions.append(None)

        clusters = [
            RankedCluster(
                cluster_id=group.cluster_id,
                representative_document_id=group.representative_document_id,
                member_document_ids=group.member_document_ids,
                cohesion_score=group.cohesion_score,
                relevance=score,
                selected_for_summary=decision is None,
                skip_reason=decision,
            )
            for (group, _), (_, score), decision in zip(planned, scored, decisions, strict=True)
        ]

        total_documents = len(request.documents)
        return PipelineResponse(
            clusters=clusters,
            summaries=summaries,
            total_documents=total_documents,
            clusters_formed=len(cluster_response.clusters),
            summarized_count=len(summaries),
            volume_reduction_rate=round(1.0 - len(summaries) / total_documents, 3),
            total_tokens=sum(summary.total_tokens for summary in summaries),
            budget_exhausted=budget_exhausted,
            # Pusta lista streszczeń nie uprawnia do deklarowania, że cokolwiek wygenerował
            # model — zgodnie z §4 AGENTS.md metadane opisują to, co faktycznie się wydarzyło.
            is_generative=bool(summaries) and all(s.is_generative for s in summaries),
            method=(
                f"L1: {cluster_response.method}; L2: scoring liniowy z rozmiarem klastra jako "
                f"liczbą źródeł; L3: top-{request.top_n} powyżej istotności "
                f"{request.min_relevance}, z bramką budżetu tokenów przed każdym wywołaniem"
            ),
        )

    def _score_cluster(
        self, group: ClusterGroup, by_id: dict[str, PipelineDocument]
    ) -> ScoreResponse:
        """Liczy istotność klastra na jego reprezentancie, z rozmiarem klastra jako zasięgiem.

        Reprezentant jest najbliższy centroidowi, więc najlepiej opisuje temat klastra.
        Pozostałe metadane bierzemy właśnie od niego — poza `sources_count`, które jest
        własnością klastra, a nie pojedynczego dokumentu.
        """
        representative = by_id[group.representative_document_id]
        return self._scorer.calculate_score(
            ScoreRequest(
                stage=representative.stage,
                pkd_overlap_count=representative.pkd_overlap_count,
                sources_count=len(group.member_document_ids),
                diff_chars_changed=representative.diff_chars_changed,
                has_hard_deadline=representative.has_hard_deadline,
            )
        )
