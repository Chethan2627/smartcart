import uuid
from typing import Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.inventory import InventoryAuditLog
from app.repositories.base import BaseRepository


class InventoryAuditLogRepository(BaseRepository[InventoryAuditLog]):
    """
    Read-only repository for InventoryAuditLog entity.
    Audit log rows are populated automatically by PostgreSQL trigger `inventory_audit`.
    No insert, update, or delete operations are exposed.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(InventoryAuditLog, session)

    async def list_by_store_and_product(
        self,
        store_id: uuid.UUID,
        product_id: uuid.UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[InventoryAuditLog]:
        """
        Retrieve audit history for a store and product ordered newest first.
        Utilizes index inventory_audit_item_idx on (store_id, product_id, changed_at DESC).
        """
        stmt = (
            select(InventoryAuditLog)
            .where(
                InventoryAuditLog.store_id == store_id,
                InventoryAuditLog.product_id == product_id,
            )
            .order_by(InventoryAuditLog.changed_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_by_store(
        self,
        store_id: uuid.UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[InventoryAuditLog]:
        """Retrieve audit history for an entire store ordered newest first."""
        stmt = (
            select(InventoryAuditLog)
            .where(InventoryAuditLog.store_id == store_id)
            .order_by(InventoryAuditLog.changed_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_recent(self, limit: int = 50) -> Sequence[InventoryAuditLog]:
        """Retrieve most recent audit log entries across all stores and products."""
        stmt = (
            select(InventoryAuditLog)
            .order_by(InventoryAuditLog.changed_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
