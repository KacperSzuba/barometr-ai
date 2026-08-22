"""Generowanie ustrukturyzowanych streszczeń z bezwzględną proweniencją znakową (F1)."""

import re

from barometr_ai.core.config import Settings
from barometr_ai.domain.models import SummarizeRequest, SummarizeResponse
from barometr_ai.domain.provenance import GroundedStatement, ProvenanceSpan
from barometr_ai.services.cost_tracker_service import CostTrackerService
from barometr_ai.services.provenance_service import ProvenanceService


class SummarizerService:
    """Orkiestruje generowanie streszczeń i weryfikację każdego zdania pod kątem cytowań."""

    def __init__(self, cost_tracker: CostTrackerService, settings: Settings) -> None:
        self._cost_tracker = cost_tracker
        self._settings = settings

    def summarize(self, request: SummarizeRequest) -> SummarizeResponse:
        """Tworzy streszczenie wykonawcze z powiązaniem każdego punktu do konkretnego miejsca w tekście."""
        raw_text = request.content
        doc_id = request.document_id

        # 1. Zarejestruj szacunkowe zużycie tokenów (1 słowo ~ 1.3 tokena)
        approx_tokens = int(len(raw_text.split()) * 1.3) + 150
        self._cost_tracker.record_usage(client_id="default_client", tokens=approx_tokens)

        # 2. Wyodrębnienie kluczowych fragmentów i konstrukcja zdań z proweniencją
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", raw_text) if len(s.strip()) > 15]

        grounded_bullets: list[GroundedStatement] = []

        for sentence in sentences[: request.max_sentences]:
            idx = raw_text.find(sentence)
            if idx != -1:
                span = ProvenanceSpan(
                    source_document_id=doc_id,
                    char_start=idx,
                    char_end=idx + len(sentence),
                    exact_quote=sentence,
                )
                statement = GroundedStatement(
                    text=f"Wprowadzono regulację: {sentence}",
                    provenance=[span],
                )
                grounded_bullets.append(statement)

        # 3. Rygorystyczna filtracja faktów bez źródła (Strict Provenance Guard)
        valid_bullets = ProvenanceService.filter_ungrounded(grounded_bullets, raw_text)

        what_changed = valid_bullets[0] if valid_bullets else None
        who_affected = valid_bullets[1] if len(valid_bullets) > 1 else None
        next_steps = valid_bullets[2] if len(valid_bullets) > 2 else None

        return SummarizeResponse(
            document_id=doc_id,
            summary_bullets=valid_bullets,
            what_changed=what_changed,
            who_is_affected=who_affected,
            next_steps=next_steps,
            model_version=self._settings.model_version,
            prompt_version=self._settings.prompt_version,
            total_tokens=approx_tokens,
        )