"""Awaryjny, deterministyczny generator ekstrakcyjny działający bez dostępu do sieci."""

import re

from barometr_ai.domain.llm import (
    SECTION_MARKERS,
    CitedSegment,
    CitedSpan,
    LLMCompletion,
    LLMPrompt,
    SummarySection,
)

_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")
_MIN_SENTENCE_LENGTH = 15
_MAX_ADDITIONAL_FINDINGS = 2
_NO_BASIS = "BRAK_PODSTAWY"

_MARKER_BY_SECTION: dict[SummarySection, str] = {
    section: marker for marker, section in SECTION_MARKERS.items()
}

_WHAT_CHANGED_KEYWORDS = (
    "wprowadza",
    "zmienia",
    "nowelizacja",
    "nowelizuje",
    "uchyla",
    "ustanawia",
    "określa",
    "podwyższa",
    "obniża",
    "zakazuje",
    "nakłada",
    "rozszerza",
    "znosi",
    "projekt ustawy",
    "rozporządzenie",
    "dodaje się",
    "otrzymuje brzmienie",
)
_WHO_IS_AFFECTED_KEYWORDS = (
    "przedsiębiorc",
    "obywatel",
    "podmiot",
    "pracodawc",
    "pracownik",
    "gmin",
    "samorząd",
    "właściciel",
    "podatnik",
    "konsument",
    "dotyczy",
    "stosuje się",
    "adresat",
    "branż",
    "instalacj",
    "spółk",
    "rolnik",
    "inwestor",
)
_NEXT_STEPS_KEYWORDS = (
    "wejdzie w życie",
    "wchodzi w życie",
    "wejść w życie",
    "vacatio legis",
    "termin",
    "konsultacj",
    "od dnia",
    "do dnia",
    "w ciągu",
    "obowiązek",
    "skierowano",
    "etap",
    "pierwsze czytanie",
    "drugie czytanie",
    "senat",
    "podpis prezydenta",
    "opiniowanie",
)


class HeuristicLLMAdapter:
    """Ekstrakcyjny generator regułowy zwracający ten sam kontrakt co prawdziwy model.

    To NIE jest model językowy i nie wolno przypisywać jego wynikom jakości generatywnej —
    `is_generative` zwraca False, a metadane raportują `heuristic-v0`, żeby odpowiedź API nie
    sugerowała rygoru, którego nie ma. Służy do pracy offline, testów deterministycznych
    i degradacji, gdy dostawca modelu jest niedostępny.

    Nie dokleja żadnych własnych sformułowań do zdań dokumentu: każdy segment jest dosłownym
    fragmentem tekstu źródłowego wraz z policzonym offsetem.
    """

    MODEL_NAME = "heuristic-extractive-pl"
    MODEL_VERSION = "heuristic-v0"

    @property
    def model_name(self) -> str:
        return self.MODEL_NAME

    @property
    def model_version(self) -> str:
        return self.MODEL_VERSION

    @property
    def is_generative(self) -> bool:
        return False

    async def complete(self, prompt: LLMPrompt) -> LLMCompletion:
        """Buduje szkic streszczenia wyłącznie z dosłownych zdań dokumentu źródłowego."""
        document = prompt.document.text
        segments = self._build_segments(document)
        rendered = "".join(segment.text for segment in segments)

        return LLMCompletion(
            segments=segments,
            model_name=self.MODEL_NAME,
            model_version=self.MODEL_VERSION,
            prompt_tokens=self._estimate_tokens(f"{prompt.system} {prompt.user} {document}"),
            completion_tokens=self._estimate_tokens(rendered),
            tokens_are_estimated=True,
            stop_reason="end_turn",
        )

    def _build_segments(self, document: str) -> list[CitedSegment]:
        """Wybiera zdania per sekcja i emituje je ze znacznikami oraz offsetami znakowymi."""
        spans = self._sentence_spans(document)
        segments: list[CitedSegment] = []
        used: set[int] = set()

        for section, keywords in (
            (SummarySection.WHAT_CHANGED, _WHAT_CHANGED_KEYWORDS),
            (SummarySection.WHO_IS_AFFECTED, _WHO_IS_AFFECTED_KEYWORDS),
            (SummarySection.NEXT_STEPS, _NEXT_STEPS_KEYWORDS),
        ):
            index = self._pick_sentence(spans, keywords, used)
            if index is None and section is SummarySection.WHAT_CHANGED and spans:
                index = (
                    0  # zdanie otwierające jest dopuszczalnym fallbackiem tylko dla istoty zmiany
                )
            segments.append(CitedSegment(text=f"{_MARKER_BY_SECTION[section]}\n"))
            if index is None:
                segments.append(CitedSegment(text=f"{_NO_BASIS}\n"))
                continue
            used.add(index)
            segments.append(self._segment_for(spans[index]))

        segments.append(
            CitedSegment(text=f"{_MARKER_BY_SECTION[SummarySection.ADDITIONAL_FINDINGS]}\n")
        )
        remaining = [span for i, span in enumerate(spans) if i not in used][
            :_MAX_ADDITIONAL_FINDINGS
        ]
        if not remaining:
            segments.append(CitedSegment(text=f"{_NO_BASIS}\n"))
        else:
            segments.extend(self._segment_for(span) for span in remaining)
        return segments

    @staticmethod
    def _segment_for(span: tuple[int, int, str]) -> CitedSegment:
        start, end, text = span
        return CitedSegment(
            text=f"{text}\n",
            citations=[CitedSpan(char_start=start, char_end=end, cited_text=text)],
        )

    @staticmethod
    def _sentence_spans(text: str) -> list[tuple[int, int, str]]:
        """Zwraca zdania wraz z bezwzględnymi offsetami w dokumencie źródłowym."""
        spans: list[tuple[int, int, str]] = []
        cursor = 0
        for raw in _SENTENCE_SPLIT_PATTERN.split(text):
            start = text.find(raw, cursor)
            if start == -1:
                continue
            cursor = start + len(raw)
            stripped = raw.strip()
            if len(stripped) <= _MIN_SENTENCE_LENGTH:
                continue
            offset = raw.find(stripped)
            spans.append((start + offset, start + offset + len(stripped), stripped))
        return spans

    @staticmethod
    def _pick_sentence(
        spans: list[tuple[int, int, str]], keywords: tuple[str, ...], used: set[int]
    ) -> int | None:
        best_index: int | None = None
        best_score = 0
        for index, (_, _, sentence) in enumerate(spans):
            if index in used:
                continue
            lowered = sentence.lower()
            score = sum(1 for keyword in keywords if keyword in lowered)
            if score > best_score:
                best_index, best_score = index, score
        return best_index

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Zgrubny szacunek lokalny. Zawyżony względem angielskiego, bo polski tokenizuje się gorzej.

        Wynik zawsze wraca z `tokens_are_estimated=True` — nie wolno go mylić z rozliczeniem
        dostawcy. Ścieżka produkcyjna czyta realne `usage` z odpowiedzi API.
        """
        return int(len(text.split()) * 2.5) + 1
