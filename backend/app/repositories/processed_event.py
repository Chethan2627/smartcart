from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.outbox import ProcessedEvent
from app.repositories.base import BaseRepository


class ProcessedEventRepository(BaseRepository[ProcessedEvent]):
    """
    Repository for ProcessedEvent entity.
    Composite primary key: (event_id, consumer_group).
    Ensures exactly-once idempotent event consumption across consumer groups.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(ProcessedEvent, session)

    async def get_event(
        self, event_id: str, consumer_group: str
    ) -> Optional[ProcessedEvent]:
        """Retrieve deduplication record by event ID and consumer group via composite PK."""
        return await self.get_by_pk(event_id, consumer_group)

    async def is_processed(self, event_id: str, consumer_group: str) -> bool:
        """Check if an event has already been successfully processed by a consumer group."""
        return await self.exists(event_id, consumer_group)
