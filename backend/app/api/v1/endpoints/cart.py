"""
SmartCart 2.0 – Shopping Cart API Endpoints.
Provides:
- Current customer cart retrieval (GET /api/v1/cart).
- Add item to cart with stock reservation hold (POST /api/v1/cart/items).
- Update cart item quantity (PATCH /api/v1/cart/items/{product_id}).
- Remove cart item and release reservation (DELETE /api/v1/cart/items/{product_id}).
- Clear all items in active cart (DELETE /api/v1/cart).

Guarantees:
- Customer ID is securely derived from JWT authentication, never accepted from request input.
- All product prices are database-authoritative from PostgreSQL products table.
- Stock reservations strictly expire after the configured 10-minute (600s) TTL.
- Enforces single-store cart constraint (items cannot be mixed across fulfillment stores).
"""
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_cart_service,
    get_current_customer,
    get_db,
)
from app.core.exceptions import NotFoundError
from app.models.customer import Customer
from app.schemas.cart import (
    CartItemAddRequest,
    CartItemUpdateRequest,
    CartResponse,
)
from app.services.cart import CartService

router = APIRouter(prefix="/cart", tags=["Cart"])


@router.get(
    "",
    response_model=CartResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve current customer shopping cart",
    description=(
        "Returns the authenticated customer's active shopping cart with line items, "
        "authoritative database prices, item subtotals, grand total, and earliest expiration timestamp. "
        "Automatically filters out expired reservations."
    ),
)
async def get_cart(
    current_customer: Customer = Depends(get_current_customer),
    cart_service: CartService = Depends(get_cart_service),
) -> CartResponse:
    """Retrieve active cart state for the authenticated customer."""
    return await cart_service.get_cart(customer_id=current_customer.id)


@router.post(
    "/items",
    response_model=CartResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add item to cart and reserve stock",
    description=(
        "Adds an item to the customer's cart by holding a 10-minute reservation via PostgreSQL reserve_stock(). "
        "Validates store and product are active. Rejects items from a different store than existing cart items. "
        "Returns HTTP 409 if available stock is insufficient."
    ),
)
async def add_item_to_cart(
    payload: CartItemAddRequest,
    current_customer: Customer = Depends(get_current_customer),
    cart_service: CartService = Depends(get_cart_service),
    session: AsyncSession = Depends(get_db),
) -> CartResponse:
    """
    Add product to active cart with authoritative 10-minute reservation hold.
    """
    cart = await cart_service.add_to_cart(
        customer_id=current_customer.id,
        store_id=payload.store_id,
        product_id=payload.product_id,
        qty=payload.qty,
        ttl_seconds=600,
    )
    await session.commit()
    return cart


@router.patch(
    "/items/{product_id}",
    response_model=CartResponse,
    status_code=status.HTTP_200_OK,
    summary="Update cart item quantity",
    description=(
        "Updates the desired quantity of an existing item in the cart. "
        "Uses safe nested transaction rollback: if the new quantity exceeds available stock, "
        "the customer's original reservation is preserved without loss."
    ),
)
async def update_cart_item_quantity(
    product_id: UUID,
    payload: CartItemUpdateRequest,
    current_customer: Customer = Depends(get_current_customer),
    cart_service: CartService = Depends(get_cart_service),
    session: AsyncSession = Depends(get_db),
) -> CartResponse:
    """
    Update item quantity using safe reservation replacement.
    """
    current_cart = await cart_service.get_cart(customer_id=current_customer.id)
    item = next((i for i in current_cart.items if i.product_id == product_id), None)
    if item is None:
        raise NotFoundError(f"Product '{product_id}' is not in your shopping cart")

    cart = await cart_service.update_item_quantity(
        customer_id=current_customer.id,
        reservation_id=item.reservation_id,
        new_qty=payload.qty,
        ttl_seconds=600,
    )
    await session.commit()
    return cart


@router.delete(
    "/items/{product_id}",
    response_model=CartResponse,
    status_code=status.HTTP_200_OK,
    summary="Remove item from cart",
    description=(
        "Removes a line item from the shopping cart and immediately releases its reserved stock "
        "back to available inventory via PostgreSQL release_reservation()."
    ),
)
async def remove_cart_item(
    product_id: UUID,
    current_customer: Customer = Depends(get_current_customer),
    cart_service: CartService = Depends(get_cart_service),
    session: AsyncSession = Depends(get_db),
) -> CartResponse:
    """
    Remove product from cart and release reservation hold.
    """
    current_cart = await cart_service.get_cart(customer_id=current_customer.id)
    item = next((i for i in current_cart.items if i.product_id == product_id), None)
    if item is None:
        raise NotFoundError(f"Product '{product_id}' is not in your shopping cart")

    cart = await cart_service.remove_from_cart(
        customer_id=current_customer.id,
        reservation_id=item.reservation_id,
    )
    await session.commit()
    return cart


@router.delete(
    "",
    response_model=CartResponse,
    status_code=status.HTTP_200_OK,
    summary="Clear all items from shopping cart",
    description="Releases all active reservations in the customer's cart and returns an empty cart.",
)
async def clear_cart(
    current_customer: Customer = Depends(get_current_customer),
    cart_service: CartService = Depends(get_cart_service),
    session: AsyncSession = Depends(get_db),
) -> CartResponse:
    """
    Clear all cart items and release all associated reservations.
    """
    cart = await cart_service.clear_cart(customer_id=current_customer.id)
    await session.commit()
    return cart
