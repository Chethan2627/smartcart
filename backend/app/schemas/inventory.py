from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from app.models.enums import ReservationStatus


class StockResponse(BaseModel):
    """Store-wise inventory balance response."""

    store_id: UUID
    product_id: UUID
    qty_on_hand: int = Field(strict=True, ge=0, description="Total physical inventory on hand")
    qty_reserved: int = Field(strict=True, ge=0, description="Currently reserved inventory")
    qty_available: int = Field(strict=True, ge=0, description="Available stock (on_hand - reserved)")
    low_stock_threshold: int = Field(strict=True, ge=0, description="Low stock alert threshold")
    is_low_stock: bool = Field(description="True if available stock <= threshold")
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReservationCreateRequest(BaseModel):
    """Request to create an inventory reservation hold."""

    store_id: UUID
    product_id: UUID
    qty: int = Field(strict=True, gt=0, description="Strictly positive integer quantity to reserve")
    ttl_seconds: Optional[int] = Field(
        default=600, strict=True, gt=0, le=3600, description="Reservation hold duration in seconds (default 10 min)"
    )

    model_config = ConfigDict(extra="forbid")


class ReservationResponse(BaseModel):
    """Active or historic inventory reservation response."""

    id: UUID
    customer_id: UUID
    store_id: UUID
    product_id: UUID
    qty: int = Field(strict=True, gt=0)
    status: ReservationStatus
    expires_at: datetime
    order_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InventoryAuditLogResponse(BaseModel):
    """Read-only inventory audit log entry response."""

    id: int = Field(strict=True)
    store_id: UUID
    product_id: UUID
    old_on_hand: int = Field(strict=True)
    new_on_hand: int = Field(strict=True)
    old_reserved: int = Field(strict=True)
    new_reserved: int = Field(strict=True)
    reason: str
    changed_at: datetime

    model_config = ConfigDict(from_attributes=True)
