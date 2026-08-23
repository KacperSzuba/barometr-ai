"""Strict provenance domain models (source document citation tracking)."""

from pydantic import BaseModel, ConfigDict, Field


class ProvenanceSpan(BaseModel):
    """Exact location of a verified fact in a source document.

    Świadomie bez `str_strip_whitespace`: `exact_quote` musi odpowiadać wycinkowi
    `source_text[char_start:char_end]` znak w znak. Przycinanie białych znaków rozjeżdżałoby
    cytat z offsetami i odrzucałoby poprawne odwołania.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_document_id: str = Field(
        ..., min_length=1, description="Canonical ID of the source document"
    )
    char_start: int = Field(..., ge=0, description="Character start index (0-based)")
    char_end: int = Field(..., ge=0, description="Character end index (exclusive)")
    exact_quote: str = Field(default="", description="Exact snippet extracted from source")

    def validate_against_text(self, source_text: str) -> bool:
        """Verify that the character span matches the source text."""
        if (
            self.char_start < 0
            or self.char_end > len(source_text)
            or self.char_start >= self.char_end
        ):
            return False
        return not (
            bool(self.exact_quote)
            and source_text[self.char_start : self.char_end] != self.exact_quote
        )


class GroundedStatement(BaseModel):
    """A generated sentence or statement strictly backed by one or more provenance spans."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    text: str = Field(..., min_length=1, description="Generated text statement")
    provenance: list[ProvenanceSpan] = Field(
        ..., min_length=1, description="Must contain at least 1 verified source span"
    )
