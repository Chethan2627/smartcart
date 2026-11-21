import uuid
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.outbox import IdempotencyKey
from app.repositories.base import BaseRepository


class IdempotencyKeyRepository(BaseRepository[IdempotencyKey]):
    """
    Repository for IdempotencyKey entity.
    Composite primary key: (customer_id, key).
    Ensures safe, deduplicated checkout operations.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(IdempotencyKey, session)

    async def get_by_customer_and_key(
        self, customer_id: uuid.UUID, key: str
    ) -> Optional[IdempotencyKey]:
        """Retrieve idempotency record by customer UUID and header key string."""
        return await self.get_by_pk(customer_id, key)
