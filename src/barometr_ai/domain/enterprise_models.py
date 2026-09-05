"""Modele DTO dla faz F2-F5 (NER, Nowość, Framing, Briefing, Samorząd, Gov)."""

from enum import Enum

from pydantic import Field, model_validator

from barometr_ai.domain.models import BaseDTO
from barometr_ai.domain.provenance import GroundedStatement


# --- F2: /v1/novelty ---
class NoveltyType(str, Enum):
    NEW_EVENT = "new_event"  # Zupełnie nowe zdarzenie w sprawie
    ELABORATION = "elaboration"  # Rozwinięcie / nowe szczegóły
    RECYCLED = "recycled"  # Powtórzenie znanych faktów (do ukrycia)
    COMMENTARY = "commentary"  # Publicystyka / opinia


class NoveltyRequest(BaseDTO):
    new_text: str = Field(..., min_length=10)
    history_texts: list[str] = Field(default_factory=list)
    similarity_threshold: float = Field(
        default=0.85, ge=0.0, le=1.0, description="Próg uznania materiału za recykling"
    )
    elaboration_threshold: float = Field(
        default=0.65, ge=0.0, le=1.0, description="Próg uznania materiału za rozwinięcie tematu"
    )

    @model_validator(mode="after")
    def _thresholds_ordered(self) -> "NoveltyRequest":
        if self.elaboration_threshold > self.similarity_threshold:
            raise ValueError(
                "elaboration_threshold nie może być wyższy niż similarity_threshold — "
                "klasa ELABORATION byłaby wtedy nieosiągalna."
            )
        return self


class NoveltyResponse(BaseDTO):
    classification: NoveltyType
    novelty_score: float = Field(
        ..., ge=0.0, le=1.0, description="1.0 = całkowita nowość, 0.0 = pełny recykling"
    )
    highest_similarity: float
    is_suppressed: bool = Field(
        ..., description="True jeśli materiał jest recyklingiem i powinien być ukryty"
    )
    method: str = Field(..., description="Jawny opis metody i progów użytych do klasyfikacji")


# --- F2: /v1/ner ---
class EntityType(str, Enum):
    PERSON = "person"  # Poseł, minister, urzędnik
    INSTITUTION = "institution"  # Sejm, Ministerstwo, UOKiK, KNF
    COMPANY = "company"  # Spółka, bank, podmiot gospodarczy
    LEGAL_ACT = "legal_act"  # Druk sejmowy, ustawa, Dz.U.


class ExtractedEntity(BaseDTO):
    name: str
    entity_type: EntityType
    char_start: int
    char_end: int
    role: str | None = None  # wnioskodawca, sprawozdawca, zgłaszający uwagę


class RelationType(str, Enum):
    """Relacje wyprowadzane z jawnej konstrukcji czasownikowej w jednym zdaniu."""

    SUBMITTED = "submitted"  # złożył / skierował / wniósł do
    AMENDED = "amended"  # zgłosił poprawkę do / znowelizował
    REGULATES = "regulates"  # nadzoruje / sprawuje nadzór nad
    OPPOSES = "opposes"  # sprzeciwił się / zgłosił sprzeciw wobec
    NOTIFIED = "notified"  # powiadomił / poinformował


class EntityRelation(BaseDTO):
    """Relacja między dwiema encjami, zakotwiczona w konkretnym fragmencie tekstu.

    Offsety są obowiązkowe: relacja bez wskazania miejsca, z którego wynika, jest
    nieodróżnialna od zgadniętej — a to dokładnie ta awaria, przed którą broni architektura.
    """

    source_entity: str
    target_entity: str
    relation_type: RelationType
    char_start: int = Field(..., ge=0, description="Początek fragmentu uzasadniającego relację")
    char_end: int = Field(..., ge=0, description="Koniec fragmentu (wyłącznie)")
    trigger: str = Field(
        ..., min_length=1, description="Konstrukcja czasownikowa, z której relacja wynika"
    )


class NERRequest(BaseDTO):
    text: str = Field(..., min_length=10)


class NERResponse(BaseDTO):
    entities: list[ExtractedEntity]
    relations: list[EntityRelation]


# --- F3: /v1/framing ---
class FramingType(str, Enum):
    COST_OF_LIVING = "cost_of_living"  # Wpływ na portfel obywatela
    PROCEDURAL = "procedural"  # Przebieg legislacyjny / terminy
    POLITICAL = "political"  # Spór partyjny / koalicja
    EXPERT = "expert"  # Analiza prawno-ekonomiczna


class MediaOutletFraming(BaseDTO):
    outlet_name: str
    dominant_framing: FramingType | None = Field(
        default=None, description="None gdy sygnały leksykalne nie rozstrzygają ramy"
    )
    framing_signal_count: int = Field(
        default=0, ge=0, description="Liczba trafień leksykalnych, na których oparto klasyfikację"
    )
    neutrality_score: float | None = Field(
        default=None, description="None dopóki pomiar tonu wobec sprawy nie jest zaimplementowany"
    )
    ownership_transparency: str | None = Field(
        default=None, description="None dopóki brak integracji z rejestrem KRS wydawcy"
    )


class FramingAnalysisRequest(BaseDTO):
    cluster_id: str
    articles: list[dict[str, str]] = Field(..., min_length=2)


class FramingAnalysisResponse(BaseDTO):
    cluster_id: str
    outlets: list[MediaOutletFraming]
    framing_diversity_score: float = Field(
        ..., ge=0.0, le=1.0, description="Udział odrębnych ram wśród sklasyfikowanych materiałów"
    )
    unclassified_count: int = Field(
        default=0, ge=0, description="Materiały bez rozstrzygniętej ramy"
    )


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
    subject: str | None = Field(
        default=None, description="Przedmiot z formuły 'w sprawie ...'; None gdy nieobecna"
    )
    is_spatial_planning: bool
    budget_impact_pln: float | None = Field(
        default=None, description="Kwota wyłącznie z kontekstu budżetowego; None gdy niepewna"
    )
    detected_amounts_pln: list[float] = Field(
        default_factory=list, description="Wszystkie kwoty rozpoznane w dokumencie, w kolejności"
    )
    summary_plain_polish: str | None = Field(
        default=None,
        description="None dopóki streszczanie prostym językiem nie jest zaimplementowane",
    )


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
    confidence_error_margins: dict[str, float] = Field(
        ..., description="Połowa szerokości przedziału 95% w punktach procentowych, per partia"
    )
    house_effects: dict[str, dict[str, float]] = Field(
        ..., description="pollster -> partia -> odchylenie od średniej leave-one-out"
    )
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
    sentiment: str | None = Field(
        default=None, description="None dopóki analiza sentymentu nie jest zaimplementowana"
    )


class CitizenFeedbackResponse(BaseDTO):
    clusters: list[FeedbackCluster]
    suppressed_count_below_k: int
    privacy_guarantee: str
