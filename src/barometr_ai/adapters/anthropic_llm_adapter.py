"""Adapter Claude API implementujący `LLMPort` z natywnymi cytowaniami znakowymi."""

import logging
from typing import Any, cast

import anthropic
from anthropic.types import (
    DocumentBlockParam,
    MessageParam,
    TextBlockParam,
)

from barometr_ai.core.exceptions import ModelInferenceError
from barometr_ai.domain.llm import CitedSegment, CitedSpan, LLMCompletion, LLMPrompt

logger = logging.getLogger(__name__)


class AnthropicLLMAdapter:
    """Wywołuje model Claude, przekazując dokument źródłowy jako zaindeksowany blok.

    Offsety znakowe w odpowiedzi liczy API na dokumencie, który samo zindeksowało — model
    ich nie przepisuje, więc nie ma ich jak zmyślić. Walidator proweniencji w warstwie
    serwisów i tak weryfikuje każdy offset wobec tekstu źródłowego; to obrona w głąb,
    a nie zaufanie do dostawcy.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float = 120.0,
        max_retries: int = 2,
    ) -> None:
        if not api_key:
            raise ValueError("AnthropicLLMAdapter wymaga niepustego klucza API.")
        self._model = model
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=max_retries,
        )

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def model_version(self) -> str:
        return self._model

    @property
    def is_generative(self) -> bool:
        return True

    async def complete(self, prompt: LLMPrompt) -> LLMCompletion:
        """Wykonuje wywołanie modelu i mapuje bloki odpowiedzi na segmenty z odwołaniami."""
        document_block: DocumentBlockParam = {
            "type": "document",
            "source": {
                "type": "text",
                "media_type": "text/plain",
                "data": prompt.document.text,
            },
            "title": prompt.document.title or prompt.document.document_id,
            "citations": {"enabled": True},
            # Punkt cachowania obejmuje prompt systemowy i dokument. Przy regeneracji
            # odrzuconych sekcji ten sam dokument jedzie ponownie — odczyt z cache kosztuje
            # ułamek ceny wejścia, a to on stanowi większość żądania.
            "cache_control": {"type": "ephemeral"},
        }
        instruction_block: TextBlockParam = {"type": "text", "text": prompt.user}
        messages: list[MessageParam] = [
            {"role": "user", "content": [document_block, instruction_block]}
        ]

        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=prompt.max_output_tokens,
                system=[{"type": "text", "text": prompt.system}],
                # Bez `thinking`: rodzina Opus 5 domyślnie działa adaptacyjnie. Wyłączanie
                # rozumowania ma udokumentowane skutki uboczne, obniżenie `effort` nie ma.
                output_config={"effort": cast(Any, prompt.effort)},
                messages=messages,
            )
        except anthropic.NotFoundError as exc:
            raise ModelInferenceError(
                f"Nieznany model {self._model!r} po stronie dostawcy.",
                details={"model": self._model},
            ) from exc
        except anthropic.AuthenticationError as exc:
            raise ModelInferenceError(
                "Dostawca modelu odrzucił klucz API.", details={"model": self._model}
            ) from exc
        except anthropic.RateLimitError as exc:
            raise ModelInferenceError(
                "Przekroczono limit żądań u dostawcy modelu.",
                details={
                    "model": self._model,
                    "retry_after": exc.response.headers.get("retry-after"),
                },
            ) from exc
        except anthropic.APIStatusError as exc:
            raise ModelInferenceError(
                f"Dostawca modelu zwrócił błąd {exc.status_code}.",
                details={"model": self._model, "status_code": exc.status_code},
            ) from exc
        except anthropic.APIConnectionError as exc:
            raise ModelInferenceError(
                "Nie udało się połączyć z dostawcą modelu.", details={"model": self._model}
            ) from exc

        if response.stop_reason == "refusal":
            category = response.stop_details.category if response.stop_details else None
            raise ModelInferenceError(
                "Model odmówił wykonania żądania.",
                details={"model": self._model, "category": category},
            )
        if response.stop_reason == "max_tokens":
            logger.warning(
                "Odpowiedź modelu ucięta limitem max_tokens",
                extra={"model": self._model, "prompt_id": prompt.prompt_id},
            )

        usage = response.usage
        return LLMCompletion(
            segments=self._map_segments(response.content),
            model_name=self._model,
            model_version=response.model,
            prompt_tokens=usage.input_tokens,
            completion_tokens=usage.output_tokens,
            cache_read_tokens=usage.cache_read_input_tokens or 0,
            tokens_are_estimated=False,
            stop_reason=response.stop_reason,
        )

    @staticmethod
    def _map_segments(content: list[Any]) -> list[CitedSegment]:
        """Mapuje bloki tekstowe odpowiedzi na segmenty, zachowując kolejność i odwołania."""
        segments: list[CitedSegment] = []
        for block in content:
            if getattr(block, "type", None) != "text":
                continue
            segments.append(
                CitedSegment(
                    text=block.text,
                    citations=AnthropicLLMAdapter._map_citations(block.citations),
                )
            )
        return segments

    @staticmethod
    def _map_citations(citations: list[Any] | None) -> list[CitedSpan]:
        """Zachowuje wyłącznie odwołania znakowe — jedyny typ zgodny z kontraktem proweniencji."""
        if not citations:
            return []
        spans: list[CitedSpan] = []
        for citation in citations:
            if getattr(citation, "type", None) != "char_location":
                # Odwołania stronicowe (PDF) nie mają odpowiednika w `ProvenanceSpan`.
                # Pomijamy je świadomie — brak odwołania odrzuci sekcję w walidatorze.
                logger.warning("Pominięto odwołanie typu %s", getattr(citation, "type", "?"))
                continue
            spans.append(
                CitedSpan(
                    char_start=citation.start_char_index,
                    char_end=citation.end_char_index,
                    cited_text=citation.cited_text,
                )
            )
        return spans
