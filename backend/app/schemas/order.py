from datetime import datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from app.models.enums import OrderStatus


class CheckoutRequest(BaseModel):
    """
    Checkout request payload.
    Prices and totals are strictly calculated server-side from verified active
    cart reservations and database product records. Clients cannot supply prices.
    """

    store_id: UUID = Field(description="Fulfilling store location UUID")
    delivery_address: Optional[str] = Field(
        default=None, max_length=500, description="Optional override delivery address"
    )

    model_config = ConfigDict(extra="forbid")


class OrderItemResponse(BaseModel):
    """Line item in an order."""

    id: int
    order_id: UUID
    product_id: UUID
    qty: int = Field(strict=True, gt=0, description="Ordered quantity")
    unit_price_paise: int = Field(strict=True, ge=0, description="Unit price in paise locked at purchase time")
    item_subtotal_paise: Optional[int] = Field(
        default=None, strict=True, ge=0, description="Line subtotal in paise"
    )

    model_config = ConfigDict(from_attributes=True)


class OrderStatusHistoryResponse(BaseModel):
    """Historical status transition record for an order."""

    id: int
    order_id: UUID
    from_status: Optional[OrderStatus] = None
    to_status: OrderStatus
    changed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrderResponse(BaseModel):
    """Full order response with nested line items and transition history."""

    id: UUID
    order_number: str = Field(description="Unique formatted sequential number (SC-YYYY-XXXXXX)")
    customer_id: UUID
    store_id: UUID
    status: OrderStatus
    total_paise: int = Field(strict=True, ge=0, description="Total order amount in Indian paise")
    items: List[OrderItemResponse] = Field(default_factory=list)
    status_history: List[OrderStatusHistoryResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrderCancelRequest(BaseModel):
    """Request to cancel an order and restore inventory."""

    reason: Optional[str] = Field(
        default="Customer requested cancellation",
        max_length=255,
        description="Reason for cancellation",
    )

    model_config = ConfigDict(extra="forbid")


class OrderStatusUpdateRequest(BaseModel):
    """Store manager request to transition order status along state machine."""

    to_status: OrderStatus = Field(description="Target order status (e.g., PACKED, SHIPPED, DELIVERED)")

    model_config = ConfigDict(extra="forbid")


class OrderFilterParams(BaseModel):
    """Query parameters for order searching and management."""

    store_id: Optional[UUID] = None
    status: Optional[OrderStatus] = None
    skip: int = Field(default=0, strict=True, ge=0, description="Pagination offset")
    limit: int = Field(default=20, strict=True, ge=1, le=100, description="Pagination limit (max 100)")

    model_config = ConfigDict(extra="forbid")
