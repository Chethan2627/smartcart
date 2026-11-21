from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from app.models.enums import UserRole


class CustomerRegisterRequest(BaseModel):
    """
    Customer self-registration request.
    Clients cannot select roles, assign stores, or inject password hashes;
    unexpected fields are strictly forbidden and rejected.
    """

    email: EmailStr = Field(description="Unique email address for account")
    password: str = Field(min_length=8, max_length=128, description="Plaintext password (min 8 chars)")
    full_name: str = Field(min_length=1, max_length=150, description="Full display name")
    phone: Optional[str] = Field(default=None, max_length=20, description="Contact phone number")
    address: Optional[str] = Field(default=None, max_length=500, description="Delivery address")

    model_config = ConfigDict(extra="forbid")


class StoreManagerAssignRequest(BaseModel):
    """Admin request to assign a STORE_MANAGER to a specific store."""

    assigned_store_id: UUID = Field(description="Target store UUID to assign to the manager")

    model_config = ConfigDict(extra="forbid")


class UserStatusUpdateRequest(BaseModel):
    """Admin request to activate or deactivate a user account."""

    is_active: bool = Field(description="Target account active status")

    model_config = ConfigDict(extra="forbid")


class UserResponse(BaseModel):
    """Public user account response representation."""

    id: UUID
    email: EmailStr
    full_name: str
    role: UserRole
    assigned_store_id: Optional[UUID] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CustomerProfileResponse(BaseModel):
    """Customer profile response with optional nested user account info."""

    id: UUID
    user_id: UUID
    phone: Optional[str] = None
    address: Optional[str] = None
    created_at: datetime
    user: Optional[UserResponse] = None

    model_config = ConfigDict(from_attributes=True)
