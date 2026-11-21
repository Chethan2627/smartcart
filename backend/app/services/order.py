"""
Order domain service for SmartCart 2.0.
Coordinates order lifecycle, customer order history, and status transitions.
All order cancellations, inventory restorations, and state-machine transitions
are authoritatively governed by PostgreSQL functions and database triggers.
"""
from typing import Optional, Sequence
from uuid import UUID
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BadRequestError,
    ForbiddenError,
    InvalidStateTransitionError,
    NotFoundError,
    SmartCartError,
    ValidationError,
)
from app.models.enums import OrderStatus
from app.models.order import Order
from app.repositories.order import OrderRepository


class OrderService:
    """Service managing order lifecycle, retrieval, and state transitions."""

    def __init__(
        self,
        order_repo: OrderRepository,
        session: Optional[AsyncSession] = None,
    ) -> None:
        self.order_repo = order_repo
        self.session = session or order_repo.session

    async def get_order(
        self,
        order_id: UUID,
        customer_id: Optional[UUID] = None,
    ) -> Order:
        """
        Retrieve an order with its line items, status history, store, and customer.
        Validates customer ownership if customer_id is provided.
        """
        order = await self.order_repo.get_with_items_and_history(order_id)
        if order is None:
            raise NotFoundError(f"Order '{order_id}' not found")

        if customer_id is not None and order.customer_id != customer_id:
            raise ForbiddenError("Cannot access order belonging to another customer")

        return order

    async def get_order_by_number(
        self,
        order_number: str,
        customer_id: Optional[UUID] = None,
    ) -> Order:
        """
        Retrieve an order by unique sequential order number (e.g., SC-2026-000001).
        Validates customer ownership if customer_id is provided.
        """
        order = await self.order_repo.get_by_order_number(order_number)
        if order is None:
            raise NotFoundError(f"Order '{order_number}' not found")

        if customer_id is not None and order.customer_id != customer_id:
            raise ForbiddenError("Cannot access order belonging to another customer")

        return order

    async def list_customer_orders(
        self,
        customer_id: UUID,
        skip: int = 0,
        limit: int = 20,
    ) -> Sequence[Order]:
        """
        Retrieve a paginated list of orders placed by a customer, ordered newest first.
        """
        if skip < 0:
            raise ValidationError("skip must be non-negative")
        if limit <= 0 or limit > 100:
            raise ValidationError("limit must be between 1 and 100")

        return await self.order_repo.list_by_customer(customer_id, skip=skip, limit=limit)

    async def list_store_orders(
        self,
        store_id: UUID,
        status: Optional[OrderStatus] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> Sequence[Order]:
        """
        Retrieve a paginated list of orders for a store, optionally filtered by status.
        """
        if skip < 0:
            raise ValidationError("skip must be non-negative")
        if limit <= 0 or limit > 100:
            raise ValidationError("limit must be between 1 and 100")

        return await self.order_repo.list_by_store_and_status(
            store_id, status=status, skip=skip, limit=limit
        )

    async def cancel_order(
        self,
        order_id: UUID,
        customer_id: Optional[UUID] = None,
        reason: str = "Customer requested cancellation",
    ) -> bool:
        """
        Cancel an order atomically via PostgreSQL's cancel_order() function.
        Validates customer ownership, transitions order to CANCELLED, restores inventory,
        releases active reservations, and logs the order.cancelled outbox event.
        Returns False if the order was already CANCELLED (idempotent cancellation).
        """
        if not reason or not reason.strip():
            raise ValidationError("Cancellation reason must not be empty")
        if len(reason) > 255:
            raise ValidationError("Cancellation reason must not exceed 255 characters")

        stmt = text("SELECT cancel_order(:order_id, :customer_id, :reason)")
        try:
            result = await self.session.execute(
                stmt,
                {
                    "order_id": order_id,
                    "customer_id": customer_id,
                    "reason": reason.strip(),
                },
            )
            return bool(result.scalar_one_or_none())
        except DBAPIError as exc:
            msg = str(exc.orig) if hasattr(exc, "orig") and exc.orig else str(exc)
            if "P0002" in msg or "not found" in msg.lower():
                raise NotFoundError(f"Order '{order_id}' not found") from exc
            if "42501" in msg or "unauthorized" in msg.lower() or "does not belong" in msg.lower():
                raise ForbiddenError("Unauthorized: order does not belong to specified customer") from exc
            if "23514" in msg or "cannot cancel order in" in msg.lower() or "invalid order transition" in msg.lower():
                raise InvalidStateTransitionError(msg) from exc
            raise SmartCartError(f"Database error during order cancellation: {msg}") from exc

    async def confirm_order(self, order_id: UUID) -> bool:
        """
        Confirm a pending order atomically via PostgreSQL's confirm_order() function.
        Consumes valid reservations, decrements inventory, marks order CONFIRMED,
        and generates order.placed outbox event.
        """
        stmt = text("SELECT confirm_order(:order_id)")
        try:
            result = await self.session.execute(stmt, {"order_id": order_id})
            return bool(result.scalar_one_or_none())
        except DBAPIError as exc:
            msg = str(exc.orig) if hasattr(exc, "orig") and exc.orig else str(exc)
            if "23503" in msg or "does not exist" in msg.lower():
                raise NotFoundError(f"Order '{order_id}' not found") from exc
            if "42501" in msg or "unauthorized" in msg.lower() or "different customer" in msg.lower():
                raise ForbiddenError(msg) from exc
            if "23514" in msg:
                raise BadRequestError(msg) from exc
            raise SmartCartError(f"Database error during order confirmation: {msg}") from exc

    async def update_order_status(
        self,
        order_id: UUID,
        to_status: OrderStatus,
    ) -> Order:
        """
        Transition order status along the authorized state machine (e.g., PACKED, SHIPPED, DELIVERED).
        State transitions are authoritatively enforced by the database trigger enforce_order_transition().
        """
        order = await self.get_order(order_id)
        if order.status == to_status:
            return order

        order.status = to_status
        try:
            await self.session.flush()
            return order
        except DBAPIError as exc:
            msg = str(exc.orig) if hasattr(exc, "orig") and exc.orig else str(exc)
            if "23514" in msg or "invalid order transition" in msg.lower():
                raise InvalidStateTransitionError(
                    f"Invalid order transition to '{to_status.value if hasattr(to_status, 'value') else to_status}'"
                ) from exc
            raise SmartCartError(f"Database error during status update: {msg}") from exc
