"""Podział odpowiedzi modelu na sekcje streszczenia po znacznikach.

Cytowania wykluczają wyjścia strukturalne (`output_config.format` zwraca 400), więc struktura
odpowiedzi jest wymuszana promptem i rozpoznawana tutaj. Świadoma wymiana: parsowanie
znaczników jest ryzykiem operacyjnym, zmyślony cytat byłby ryzykiem produktowym.
"""

import re

from barometr_ai.domain.llm import SECTION_MARKERS, CitedSegment, SummarySection

NO_BASIS_TOKEN = "BRAK_PODSTAWY"

_MARKER_PATTERN = re.compile("|".join(re.escape(marker) for marker in SECTION_MARKERS))


def parse_sections(segments: list[CitedSegment]) -> dict[SummarySection, list[CitedSegment]]:
    """Grupuje segmenty odpowiedzi w sekcje, zachowując kolejność i odwołania.

    Odwołania bloku przypisywane są do każdego niepustego fragmentu treści z tego bloku.
    W praktyce blok cytowany zawiera wyłącznie treść — znaczniki model emituje osobno —
    więc przypisanie jest jednoznaczne. Treść przed pierwszym znacznikiem jest pomijana.
    """
    sections: dict[SummarySection, list[CitedSegment]] = {section: [] for section in SummarySection}
    current: SummarySection | None = None

    for segment in segments:
        cursor = 0
        text = segment.text
        for match in _MARKER_PATTERN.finditer(text):
            _append_run(sections, current, text[cursor : match.start()], segment)
            current = SECTION_MARKERS[match.group(0)]
            cursor = match.end()
        _append_run(sections, current, text[cursor:], segment)

    return sections


def _append_run(
    sections: dict[SummarySection, list[CitedSegment]],
    section: SummarySection | None,
    run: str,
    source: CitedSegment,
) -> None:
    """Dokłada fragment treści do bieżącej sekcji, o ile niesie cokolwiek poza białymi znakami."""
    if section is None:
        return
    stripped = run.strip()
    if not stripped or stripped == NO_BASIS_TOKEN:
        return
    sections[section].append(CitedSegment(text=stripped, citations=source.citations))


def markers_seen(segments: list[CitedSegment]) -> set[SummarySection]:
    """Zwraca sekcje, których znacznik faktycznie wystąpił w odpowiedzi modelu.

    Sam podział na sekcje tego nie rozstrzyga: sekcja pusta wygląda identycznie, gdy model
    świadomie wpisał w nią BRAK_PODSTAWY i gdy w ogóle nie wypisał jej znacznika. Pierwsze
    jest poprawną odpowiedzią, drugie — awarią formatu, po której nie wolno oddać pustego
    streszczenia jako wyniku.
    """
    seen: set[SummarySection] = set()
    for segment in segments:
        for match in _MARKER_PATTERN.finditer(segment.text):
            seen.add(SECTION_MARKERS[match.group(0)])
    return seen
