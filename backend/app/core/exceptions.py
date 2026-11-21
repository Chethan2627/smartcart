"""
Domain exception hierarchy for SmartCart 2.0.
Provides clean domain exceptions decoupled from HTTP transport layer.
"""
from typing import Any, Dict, Optional


class SmartCartError(Exception):
    """Base exception for all domain and service errors in SmartCart."""

    def __init__(
        self, message: str, details: Optional[Dict[str, Any]] = None
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


# 401 Unauthorized
class AuthenticationError(SmartCartError):
    """Raised when authentication credentials or token validation fails."""

    pass


class TokenExpiredError(AuthenticationError):
    """Raised specifically when a JWT access token has expired."""

    pass


class InvalidTokenError(AuthenticationError):
    """Raised when a JWT access token signature, format, or claims are invalid."""

    pass


# 403 Forbidden
class ForbiddenError(SmartCartError):
    """Raised when an authenticated entity lacks permission to access a resource."""

    pass


# 404 Not Found
class NotFoundError(SmartCartError):
    """Raised when a requested resource does not exist."""

    pass


# 409 Conflict
class ConflictError(SmartCartError):
    """Base exception for state or concurrency conflicts."""

    pass


class InsufficientStockError(ConflictError):
    """Raised when available inventory is insufficient for a reservation."""

    pass


class IdempotencyConflictError(ConflictError):
    """Raised when an idempotency key is reused with a differing request body."""

    pass


class DuplicateResourceError(ConflictError):
    """Raised when attempting to create a resource with a non-unique field (e.g., email, SKU)."""

    pass


# 422 Validation
class ValidationError(SmartCartError):
    """Raised when business logic or input validation invariants are violated."""

    pass


# 400 Bad Request
class BadRequestError(SmartCartError):
    """Raised for malformed client operations or invalid requests."""

    pass


class InvalidStateTransitionError(BadRequestError):
    """Raised when an illegal entity state transition is attempted."""

    pass
