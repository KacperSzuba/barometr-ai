"""Wykrywanie nowości vs. recykling informacji (F2)."""

import numpy as np

from barometr_ai.domain.enterprise_models import (
    NoveltyRequest,
    NoveltyResponse,
    NoveltyType,
)
from barometr_ai.ports.embedder import EmbedderPort


class NoveltyDetectorService:
    """Odróżnia nowe fakty i rozwinięcia od odgrzewanego recyklingu depesz."""

    def __init__(self, embedder: EmbedderPort) -> None:
        self._embedder = embedder

    def evaluate_novelty(self, request: NoveltyRequest) -> NoveltyResponse:
        if not request.history_texts:
            return NoveltyResponse(
                classification=NoveltyType.NEW_EVENT,
                novelty_score=1.0,
                highest_similarity=0.0,
                is_suppressed=False,
            )

        new_vec = np.array(self._embedder.embed_texts([request.new_text], normalize=True)[0])
        history_vecs = self._embedder.embed_texts(request.history_texts, normalize=True)

        similarities = [float(np.dot(new_vec, np.array(h_vec))) for h_vec in history_vecs]
        max_sim = max(similarities) if similarities else 0.0

        if max_sim >= 0.85:
            classification = NoveltyType.RECYCLED
            novelty_score = round(1.0 - max_sim, 3)
            is_suppressed = True
        elif max_sim >= 0.65:
            classification = NoveltyType.ELABORATION
            novelty_score = round(1.0 - (max_sim * 0.7), 3)
            is_suppressed = False
        else:
            classification = NoveltyType.NEW_EVENT
            novelty_score = round(1.0 - max_sim, 3)
            is_suppressed = False

        return NoveltyResponse(
            classification=classification,
            novelty_score=max(0.0, min(1.0, novelty_score)),
            highest_similarity=round(max_sim, 3),
            is_suppressed=is_suppressed,
        )