"""Port warstwy generatywnej — kontrakt dla dowolnego dostawcy modelu językowego."""

from typing import Protocol, runtime_checkable

from barometr_ai.domain.llm import LLMCompletion, LLMPrompt


@runtime_checkable
class LLMPort(Protocol):
    """Minimalny kontrakt generatora tekstu wymagany przez warstwę serwisów."""

    @property
    def model_name(self) -> str:
        """Nazwa modelu raportowana w metadanych odpowiedzi."""
        ...

    @property
    def model_version(self) -> str:
        """Wersja modelu — musi odpowiadać temu, co realnie wykonało inferencję."""
        ...

    @property
    def is_generative(self) -> bool:
        """False dla adapterów zastępczych, których wynikom nie wolno przypisywać jakości modelu."""
        ...

    async def complete(self, prompt: LLMPrompt) -> LLMCompletion:
        """Wykonuje pojedyncze wywołanie i zwraca odpowiedź z odwołaniami oraz licznikami tokenów."""
        ...
