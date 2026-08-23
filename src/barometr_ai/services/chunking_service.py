"""Algorytmy podziału tekstu (chunking) z zachowaniem ścisłej proweniencji."""

import re

from pydantic import BaseModel, ConfigDict, Field

from barometr_ai.domain.provenance import ProvenanceSpan


class TextChunk(BaseModel):
    """Fragment tekstu wraz z metadanymi proweniencji wskazującymi na oryginał."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(..., min_length=1)
    span: ProvenanceSpan


class ChunkingService:
    """Dzieli długie dokumenty na okna kontekstowe bez gubienia pozycji znakowych."""

    def __init__(self, target_chunk_size: int = 500, overlap: int = 50) -> None:
        self.target_chunk_size = target_chunk_size
        self.overlap = overlap

    def split_text(self, document_id: str, text: str) -> list[TextChunk]:
        """Dzieli tekst po granicach akapitów/zdań, zachowując bezwzględne indeksy znaków."""
        if not text.strip():
            return []

        chunks: list[TextChunk] = []
        text_len = len(text)
        start = 0

        while start < text_len:
            end = min(start + self.target_chunk_size, text_len)

            if end < text_len:
                boundary = self._find_natural_boundary(text, start, end)
                if boundary > start:
                    end = boundary

            chunk_text = text[start:end]
            trimmed_text, offset_start, _ = self._trim_with_offsets(chunk_text)

            if trimmed_text:
                span = ProvenanceSpan(
                    source_document_id=document_id,
                    char_start=start + offset_start,
                    char_end=start + offset_start + len(trimmed_text),
                    exact_quote=trimmed_text,
                )
                chunks.append(TextChunk(text=trimmed_text, span=span))

            if end >= text_len:
                break

            start = max(end - self.overlap, start + 1)

        return chunks

    @staticmethod
    def _find_natural_boundary(text: str, start: int, end: int) -> int:
        """Szuka podwójnej nowej linii, pojedynczej nowej linii lub kropki przed 'end'."""
        sub = text[start:end]
        para_idx = sub.rfind("\n\n")
        if para_idx != -1 and para_idx > len(sub) // 2:
            return start + para_idx + 2

        sentence_matches = list(re.finditer(r"[.!?]\s", sub))
        if sentence_matches:
            last_match = sentence_matches[-1]
            if last_match.end() > len(sub) // 2:
                return start + last_match.end()

        space_idx = sub.rfind(" ")
        if space_idx != -1 and space_idx > len(sub) // 2:
            return start + space_idx + 1

        return end

    @staticmethod
    def _trim_with_offsets(s: str) -> tuple[str, int, int]:
        """Zwraca przycięty string oraz przesunięcie początku i końca."""
        l_stripped = s.lstrip()
        offset_start = len(s) - len(l_stripped)
        trimmed = l_stripped.rstrip()
        offset_end = len(l_stripped) - len(trimmed)
        return trimmed, offset_start, offset_end
