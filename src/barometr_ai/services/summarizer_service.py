"""Generowanie ustrukturyzowanych streszczeń z bezwzględną proweniencją znakową (F1)."""

import logging

from barometr_ai.core.config import Settings
from barometr_ai.domain.llm import (
    SECTION_LABELS,
    CitedSegment,
    SourceDocument,
    SummarySection,
)
from barometr_ai.domain.models import SummarizeRequest, SummarizeResponse
from barometr_ai.domain.provenance import GroundedStatement, ProvenanceSpan
from barometr_ai.ports.llm import LLMPort
from barometr_ai.services.cost_tracker_service import CostTrackerService
from barometr_ai.services.prompt_registry import (
    SUMMARY_EXECUTIVE_PL,
    PromptTemplate,
    build_rejection_feedback,
)
from barometr_ai.services.provenance_service import ProvenanceService
from barometr_ai.services.section_parser import parse_sections

logger = logging.getLogger(__name__)

#: Sekcje, dla których odpowiedź zwraca pojedyncze twierdzenie.
_SINGULAR_SECTIONS = (
    SummarySection.WHAT_CHANGED,
    SummarySection.WHO_IS_AFFECTED,
    SummarySection.NEXT_STEPS,
)

#: Zgrubny narzut promptu w tokenach, doliczany do bramki budżetowej przed wywołaniem.
_PROMPT_OVERHEAD_TOKENS = 800


