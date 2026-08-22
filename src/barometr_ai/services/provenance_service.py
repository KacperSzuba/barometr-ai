"""Service for validating and enforcing strict provenance on model outputs."""

from barometr_ai.domain.provenance import GroundedStatement


class ProvenanceService:
    """Validates that all statements produced by LLM are strictly anchored in source text."""

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
    def filter_ungrounded(cls, statements: list[GroundedStatement], source_text: str) -> list[GroundedStatement]:
        """Filter out any statement failing provenance verification."""
        return [stmt for stmt in statements if cls.verify_statement(stmt, source_text)]
