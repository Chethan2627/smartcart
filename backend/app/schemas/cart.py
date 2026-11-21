from datetime import datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class CartItemAddRequest(BaseModel):
    """Request to add a product to the active cart (reserves stock)."""

    store_id: UUID = Field(description="Fulfillment store location UUID")
    product_id: UUID = Field(description="Product SKU identifier UUID")
    qty: int = Field(strict=True, gt=0, description="Strictly positive integer quantity to add")

    model_config = ConfigDict(extra="forbid")


class CartItemUpdateRequest(BaseModel):
    """Request to update an existing cart item's reserved quantity."""

    qty: int = Field(strict=True, gt=0, description="New desired strictly positive integer quantity")

    model_config = ConfigDict(extra="forbid")


class CartItemResponse(BaseModel):
    """Line item in a customer's active shopping cart."""

    reservation_id: UUID
    product_id: UUID
    product_name: str
    product_sku: str
    unit_price_paise: int = Field(strict=True, ge=0, description="Current unit price in paise from database")
    qty: int = Field(strict=True, gt=0)
    item_subtotal_paise: int = Field(strict=True, ge=0, description="Line item subtotal (qty * unit_price_paise)")
    expires_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CartResponse(BaseModel):
    """Aggregated shopping cart state for an active customer session."""

    store_id: Optional[UUID] = None
    items: List[CartItemResponse] = Field(default_factory=list)
    total_items: int = Field(strict=True, ge=0, description="Total number of items in cart")
    total_paise: int = Field(strict=True, ge=0, description="Grand total in Indian paise")
    earliest_expiration: Optional[datetime] = None
