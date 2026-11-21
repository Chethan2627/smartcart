from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from app.models.enums import UserRole


class LoginRequest(BaseModel):
    """User login credentials request."""

    email: EmailStr = Field(description="User registered email address")
    password: str = Field(min_length=1, description="User plaintext password")

    model_config = ConfigDict(extra="forbid")


class TokenResponse(BaseModel):
    """JWT authentication token response."""

    access_token: str = Field(description="Cryptographically signed JWT access token")
    token_type: str = Field(default="bearer", description="Token scheme (bearer)")
    expires_in: int = Field(strict=True, ge=0, description="Token lifetime in seconds")


class TokenPayload(BaseModel):
    """Decoded JWT payload claims."""

    sub: str = Field(description="Subject identifier (user UUID string)")
    email: Optional[EmailStr] = None
    role: Optional[UserRole] = None
    store_id: Optional[UUID] = None
    customer_id: Optional[UUID] = None
    exp: Optional[int] = Field(default=None, strict=True)
    iat: Optional[int] = Field(default=None, strict=True)
