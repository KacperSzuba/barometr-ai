"""Adapter dla silnika FastEmbed (ONNX) implementujący EmbedderPort."""

import numpy as np
from fastembed import TextEmbedding


class FastEmbedAdapter:
    """Lokalny, zoptymalizowany pod CPU model generowania embeddingów."""

    def __init__(
        self,
        model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    ) -> None:
        self._model_name = model_name
        self._model = TextEmbedding(model_name=self._model_name)
        self._dimension = 384

    @property
    def model_name(self) -> str:
        """Zwraca nazwę i wersję modelu."""
        return self._model_name

    @property
    def dimension(self) -> int:
        """Zwraca wymiar wektora (dla tego modelu to 384 liczby)."""
        return self._dimension

    def embed_texts(self, texts: list[str], normalize: bool = True) -> list[list[float]]:
        """Przekształca listę tekstów w listę wektorów embeddingów."""
        if not texts:
            return []

        embeddings_generator = self._model.embed(texts)
        results: list[list[float]] = []

        for vec in embeddings_generator:
            if normalize:
                norm = np.linalg.norm(vec)
                if norm > 0:
                    vec = vec / norm
            results.append(vec.tolist())

        return results
