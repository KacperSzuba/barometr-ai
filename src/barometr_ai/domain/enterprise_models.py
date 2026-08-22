"""Modele DTO dla faz F2-F5 (NER, Nowość, Framing, Briefing, Samorząd, Gov)."""

from enum import Enum

from pydantic import Field

from barometr_ai.domain.models import BaseDTO
from barometr_ai.domain.provenance import GroundedStatement


# --- F2: /v1/novelty ---
class NoveltyType(str, Enum):
    NEW_EVENT = "new_event"          # Zupełnie nowe zdarzenie w sprawie
    ELABORATION = "elaboration"      # Rozwinięcie / nowe szczegóły
    RECYCLED = "recycled"            # Powtórzenie znanych faktów (do ukrycia)
    COMMENTARY = "commentary"        # Publicystyka / opinia


class NoveltyRequest(BaseDTO):
    new_text: str = Field(..., min_length=10)
    history_texts: list[str] = Field(default_factory=list)
    similarity_threshold: float = Field(default=0.80)


class NoveltyResponse(BaseDTO):
    classification: NoveltyType
    novelty_score: float = Field(..., ge=0.0, le=1.0, description="1.0 = całkowita nowość, 0.0 = pełny recykling")
    highest_similarity: float
    is_suppressed: bool = Field(..., description="True jeśli materiał jest recyklingiem i powinien być ukryty")


# --- F2: /v1/ner ---
class EntityType(str, Enum):
    PERSON = "person"                # Poseł, minister, urzędnik
    INSTITUTION = "institution"      # Sejm, Ministerstwo, UOKiK, KNF
    COMPANY = "company"              # Spółka, bank, podmiot gospodarczy
    LEGAL_ACT = "legal_act"          # Druk sejmowy, ustawa, Dz.U.


class ExtractedEntity(BaseDTO):
    name: str
    entity_type: EntityType
    char_start: int
    char_end: int
    role: str | None = None          # wnioskodawca, sprawozdawca, zgłaszający uwagę


class EntityRelation(BaseDTO):
    source_entity: str
    target_entity: str
    relation_type: str               # SUBMITTED, AMENDED, REGULATES, OPPOSES


class NERRequest(BaseDTO):
    text: str = Field(..., min_length=10)


class NERResponse(BaseDTO):
    entities: list[ExtractedEntity]
    relations: list[EntityRelation]


# --- F3: /v1/framing ---
class FramingType(str, Enum):
    COST_OF_LIVING = "cost_of_living"  # Wpływ na portfel obywatela
    PROCEDURAL = "procedural"          # Przebieg legislacyjny / terminy
    POLITICAL = "political"            # Spór partyjny / koalicja
    EXPERT = "expert"                  # Analiza prawno-ekonomiczna


class MediaOutletFraming(BaseDTO):
    outlet_name: str
    dominant_framing: FramingType
    neutrality_score: float = Field(..., ge=0.0, le=1.0)
    ownership_transparency: str


class FramingAnalysisRequest(BaseDTO):
    cluster_id: str
    articles: list[dict[str, str]] = Field(..., min_length=2)


class FramingAnalysisResponse(BaseDTO):
    cluster_id: str
    outlets: list[MediaOutletFraming]
    framing_diversity_score: float


# --- F3: /v1/briefing ---
class BriefingRequest(BaseDTO):
    topic: str
    document_ids: list[str]
    timeframe_months: int = Field(default=6, ge=1, le=24)
    raw_texts: list[str] = Field(..., min_length=1)


class BriefingResponse(BaseDTO):
    topic: str
    executive_summary: list[GroundedStatement]
    timeline_milestones: list[dict[str, str]]
    stakeholders_summary: str
    next_anticipated_steps: str


# --- F4: /v1/local/parse ---
class LocalDocType(str, Enum):
    UCHWALA_RADY = "uchwala_rady"
    PROTOKOL_SESJI = "protokol_sesji"
    BUDGET_UCHWALA = "budget_uchwala"
    MPZP = "mpzp"


class LocalParseRequest(BaseDTO):
    bip_text: str = Field(..., min_length=20)
    gmina_teryt: str = Field(..., min_length=4)


class LocalParseResponse(BaseDTO):
    doc_type: LocalDocType
    resolution_number: str | None = None
    subject: str
    is_spatial_planning: bool
    budget_impact_pln: float | None = None
    summary_plain_polish: str


# --- F5: /v1/gov/polls ---
class PollItem(BaseDTO):
    pollster: str
    sample_size: int
    date: str
    results: dict[str, float]  # partia -> procent


class PollsAggregateRequest(BaseDTO):
    polls: list[PollItem] = Field(..., min_length=2)
    half_life_days: int = Field(default=14)


class PollsAggregateResponse(BaseDTO):
    pooled_average: dict[str, float]
    confidence_error_margins: dict[str, float]
    house_effects: dict[str, dict[str, float]]  # pollster -> partia -> odchylenie
    methodology_note: str


# --- F5: /v1/gov/feedback ---
class FeedbackItem(BaseDTO):
    id: str
    message: str


class CitizenFeedbackRequest(BaseDTO):
    messages: list[FeedbackItem]
    min_k_threshold: int = Field(default=50)


class FeedbackCluster(BaseDTO):
    topic: str
    paraphrase_summary: str
    count: int = Field(..., ge=50, description="Nigdy nie ujawniane poniżej progu k >= 50")
    sentiment: str


class CitizenFeedbackResponse(BaseDTO):
    clusters: list[FeedbackCluster]
    suppressed_count_below_k: int
    privacy_guarantee: str