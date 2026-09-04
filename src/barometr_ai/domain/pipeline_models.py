"""Kontrakty orkiestratora kaskady kosztowej L1 → L2 → L3.

Moduł osobny, bo łączy DTO z `models` i `advanced_models`, a ten drugi importuje pierwszy.
"""

from pydantic import Field

from barometr_ai.domain.advanced_models import LegislativeStage, ScoreResponse
from barometr_ai.domain.models import BaseDTO, SummarizeResponse


class PipelineDocument(BaseDTO):
    """Dokument wejściowy kaskady wraz z metadanymi potrzebnymi do scoringu istotności.

    Metadane pochodzą z backendu — serwis AI jest bezstanowy i nie ma skąd ich wziąć sam.
    Wszystkie poza `stage` mają wartości domyślne, żeby wsad bez metadanych też przeszedł;
    scoring zwróci wtedy odpowiednio niski wynik z jawnym wytłumaczeniem.
    """

    id: str
    content: str
    embedding: list[float] | None = Field(
        default=None,
        description="Gotowy wektor z pgvector. Przekazany pozwala pominąć inferencję L1.",
    )
    stage: LegislativeStage = Field(
        default=LegislativeStage.GOV_WORK, description="Etap procesu legislacyjnego"
    )
    pkd_overlap_count: int = Field(
        default=0, ge=0, description="Liczba kodów PKD klienta trafionych przez ten akt"
    )
    diff_chars_changed: int = Field(
        default=0, ge=0, description="Skala zmian wobec poprzedniej wersji"
    )
    has_hard_deadline: bool = Field(default=False)


class PipelineRequest(BaseDTO):
    documents: list[PipelineDocument] = Field(..., min_length=1)
    cluster_threshold: float = Field(default=0.82, ge=0.0, le=1.0)
    top_n: int = Field(
        default=5, ge=1, le=50, description="Ile najistotniejszych klastrów trafia do L3"
    )
    min_relevance: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Klastry poniżej tego progu istotności nie trafiają do L3 nawet w top-N",
    )
    max_sentences: int = Field(default=4, ge=1, le=20)
    target_audience: str = Field(default="executive", description="executive | legal_analyst")


class RankedCluster(BaseDTO):
    """Klaster z warstwy L1 wraz z wynikiem istotności z L2 i decyzją o wejściu do L3."""

    cluster_id: str
    representative_document_id: str
    member_document_ids: list[str]
    cohesion_score: float
    relevance: ScoreResponse = Field(
        ..., description="Wynik istotności z rozbiciem na czynniki — „dlaczego to widzisz”"
    )
    selected_for_summary: bool
    skip_reason: str | None = Field(
        default=None,
        description="Dlaczego klaster nie trafił do L3. None, gdy trafił.",
    )


class PipelineResponse(BaseDTO):
    clusters: list[RankedCluster] = Field(
        ..., description="Wszystkie klastry, malejąco po istotności — także te pominięte"
    )
    summaries: list[SummarizeResponse] = Field(
        default_factory=list, description="Streszczenia klastrów wybranych do L3"
    )
    total_documents: int
    clusters_formed: int
    summarized_count: int
    volume_reduction_rate: float = Field(
        ...,
        description="Udział wolumenu odciętego przed warstwą płatną: "
        "1 − (liczba streszczeń / liczba dokumentów wejściowych)",
    )
    total_tokens: int
    budget_exhausted: bool = Field(
        default=False,
        description="True, gdy dzienny budżet tokenów zatrzymał kaskadę przed wyczerpaniem top-N",
    )
    is_generative: bool = Field(
        ...,
        description="False, gdy streszczenia pochodzą z adaptera zastępczego, a nie z modelu. "
        "Przy pustej liście streszczeń zawsze False.",
    )
    method: str
