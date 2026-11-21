"""
Shopping cart domain service for SmartCart 2.0.
Coordinates active customer cart state, TTL reservation lifecycle, safe quantity updates,
and authoritative database pricing in paise.
"""
from datetime import datetime, timezone
import inspect
from typing import List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BadRequestError,
    ForbiddenError,
    InsufficientStockError,
    NotFoundError,
    ValidationError,
)
from app.models.enums import ReservationStatus
from app.repositories.reservation import ReservationRepository
from app.schemas.cart import CartItemResponse, CartResponse
from app.services.inventory import InventoryService
from app.services.product import ProductService
from app.services.store import StoreService


class CartService:
    """Service managing customer shopping cart operations and stock reservation synchronization."""

    def __init__(
        self,
        inventory_service: InventoryService,
        product_service: ProductService,
        store_service: StoreService,
        reservation_repo: ReservationRepository,
        session: Optional[AsyncSession] = None,
    ) -> None:
        self.inventory_service = inventory_service
        self.product_service = product_service
        self.store_service = store_service
        self.reservation_repo = reservation_repo
        self.session = session or inventory_service.session

    async def get_cart(self, customer_id: UUID) -> CartResponse:
        """
        Retrieve the current customer's active shopping cart.
        Calculates item totals using authoritative database prices in paise.
        Filters out expired or already-consumed reservations.
        """
        all_reservations = await self.reservation_repo.list_active_by_customer(customer_id)
        now = datetime.now(timezone.utc)

        # Retain only unlinked (order_id is None) and unexpired ACTIVE reservations
        valid_reservations = []
        for r in all_reservations:
            if r.order_id is not None:
                continue
            exp = r.expires_at if r.expires_at.tzinfo is not None else r.expires_at.replace(tzinfo=timezone.utc)
            if exp > now:
                valid_reservations.append(r)

        items: List[CartItemResponse] = []
        for res in valid_reservations:
            product = await self.product_service.get_product_by_id(res.product_id)
            subtotal = res.qty * product.price_paise
            items.append(
                CartItemResponse(
                    reservation_id=res.id,
                    product_id=product.id,
                    product_name=product.name,
                    product_sku=product.sku,
                    unit_price_paise=product.price_paise,
                    qty=res.qty,
                    item_subtotal_paise=subtotal,
                    expires_at=res.expires_at,
                )
            )

        total_items = sum(item.qty for item in items)
        total_paise = sum(item.item_subtotal_paise for item in items)
        earliest_exp = min((item.expires_at for item in items), default=None)
        store_id = valid_reservations[0].store_id if valid_reservations else None

        return CartResponse(
            store_id=store_id,
            items=items,
            total_items=total_items,
            total_paise=total_paise,
            earliest_expiration=earliest_exp,
        )

    async def add_to_cart(
        self,
        customer_id: UUID,
        store_id: UUID,
        product_id: UUID,
        qty: int,
        ttl_seconds: int = 600,
    ) -> CartResponse:
        """
        Add a product to the customer's cart by creating an inventory reservation.
        Validates active store and active product eligibility.
        Prevents mixing items from different store locations in a single cart.
        If product already exists in cart, merges and updates reservation quantity.
        """
        if qty is None or qty <= 0:
            raise ValidationError("Quantity must be a strictly positive integer")

        # 1. Validate active status of store and product
        await self.store_service.get_store_by_id(store_id, require_active=True)
        await self.product_service.get_product_by_id(product_id, require_active=True)

        # 2. Check current cart for store consistency and existing items
        current_cart = await self.get_cart(customer_id)
        if current_cart.store_id is not None and current_cart.store_id != store_id and current_cart.items:
            raise BadRequestError(
                "Cart already contains items from a different store. Please checkout or empty cart first."
            )

        # Check if product is already in cart
        existing_item = next((item for item in current_cart.items if item.product_id == product_id), None)
        if existing_item is not None:
            new_qty = existing_item.qty + qty
            return await self.update_item_quantity(
                customer_id=customer_id,
                reservation_id=existing_item.reservation_id,
                new_qty=new_qty,
                ttl_seconds=ttl_seconds,
            )

        # 3. Create fresh stock reservation
        await self.inventory_service.reserve_stock(
            customer_id=customer_id,
            store_id=store_id,
            product_id=product_id,
            qty=qty,
            ttl_seconds=ttl_seconds,
        )

        return await self.get_cart(customer_id)

    async def update_item_quantity(
        self,
        customer_id: UUID,
        reservation_id: UUID,
        new_qty: int,
        ttl_seconds: int = 600,
    ) -> CartResponse:
        """
        Safely update the quantity of a cart item.
        Uses a savepoint / nested transaction boundary:
        If reserving the new quantity fails (e.g. InsufficientStockError), the savepoint rolls back,
        preserving the customer's original valid reservation without data loss.
        """
        if new_qty is None or new_qty <= 0:
            raise ValidationError("Quantity must be a strictly positive integer")

        res = await self.inventory_service.get_reservation(reservation_id, customer_id=customer_id)
        if res.status != ReservationStatus.ACTIVE:
            raise BadRequestError(f"Cannot update reservation in '{res.status}' status")

        if res.qty == new_qty:
            return await self.get_cart(customer_id)

        # Validate store and product are still active
        await self.store_service.get_store_by_id(res.store_id, require_active=True)
        await self.product_service.get_product_by_id(res.product_id, require_active=True)

        async def _execute_safe_quantity_update() -> None:
            # Release old reservation
            released = await self.inventory_service.release_reservation(
                reservation_id=reservation_id,
                customer_id=customer_id,
            )
            if not released:
                raise BadRequestError("Could not release existing reservation during update")

            # Attempt to reserve new quantity
            await self.inventory_service.reserve_stock(
                customer_id=customer_id,
                store_id=res.store_id,
                product_id=res.product_id,
                qty=new_qty,
                ttl_seconds=ttl_seconds,
            )

        session = self.session
        in_tx = session.in_transaction()
        if inspect.iscoroutine(in_tx):
            in_tx = await in_tx

        if in_tx:
            cm = session.begin_nested()
            if inspect.iscoroutine(cm):
                cm = await cm
            async with cm:
                await _execute_safe_quantity_update()
        else:
            cm = session.begin()
            if inspect.iscoroutine(cm):
                cm = await cm
            async with cm:
                await _execute_safe_quantity_update()

        return await self.get_cart(customer_id)

    async def remove_from_cart(
        self,
        customer_id: UUID,
        reservation_id: UUID,
    ) -> CartResponse:
        """
        Remove an item from the customer's active cart by releasing its reservation.
        Enforces customer ownership.
        """
        await self.inventory_service.release_reservation(
            reservation_id=reservation_id,
            customer_id=customer_id,
        )
        return await self.get_cart(customer_id)

    async def clear_cart(self, customer_id: UUID) -> CartResponse:
        """
        Release all active cart reservations for the customer.
        """
        all_reservations = await self.reservation_repo.list_active_by_customer(customer_id)
        for res in all_reservations:
            if res.order_id is None and res.status == ReservationStatus.ACTIVE:
                await self.inventory_service.release_reservation(
                    reservation_id=res.id,
                    customer_id=customer_id,
                )
        return await self.get_cart(customer_id)
