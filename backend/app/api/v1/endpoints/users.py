"""
SmartCart 2.0 – User Management API Endpoints.
Provides:
- Current user profile retrieval (GET /api/v1/users/me).
- Authorized user profile lookup (GET /api/v1/users/{user_id}).
- Administrator user activation/deactivation (PATCH /api/v1/users/{user_id}/status).
- Administrator store manager assignment (PUT /api/v1/users/{user_id}/store-manager).

Note on User Listing (GET /api/v1/users):
Per SmartCart 2.0 architecture standards, routes must strictly delegate business logic to
domain services. The current UserService implementation does not support paginated user
enumeration, and routes are forbidden from placing raw database queries or inventing
unsupported service methods. Therefore, paginated user listing is reported as a known
limitation pending future service expansion.
"""
from uuid import UUID
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user,
    get_db,
    get_user_service,
    require_admin,
)
from app.core.exceptions import ForbiddenError
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.user import (
    CustomerProfileResponse,
    StoreManagerAssignRequest,
    UserResponse,
    UserStatusUpdateRequest,
)
from app.services.user import UserService

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current user account details",
    description="Returns the profile of the currently authenticated user.",
)
async def get_my_profile(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Return authenticated caller's profile."""
    return UserResponse.model_validate(current_user)


@router.get(
    "/me/customer",
    response_model=CustomerProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current customer profile",
    description="Returns full customer details including delivery address and phone number for CUSTOMER accounts.",
)
async def get_my_customer_profile(
    current_user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
) -> CustomerProfileResponse:
    """Return authenticated customer's full profile including address and phone."""
    if current_user.role != UserRole.CUSTOMER:
        raise ForbiddenError("Only customer accounts possess a customer profile")

    user, customer = await user_service.get_customer_profile(current_user.id)
    if customer is None:
        raise ForbiddenError("Customer profile not found for authenticated user")

    return CustomerProfileResponse(
        id=customer.id,
        user_id=customer.user_id,
        phone=customer.phone,
        address=customer.address,
        created_at=customer.created_at,
        user=UserResponse.model_validate(user),
    )


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Authorized user profile lookup",
    description=(
        "Retrieves a user profile by ID. Administrators can view any user; "
        "customers and store managers are restricted strictly to their own profile."
    ),
)
async def get_user_by_id(
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
) -> UserResponse:
    """
    Look up user by ID with authorization checks.
    Raises ForbiddenError if a non-admin attempts to view another user's profile.
    """
    if current_user.role not in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
        if current_user.id != user_id:
            raise ForbiddenError("You are not authorized to access another user's profile")

    user = await user_service.get_user_by_id(user_id)
    return UserResponse.model_validate(user)


@router.patch(
    "/{user_id}/status",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Activate or deactivate a user account",
    description=(
        "Administrator-only endpoint to toggle account active status. "
        "Prevents administrators from deactivating their own accounts."
    ),
)
async def update_user_status(
    user_id: UUID,
    payload: UserStatusUpdateRequest,
    admin_user: User = Depends(require_admin),
    user_service: UserService = Depends(get_user_service),
    session: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Activate or deactivate a target user account."""
    updated_user = await user_service.update_user_status(
        admin_user=admin_user,
        target_user_id=user_id,
        is_active=payload.is_active,
    )
    await session.commit()
    return UserResponse.model_validate(updated_user)


@router.put(
    "/{user_id}/store-manager",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Assign user as Store Manager for a store",
    description=(
        "Administrator-only endpoint to promote a user to STORE_MANAGER and bind them "
        "to a designated store. Validates that the store exists and is currently active."
    ),
)
async def assign_store_manager(
    user_id: UUID,
    payload: StoreManagerAssignRequest,
    admin_user: User = Depends(require_admin),
    user_service: UserService = Depends(get_user_service),
    session: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Assign store manager role and store binding."""
    updated_user = await user_service.assign_store_manager(
        admin_user=admin_user,
        target_user_id=user_id,
        store_id=payload.assigned_store_id,
    )
    await session.commit()
    return UserResponse.model_validate(updated_user)
