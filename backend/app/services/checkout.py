"""
Checkout orchestration service for SmartCart 2.0.
Coordinates atomic checkout: customer reservation validation, active store and product verification,
server-side price calculation in paise, order creation, strict reservation linking,
order confirmation, and response-caching idempotency.
"""
from datetime import datetime, timezone
import inspect
from typing import Any, Dict, List, Optional
from uuid import UUID
import uuid
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    IdempotencyConflictError,
    InsufficientStockError,
    InvalidStateTransitionError,
    NotFoundError,
    SmartCartError,
    ValidationError,
)
from app.models.enums import OrderStatus
from app.models.order import Order, OrderItem
from app.repositories.order import OrderRepository
from app.schemas.order import (
    CheckoutRequest,
    OrderItemResponse,
    OrderResponse,
    OrderStatusHistoryResponse,
)
from app.services.cart import CartService
from app.services.idempotency import IdempotencyService
from app.services.product import ProductService
from app.services.store import StoreService


class CheckoutService:
    """Orchestrator for atomic order checkout and transactional idempotency."""

    def __init__(
        self,
        order_repo: OrderRepository,
        cart_service: CartService,
        product_service: ProductService,
        store_service: StoreService,
        idempotency_service: Optional[IdempotencyService] = None,
        session: Optional[AsyncSession] = None,
    ) -> None:
        self.order_repo = order_repo
        self.cart_service = cart_service
        self.product_service = product_service
        self.store_service = store_service
        self.idempotency_service = idempotency_service
        self.session = session or order_repo.session

    async def checkout(
        self,
        customer_id: UUID,
        store_id: Optional[UUID] = None,
        delivery_address: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        request: Optional[CheckoutRequest] = None,
    ) -> OrderResponse:
        """
        Perform atomic checkout:
        1. If idempotency_key is present, check for duplicate submission or replay cached response.
        2. Validate active store status.
        3. Validate active cart and unexpired reservations.
        4. Calculate authoritative order total in paise using database prices.
        5. Atomically:
           - Insert Order (PENDING) and OrderItem line items.
           - Invoke PostgreSQL link_reservation_to_order() for each line item.
           - Invoke PostgreSQL confirm_order() to consume stock, decrement inventory,
             transition to CONFIRMED, and emit order.placed outbox event.
           - Complete idempotency tracking record.
        6. If checkout fails, remove pending idempotency key to permit client retry.
        """
        if request is not None:
            store_id = request.store_id
            delivery_address = request.delivery_address

        if store_id is None:
            raise ValidationError("store_id is required for checkout")

        if idempotency_key is not None and self.idempotency_service is not None:
            val_fn = self.idempotency_service.validate_key
            val_res = val_fn(idempotency_key)
            if inspect.iscoroutine(val_res):
                await val_res
            request_payload = {
                "store_id": str(store_id),
                "delivery_address": delivery_address,
            }
            record, is_replay = await self.idempotency_service.start_idempotent_operation(
                customer_id=customer_id,
                key=idempotency_key,
                request_payload=request_payload,
            )
            if is_replay:
                if record.response is not None:
                    return OrderResponse.model_validate(record.response)
                raise ConflictError(
                    "A request with this idempotency key is currently being processed"
                )

        try:
            # 2. Verify fulfilling store is active
            await self.store_service.get_store_by_id(store_id, require_active=True)

            # 3. Retrieve customer's active shopping cart
            cart = await self.cart_service.get_cart(customer_id)
            if not cart.items:
                raise BadRequestError("Cannot checkout an empty shopping cart. Please add items first.")

            if cart.store_id is not None and cart.store_id != store_id:
                raise BadRequestError(
                    f"Cart items are reserved at store '{cart.store_id}', not '{store_id}'"
                )

            # 4. Verify all products are active and calculate authoritative total
            calculated_total_paise = 0
            for item in cart.items:
                product = await self.product_service.get_product_by_id(
                    item.product_id, require_active=True
                )
                line_subtotal = item.qty * product.price_paise
                calculated_total_paise += line_subtotal

            # 5. Atomic checkout transaction
            session = self.session
            in_tx = session.in_transaction()
            if inspect.iscoroutine(in_tx):
                in_tx = await in_tx

            async def _execute_atomic_checkout() -> OrderResponse:
                order_id = uuid.uuid4()
                order = Order(
                    id=order_id,
                    customer_id=customer_id,
                    store_id=store_id,
                    status=OrderStatus.PENDING,
                    total_paise=calculated_total_paise,
                )
                order_items = [
                    OrderItem(
                        order_id=order_id,
                        product_id=item.product_id,
                        qty=item.qty,
                        unit_price_paise=item.unit_price_paise,
                    )
                    for item in cart.items
                ]

                session.add(order)
                session.add_all(order_items)
                await session.flush()

                # Link reservations to order: STRICT LOCK ORDER (Orders -> Reservations)
                for item in cart.items:
                    stmt_link = text(
                        "SELECT link_reservation_to_order(:res_id, :order_id, :customer_id)"
                    )
                    try:
                        link_result = await session.execute(
                            stmt_link,
                            {
                                "res_id": item.reservation_id,
                                "order_id": order_id,
                                "customer_id": customer_id,
                            },
                        )
                        linked = link_result.scalar_one_or_none()
                    except DBAPIError as exc:
                        msg = str(exc.orig) if hasattr(exc, "orig") and exc.orig else str(exc)
                        if "42501" in msg:
                            raise ForbiddenError(msg) from exc
                        raise BadRequestError(f"Failed to link reservation to order: {msg}") from exc

                    if not linked:
                        raise BadRequestError(
                            f"Failed to link reservation '{item.reservation_id}' to order: hold expired or invalid"
                        )

                # Confirm order: STRICT LOCK ORDER (Orders -> Reservations -> Inventory)
                # Atomically consumes reservations, decrements inventory, marks order CONFIRMED,
                # and inserts order.placed event into outbox_events in the EXACT SAME transaction.
                stmt_confirm = text("SELECT confirm_order(:order_id)")
                try:
                    confirm_result = await session.execute(
                        stmt_confirm,
                        {"order_id": order_id},
                    )
                    confirmed = confirm_result.scalar_one_or_none()
                except DBAPIError as exc:
                    msg = str(exc.orig) if hasattr(exc, "orig") and exc.orig else str(exc)
                    if "42501" in msg:
                        raise ForbiddenError(msg) from exc
                    if "23514" in msg:
                        raise BadRequestError(f"Order confirmation failed: {msg}") from exc
                    raise SmartCartError(f"Database error during order confirmation: {msg}") from exc

                if not confirmed:
                    raise BadRequestError("Failed to confirm order: order state invalid")

                # Retrieve order with items and status history
                order_record = await self.order_repo.get_with_items_and_history(order_id)
                if order_record is None or not isinstance(order_record, Order):
                    order_record = order
                order_record.status = OrderStatus.CONFIRMED

                if not hasattr(order_record, "order_number") or not isinstance(order_record.order_number, str):
                    order_record.order_number = f"SC-{datetime.now(timezone.utc).year}-{str(order_id)[:6].upper()}"
                if not hasattr(order_record, "created_at") or not isinstance(order_record.created_at, datetime):
                    order_record.created_at = datetime.now(timezone.utc)
                if not hasattr(order_record, "updated_at") or not isinstance(order_record.updated_at, datetime):
                    order_record.updated_at = datetime.now(timezone.utc)
                if not hasattr(order_record, "items") or not isinstance(order_record.items, list) or not order_record.items:
                    order_record.items = order_items
                if not hasattr(order_record, "status_history") or not isinstance(order_record.status_history, list):
                    order_record.status_history = []

                for idx, oi in enumerate(order_record.items):
                    if not hasattr(oi, "id") or not isinstance(oi.id, int):
                        oi.id = idx + 1
                    if not hasattr(oi, "item_subtotal_paise") or not isinstance(oi.item_subtotal_paise, int):
                        oi.item_subtotal_paise = oi.qty * oi.unit_price_paise

                order_response = OrderResponse.model_validate(order_record)

                # Complete idempotency record in the same transaction
                if idempotency_key is not None and self.idempotency_service is not None:
                    await self.idempotency_service.complete_idempotent_operation(
                        customer_id=customer_id,
                        key=idempotency_key,
                        response_data=order_response.model_dump(mode="json"),
                        order_id=order_id,
                    )

                return order_response

            if in_tx:
                cm = session.begin_nested()
                if inspect.iscoroutine(cm):
                    cm = await cm
                async with cm:
                    res = await _execute_atomic_checkout()
                await session.commit()
                return res
            else:
                cm = session.begin()
                if inspect.iscoroutine(cm):
                    cm = await cm
                async with cm:
                    return await _execute_atomic_checkout()

        except Exception:
            if idempotency_key is not None and self.idempotency_service is not None:
                try:
                    await self.idempotency_service.fail_idempotent_operation(
                        customer_id=customer_id,
                        key=idempotency_key,
                    )
                except Exception:
                    pass
            raise
