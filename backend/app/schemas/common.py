"""
Common schema types, validation helpers, and pagination parameters.
"""
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class PaginationParams(BaseModel):
    """Standardized pagination parameters for list endpoints."""

    skip: int = Field(default=0, strict=True, ge=0, description="Number of records to skip")
    limit: int = Field(
        default=20, strict=True, ge=1, le=100, description="Maximum number of records to return (capped at 100)"
    )

    model_config = ConfigDict(extra="forbid")


class ErrorDetail(BaseModel):
    """Detailed error object conforming to SmartCart 2.0 API standards."""

    code: str = Field(description="Machine-readable error code")
    message: str = Field(description="Human-readable error description")
    details: Optional[Dict[str, Any]] = Field(
        default=None, description="Optional structured context or validation field errors"
    )

    model_config = ConfigDict(extra="forbid")


class ErrorResponse(BaseModel):
    """Standardized error envelope returned on all 4xx and 5xx API responses."""

    error: ErrorDetail

    model_config = ConfigDict(extra="forbid")


__all__ = [
    "EmailStr",
    "PaginationParams",
    "ErrorDetail",
    "ErrorResponse",
]
