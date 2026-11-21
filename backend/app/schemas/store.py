from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class StoreResponse(BaseModel):
    """Store fulfillment center response."""

    id: UUID
    code: str
    name: str
    city: str
    state: str
    address: Optional[str] = None
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StoreFilterParams(BaseModel):
    """Query parameters for store listing and filtering."""

    state: Optional[str] = None
    city: Optional[str] = None
    is_active: Optional[bool] = True
    skip: int = Field(default=0, strict=True, ge=0, description="Pagination offset")
    limit: int = Field(default=50, strict=True, ge=1, le=100, description="Pagination limit (max 100)")

    model_config = ConfigDict(extra="forbid")
