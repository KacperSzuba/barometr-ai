"""Wykrywanie nowości vs. recykling informacji (F2)."""

import numpy as np

from barometr_ai.domain.enterprise_models import (
    NoveltyRequest,
    NoveltyResponse,
    NoveltyType,
)
from barometr_ai.ports.embedder import EmbedderPort


class NoveltyDetectorService:
    """Odróżnia nowe fakty i rozwinięcia od odgrzewanego recyklingu depesz.

    Świadome ograniczenie: klasyfikacja opiera się na maksymalnym podobieństwie do historii,
    a nie na ekstrakcji twierdzeń. Materiał dodający jeden nowy fakt do znanego tekstu jest
    dla tej metody nieodróżnialny od recyklingu, dlatego klasa `COMMENTARY` nigdy nie jest
    zwracana. Pełna realizacja zadania F2 wymaga porównania twierdzeń, nie wektorów.
    """

    def __init__(self, embedder: EmbedderPort) -> None:
        self._embedder = embedder

    def evaluate_novelty(self, request: NoveltyRequest) -> NoveltyResponse:
        if not request.history_texts:
            return NoveltyResponse(
                classification=NoveltyType.NEW_EVENT,
                novelty_score=1.0,
                highest_similarity=0.0,
                is_suppressed=False,
                method="brak historii do porównania",
            )

        new_vec = np.array(self._embedder.embed_texts([request.new_text], normalize=True)[0])
        history_vecs = self._embedder.embed_texts(request.history_texts, normalize=True)

        similarities = [float(np.dot(new_vec, np.array(vec))) for vec in history_vecs]
        max_sim = max(similarities) if similarities else 0.0

        # Progi pochodzą z żądania. Poprzednia wersja miała je zaszyte (0,85 / 0,65),
        # a pole `similarity_threshold` z kontraktu API było po cichu ignorowane.
        if max_sim >= request.similarity_threshold:
            classification = NoveltyType.RECYCLED
            is_suppressed = True
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
            ),
        )