class SummarizerService:
    """Orkiestruje generowanie streszczeń i weryfikację każdego zdania pod kątem cytowań.

    Sekcja, której nie da się zakotwiczyć w tekście źródłowym, wraca do modelu z korektą.
    Po wyczerpaniu prób jest odrzucana i raportowana w `rejected_sections` — nigdy nie jest
    uzupełniana zastępczą treścią. To realizacja punktu 4 zadania F1, opisanego w
    specyfikacji jako nieusuwalny.
    """

    def __init__(
        self,
        *,
        llm: LLMPort,
        cost_tracker: CostTrackerService,
        settings: Settings,
        template: PromptTemplate = SUMMARY_EXECUTIVE_PL,
    ) -> None:
        self._llm = llm
        self._cost_tracker = cost_tracker
        self._settings = settings
        self._template = template

    async def summarize(
        self, request: SummarizeRequest, *, client_id: str = "unknown"
    ) -> SummarizeResponse:
        """Tworzy streszczenie z powiązaniem każdego punktu do konkretnego miejsca w tekście."""
        source_text = request.content
        document = SourceDocument(document_id=request.document_id, text=source_text)
        # Trzy sekcje bazowe są stałe; `max_sentences` steruje liczbą ustaleń dodatkowych.
        max_additional = max(0, request.max_sentences - len(_SINGULAR_SECTIONS))

        accepted: dict[SummarySection, list[GroundedStatement]] = {}
        resolved: set[SummarySection] = set()
        rejections: list[tuple[SummarySection, str]] = []
        feedback = ""
        prompt_tokens = completion_tokens = 0
        estimated = False
        attempt = 0

        for attempt in range(1, self._settings.llm_regeneration_attempts + 2):
            self._cost_tracker.ensure_capacity(self.estimate_request_tokens(source_text))

            prompt = self._template.render(
                document=document,
                audience=request.target_audience,
                max_additional=max_additional,
                feedback=feedback,
            )
            completion = await self._llm.complete(prompt)

            prompt_tokens += completion.prompt_tokens
            completion_tokens += completion.completion_tokens
            estimated = estimated or completion.tokens_are_estimated
            # Tokeny są już wydane u dostawcy — księgujemy je nawet ponad budżet,
            # a kolejne wywołanie zablokuje `ensure_capacity`.
            self._cost_tracker.record_usage(
                client_id=client_id, tokens=completion.total_tokens, enforce=False
            )

            sections = parse_sections(completion.segments)
            rejections = []

            for section in SummarySection:
                if section in resolved:
                    continue
                statements, reason = self._ground_section(
                    sections[section], document_id=request.document_id, source_text=source_text
                )
                if statements:
                    accepted[section] = statements
                    resolved.add(section)
                elif reason is None:
                    # Model jawnie zadeklarował brak podstawy — to poprawna odpowiedź.
                    resolved.add(section)
                else:
                    rejections.append((section, reason))

            if not rejections:
                break

            logger.info(
                "Odrzucono sekcje przez walidator proweniencji",
                extra={
                    "document_id": request.document_id,
                    "attempt": attempt,
                    "sections": [section.value for section, _ in rejections],
                },
            )
            feedback = build_rejection_feedback(attempt + 1, rejections)

        return self._build_response(
            request=request,
            accepted=accepted,
            rejected=[section for section, _ in rejections],
            attempts=attempt,
            total_tokens=prompt_tokens + completion_tokens,
            estimated=estimated,
        )

    def _ground_section(
        self, segments: list[CitedSegment], *, document_id: str, source_text: str
    ) -> tuple[list[GroundedStatement], str | None]:
        """Zamienia segmenty sekcji na twierdzenia z proweniencją.

        Zwraca `(statements, None)` przy sukcesie, `([], None)` gdy model nie zaproponował
        treści dla sekcji, oraz `([], powód)` gdy treść była, ale nie dało się jej zakotwiczyć.
        Tylko ten ostatni przypadek uruchamia regenerację.
        """
        if not segments:
            return [], None

        statements: list[GroundedStatement] = []
        uncited = 0
        drifted = 0

        for segment in segments:
            spans: list[ProvenanceSpan] = []
            for citation in segment.citations:
                span = ProvenanceService.to_provenance_span(
                    citation, document_id=document_id, source_text=source_text
                )
                if span is None:
                    drifted += 1
                    continue
                spans.append(span)
            if not spans:
                uncited += 1
                continue
            statements.append(GroundedStatement(text=segment.text, provenance=spans))

        if statements:
            return statements, None
        if drifted:
            return [], f"odwolanie nie zgadza sie z trescia dokumentu ({drifted} szt.)"
        return [], f"tresc bez odwolania do dokumentu zrodlowego ({uncited} szt.)"

    def _build_response(
        self,
        *,
        request: SummarizeRequest,
        accepted: dict[SummarySection, list[GroundedStatement]],
        rejected: list[SummarySection],
        attempts: int,
        total_tokens: int,
        estimated: bool,
    ) -> SummarizeResponse:
        def first(section: SummarySection) -> GroundedStatement | None:
            found = accepted.get(section)
            return found[0] if found else None

        bullets = [
            statement for section in SummarySection for statement in accepted.get(section, [])
        ]

        return SummarizeResponse(
            document_id=request.document_id,
            summary_bullets=bullets,
            what_changed=first(SummarySection.WHAT_CHANGED),
            who_is_affected=first(SummarySection.WHO_IS_AFFECTED),
            next_steps=first(SummarySection.NEXT_STEPS),
            additional_findings=accepted.get(SummarySection.ADDITIONAL_FINDINGS, []),
            rejected_sections=[SECTION_LABELS[section] for section in rejected],
            attempts=attempts,
            is_generative=self._llm.is_generative,
            tokens_are_estimated=estimated,
            model_version=self._llm.model_version,
            prompt_version=self._template.version,
            total_tokens=total_tokens,
        )

    @staticmethod
    def estimate_request_tokens(source_text: str) -> int:
        """Zgrubny szacunek wyłącznie do bramki budżetowej przed wywołaniem.

        Publiczny, bo tej samej bramki używa orkiestrator kaskady, żeby zawęzić top-N
        zanim wyśle cokolwiek do modelu.

        Rozliczenie opiera się na realnym `usage` z odpowiedzi dostawcy, nie na tej liczbie.
        Mnożnik 2,5 odzwierciedla gorszą tokenizację polszczyzny niż angielska reguła 1,3.
        """
        return int(len(source_text.split()) * 2.5) + _PROMPT_OVERHEAD_TOKENS
