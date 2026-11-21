from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class ProductResponse(BaseModel):
    """Catalogue product details response."""

    id: UUID
    sku: str
    name: str
    description: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    price_paise: int = Field(strict=True, ge=0, description="Product price in Indian paise (non-negative integer)")
    attributes: Dict[str, Any] = Field(default_factory=dict, description="Dynamic JSONB product attributes")
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProductFilterParams(BaseModel):
    """Query parameters for catalog browsing and filtering."""

    category: Optional[str] = None
    brand: Optional[str] = None
    is_active: Optional[bool] = True
    skip: int = Field(default=0, strict=True, ge=0, description="Pagination offset")
    limit: int = Field(default=20, strict=True, ge=1, le=100, description="Pagination limit (max 100)")

    model_config = ConfigDict(extra="forbid")
