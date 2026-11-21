import uuid
from typing import Optional, Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models.enums import OrderStatus
from app.models.order import Order
from app.repositories.base import BaseRepository


class OrderRepository(BaseRepository[Order]):
    """
    Repository for Order entity.
    Order state machine transitions and audit history are governed by PostgreSQL triggers.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Order, session)

    async def get_by_order_number(self, order_number: str) -> Optional[Order]:
        """Retrieve an order by its unique sequential order number (e.g., SC-2026-000001)."""
        stmt = select(Order).where(Order.order_number == order_number)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_with_items_and_history(self, order_id: uuid.UUID) -> Optional[Order]:
        """Retrieve an order with eager-loaded items and status transition history."""
        stmt = (
            select(Order)
            .options(
                selectinload(Order.items),
                selectinload(Order.status_history),
                selectinload(Order.store),
                selectinload(Order.customer),
            )
            .where(Order.id == order_id)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_by_customer(
        self, customer_id: uuid.UUID, skip: int = 0, limit: int = 100
    ) -> Sequence[Order]:
        """Retrieve orders placed by a customer, ordered newest first."""
        stmt = (
            select(Order)
            .where(Order.customer_id == customer_id)
            .order_by(Order.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_by_store_and_status(
        self,
        store_id: uuid.UUID,
        status: Optional[OrderStatus] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[Order]:
        """Retrieve orders for a fulfilling store, optionally filtered by status."""
        stmt = select(Order).where(Order.store_id == store_id)
        if status:
            stmt = stmt.where(Order.status == status)
        stmt = stmt.order_by(Order.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()
