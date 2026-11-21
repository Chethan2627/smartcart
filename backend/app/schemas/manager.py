"""
Pydantic schemas for Store Manager product catalogue and inventory management.
Enforces validation, typing, and clear serialization contracts for manager APIs.
"""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class StockAdjustmentType(str, Enum):
    """Supported stock adjustment types."""
    INCREASE = "INCREASE"
    DECREASE = "DECREASE"
    SET = "SET"


class ProductCreateManagerRequest(BaseModel):
    """Request payload to create a product in catalogue and optionally initialize store stock."""
    sku: str = Field(..., min_length=2, max_length=64, description="Unique SKU code")
    name: str = Field(..., min_length=1, max_length=255, description="Product display name")
    description: Optional[str] = Field(default=None, max_length=2000)
    brand: Optional[str] = Field(default=None, max_length=100)
    category: Optional[str] = Field(default=None, max_length=100)
    price_paise: int = Field(..., ge=0, description="Global price in Indian paise (e.g. 9900 = Rs 99.00)")
    attributes: Dict[str, Any] = Field(default_factory=dict, description="Dynamic JSONB attributes")
    initial_stock: int = Field(default=0, ge=0, description="Initial physical stock on hand for manager's store")
    low_stock_threshold: int = Field(default=5, ge=0, description="Low-stock threshold for manager's store")

    model_config = ConfigDict(extra="forbid")


class ProductUpdateManagerRequest(BaseModel):
    """
    Request payload to update product metadata.
    Note: Updating 'price_paise' is strictly forbidden for STORE_MANAGER and only allowed for ADMIN.
    """
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=2000)
    brand: Optional[str] = Field(default=None, max_length=100)
    category: Optional[str] = Field(default=None, max_length=100)
    attributes: Optional[Dict[str, Any]] = None
    price_paise: Optional[int] = Field(default=None, ge=0, description="Admin-only global price update")
    is_active: Optional[bool] = None

    model_config = ConfigDict(extra="forbid")


class StockAdjustmentRequest(BaseModel):
    """Request payload to perform an atomic, audited stock adjustment."""
    adjustment_type: StockAdjustmentType = Field(..., description="INCREASE, DECREASE, or SET")
    quantity: int = Field(..., ge=0, description="Adjustment quantity (non-negative integer)")
    reason: str = Field(..., min_length=3, max_length=255, description="Business justification for audit log")
    low_stock_threshold: Optional[int] = Field(default=None, ge=0, description="Optional updated low-stock threshold")

    model_config = ConfigDict(extra="forbid")


class StockAdjustmentResponse(BaseModel):
    """Response payload returned following a successful stock adjustment."""
    store_id: UUID
    product_id: UUID
    old_on_hand: int = Field(..., ge=0)
    new_on_hand: int = Field(..., ge=0)
    qty_reserved: int = Field(..., ge=0)
    qty_available: int = Field(..., ge=0)
    adjustment_type: StockAdjustmentType
    quantity_delta: int
    reason: str
    low_stock_threshold: int = Field(..., ge=0)
    is_low_stock: bool
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProductImageResponse(BaseModel):
    """Image metadata for product."""
    url: str
    secure_url: Optional[str] = None
    public_id: Optional[str] = None
    format: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    bytes: Optional[int] = None


class ManagerProductResponse(BaseModel):
    """Product response enriched with store-specific inventory status for managers."""
    id: UUID
    sku: str
    name: str
    description: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    price_paise: int
    attributes: Dict[str, Any] = Field(default_factory=dict)
    image: Optional[ProductImageResponse] = None
    is_active: bool
    store_id: Optional[UUID] = None
    qty_on_hand: Optional[int] = None
    qty_reserved: Optional[int] = None
    qty_available: Optional[int] = None
    low_stock_threshold: Optional[int] = None
    is_low_stock: Optional[bool] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
