"""Kontrakty domenowe warstwy generatywnej (LLM) — niezależne od dostawcy i frameworka.

Model nie przepisuje cytatów. Dokument źródłowy jest przekazywany dostawcy jako osobny,
zaindeksowany blok, a odwołania wracają jako offsety znakowe policzone po stronie API.
Dzięki temu odrzucenie sekcji oznacza realny brak podstawy w tekście, a nie znormalizowaną
spację albo półpauzę zamienioną na dywiz.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class SummarySection(StrEnum):
    """Sekcje streszczenia wykonawczego wymagane przez zadanie F1."""

    WHAT_CHANGED = "what_changed"
    WHO_IS_AFFECTED = "who_is_affected"
    NEXT_STEPS = "next_steps"
    ADDITIONAL_FINDINGS = "additional_findings"


#: Znaczniki, po których dzielona jest odpowiedź modelu. Cytowania wykluczają wyjścia
#: strukturalne (`output_config.format` zwraca 400), więc struktura jest wymuszana promptem
#: i rozpoznawana po znacznikach — świadoma wymiana opisana w ADR 0002.
SECTION_MARKERS: dict[str, SummarySection] = {
    "[CO_SIE_ZMIENIA]": SummarySection.WHAT_CHANGED,
    "[KOGO_DOTYCZY]": SummarySection.WHO_IS_AFFECTED,
    "[CO_DALEJ]": SummarySection.NEXT_STEPS,
    "[USTALENIA_DODATKOWE]": SummarySection.ADDITIONAL_FINDINGS,
}

#: Etykiety sekcji używane w komunikatach korekty kierowanych z powrotem do modelu.
SECTION_LABELS: dict[SummarySection, str] = {
    SummarySection.WHAT_CHANGED: "co się zmienia",
    SummarySection.WHO_IS_AFFECTED: "kogo dotyczy",
    SummarySection.NEXT_STEPS: "co dalej",
    SummarySection.ADDITIONAL_FINDINGS: "ustalenia dodatkowe",
}


class SourceDocument(BaseModel):
    """Dokument źródłowy przekazywany dostawcy jako osobny blok treści.

    `str_strip_whitespace` jest celowo wyłączone: offsety zwracane przez dostawcę odnoszą się
    do tego dokładnie ciągu znaków, więc jakakolwiek normalizacja rozjechałaby proweniencję.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str = Field(..., min_length=1)
    title: str = Field(default="")
    text: str = Field(..., min_length=1)


class LLMPrompt(BaseModel):
    """Pojedyncze, wersjonowane wywołanie modelu generatywnego.

    Brak pola `temperature`: rodzina Claude 4.6+ odrzuca parametry próbkowania błędem 400.
    Głębokość rozumowania steruje się polem `effort`.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt_id: str = Field(..., min_length=1, description="Identyfikator promptu w rejestrze")
    prompt_version: str = Field(
        ..., min_length=1, description="Wersja promptu użyta do wygenerowania odpowiedzi"
    )
    system: str = Field(..., min_length=1)
    user: str = Field(..., min_length=1)
    document: SourceDocument
    max_output_tokens: int = Field(default=4096, ge=1)
    effort: str = Field(default="low", description="low | medium | high | xhigh | max")


class CitedSpan(BaseModel):
    """Odwołanie do fragmentu dokumentu źródłowego, wyrażone offsetem znakowym."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    char_start: int = Field(..., ge=0)
    char_end: int = Field(..., ge=0)
    cited_text: str = Field(default="")


class CitedSegment(BaseModel):
    """Fragment odpowiedzi modelu wraz z odwołaniami, które dostawca do niego przypisał.

    Segment bez odwołań jest dopuszczalny na tym poziomie (np. wiersz ze znacznikiem sekcji).
    Bramką jakości jest walidator proweniencji w warstwie serwisów, nie ten kontrakt.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(default="")
    citations: list[CitedSpan] = Field(default_factory=list)


class LLMCompletion(BaseModel):
    """Odpowiedź modelu wraz z odwołaniami i metadanymi rozliczeniowymi."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    segments: list[CitedSegment] = Field(default_factory=list)
    model_name: str = Field(..., min_length=1)
    model_version: str = Field(..., min_length=1)
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    cache_read_tokens: int = Field(default=0, ge=0)
    tokens_are_estimated: bool = Field(
        default=False,
        description="True, gdy zużycie tokenów jest szacunkiem lokalnym, a nie danymi od dostawcy",
    )
    stop_reason: str | None = Field(default=None)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def text(self) -> str:
        """Płaska treść odpowiedzi — do logowania i diagnostyki, nigdy do proweniencji."""
        return "".join(segment.text for segment in self.segments)
