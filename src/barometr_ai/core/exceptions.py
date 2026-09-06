"""Domain and infrastructure exceptions for Barometr AI."""

from typing import Any


class BarometrAIError(Exception):
    """Base exception for all Barometr AI errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, Any] = details or {}


class ProvenanceViolationError(BarometrAIError):
    """Raised when generated output cannot be verified against source text spans."""


class ModelInferenceError(BarometrAIError):
    """Raised when a model fails during inference or cannot be loaded."""


class BudgetExceededError(BarometrAIError):
    """Raised when token/cost budget for the client or day is exceeded."""


class InvalidDocumentBatchError(BarometrAIError):
    """Raised when a batch of documents cannot be processed as submitted."""


class ServiceAuthenticationError(BarometrAIError):
    """Raised when a caller presents no service key, or the wrong one."""
