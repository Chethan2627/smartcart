"""
Authentication domain service for SmartCart 2.0.
Handles credential verification, inactive account prevention, customer identity resolution,
and signed JWT token generation without user enumeration.
"""
from datetime import timedelta
from typing import Any, Dict, Optional, Tuple
from uuid import UUID

from app.config import settings
from app.core.exceptions import AuthenticationError
from app.core.security import create_access_token, verify_password
from app.models.enums import UserRole
from app.models.user import User
from app.repositories.customer import CustomerRepository
from app.repositories.user import UserRepository
from app.schemas.auth import TokenResponse


class AuthService:
    """Service handling user authentication and token creation."""

    def __init__(
        self,
        user_repo: UserRepository,
        customer_repo: Optional[CustomerRepository] = None,
    ) -> None:
        self.user_repo = user_repo
        self.customer_repo = customer_repo

    async def authenticate_user(self, email: str, password: str) -> Tuple[User, Optional[UUID]]:
        """
        Authenticate user credentials.
        Returns tuple of (User, customer_id).
        Raises AuthenticationError on invalid credentials or inactive account.
        Uses constant error message to prevent email enumeration attacks.
        """
        normalized_email = email.strip().lower() if email else ""
        user = await self.user_repo.get_by_email(normalized_email)
        if user is None:
            # Constant-time mitigation / unified error message
            raise AuthenticationError("Invalid email or password")

        if not verify_password(password, user.password_hash):
            raise AuthenticationError("Invalid email or password")

        if not user.is_active:
            raise AuthenticationError("Account is inactive. Please contact support.")

        customer_id: Optional[UUID] = None
        if user.role == UserRole.CUSTOMER and self.customer_repo is not None:
            customer = await self.customer_repo.get_by_user_id(user.id)
            if customer is not None:
                customer_id = customer.id

        return user, customer_id

    async def create_token_for_user(
        self,
        user: User,
        customer_id: Optional[UUID] = None,
        expires_delta: Optional[timedelta] = None,
    ) -> TokenResponse:
        """
        Generate a signed JWT access token for an authenticated user with claims:
        sub, email, role, store_id (if STORE_MANAGER), and customer_id (if CUSTOMER).
        """
        role_val = user.role.value if hasattr(user.role, "value") else str(user.role)
        claims: Dict[str, Any] = {
            "sub": str(user.id),
            "email": user.email,
            "role": role_val,
        }

        if user.role == UserRole.STORE_MANAGER and user.assigned_store_id:
            claims["store_id"] = str(user.assigned_store_id)

        if user.role == UserRole.CUSTOMER and customer_id:
            claims["customer_id"] = str(customer_id)

        access_token = create_access_token(data=claims, expires_delta=expires_delta)
        expires_seconds = int(
            expires_delta.total_seconds()
            if expires_delta is not None
            else settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )

        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=expires_seconds,
        )

    async def login(
        self,
        email: str,
        password: str,
        expires_delta: Optional[timedelta] = None,
    ) -> TokenResponse:
        """Convenience method combining user authentication and token creation."""
        user, customer_id = await self.authenticate_user(email=email, password=password)
        return await self.create_token_for_user(
            user=user,
            customer_id=customer_id,
            expires_delta=expires_delta,
        )
