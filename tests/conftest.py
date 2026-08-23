"""Pytest fixtures."""

import os

# Testy nie pobierają modelu produkcyjnego (2,24 GB). Ustawienie musi poprzedzać pierwszy
# import konfiguracji, bo `get_settings()` jest cache'owany na czas życia procesu.
os.environ.setdefault(
    "EMBEDDING_MODEL_NAME", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)
os.environ.setdefault("EMBEDDING_DIMENSION", "384")
os.environ.setdefault("EMBEDDING_MODEL_VERSION", "test-minilm@v1")
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("ANTHROPIC_API_KEY", "")

import pytest
from httpx import ASGITransport, AsyncClient

from barometr_ai.adapters.fastembed_adapter import FastEmbedAdapter
from barometr_ai.adapters.heuristic_llm_adapter import HeuristicLLMAdapter
from barometr_ai.core.config import Settings
from barometr_ai.main import create_app
from barometr_ai.ports.embedder import EmbedderPort
from barometr_ai.services.cost_tracker_service import CostTrackerService
from barometr_ai.services.summarizer_service import SummarizerService


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def async_client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None)


@pytest.fixture(scope="session")
def embedder() -> EmbedderPort:
    """Jeden załadowany model na całą sesję testową — ładowanie ONNX jest kosztowne."""
    settings = Settings(_env_file=None)
    return FastEmbedAdapter(
        settings.embedding_model_name,
        dimension=settings.embedding_dimension,
        model_version=settings.embedding_model_version,
        needs_e5_prefix=settings.embedding_needs_e5_prefix,
        batch_size=settings.embedding_batch_size,
    )


@pytest.fixture
def summarizer(settings: Settings) -> SummarizerService:
    """Serwis streszczeń na adapterze zastępczym — deterministyczny, bez sieci."""
    return SummarizerService(
        llm=HeuristicLLMAdapter(),
        cost_tracker=CostTrackerService(daily_budget=settings.daily_token_budget),
        settings=settings,
    )
