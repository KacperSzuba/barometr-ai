"""Contracts and DTOs for AI endpoints."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from barometr_ai.domain.provenance import GroundedStatement
from barometr_ai.ports.embedder import InputType


class BaseDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


# --- /v1/embed ---
class EmbedRequest(BaseDTO):
    texts: list[str] = Field(
        ..., min_length=1, max_length=128, description="List of texts to embed"
    )
    normalize: bool = Field(default=True, description="L2 normalization for cosine similarity")
    input_type: InputType = Field(
        default="passage",
        description="passage = dokument do indeksu, query = zapytanie. Istotne dla modeli rodziny E5.",
    )


class EmbedResponse(BaseDTO):
    embeddings: list[list[float]]
    model_name: str
    model_version: str = Field(
        ..., description="Wersja wektorów; jej zmiana wymusza przeliczenie indeksu pgvector"
    )
    dimension: int
    count: int


# --- /v1/classify ---
class ClassifyRequest(BaseDTO):
    title: str = Field(..., min_length=3)
    content: str = Field(..., min_length=10)
    source_type: str = Field(default="legislation", description="legislation | rcl | media | bip")


class TopicCategory(BaseDTO):
    code: str = Field(..., description="PKD or regulatory taxonomy code")
    label: str = Field(..., description="Human readable name")
    confidence: float = Field(..., ge=0.0, le=1.0)


class ClassifyResponse(BaseDTO):
    topics: list[TopicCategory]
    primary_pkd: list[str]
    confidence_score: float
    model_version: str


# --- /v1/cluster ---
class DocumentItem(BaseDTO):
    id: str
    content: str
    embedding: list[float] | None = None


class ClusterRequest(BaseDTO):
    documents: list[DocumentItem] = Field(..., min_length=2)
    threshold: float = Field(default=0.82, ge=0.0, le=1.0)


class ClusterGroup(BaseDTO):
    cluster_id: str = Field(
        ...,
        description="Skrót ze składu klastra. Ten sam zestaw dokumentów daje ten sam "
        "identyfikator między wywołaniami, więc nadaje się na klucz cache'u.",
    )
    representative_document_id: str = Field(
        ..., description="Członek klastra położony najbliżej centroidu"
    )
    member_document_ids: list[str]
    cohesion_score: float = Field(
        ..., description="Średni kosinus członków klastra do jego centroidu"
    )


class ClusterResponse(BaseDTO):
    clusters: list[ClusterGroup]
    reduction_rate: float
    total_processed: int
    exact_duplicates_removed: int = Field(
        default=0,
        description="Dokumenty scalone jako przedruk identyczny po zniesieniu wielkości "
        "liter i interpunkcji. Serwis nie ma warstwy near-duplicate — uzasadnienie w ADR 0003.",
    )
    method: str = Field(
        default="", description="Metoda i progi użyte do wyliczenia podziału na klastry"
    )


# --- /v1/summarize ---
class SummarizeRequest(BaseDTO):
    document_id: str = Field(...)
    content: str = Field(..., min_length=50)
    max_sentences: int = Field(default=4, ge=1, le=20)
    target_audience: str = Field(default="executive", description="executive | legal_analyst")


class SummarizeResponse(BaseDTO):
    document_id: str
    summary_bullets: list[GroundedStatement]
    what_changed: GroundedStatement | None = None
    who_is_affected: GroundedStatement | None = None
    next_steps: GroundedStatement | None = None
    additional_findings: list[GroundedStatement] = Field(default_factory=list)
    rejected_sections: list[str] = Field(
        default_factory=list,
        description="Sekcje odrzucone przez walidator proweniencji po wyczerpaniu prób regeneracji",
    )
    attempts: int = Field(
        default=1, ge=1, description="Liczba wywołań modelu użytych do zbudowania odpowiedzi"
    )
    is_generative: bool = Field(
        ...,
        description="False, gdy odpowiedź pochodzi z adaptera zastępczego, a nie z modelu językowego",
    )
    tokens_are_estimated: bool = Field(
        default=False,
        description="True, gdy licznik tokenów jest szacunkiem lokalnym, a nie danymi dostawcy",
    )
    model_version: str
    prompt_version: str
    total_tokens: int


# --- /v1/usage ---
class UsageResponse(BaseDTO):
    """Rozliczenie zużycia tokenów dla klienta z nagłówka `X-Client-Id` (wymóg F1).

    Wszystkie liczby pochodzą z licznika budżetu; żadna nie jest szacunkiem. Zakres licznika
    jest podany wprost, bo przy magazynie w pamięci procesu wynik opisuje jeden proces, a nie
    cały serwis — odbiorca musi wiedzieć, którą z tych dwóch liczb czyta.
    """

    client_id: str = Field(..., description="Klient z nagłówka X-Client-Id; `unknown` gdy brak")
    client_tokens_today: int = Field(..., ge=0, description="Tokeny wydane dziś przez tego klienta")
    service_tokens_today: int = Field(..., ge=0, description="Tokeny wydane dziś przez cały serwis")
    daily_budget: int = Field(..., ge=1, description="Dzienny limit tokenów serwisu")
    usage_ratio: float = Field(
        ..., ge=0.0, description="service_tokens_today / daily_budget; może przekroczyć 1.0"
    )
    alert_threshold: float = Field(..., gt=0.0, le=1.0)
    alert_active: bool = Field(..., description="True gdy usage_ratio osiągnął próg alertu")
    budget_scope: Literal["process", "shared"] = Field(
        ...,
        description=(
            "process = licznik w pamięci jednego workera, liczby nie obejmują pozostałych "
            "replik. shared = licznik wspólny dla całego wdrożenia."
        ),
    )
