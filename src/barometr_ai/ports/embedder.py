"""Embedder interface."""

from typing import Literal, Protocol

#: `passage` — dokument trafiający do indeksu. `query` — zapytanie wyszukiwarki.
#: Rozróżnienie jest istotne dla rodziny E5, która wymaga odmiennych prefiksów wejściowych.
InputType = Literal["passage", "query"]


class EmbedderPort(Protocol):
    """Port for text embedding generators."""

    def embed_texts(
        self,
        texts: list[str],
        normalize: bool = True,
        *,
        input_type: InputType = "passage",
    ) -> list[list[float]]:
        """Convert a batch of texts into embedding vectors."""
        ...

    @property
    def model_name(self) -> str:
        """Name and version of the active embedding model."""
        ...

    @property
    def model_version(self) -> str:
        """Wersja wektorów. Jej zmiana wymusza przeliczenie indeksu po stronie backendu."""
        ...

    @property
    def dimension(self) -> int:
        """Vector dimension."""
        ...
