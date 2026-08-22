"""Rejestracja serwisów F2-F5 w dependencies.py."""

from functools import lru_cache

from barometr_ai.adapters.fastembed_adapter import FastEmbedAdapter
from barometr_ai.core.config import get_settings
from barometr_ai.ports.embedder import EmbedderPort
from barometr_ai.services.classifier_service import ClassifierService
from barometr_ai.services.clustering_service import ClusteringService
from barometr_ai.services.cost_tracker_service import CostTrackerService
from barometr_ai.services.novelty_detector import NoveltyDetectorService
from barometr_ai.services.summarizer_service import SummarizerService


@lru_cache(maxsize=1)
def get_embedder() -> EmbedderPort:
    return FastEmbedAdapter()


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
def get_cost_tracker() -> CostTrackerService:
    settings = get_settings()
    return CostTrackerService(
        daily_budget=settings.daily_token_budget,
        alert_threshold=settings.cost_alert_threshold,
    )


@lru_cache(maxsize=1)
def get_summarizer_service() -> SummarizerService:
    return SummarizerService(cost_tracker=get_cost_tracker(), settings=get_settings())