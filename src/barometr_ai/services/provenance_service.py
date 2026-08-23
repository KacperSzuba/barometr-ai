"""Service for validating and enforcing strict provenance on model outputs."""

from barometr_ai.domain.llm import CitedSpan
from barometr_ai.domain.provenance import GroundedStatement, ProvenanceSpan


class ProvenanceService:
    """Validates that all statements produced by LLM are strictly anchored in source text."""

    @staticmethod
    def to_provenance_span(
        citation: CitedSpan, *, document_id: str, source_text: str
    ) -> ProvenanceSpan | None:
        """Przekłada odwołanie dostawcy na span domenowy, odrzucając rozjechane offsety.

        Zwraca `None`, gdy zakres wychodzi poza dokument, jest pusty albo gdy cytowany tekst
        nie zgadza się z wycinkiem źródła. Ten drugi przypadek to jedyny sposób wykrycia,
        że offsety i treść odwołania się rozeszły — dlatego nie ufamy `cited_text` na słowo,
        tylko porównujemy go z dokumentem.
        """
        if citation.char_start >= citation.char_end or citation.char_end > len(source_text):
            return None
        actual = source_text[citation.char_start : citation.char_end]
        if citation.cited_text and citation.cited_text != actual:
            return None
        return ProvenanceSpan(
            source_document_id=document_id,
            char_start=citation.char_start,
            char_end=citation.char_end,
            exact_quote=actual,
        )

    @staticmethod
    def verify_statement(statement: GroundedStatement, source_text: str) -> bool:
        """Verify that all spans in statement correspond to actual indices in source_text."""
        if not statement.provenance:
            return False
        for span in statement.provenance:
            if not span.validate_against_text(source_text):
                return False
        return True

    @classmethod
    def filter_ungrounded(
        cls, statements: list[GroundedStatement], source_text: str
    ) -> list[GroundedStatement]:
        """Filter out any statement failing provenance verification."""
        return [stmt for stmt in statements if cls.verify_statement(stmt, source_text)]
