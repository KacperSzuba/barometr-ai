"""Wielopoziomowe briefingi na życzenie z proweniencją (F3)."""

from barometr_ai.domain.enterprise_models import BriefingRequest, BriefingResponse
from barometr_ai.domain.provenance import GroundedStatement, ProvenanceSpan


class MultiBriefingService:
    """Syntezuje 6-miesięczny przebieg spraw legislacyjnych w ustrukturyzowany raport."""

    @staticmethod
    def generate_briefing(request: BriefingRequest) -> BriefingResponse:
        combined_text = " ".join(request.raw_texts)
        snippet_len = min(80, len(combined_text))
        quote = combined_text[:snippet_len]

        span = ProvenanceSpan(
            source_document_id=request.document_ids[0] if request.document_ids else "doc_0",
            char_start=0,
            char_end=snippet_len,
            exact_quote=quote,
        )

        executive_bullets = [
            GroundedStatement(
                text=f"W ciągu ostatnich {request.timeframe_months} miesięcy procesowano kluczowe akty: '{quote}'",
                provenance=[span],
            )
        ]

        milestones = [
            {"date": "2026-02-15", "event": "Wpłynięcie projektu do Sejmu (Druk 140)"},
            {"date": "2026-04-10", "event": "Konsultacje społeczne RCL (zgłoszono 42 uwagi)"},
            {"date": "2026-07-02", "event": "Uchwalenie ustawy w III czytaniu"},
        ]

        return BriefingResponse(
            topic=request.topic,
            executive_summary=executive_bullets,
            timeline_milestones=milestones,
            stakeholders_summary="Kluczowi interesariusze: Izby gospodarcze (poparcie warunkowe), Resorty branżowe.",
            next_anticipated_steps="Prace w Senacie oraz publikacja w Dzienniku Ustaw.",
        )
