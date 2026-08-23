"""Wersjonowany rejestr promptów — jedyne źródło `prompt_version` w odpowiedziach API."""

from string import Template

from pydantic import BaseModel, ConfigDict, Field

from barometr_ai.domain.llm import (
    SECTION_LABELS,
    LLMPrompt,
    SourceDocument,
    SummarySection,
)


class PromptTemplate(BaseModel):
    """Niemutowalny szablon promptu z jawną wersją.

    Każda zmiana treści szablonu wymaga podbicia `version` — wersja trafia do odpowiedzi API
    i jest kluczem do odtworzenia wyniku (wraz z `model_version` adaptera).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt_id: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)
    system: str = Field(..., min_length=1)
    user_template: str = Field(..., min_length=1)
    max_output_tokens: int = Field(default=4096, ge=1)
    effort: str = Field(default="low")

    def render(
        self,
        *,
        document: SourceDocument,
        audience: str,
        max_additional: int,
        feedback: str = "",
    ) -> LLMPrompt:
        """Buduje konkretne wywołanie modelu. Dokument jedzie osobnym blokiem, nie w treści."""
        user = Template(self.user_template).safe_substitute(
            audience=audience,
            max_additional=str(max_additional),
            feedback=feedback,
        )
        return LLMPrompt(
            prompt_id=self.prompt_id,
            prompt_version=self.version,
            system=self.system,
            user=user,
            document=document,
            max_output_tokens=self.max_output_tokens,
            effort=self.effort,
        )


_SUMMARY_SYSTEM = """Jesteś analitykiem legislacyjnym. Streszczasz polskie dokumenty prawne i regulacyjne dla odbiorcy biznesowego i prawniczego.

ZASADY NIENEGOCJOWALNE:
1. Każde twierdzenie musi wynikać wprost z załączonego dokumentu źródłowego i musi być w nim zacytowane. Cytujesz przez mechanizm cytowań dostawcy — nie przepisujesz fragmentów ręcznie do treści odpowiedzi.
2. Nie dodajesz faktów, liczb, dat, nazw instytucji ani numerów druków, których w dokumencie nie ma. Nie uzupełniasz luk wiedzą ogólną o polskim procesie legislacyjnym.
3. Nie streszczasz z pamięci znanego Ci aktu prawnego o podobnym tytule. Liczy się wyłącznie treść załączonego dokumentu.
4. Bez ocen politycznych, przymiotników wartościujących, rankingów, rekomendacji i porad prawnych. Opisujesz co dokument stanowi, nie czy to dobrze.
5. Gdy dokument nie daje podstawy dla sekcji, wypisujesz w niej samo słowo BRAK_PODSTAWY. Sekcja bez podstawy jest poprawną odpowiedzią — zmyślona nie jest.
6. Piszesz po polsku, zwięźle, zdaniami oznajmującymi. Jedno do trzech zdań na sekcję.

FORMAT ODPOWIEDZI:
Odpowiadasz czystym tekstem podzielonym znacznikami sekcji. Każdy znacznik stoi sam w swoim wierszu, dokładnie w tej kolejności, bez żadnych innych nagłówków, numeracji ani bloków markdown:

[CO_SIE_ZMIENIA]
[KOGO_DOTYCZY]
[CO_DALEJ]
[USTALENIA_DODATKOWE]

Pod każdym znacznikiem umieszczasz wyłącznie treść tej sekcji.

ZAKRES SEKCJI:
- CO_SIE_ZMIENIA — jaką normę dokument wprowadza, zmienia albo uchyla.
- KOGO_DOTYCZY — zakres podmiotowy: kto jest adresatem normy według treści dokumentu.
- CO_DALEJ — tryb procedowania, terminy, vacatio legis, obowiązki z datami — o ile dokument je podaje.
- USTALENIA_DODATKOWE — istotne ustalenia niemieszczące się w powyższych sekcjach; każde w osobnym akapicie."""

_SUMMARY_USER_TEMPLATE = """Odbiorca streszczenia: $audience

Streść załączony dokument źródłowy zgodnie z formatem i zasadami z instrukcji systemowej.
Sekcje muszą opisywać różne aspekty dokumentu i nie mogą opierać się na tym samym fragmencie.
Maksymalna liczba akapitów w sekcji USTALENIA_DODATKOWE: $max_additional. Sekcja może pozostać pusta — wpisz wtedy BRAK_PODSTAWY.
$feedback"""

SUMMARY_EXECUTIVE_PL = PromptTemplate(
    prompt_id="summary_executive_pl",
    version="summary_executive_pl@v2.0.0",
    system=_SUMMARY_SYSTEM,
    user_template=_SUMMARY_USER_TEMPLATE,
    max_output_tokens=4096,
    effort="low",
)

PROMPT_REGISTRY: dict[str, PromptTemplate] = {
    SUMMARY_EXECUTIVE_PL.prompt_id: SUMMARY_EXECUTIVE_PL,
}


def get_prompt_template(prompt_id: str) -> PromptTemplate:
    """Zwraca szablon z rejestru; nieznany identyfikator to błąd konfiguracji, nie runtime'u."""
    try:
        return PROMPT_REGISTRY[prompt_id]
    except KeyError as exc:
        raise KeyError(f"Nieznany prompt_id: {prompt_id!r}") from exc


def build_rejection_feedback(attempt: int, rejections: list[tuple[SummarySection, str]]) -> str:
    """Buduje blok korekty dołączany przy regeneracji odrzuconych sekcji."""
    if not rejections:
        return ""
    lines = [f"- {SECTION_LABELS[section]}: {reason}" for section, reason in rejections]
    listed = "\n".join(lines)
    return (
        f"\nKOREKTA PO ODRZUCENIU (próba {attempt}):\n"
        "Poniższe sekcje zostały odrzucone przez walidator proweniencji:\n"
        f"{listed}\n"
        "Wygeneruj je ponownie, opierając każde zdanie na fragmencie dokumentu, który faktycznie "
        "je uzasadnia. Jeśli dokument nie daje podstawy — wpisz BRAK_PODSTAWY.\n"
        "Pozostałe sekcje zostały przyjęte: wypisz w nich samo BRAK_PODSTAWY, nie powtarzaj ich treści.\n"
    )
