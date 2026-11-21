import uuid
from typing import Optional, Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.inventory import Inventory
from app.repositories.base import BaseRepository


class InventoryRepository(BaseRepository[Inventory]):
    """
    Repository for Inventory entity.
    Uses composite primary key: (store_id, product_id).
    Atomic stock reservations and releases are handled exclusively by PostgreSQL functions.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Inventory, session)

    async def get_stock(
        self, store_id: uuid.UUID, product_id: uuid.UUID
    ) -> Optional[Inventory]:
        """Retrieve inventory for a specific store and product via composite primary key."""
        return await self.get_by_pk(store_id, product_id)

    async def list_by_store(
        self, store_id: uuid.UUID, skip: int = 0, limit: int = 100
    ) -> Sequence[Inventory]:
        """Retrieve inventory items for a given store."""
        stmt = (
            select(Inventory)
            .where(Inventory.store_id == store_id)
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_low_stock(
        self, store_id: Optional[uuid.UUID] = None
    ) -> Sequence[Inventory]:
        """
        Retrieve inventory items where available stock (qty_on_hand - qty_reserved)
        is at or below the low_stock_threshold.
        """
        available_qty = Inventory.qty_on_hand - Inventory.qty_reserved
        stmt = select(Inventory).where(available_qty <= Inventory.low_stock_threshold)
        if store_id:
            stmt = stmt.where(Inventory.store_id == store_id)
        result = await self.session.execute(stmt)
        return result.scalars().all()
