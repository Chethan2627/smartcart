from typing import Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.enums import OutboxStatus
from app.models.outbox import OutboxEvent
from app.repositories.base import BaseRepository


class OutboxEventRepository(BaseRepository[OutboxEvent]):
    """
    Repository for OutboxEvent entity.
    Supports transactional outbox pattern for Kafka event dispatching.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(OutboxEvent, session)

    async def list_pending(self, limit: int = 100) -> Sequence[OutboxEvent]:
        """
        Retrieve batch of PENDING events ordered by creation timestamp.
        Uses partial index outbox_events_pending_idx.
        """
        stmt = (
            select(OutboxEvent)
            .where(OutboxEvent.status == OutboxStatus.PENDING)
            .order_by(OutboxEvent.created_at.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_by_aggregate(
        self, aggregate_type: str, aggregate_id: str
    ) -> Sequence[OutboxEvent]:
        """Retrieve events for a given aggregate (e.g., aggregate_type='order', aggregate_id=order_id)."""
        stmt = (
            select(OutboxEvent)
            .where(
                OutboxEvent.aggregate_type == aggregate_type,
                OutboxEvent.aggregate_id == aggregate_id,
            )
            .order_by(OutboxEvent.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
