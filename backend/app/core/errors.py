"""Typed exception hierarchy.

API-facing errors carry an HTTP status and a stable machine code for the error envelope.
Agent-facing errors carry a ``FailureKind`` so the runtime can pick a recovery strategy
without string matching.
"""

from typing import Any

from app.domain.enums import FailureKind


class AppError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class InvalidStateError(ConflictError):
    code = "invalid_state"


class AuthenticationError(AppError):
    status_code = 401
    code = "unauthenticated"


class RateLimitedError(AppError):
    status_code = 429
    code = "rate_limited"

    def __init__(self, message: str, *, retry_after_seconds: float) -> None:
        super().__init__(message, details={"retry_after_seconds": retry_after_seconds})
        self.retry_after_seconds = retry_after_seconds


class DependencyUnavailableError(AppError):
    status_code = 503
    code = "dependency_unavailable"


class AgentError(AppError):
    """Raised inside the agent runtime; never leaks to API callers as-is."""

    failure_kind = FailureKind.FATAL


class ToolError(AgentError):
    failure_kind = FailureKind.STRUCTURAL


class RetryableToolError(ToolError):
    failure_kind = FailureKind.TRANSIENT


class ToolTimeoutError(RetryableToolError):
    code = "tool_timeout"


class ToolInputError(ToolError):
    code = "tool_input_invalid"


class PolicyViolationError(AgentError):
    failure_kind = FailureKind.POLICY
    code = "policy_violation"


class CircuitOpenError(RetryableToolError):
    code = "circuit_open"


class LLMError(AgentError):
    code = "llm_error"


class LLMRetryableError(LLMError):
    failure_kind = FailureKind.TRANSIENT


class LLMRateLimitedError(LLMRetryableError):
    code = "llm_rate_limited"

    def __init__(self, message: str, *, retry_after_seconds: float | None = None) -> None:
        super().__init__(message, details={"retry_after_seconds": retry_after_seconds})
        self.retry_after_seconds = retry_after_seconds


class LLMUnavailableError(LLMError):
    """Every configured backend failed or was unavailable for this call."""

    failure_kind = FailureKind.TRANSIENT
    code = "llm_unavailable"


class LLMResponseInvalidError(LLMError):
    code = "llm_response_invalid"


class BudgetExceededError(AgentError):
    code = "budget_exceeded"


class VerificationFailedError(AgentError):
    code = "verification_failed"
