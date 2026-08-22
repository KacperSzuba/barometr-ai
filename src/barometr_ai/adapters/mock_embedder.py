"""Lightweight deterministic embedder for local development and testing."""

import hashlib
import math


class MockLocalEmbedder:
    """Generates reproducible mock embeddings without requiring heavy PyTorch weights in dev."""

    def __init__(self, dimension: int = 1024, model_name: str = "mock-mmlw-large") -> None:
        self._dimension = dimension
        self._model_name = model_name

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_texts(self, texts: list[str], normalize: bool = True) -> list[list[float]]:
        results: list[list[float]] = []
        for text in texts:
            h = hashlib.sha256(text.encode("utf-8")).digest()
            vec = [(float(b) / 255.0 * 2.0 - 1.0) for b in h[:32]]
            repeat_count = math.ceil(self._dimension / len(vec))
            full_vec = (vec * repeat_count)[:self._dimension]

            if normalize:
                norm = math.sqrt(sum(x * x for x in full_vec)) or 1.0
                full_vec = [x / norm for x in full_vec]

            results.append(full_vec)
        return results
