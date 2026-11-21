from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from app.models.enums import OutboxStatus


class OutboxEventSummaryResponse(BaseModel):
    """
    Public / summary representation of a transactional outbox event.
    Omits sensitive internal payload fields and raw execution errors (last_error).
    """

    id: UUID
    aggregate_type: str
    aggregate_id: str
    event_type: str
    status: OutboxStatus
    retry_count: int = Field(strict=True, ge=0, description="Dispatch retry counter")
    created_at: datetime
    published_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class OutboxEventDetailResponse(BaseModel):
    """
    Diagnostic / internal administrator representation of a transactional outbox event.
    Includes event payload and dispatch error diagnostics (last_error).
    """

    id: UUID
    aggregate_type: str
    aggregate_id: str
    event_type: str
    payload: Dict[str, Any]
    status: OutboxStatus
    retry_count: int = Field(strict=True, ge=0, description="Dispatch retry counter")
    last_error: Optional[str] = None
    created_at: datetime
    published_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# Alias for backward compatibility
OutboxEventResponse = OutboxEventDetailResponse
