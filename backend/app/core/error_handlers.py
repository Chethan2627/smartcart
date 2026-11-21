"""
Centralized exception handling for SmartCart 2.0.
Translates domain exceptions, Pydantic validation errors, and unhandled system errors
into standard, consistent HTTP responses across the entire REST API.
"""
import logging
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import (
    AuthenticationError,
    BadRequestError,
    ConflictError,
    DuplicateResourceError,
    ForbiddenError,
    IdempotencyConflictError,
    InsufficientStockError,
    InvalidStateTransitionError,
    InvalidTokenError,
    NotFoundError,
    SmartCartError,
    TokenExpiredError,
    ValidationError,
)

logger = logging.getLogger(__name__)


def create_error_response(
    status_code: int,
    code: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> JSONResponse:
    """Construct a standardized JSON error envelope response."""
    content = {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        }
    }
    return JSONResponse(status_code=status_code, content=content, headers=headers)


# Specific-to-general domain exception mapping
DOMAIN_EXCEPTION_MAP = [
    (TokenExpiredError, status.HTTP_401_UNAUTHORIZED, "TOKEN_EXPIRED", {"WWW-Authenticate": 'Bearer error="invalid_token", error_description="The access token expired"'}),
    (InvalidTokenError, status.HTTP_401_UNAUTHORIZED, "INVALID_TOKEN", {"WWW-Authenticate": 'Bearer error="invalid_token"'}),
    (AuthenticationError, status.HTTP_401_UNAUTHORIZED, "AUTHENTICATION_FAILED", {"WWW-Authenticate": "Bearer"}),
    (ForbiddenError, status.HTTP_403_FORBIDDEN, "FORBIDDEN", None),
    (NotFoundError, status.HTTP_404_NOT_FOUND, "NOT_FOUND", None),
    (InsufficientStockError, status.HTTP_409_CONFLICT, "INSUFFICIENT_STOCK", None),
    (IdempotencyConflictError, status.HTTP_409_CONFLICT, "IDEMPOTENCY_CONFLICT", None),
    (DuplicateResourceError, status.HTTP_409_CONFLICT, "DUPLICATE_RESOURCE", None),
    (ConflictError, status.HTTP_409_CONFLICT, "CONFLICT", None),
    (ValidationError, status.HTTP_422_UNPROCESSABLE_CONTENT, "VALIDATION_ERROR", None),
    (InvalidStateTransitionError, status.HTTP_400_BAD_REQUEST, "INVALID_STATE_TRANSITION", None),
    (BadRequestError, status.HTTP_400_BAD_REQUEST, "BAD_REQUEST", None),
]


async def smartcart_error_handler(request: Request, exc: SmartCartError) -> JSONResponse:
    """Handle all domain exceptions deriving from SmartCartError."""
    for exc_cls, status_code, code, headers in DOMAIN_EXCEPTION_MAP:
        if isinstance(exc, exc_cls):
            return create_error_response(
                status_code=status_code,
                code=code,
                message=exc.message,
                details=exc.details,
                headers=headers,
            )

    return create_error_response(
        status_code=status.HTTP_400_BAD_REQUEST,
        code="DOMAIN_ERROR",
        message=exc.message,
        details=exc.details,
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    Handle FastAPI / Pydantic request validation errors.
    Returns HTTP 422 with sanitized, structured field-level error details.
    """
    sanitized_errors: List[Dict[str, Any]] = []
    for err in exc.errors():
        sanitized_errors.append(
            {
                "loc": list(err.get("loc", [])),
                "msg": str(err.get("msg", "")),
                "type": str(err.get("type", "")),
            }
        )

    return create_error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code="VALIDATION_ERROR",
        message="Request payload validation failed",
        details={"errors": sanitized_errors},
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle Starlette and FastAPI HTTPExceptions uniformly."""
    code = f"HTTP_{exc.status_code}"
    return create_error_response(
        status_code=exc.status_code,
        code=code,
        message=str(exc.detail),
        details={},
        headers=exc.headers,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch-all for unhandled server exceptions.
    Logs detailed traceback internally while returning a sanitized HTTP 500 response.
    Never leaks database credentials, internal IPs, or stack traces to clients.
    """
    logger.error(
        "Unhandled internal server error on %s %s: %s",
        request.method,
        request.url.path,
        exc,
        exc_info=True,
    )
    return create_error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="INTERNAL_SERVER_ERROR",
        message="An unexpected internal server error occurred. Please contact support.",
        details={},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all centralized exception handlers on the FastAPI application instance."""
    app.add_exception_handler(SmartCartError, smartcart_error_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
