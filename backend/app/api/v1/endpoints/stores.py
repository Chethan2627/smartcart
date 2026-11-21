"""
SmartCart 2.0 – Store API Endpoints.
Provides:
- Listing active stores with pagination and location filters (GET /api/v1/stores).
- Store details retrieval by ID (GET /api/v1/stores/{store_id}).

Note on Store Availability (GET /api/v1/stores/{store_id}/availability):
Omitted per architecture specification. In SmartCart 2.0, inventory availability is
scoped to store + product pairs via InventoryService and the inventory_available view.
StoreService does not define a store-level aggregate availability concept, and raw
database queries are forbidden in API endpoint handlers.
"""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import (
    get_optional_current_user,
    get_store_service,
)
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.store import StoreFilterParams, StoreResponse
from app.services.store import StoreService

router = APIRouter(prefix="/stores", tags=["Stores"])


@router.get(
    "",
    response_model=List[StoreResponse],
    status_code=status.HTTP_200_OK,
    summary="List active stores",
    description=(
        "Retrieves active fulfillment stores. Supports pagination (skip/limit) and location "
        "filtering by state and optional city. Inactive stores are excluded for public and customer users."
    ),
)
async def list_stores(
    state: Optional[str] = Query(None, description="Filter stores by state (e.g. KA)"),
    city: Optional[str] = Query(None, description="Filter stores by city (e.g. Bangalore)"),
    is_active: Optional[bool] = Query(True, description="Filter by active status (Admin only for inactive)"),
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(50, ge=1, le=100, description="Pagination limit (max 100)"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    store_service: StoreService = Depends(get_store_service),
) -> List[StoreResponse]:
    """
    List stores with location filtering and pagination.
    Inactive stores are strictly hidden from non-admin users.
    """
    # Validate filter inputs via schema DTO
    StoreFilterParams(state=state, city=city, is_active=is_active, skip=skip, limit=limit)

    is_admin = current_user is not None and current_user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)

    # Inactive stores must not appear in public listings
    if not is_admin:
        effective_require_active = True
    else:
        effective_require_active = (is_active is not False)

    if state:
        stores = await store_service.list_stores_by_location(
            state=state, city=city, require_active=effective_require_active
        )
        paginated_stores = stores[skip : skip + limit]
    else:
        paginated_stores = await store_service.list_active_stores(skip=skip, limit=limit)

    return [StoreResponse.model_validate(s) for s in paginated_stores]


@router.get(
    "/{store_id}",
    response_model=StoreResponse,
    status_code=status.HTTP_200_OK,
    summary="Get store details",
    description=(
        "Retrieves store details by UUID. Inactive stores are only viewable by "
        "administrators or the assigned store manager."
    ),
)
async def get_store(
    store_id: UUID,
    current_user: Optional[User] = Depends(get_optional_current_user),
    store_service: StoreService = Depends(get_store_service),
) -> StoreResponse:
    """
    Retrieve store by ID.
    Inactive stores are inaccessible to public visitors, customers, and unaffiliated managers.
    """
    is_admin = current_user is not None and current_user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)
    is_assigned_manager = (
        current_user is not None
        and current_user.role == UserRole.STORE_MANAGER
        and current_user.assigned_store_id == store_id
    )

    # Inactive store access is only granted to administrators or the assigned store manager
    require_active = not (is_admin or is_assigned_manager)

    store = await store_service.get_store_by_id(store_id, require_active=require_active)
    return StoreResponse.model_validate(store)
