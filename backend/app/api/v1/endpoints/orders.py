"""
SmartCart 2.0 – Order Management API Endpoints.
Provides:
- Paginated customer and store order listing (GET /api/v1/orders).
- Order details lookup by UUID (GET /api/v1/orders/{order_id}).
- Order cancellation and inventory restoration (POST /api/v1/orders/{order_id}/cancel).

Enforces:
- Customer ownership: customers can only view and cancel their own orders.
- Store manager isolation: store managers are restricted to orders from their assigned store.
- Administrators have global multi-store visibility.
- Order cancellations, state transitions, and stock restoration are executed via PostgreSQL cancel_order().
"""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user,
    get_customer_repository,
    get_db,
    get_order_service,
)
from app.core.exceptions import BadRequestError, ForbiddenError, NotFoundError
from app.models.enums import OrderStatus, UserRole
from app.models.user import User
from app.repositories.customer import CustomerRepository
from app.schemas.order import (
    OrderCancelRequest,
    OrderFilterParams,
    OrderResponse,
)
from app.services.order import OrderService

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.get(
    "",
    response_model=List[OrderResponse],
    status_code=status.HTTP_200_OK,
    summary="List customer or store orders",
    description=(
        "Retrieves a paginated list of orders: "
        "- For CUSTOMER: returns caller's own orders newest first. "
        "- For STORE_MANAGER: returns orders fulfilled by their assigned store. "
        "- For ADMIN: returns orders for the specified store_id filter."
    ),
)
async def list_orders(
    store_id: Optional[UUID] = Query(None, description="Fulfilling store filter (admin/store manager)"),
    order_status: Optional[OrderStatus] = Query(None, alias="status", description="Order status filter"),
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(20, ge=1, le=100, description="Pagination limit (max 100)"),
    current_user: User = Depends(get_current_user),
    order_service: OrderService = Depends(get_order_service),
    customer_repo: CustomerRepository = Depends(get_customer_repository),
) -> List[OrderResponse]:
    """
    List orders with role-based scoping and pagination.
    """
    # Validate via schema DTO
    OrderFilterParams(store_id=store_id, status=order_status, skip=skip, limit=limit)

    if current_user.role == UserRole.CUSTOMER:
        customer = await customer_repo.get_by_user_id(current_user.id)
        if customer is None:
            raise NotFoundError("Customer profile not found for user")
        orders = await order_service.list_customer_orders(
            customer_id=customer.id, skip=skip, limit=limit
        )
        full_orders = [await order_service.get_order(o.id) for o in orders]
        return [OrderResponse.model_validate(o) for o in full_orders]

    if current_user.role == UserRole.STORE_MANAGER:
        if current_user.assigned_store_id is None:
            raise ForbiddenError("Store manager is not assigned to any store")
        orders = await order_service.list_store_orders(
            store_id=current_user.assigned_store_id,
            status=order_status,
            skip=skip,
            limit=limit,
        )
        full_orders = [await order_service.get_order(o.id) for o in orders]
        return [OrderResponse.model_validate(o) for o in full_orders]

    if current_user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
        if store_id is not None:
            orders = await order_service.list_store_orders(
                store_id=store_id, status=order_status, skip=skip, limit=limit
            )
            full_orders = [await order_service.get_order(o.id) for o in orders]
            return [OrderResponse.model_validate(o) for o in full_orders]
        raise BadRequestError("store_id parameter is required when administrators list store orders")

    raise ForbiddenError("User role is not authorized to list orders")


@router.get(
    "/{order_id}",
    response_model=OrderResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve order details",
    description="Inspects an order with line items and status transition history. Enforces strict ownership.",
)
async def get_order(
    order_id: UUID,
    current_user: User = Depends(get_current_user),
    order_service: OrderService = Depends(get_order_service),
    customer_repo: CustomerRepository = Depends(get_customer_repository),
) -> OrderResponse:
    """
    Get order details by UUID:
    - Customers can only access their own orders.
    - Store managers can only access orders for their assigned store.
    - Administrators can inspect any order.
    """
    if current_user.role == UserRole.CUSTOMER:
        customer = await customer_repo.get_by_user_id(current_user.id)
        if customer is None:
            raise NotFoundError("Customer profile not found for user")
        order = await order_service.get_order(order_id=order_id, customer_id=customer.id)
        return OrderResponse.model_validate(order)

    order = await order_service.get_order(order_id=order_id, customer_id=None)

    if current_user.role == UserRole.STORE_MANAGER:
        if current_user.assigned_store_id != order.store_id:
            raise ForbiddenError("Store manager is not authorized to view orders from another store")

    return OrderResponse.model_validate(order)


@router.post(
    "/{order_id}/cancel",
    response_model=OrderResponse,
    status_code=status.HTTP_200_OK,
    summary="Cancel order and restore inventory",
    description=(
        "Cancels an eligible order via PostgreSQL cancel_order(). "
        "Restores reserved inventory, transitions order to CANCELLED, and logs order.cancelled outbox event. "
        "Enforces customer ownership and store-manager isolation."
    ),
)
async def cancel_order(
    order_id: UUID,
    payload: Optional[OrderCancelRequest] = None,
    current_user: User = Depends(get_current_user),
    order_service: OrderService = Depends(get_order_service),
    customer_repo: CustomerRepository = Depends(get_customer_repository),
    session: AsyncSession = Depends(get_db),
) -> OrderResponse:
    """
    Cancel order and restore inventory.
    """
    reason = payload.reason if (payload and payload.reason) else "Customer requested cancellation"

    if current_user.role == UserRole.CUSTOMER:
        customer = await customer_repo.get_by_user_id(current_user.id)
        if customer is None:
            raise NotFoundError("Customer profile not found for user")
        await order_service.cancel_order(
            order_id=order_id, customer_id=customer.id, reason=reason
        )
    elif current_user.role == UserRole.STORE_MANAGER:
        order = await order_service.get_order(order_id=order_id, customer_id=None)
        if current_user.assigned_store_id != order.store_id:
            raise ForbiddenError("Store manager cannot cancel orders from another store")
        await order_service.cancel_order(
            order_id=order_id, customer_id=None, reason=reason
        )
    elif current_user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
        await order_service.cancel_order(
            order_id=order_id, customer_id=None, reason=reason
        )
    else:
        raise ForbiddenError("User role is not authorized to cancel orders")

    await session.commit()
    updated_order = await order_service.get_order(order_id=order_id, customer_id=None)
    return OrderResponse.model_validate(updated_order)
