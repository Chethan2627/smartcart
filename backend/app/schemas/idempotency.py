from datetime import datetime
from typing import Annotated, Any, Dict, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

IdempotencyKeyHeader = Annotated[
    str,
    Field(
        min_length=1,
        max_length=255,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Client-supplied Idempotency-Key header value",
    ),
]


class IdempotencyRecordResponse(BaseModel):
    """Idempotent request tracking record response."""

    customer_id: UUID
    key: str = Field(min_length=1, max_length=255, description="Client-supplied Idempotency-Key")
    request_hash: str = Field(description="SHA-256 digest of request body")
    order_id: Optional[UUID] = None
    response: Optional[Dict[str, Any]] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
