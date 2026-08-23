"""Adapter dla silnika FastEmbed (ONNX) implementujący EmbedderPort."""

import logging

import numpy as np
from fastembed import TextEmbedding

from barometr_ai.core.exceptions import ModelInferenceError
from barometr_ai.ports.embedder import InputType

logger = logging.getLogger(__name__)

#: Prefiksy instrukcyjne rodziny E5. Ich pominięcie mierzalnie pogarsza jakość wyszukiwania,
#: bo model był trenowany wyłącznie na wejściach w tej formie.
_E5_PREFIXES: dict[InputType, str] = {"passage": "passage: ", "query": "query: "}


class FastEmbedAdapter:
    """Lokalny, zoptymalizowany pod CPU model generowania embeddingów.

    Nazwa modelu i wymiar pochodzą z konfiguracji, nie z kodu. Niezgodność zadeklarowanego
    wymiaru z faktycznym wywraca start serwisu zamiast po cichu zapisywać do pgvectora
    wektory o złej długości.
    """

    def __init__(
        self,
        model_name: str,
        *,
        dimension: int,
        model_version: str,
        needs_e5_prefix: bool = False,
        batch_size: int = 32,
    ) -> None:
        self._model_name = model_name
        self._model_version = model_version
        self._needs_e5_prefix = needs_e5_prefix
        self._batch_size = batch_size

        try:
            self._model = TextEmbedding(model_name=model_name)
        except Exception as exc:
            raise ModelInferenceError(
                f"Nie udało się załadować modelu embeddingów {model_name!r}. "
                "Sprawdź listę TextEmbedding.list_supported_models().",
                details={"model_name": model_name, "cause": str(exc)},
            ) from exc

        self._dimension = self._probe_dimension()
        if self._dimension != dimension:
            raise ModelInferenceError(
                f"Model {model_name!r} zwraca wektory o wymiarze {self._dimension}, "
                f"a konfiguracja deklaruje {dimension}.",
                details={
                    "model_name": model_name,
                    "actual": self._dimension,
                    "configured": dimension,
                },
            )
        logger.info(
            "Załadowano model embeddingów",
            extra={"model": model_name, "dimension": self._dimension, "e5_prefix": needs_e5_prefix},
        )

    @property
    def model_name(self) -> str:
        """Zwraca nazwę modelu."""
        return self._model_name

    @property
    def model_version(self) -> str:
        """Zwraca wersję wektorów zapisywaną razem z nimi po stronie backendu."""
        return self._model_version

    @property
    def dimension(self) -> int:
        """Zwraca faktyczny wymiar wektora zwracanego przez model."""
        return self._dimension

    def embed_texts(
        self,
        texts: list[str],
        normalize: bool = True,
        *,
        input_type: InputType = "passage",
    ) -> list[list[float]]:
        """Przekształca listę tekstów w listę wektorów embeddingów."""
        if not texts:
            return []

        prepared = self._apply_prefix(texts, input_type)
        results: list[list[float]] = []

        for vec in self._model.embed(prepared, batch_size=self._batch_size):
            if normalize:
                norm = float(np.linalg.norm(vec))
                if norm > 0:
                    vec = vec / norm
            results.append(vec.tolist())

        return results

    def _apply_prefix(self, texts: list[str], input_type: InputType) -> list[str]:
        if not self._needs_e5_prefix:
            return texts
        prefix = _E5_PREFIXES[input_type]
        return [f"{prefix}{text}" for text in texts]

    def _probe_dimension(self) -> int:
        """Odczytuje faktyczny wymiar z modelu zamiast przyjmować go na słowo z konfiguracji."""
        probe = next(iter(self._model.embed(["_"])))
        return int(probe.shape[0])
