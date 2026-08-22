"""Rozszerzone kontrakty DTO dla zaawansowanych modułów AI (F1-F3)."""

from enum import Enum

from pydantic import Field

from barometr_ai.domain.models import BaseDTO


# --- /v1/score (Scoring Istotności) ---
class LegislativeStage(str, Enum):
    GOV_WORK = "gov_work"                  # Wykaz prac RM
    CONSULTATIONS = "consultations"        # Konsultacje publiczne
    SEJM_READING_1 = "sejm_reading_1"      # I czytanie
    SEJM_COMMITTEE = "sejm_committee"      # Prace w komisji
    SEJM_READING_3 = "sejm_reading_3"      # III czytanie / uchwalenie
    SENATE = "senate"                      # Senat
    PRESIDENT_SIGN = "president_sign"      # Podpis Prezydenta
    ENACTED = "enacted"                    # Opublikowane w Dz.U.


class ScoreRequest(BaseDTO):
    stage: LegislativeStage
    pkd_overlap_count: int = Field(default=1, ge=0)
    sources_count: int = Field(default=1, ge=1)
    diff_chars_changed: int = Field(default=0, ge=0)
    has_hard_deadline: bool = Field(default=False)


class ScoreExplanation(BaseDTO):
    factor: str
    weight: float
    contribution: float


class ScoreResponse(BaseDTO):
    total_score: float = Field(..., ge=0.0, le=100.0, description="Wynik istotności 0-100")
    urgency_level: str = Field(..., description="CRITICAL | HIGH | MEDIUM | LOW")
    explanations: list[ScoreExplanation]
    model_version: str


# --- /v1/radar (Radar Ciszy) ---
class SilenceRadarRequest(BaseDTO):
    relevance_score: float = Field(..., ge=0.0, le=100.0)
    actual_media_mentions: int = Field(..., ge=0)
    stage: LegislativeStage


class SilenceRadarResponse(BaseDTO):
    expected_mentions: float
    silence_gap: float
    is_anomaly: bool = Field(..., description="Prawda, jeśli zmiana przeszła bez należnego rozgłosu")
    explanation: str


# --- /v1/diff (Legal Tree Diff & RCL Match) ---
class LegalUnitDiff(BaseDTO):
    article_ref: str = Field(..., description="np. Art. 4 ust. 2 pkt a")
    change_type: str = Field(..., description="ADDED | MODIFIED | DELETED | RENUMBERED")
    old_text: str = Field(default="")
    new_text: str = Field(default="")
    consultation_comment_id: str | None = Field(default=None)
    consultation_submitter: str | None = Field(default=None)
    correlation_confidence: float | None = Field(default=None)


class LegalDiffRequest(BaseDTO):
    version_a_text: str
    version_b_text: str
    consultation_comments: list[dict[str, str]] = Field(default_factory=list)


class LegalDiffResponse(BaseDTO):
    changes: list[LegalUnitDiff]
    significant_changes_count: int
    matched_consultations_count: int


# --- /v1/forecast (Prognozy Legislacyjne) ---
class ForecastRequest(BaseDTO):
    stage: LegislativeStage
    sponsor_type: str = Field(..., description="GOVERNMENT | DEPUTIES | CITIZENS | SENATE")
    days_in_current_stage: int = Field(..., ge=0)
    governing_coalition_support: bool = Field(default=True)


class ForecastResponse(BaseDTO):
    enactment_probability: float = Field(..., ge=0.0, le=1.0)
    confidence_interval: tuple[float, float]
    historical_base_rate: float
    brier_score_target: float
    explanation: str