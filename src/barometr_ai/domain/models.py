"""Contracts and DTOs for AI endpoints."""

from pydantic import BaseModel, ConfigDict, Field

from barometr_ai.domain.provenance import GroundedStatement


class BaseDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


# --- /v1/embed ---
class EmbedRequest(BaseDTO):
    texts: list[str] = Field(..., min_length=1, max_length=128, description="List of texts to embed")
    normalize: bool = Field(default=True, description="L2 normalization for cosine similarity")


class EmbedResponse(BaseDTO):
    embeddings: list[list[float]]
    model_version: str
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
    cluster_id: str
    representative_document_id: str
    member_document_ids: list[str]
    cohesion_score: float


class ClusterResponse(BaseDTO):
    clusters: list[ClusterGroup]
    reduction_rate: float
    total_processed: int


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
    model_version: str
    prompt_version: str
    total_tokens: int
