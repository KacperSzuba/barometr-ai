"""Embedder interface."""

from typing import Protocol


class EmbedderPort(Protocol):
    """Port for text embedding generators."""
    def embed_texts(self, texts: list[str], normalize: bool = True) -> list[list[float]]:
        """Convert a batch of texts into embedding vectors."""
        ...

    @property
    def model_name(self) -> str:
        """Name and version of the active embedding model."""
        ...

    @property
    def dimension(self) -> int:
        """Vector dimension."""
        ...
