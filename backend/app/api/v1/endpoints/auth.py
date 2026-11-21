"""
SmartCart 2.0 – Authentication API Endpoints.
Provides:
- Public customer account registration (POST /api/v1/auth/register).
- User credential login & JWT access token generation (POST /api/v1/auth/login).
- Authenticated user account inspection (GET /api/v1/auth/me).

Note on Server-Side Logout:
SmartCart 2.0 uses stateless cryptographically signed JWT access tokens (HMAC-SHA256).
Because there is no server-side token revocation / blocklist table, a server-side logout
endpoint would be a cosmetic no-op ("fake logout") that cannot invalidate client-held tokens.
Per architectural instructions, client applications manage logout by securely purging the
token from client storage; no fake server-side logout route is implemented.
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_auth_service,
    get_current_user,
    get_db,
    get_user_service,
)
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.user import (
    CustomerProfileResponse,
    CustomerRegisterRequest,
    UserResponse,
)
from app.services.auth import AuthService
from app.services.user import UserService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=CustomerProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new customer account",
    description=(
        "Public self-registration for new customers. Role is strictly locked to CUSTOMER. "
        "Passwords are encrypted with Argon2id before database persistence. "
        "Clients cannot assign roles, stores, or submit password hashes."
    ),
)
async def register_customer(
    payload: CustomerRegisterRequest,
    user_service: UserService = Depends(get_user_service),
    session: AsyncSession = Depends(get_db),
) -> CustomerProfileResponse:
    """
    Register a new customer.
    Creates user account and customer profile atomically within a single transaction.
    """
    user, customer = await user_service.register_customer(
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        phone=payload.phone,
        address=payload.address,
    )
    await session.commit()

    return CustomerProfileResponse(
        id=customer.id,
        user_id=customer.user_id,
        phone=customer.phone,
        address=customer.address,
        created_at=customer.created_at,
        user=UserResponse.model_validate(user),
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate user and obtain JWT access token",
    description=(
        "Validates user credentials against stored Argon2id hashes. "
        "Returns a cryptographically signed JWT bearer access token with authoritative "
        "user claims (sub, role, store_id, customer_id). "
        "Rejects inactive accounts with a constant-time security pattern to prevent enumeration."
    ),
)
async def login(
    payload: LoginRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    """Authenticate credentials and generate JWT token."""
    return await auth_service.login(
        email=payload.email,
        password=payload.password,
    )


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current authenticated user profile",
    description="Returns the authenticated user entity resolved from the database.",
)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Return the currently authenticated user's account details."""
    return UserResponse.model_validate(current_user)
