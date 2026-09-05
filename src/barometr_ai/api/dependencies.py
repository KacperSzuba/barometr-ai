"""Rejestracja serwisów i adapterów w kontenerze zależności FastAPI."""

import logging
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Header

from barometr_ai.adapters.anthropic_llm_adapter import AnthropicLLMAdapter
from barometr_ai.adapters.fastembed_adapter import FastEmbedAdapter
from barometr_ai.adapters.heuristic_llm_adapter import HeuristicLLMAdapter
from barometr_ai.adapters.in_memory_budget_store import InMemoryTokenBudgetStore
from barometr_ai.core.config import Settings, get_settings
from barometr_ai.ports.embedder import EmbedderPort
from barometr_ai.ports.llm import LLMPort
from barometr_ai.ports.token_budget import TokenBudgetStorePort
from barometr_ai.services.cascade_service import CascadeService
from barometr_ai.services.classifier_service import ClassifierService
from barometr_ai.services.clustering_service import ClusteringService
from barometr_ai.services.cost_tracker_service import CostTrackerService
from barometr_ai.services.novelty_detector import NoveltyDetectorService
from barometr_ai.services.relevance_scorer import RelevanceScorerService
from barometr_ai.services.summarizer_service import SummarizerService

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_embedder() -> EmbedderPort:
    settings = get_settings()
    return FastEmbedAdapter(
        settings.embedding_model_name,
        dimension=settings.embedding_dimension,
        model_version=settings.embedding_model_version,
        needs_e5_prefix=settings.embedding_needs_e5_prefix,
        batch_size=settings.embedding_batch_size,
    )


@lru_cache(maxsize=1)
def get_llm() -> LLMPort:
    """Zwraca adapter modelu generatywnego albo — przy braku klucza — adapter zastępczy.

    Degradacja jest jawna: `HeuristicLLMAdapter.is_generative` zwraca False, a ta wartość
    trafia do odpowiedzi API. Konsument nigdy nie dostaje wyniku heurystyki podanego jako
    wynik modelu. Przy `APP_ENV=production` brak klucza wywraca start serwisu (patrz Settings).
    """
    settings = get_settings()
    if not settings.llm_enabled:
        logger.warning(
            "Brak ANTHROPIC_API_KEY — streszczenia degradują do adaptera heurystycznego "
            "(is_generative=false w odpowiedziach API)."
        )
        return HeuristicLLMAdapter()
    return AnthropicLLMAdapter(
        api_key=settings.anthropic_api_key,
        model=settings.llm_model,
        timeout_seconds=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )


@lru_cache(maxsize=1)
def get_classifier_service() -> ClassifierService:
    return ClassifierService(embedder=get_embedder())


@lru_cache(maxsize=1)
def get_clustering_service() -> ClusteringService:
    return ClusteringService(embedder=get_embedder())


@lru_cache(maxsize=1)
def get_novelty_detector() -> NoveltyDetectorService:
    return NoveltyDetectorService(embedder=get_embedder())


@lru_cache(maxsize=1)
def get_token_budget_store() -> TokenBudgetStorePort:
    """Magazyn liczników budżetu. `memory` jest domyślny; `redis` czyni licznik współdzielonym.

    Import klienta Redisa jest leniwy, bo `redis` to opcjonalny extra — instalacja bez niego
    nie może wywracać startu serwisu skonfigurowanego na licznik w pamięci.
    """
    settings = get_settings()
    if settings.token_budget_backend == "memory":
        return InMemoryTokenBudgetStore()

    from redis import Redis

    from barometr_ai.adapters.redis_budget_store import RedisTokenBudgetStore

    logger.info("Licznik budżetu tokenów: Redis — limit obowiązuje wspólnie dla wszystkich replik.")
    return RedisTokenBudgetStore(Redis.from_url(settings.redis_url))


@lru_cache(maxsize=1)
def get_cost_tracker() -> CostTrackerService:
    settings = get_settings()
    return CostTrackerService(
        daily_budget=settings.daily_token_budget,
        alert_threshold=settings.cost_alert_threshold,
        store=get_token_budget_store(),
    )


@lru_cache(maxsize=1)
def get_summarizer_service() -> SummarizerService:
    return SummarizerService(
        llm=get_llm(),
        cost_tracker=get_cost_tracker(),
        settings=get_settings(),
    )


@lru_cache(maxsize=1)
def get_cascade_service() -> CascadeService:
    """Orkiestrator kaskady. Składa gotowe serwisy — sam nie tworzy żadnego adaptera."""
    return CascadeService(
        clustering=get_clustering_service(),
        scorer=RelevanceScorerService(),
        summarizer=get_summarizer_service(),
        cost_tracker=get_cost_tracker(),
    )


async def get_client_id(
    x_client_id: Annotated[str | None, Header(alias="X-Client-Id")] = None,
) -> str:
    """Identyfikator klienta do rozliczenia tokenów — wymóg dashboardu kosztu z zadania F1."""
    return x_client_id or "unknown"


SettingsDep = Annotated[Settings, Depends(get_settings)]
EmbedderDep = Annotated[EmbedderPort, Depends(get_embedder)]
SummarizerDep = Annotated[SummarizerService, Depends(get_summarizer_service)]
CostTrackerDep = Annotated[CostTrackerService, Depends(get_cost_tracker)]
ClientIdDep = Annotated[str, Depends(get_client_id)]


def reset_dependency_caches() -> None:
    """Czyści singletony — używane przez testy i przez rozgrzewkę przy starcie."""
    for cached in (
        get_embedder,
        get_llm,
        get_classifier_service,
        get_clustering_service,
        get_novelty_detector,
        get_token_budget_store,
        get_cost_tracker,
        get_summarizer_service,
        get_cascade_service,
    ):
        cached.cache_clear()
