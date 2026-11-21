"""
Inventory domain service for SmartCart 2.0.
Coordinates stock lookups, reservation holds, and releases via authoritative PostgreSQL functions.
PostgreSQL owns all stock mutations, row-locking, and concurrency control.
"""
from typing import Optional
from uuid import UUID
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BadRequestError,
    ForbiddenError,
    InsufficientStockError,
    NotFoundError,
    SmartCartError,
    ValidationError,
)
from app.models.enums import ReservationStatus
from app.models.inventory import Reservation
from app.repositories.inventory import InventoryRepository
from app.repositories.reservation import ReservationRepository
from app.schemas.inventory import StockResponse


class InventoryService:
    """Service handling store-wise inventory lookups and PostgreSQL reservation functions."""

    def __init__(
        self,
        inventory_repo: InventoryRepository,
        reservation_repo: ReservationRepository,
        session: Optional[AsyncSession] = None,
    ) -> None:
        self.inventory_repo = inventory_repo
        self.reservation_repo = reservation_repo
        self.session = session or inventory_repo.session

    async def get_stock(self, store_id: UUID, product_id: UUID) -> StockResponse:
        """
        Retrieve inventory balance for a product at a specific store.
        Raises NotFoundError if the inventory row does not exist.
        """
        stock = await self.inventory_repo.get_stock(store_id, product_id)
        if stock is None:
            raise NotFoundError(
                f"Inventory record for product '{product_id}' at store '{store_id}' not found"
            )

        qty_available = max(0, stock.qty_on_hand - stock.qty_reserved)
        is_low_stock = qty_available <= stock.low_stock_threshold

        return StockResponse(
            store_id=stock.store_id,
            product_id=stock.product_id,
            qty_on_hand=stock.qty_on_hand,
            qty_reserved=stock.qty_reserved,
            qty_available=qty_available,
            low_stock_threshold=stock.low_stock_threshold,
            is_low_stock=is_low_stock,
            updated_at=stock.updated_at,
        )

    async def get_available_stock(self, store_id: UUID, product_id: UUID) -> int:
        """
        Retrieve available stock (qty_on_hand - qty_reserved) for a product at a store.
        Uses the inventory_available view or authoritative inventory balance.
        """
        stmt = text(
            """
            SELECT qty_available
              FROM inventory_available
             WHERE store_id = :store_id
               AND product_id = :product_id
            """
        )
        result = await self.session.execute(stmt, {"store_id": store_id, "product_id": product_id})
        available = result.scalar_one_or_none()
        if available is not None:
            return int(available)

        # Fallback to direct inventory table lookup
        stock = await self.inventory_repo.get_stock(store_id, product_id)
        if stock is None:
            raise NotFoundError(
                f"Inventory not found for product '{product_id}' at store '{store_id}'"
            )
        return max(0, stock.qty_on_hand - stock.qty_reserved)

    async def reserve_stock(
        self,
        customer_id: UUID,
        store_id: UUID,
        product_id: UUID,
        qty: int,
        ttl_seconds: int = 600,
    ) -> UUID:
        """
        Reserve stock atomically by invoking PostgreSQL's reserve_stock() function.
        Strictly prevents overselling through database-level row locks and validation.
        Translates database failures into domain exceptions.
        """
        if qty is None or qty <= 0:
            raise ValidationError("Reservation quantity must be a strictly positive integer")
        if ttl_seconds is None or ttl_seconds <= 0 or ttl_seconds > 3600:
            raise ValidationError("Reservation hold TTL must be between 1 and 3600 seconds")

        stmt = text(
            """
            SELECT reserve_stock(
                :customer,
                :store,
                :product,
                :qty,
                make_interval(secs => :ttl)
            )
            """
        )

        try:
            result = await self.session.execute(
                stmt,
                {
                    "customer": customer_id,
                    "store": store_id,
                    "product": product_id,
                    "qty": qty,
                    "ttl": ttl_seconds,
                },
            )
            res_id = result.scalar_one_or_none()
        except DBAPIError as exc:
            msg = str(exc.orig) if hasattr(exc, "orig") and exc.orig else str(exc)
            if "is inactive" in msg:
                raise BadRequestError(msg) from exc
            if "does not exist" in msg:
                raise NotFoundError(msg) from exc
            if "must be positive" in msg:
                raise ValidationError(msg) from exc
            raise SmartCartError(f"Database error during stock reservation: {msg}") from exc

        if res_id is None:
            raise InsufficientStockError(
                f"Insufficient available stock for product '{product_id}' at store '{store_id}'"
            )

        return res_id

    async def release_reservation(
        self,
        reservation_id: UUID,
        customer_id: Optional[UUID] = None,
        status: ReservationStatus = ReservationStatus.RELEASED,
    ) -> bool:
        """
        Release an active reservation by calling PostgreSQL's release_reservation() function.
        Validates customer ownership and prevents unauthorized releases.
        """
        res = await self.reservation_repo.get_by_id(reservation_id)
        if res is None:
            raise NotFoundError(f"Reservation '{reservation_id}' not found")

        if customer_id is not None and res.customer_id != customer_id:
            raise ForbiddenError("Cannot release a reservation belonging to another customer")

        if res.status != ReservationStatus.ACTIVE:
            raise BadRequestError(f"Cannot release reservation in '{res.status}' status")

        status_str = status.value if hasattr(status, "value") else str(status)
        stmt = text("SELECT release_reservation(:res_id, :status)")

        try:
            result = await self.session.execute(stmt, {"res_id": reservation_id, "status": status_str})
            return bool(result.scalar_one_or_none())
        except DBAPIError as exc:
            msg = str(exc.orig) if hasattr(exc, "orig") and exc.orig else str(exc)
            raise SmartCartError(f"Database error during reservation release: {msg}") from exc

    async def expire_reservations(self, batch_size: int = 500) -> int:
        """
        Expire overdue active reservations in batches via PostgreSQL's expire_reservations().
        Used by background expiration cleanup tasks.
        """
        if batch_size is None or batch_size <= 0:
            raise ValidationError("Batch size must be a strictly positive integer")

        stmt = text("SELECT expire_reservations(:batch)")
        try:
            result = await self.session.execute(stmt, {"batch": batch_size})
            return int(result.scalar_one_or_none() or 0)
        except DBAPIError as exc:
            msg = str(exc.orig) if hasattr(exc, "orig") and exc.orig else str(exc)
            raise SmartCartError(f"Database error during reservation expiration: {msg}") from exc

    async def get_reservation(
        self,
        reservation_id: UUID,
        customer_id: Optional[UUID] = None,
    ) -> Reservation:
        """
        Retrieve reservation details and validate ownership.
        """
        res = await self.reservation_repo.get_by_id(reservation_id)
        if res is None:
            raise NotFoundError(f"Reservation '{reservation_id}' not found")

        if customer_id is not None and res.customer_id != customer_id:
            raise ForbiddenError("Cannot access reservation belonging to another customer")

        return res
