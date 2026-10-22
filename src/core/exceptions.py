"""
ServerGen AI — Custom Exception Hierarchy.

Structured exceptions for security, authentication, authorization,
policy enforcement, approval workflow, AI operations, and audit integrity.
Internal details are never exposed to API clients.
"""

from __future__ import annotations


class ServerGenError(Exception):
    """Base exception for all ServerGen AI errors."""

    def __init__(self, message: str = "An internal error occurred", code: str = "INTERNAL_ERROR"):
        self.message = message
        self.code = code
        super().__init__(self.message)


# ── Authentication ───────────────────────────────────────────────────────


class AuthenticationError(ServerGenError):
    """Raised when authentication fails (invalid credentials, expired tokens)."""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message=message, code="AUTHENTICATION_FAILED")


class AccountLockedError(AuthenticationError):
    """Raised when a user account is temporarily locked due to failed login attempts."""

    def __init__(self, message: str = "Account is temporarily locked"):
        super().__init__(message=message)
        self.code = "ACCOUNT_LOCKED"


class InvalidTokenError(AuthenticationError):
    """Raised when a JWT token is invalid, tampered, or has wrong type."""

    def __init__(self, message: str = "Invalid token"):
        super().__init__(message=message)
        self.code = "INVALID_TOKEN"


class TokenExpiredError(AuthenticationError):
    """Raised when a JWT token has expired."""

    def __init__(self, message: str = "Token has expired"):
        super().__init__(message=message)
        self.code = "TOKEN_EXPIRED"


# ── Authorization ────────────────────────────────────────────────────────


class AuthorizationError(ServerGenError):
    """Raised when a user lacks required permissions."""

    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(message=message, code="AUTHORIZATION_DENIED")


class PolicyDeniedError(ServerGenError):
    """Raised when the policy engine denies an operation."""

    def __init__(self, message: str = "Operation denied by policy", reason: str = ""):
        super().__init__(message=message, code="POLICY_DENIED")
        self.reason = reason


class ApprovalRequiredError(ServerGenError):
    """Raised when an operation requires human approval before execution."""

    def __init__(
        self,
        message: str = "Operation requires approval",
        approval_request_id: str | None = None,
    ):
        super().__init__(message=message, code="APPROVAL_REQUIRED")
        self.approval_request_id = approval_request_id


# ── Approval ─────────────────────────────────────────────────────────────


class ApprovalError(ServerGenError):
    """Base exception for approval workflow errors."""

    def __init__(self, message: str = "Approval workflow error"):
        super().__init__(message=message, code="APPROVAL_ERROR")


class ApprovalNotFoundError(ApprovalError):
    """Raised when an approval request is not found."""

    def __init__(self, message: str = "Approval request not found"):
        super().__init__(message=message)
        self.code = "APPROVAL_NOT_FOUND"


class ApprovalFingerprintMismatchError(ApprovalError):
    """Raised when the operation fingerprint does not match the approved fingerprint."""

    def __init__(self, message: str = "Operation fingerprint does not match approved operation"):
        super().__init__(message=message)
        self.code = "FINGERPRINT_MISMATCH"


class SelfApprovalError(ApprovalError):
    """Raised when a user attempts to approve their own request (separation of duties)."""

    def __init__(self, message: str = "Cannot approve your own request"):
        super().__init__(message=message)
        self.code = "SELF_APPROVAL_DENIED"


# ── AI / LLM ────────────────────────────────────────────────────────────


class ModelNotAvailableError(ServerGenError):
    """Raised when the requested or required model is not available."""

    def __init__(self, message: str = "Model is not available"):
        super().__init__(message=message, code="MODEL_NOT_AVAILABLE")


class ModelProviderError(ServerGenError):
    """Raised when the model provider (e.g., Ollama) encounters an error."""

    def __init__(self, message: str = "Model provider error"):
        super().__init__(message=message, code="MODEL_PROVIDER_ERROR")


class StructuredOutputError(ServerGenError):
    """Raised when LLM structured output fails validation."""

    def __init__(self, message: str = "Structured output validation failed"):
        super().__init__(message=message, code="STRUCTURED_OUTPUT_ERROR")


# ── Tools ────────────────────────────────────────────────────────────────


class ToolExecutionError(ServerGenError):
    """Raised when a tool execution fails."""

    def __init__(self, message: str = "Tool execution failed"):
        super().__init__(message=message, code="TOOL_EXECUTION_ERROR")


class ToolNotFoundError(ServerGenError):
    """Raised when a requested tool is not registered."""

    def __init__(self, message: str = "Tool not found"):
        super().__init__(message=message, code="TOOL_NOT_FOUND")


# ── Audit ────────────────────────────────────────────────────────────────


class AuditIntegrityError(ServerGenError):
    """Raised when the tamper-evident audit ledger hash chain is broken."""

    def __init__(
        self,
        message: str = "Audit integrity verification failed",
        broken_at_sequence: int | None = None,
    ):
        super().__init__(message=message, code="AUDIT_INTEGRITY_BROKEN")
        self.broken_at_sequence = broken_at_sequence


# ── General ─────────────────────────────────────────────────────────────


class NotFoundError(ServerGenError):
    """Raised when a requested resource is not found."""

    def __init__(self, message: str = "Resource not found"):
        super().__init__(message=message, code="NOT_FOUND")


class ConflictError(ServerGenError):
    """Raised when a resource already exists or a conflict occurs."""

    def __init__(self, message: str = "Resource conflict"):
        super().__init__(message=message, code="CONFLICT")


class ValidationError(ServerGenError):
    """Raised when client input fails domain validation."""

    def __init__(self, message: str = "Validation error"):
        super().__init__(message=message, code="VALIDATION_ERROR")


# ── Rate Limiting ────────────────────────────────────────────────────────


class RateLimitExceededError(ServerGenError):
    """Raised when a rate limit is exceeded."""

    def __init__(self, message: str = "Rate limit exceeded", retry_after_seconds: float = 0):
        super().__init__(message=message, code="RATE_LIMIT_EXCEEDED")
        self.retry_after_seconds = retry_after_seconds
