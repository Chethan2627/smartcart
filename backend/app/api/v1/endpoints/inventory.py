"""
SmartCart 2.0 – Inventory Management and Stock Reservation API Endpoints.
Provides:
- Customer stock reservation creation (POST /api/v1/inventory/reservations).
- Customer reservation retrieval (GET /api/v1/inventory/reservations/{reservation_id}).
- Reservation release (DELETE /api/v1/inventory/reservations/{reservation_id}).
- Store/product stock balance lookup (GET /api/v1/inventory/{store_id}/{product_id}).

All stock mutations, holds, and releases strictly delegate to PostgreSQL stored procedures:
- reserve_stock()
- release_reservation()
- expire_reservations()
Python code never modifies stock quantities or balances directly.
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_customer,
    get_current_user,
    get_customer_repository,
    get_db,
    get_inventory_service,
    get_optional_current_user,
    get_product_service,
    get_store_service,
)
from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.customer import Customer
from app.models.enums import UserRole
from app.models.user import User
from app.repositories.customer import CustomerRepository
from app.schemas.inventory import (
    ReservationCreateRequest,
    ReservationResponse,
    StockResponse,
)
from app.services.inventory import InventoryService
from app.services.product import ProductService
from app.services.store import StoreService

router = APIRouter(prefix="/inventory", tags=["Inventory"])


# ============================================================================
# 1. Reservation Endpoints (Declared first to prevent path matching conflicts)
# ============================================================================

@router.post(
    "/reservations",
    response_model=ReservationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an inventory hold reservation",
    description=(
        "Atomically reserves stock for a customer hold using PostgreSQL reserve_stock(). "
        "Customer ID is derived exclusively from the authenticated session. "
        "Returns HTTP 409 if available stock is insufficient."
    ),
)
async def create_reservation(
    payload: ReservationCreateRequest,
    current_customer: Customer = Depends(get_current_customer),
    inventory_service: InventoryService = Depends(get_inventory_service),
    store_service: StoreService = Depends(get_store_service),
    product_service: ProductService = Depends(get_product_service),
    session: AsyncSession = Depends(get_db),
) -> ReservationResponse:
    """
    Reserve inventory for authenticated customer.
    Enforces active store/product validation and PostgreSQL row locks.
    """
    # Validate active status
    await store_service.get_store_by_id(payload.store_id, require_active=True)
    await product_service.get_product_by_id(payload.product_id, require_active=True)

    ttl = payload.ttl_seconds if payload.ttl_seconds is not None else 600

    reservation_id = await inventory_service.reserve_stock(
        customer_id=current_customer.id,
        store_id=payload.store_id,
        product_id=payload.product_id,
        qty=payload.qty,
        ttl_seconds=ttl,
    )

    reservation = await inventory_service.get_reservation(
        reservation_id=reservation_id,
        customer_id=current_customer.id,
    )
    await session.commit()

    return ReservationResponse.model_validate(reservation)


@router.get(
    "/reservations/{reservation_id}",
    response_model=ReservationResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve inventory reservation details",
    description="Inspects reservation details and status. Enforces customer ownership and store-manager isolation.",
)
async def get_reservation(
    reservation_id: UUID,
    current_user: User = Depends(get_current_user),
    inventory_service: InventoryService = Depends(get_inventory_service),
    customer_repo: CustomerRepository = Depends(get_customer_repository),
) -> ReservationResponse:
    """
    Get reservation by ID with ownership enforcement:
    - Customer can only inspect their own reservations.
    - Store manager can only inspect reservations for their assigned store.
    - Admin can inspect any reservation.
    """
    if current_user.role == UserRole.CUSTOMER:
        customer = await customer_repo.get_by_user_id(current_user.id)
        if customer is None:
            raise NotFoundError("Customer profile not found for user")
        res = await inventory_service.get_reservation(reservation_id, customer_id=customer.id)
        return ReservationResponse.model_validate(res)

    res = await inventory_service.get_reservation(reservation_id, customer_id=None)

    if current_user.role == UserRole.STORE_MANAGER:
        if current_user.assigned_store_id != res.store_id:
            raise ForbiddenError("Store manager cannot inspect reservations from another store")

    return ReservationResponse.model_validate(res)


@router.delete(
    "/reservations/{reservation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Release an active inventory reservation",
    description=(
        "Releases reserved stock back to available inventory via PostgreSQL release_reservation(). "
        "Enforces customer ownership and store-manager isolation."
    ),
)
async def release_reservation(
    reservation_id: UUID,
    current_user: User = Depends(get_current_user),
    inventory_service: InventoryService = Depends(get_inventory_service),
    customer_repo: CustomerRepository = Depends(get_customer_repository),
    session: AsyncSession = Depends(get_db),
) -> None:
    """
    Release stock reservation and restore available balance.
    """
    if current_user.role == UserRole.CUSTOMER:
        customer = await customer_repo.get_by_user_id(current_user.id)
        if customer is None:
            raise NotFoundError("Customer profile not found for user")
        await inventory_service.release_reservation(reservation_id, customer_id=customer.id)
    elif current_user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
        await inventory_service.release_reservation(reservation_id, customer_id=None)
    elif current_user.role == UserRole.STORE_MANAGER:
        res = await inventory_service.get_reservation(reservation_id, customer_id=None)
        if current_user.assigned_store_id != res.store_id:
            raise ForbiddenError("Store manager cannot release reservations from another store")
        await inventory_service.release_reservation(reservation_id, customer_id=None)
    else:
        raise ForbiddenError("User role is not authorized to release reservations")

    await session.commit()


# ============================================================================
# 2. Store / Product Stock Lookup (Two path parameters)
# ============================================================================

@router.get(
    "/{store_id}/{product_id}",
    response_model=StockResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve store-wise product stock balance",
    description=(
        "Retrieves real-time physical on-hand, reserved, and available stock for a product "
        "at a specific store location. Enforces store-manager isolation and validates active status."
    ),
)
async def get_stock(
    store_id: UUID,
    product_id: UUID,
    current_user: Optional[User] = Depends(get_optional_current_user),
    inventory_service: InventoryService = Depends(get_inventory_service),
    store_service: StoreService = Depends(get_store_service),
    product_service: ProductService = Depends(get_product_service),
) -> StockResponse:
    """
    Retrieve inventory balance for a store + product pair.
    - Public visitors and customers may view stock for active stores and products.
    - Store managers are strictly restricted to their assigned store.
    - Administrators have global multi-store visibility.
    """
    is_admin = current_user is not None and current_user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)

    # Store manager isolation: cannot query another store's inventory
    if current_user is not None and current_user.role == UserRole.STORE_MANAGER:
        if current_user.assigned_store_id != store_id:
            raise ForbiddenError("Store manager is not authorized to access another store's inventory")

    # Inactive store / product protection for non-admin callers
    if not is_admin:
        await store_service.get_store_by_id(store_id, require_active=True)
        await product_service.get_product_by_id(product_id, require_active=True)

    return await inventory_service.get_stock(store_id=store_id, product_id=product_id)
