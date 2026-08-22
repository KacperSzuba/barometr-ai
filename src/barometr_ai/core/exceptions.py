"""Domain and infrastructure exceptions for Barometr AI."""

class BarometrAIError(Exception):
    """Base exception for all Barometr AI errors."""
    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ProvenanceViolationError(BarometrAIError):
    """Raised when generated output cannot be verified against source text spans."""


class ModelInferenceError(BarometrAIError):
    """Raised when a model fails during inference."""


class BudgetExceededError(BarometrAIError):
    """Raised when token/cost budget for the client or day is exceeded."""
