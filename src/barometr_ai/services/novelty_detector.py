"""Wykrywanie nowości vs. recykling informacji (F2)."""

import re

import numpy as np

from barometr_ai.domain.enterprise_models import (
    NoveltyRequest,
    NoveltyResponse,
    NoveltyType,
)
from barometr_ai.ports.embedder import EmbedderPort

#: Zwroty, które **same w sobie** znaczą, że autor podaje opinię, a nie relacjonuje zdarzenie.
#: Lista jest celowo wąska i pierwszoosobowa albo wprost metatekstowa: zwrot dopuszczający
#: odczytanie sprawozdawcze („należy zauważyć", „warto dodać") wpuszczałby do klasy
#: COMMENTARY zwykłe depesze. Jeden trafiony zwrot wystarcza, bo próg liczbowy („co najmniej
#: dwa") byłby stałą, której nie da się wywieść z pomiaru — patrz AGENTS.md §4.
#:
#: To rozpoznanie gatunku, nie ocena treści: serwis nie orzeka, czy opinia jest słuszna.
_COMMENTARY_MARKERS: tuple[str, ...] = (
    "moim zdaniem",
    "naszym zdaniem",
    "zdaniem autora",
    "zdaniem redakcji",
    "komentarz redakcyjny",
    "felieton",
    "w mojej ocenie",
    "uważam, że",
    "sądzę, że",
    "nie sposób zgodzić się",
    "trzeba przyznać, że",
    "pozwolę sobie",
)

_MARKER_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (marker, re.compile(r"\b" + re.escape(marker), re.IGNORECASE)) for marker in _COMMENTARY_MARKERS
)


class NoveltyDetectorService:
    """Odróżnia nowe fakty, rozwinięcia i publicystykę od odgrzewanego recyklingu depesz.

    Klasa `COMMENTARY` nie wynika z podobieństwa wektorowego — publicystyka nie jest poziomem
    nowości, tylko gatunkiem — lecz z jawnych zwrotów opiniujących w tekście. Rozpoznanie jest
    audytowalne: trafione zwroty trafiają do pola `method`.

    Recykling ma pierwszeństwo przed publicystyką: materiał powtarzający znany tekst jest
    ukrywany niezależnie od gatunku, bo bezpiecznikiem jest tu duplikat, a nie forma.

    Świadome ograniczenie, którego to nie usuwa: rozróżnienie RECYCLED od ELABORATION opiera
    się na maksymalnym podobieństwie do historii, a nie na ekstrakcji twierdzeń. Materiał
    dodający jeden nowy fakt do znanego tekstu pozostaje dla tej metody nieodróżnialny od
    recyklingu — pełna realizacja F2 wymaga porównania twierdzeń, nie wektorów.
    """

    def __init__(self, embedder: EmbedderPort) -> None:
        self._embedder = embedder

    @staticmethod
    def _commentary_markers(text: str) -> list[str]:
        """Zwraca trafione zwroty opiniujące — puste, gdy tekst jest sprawozdawczy."""
        return [marker for marker, pattern in _MARKER_PATTERNS if pattern.search(text)]

    def evaluate_novelty(self, request: NoveltyRequest) -> NoveltyResponse:
        markers = self._commentary_markers(request.new_text)

        if not request.history_texts:
            return NoveltyResponse(
                classification=(NoveltyType.COMMENTARY if markers else NoveltyType.NEW_EVENT),
                novelty_score=1.0,
                highest_similarity=0.0,
                is_suppressed=False,
                method=(
                    f"brak historii do porównania; zwroty opiniujące: {', '.join(markers)}"
                    if markers
                    else "brak historii do porównania"
                ),
            )

        new_vec = np.array(self._embedder.embed_texts([request.new_text], normalize=True)[0])
        history_vecs = self._embedder.embed_texts(request.history_texts, normalize=True)

        similarities = [float(np.dot(new_vec, np.array(vec))) for vec in history_vecs]
        max_sim = max(similarities) if similarities else 0.0

        # Progi pochodzą z żądania. Poprzednia wersja miała je zaszyte (0,85 / 0,65),
        # a pole `similarity_threshold` z kontraktu API było po cichu ignorowane.
        if max_sim >= request.similarity_threshold:
            # Duplikat jest ukrywany niezależnie od gatunku — bezpiecznikiem jest powtórzenie.
            classification = NoveltyType.RECYCLED
            is_suppressed = True
        elif markers:
            classification = NoveltyType.COMMENTARY
            is_suppressed = False
        elif max_sim >= request.elaboration_threshold:
            classification = NoveltyType.ELABORATION
            is_suppressed = False
        else:
            classification = NoveltyType.NEW_EVENT
            is_suppressed = False

        return NoveltyResponse(
            classification=classification,
            novelty_score=round(max(0.0, min(1.0, 1.0 - max_sim)), 3),
            highest_similarity=round(max_sim, 3),
            is_suppressed=is_suppressed,
            method=(
                f"maksymalne podobieństwo kosinusowe do {len(request.history_texts)} tekstów "
                f"historycznych; progi: recykling >= {request.similarity_threshold}, "
                f"rozwinięcie >= {request.elaboration_threshold}"
                + (
                    f"; zwroty opiniujące: {', '.join(markers)}"
                    if markers
                    else "; brak zwrotów opiniujących"
                )
            ),
        )
