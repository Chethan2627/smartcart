from typing import Optional, Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.store import Store
from app.repositories.base import BaseRepository


class StoreRepository(BaseRepository[Store]):
    """Repository for Store entity."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Store, session)

    async def get_by_code(self, code: str) -> Optional[Store]:
        """Retrieve a store by unique code (e.g., STORE-001)."""
        stmt = select(Store).where(Store.code == code)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_active(self, skip: int = 0, limit: int = 100) -> Sequence[Store]:
        """Retrieve active stores."""
        stmt = select(Store).where(Store.is_active == True).offset(skip).limit(limit)  # noqa: E712
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_by_state_and_city(
        self, state: str, city: Optional[str] = None
    ) -> Sequence[Store]:
        """Retrieve stores by state and optional city."""
        stmt = select(Store).where(Store.state == state)
        if city:
            stmt = stmt.where(Store.city == city)
        result = await self.session.execute(stmt)
        return result.scalars().all()
