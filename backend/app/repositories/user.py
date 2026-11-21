import uuid
from typing import Optional, Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.enums import UserRole
from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Repository for User entity."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(User, session)

    async def get_by_email(self, email: str) -> Optional[User]:
        """Retrieve a user by unique email address."""
        stmt = select(User).where(User.email == email)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_by_role(
        self, role: UserRole, skip: int = 0, limit: int = 100
    ) -> Sequence[User]:
        """Retrieve users filtered by role."""
        stmt = select(User).where(User.role == role).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_manager_for_store(self, store_id: uuid.UUID) -> Optional[User]:
        """Retrieve the assigned STORE_MANAGER for a given store."""
        stmt = select(User).where(
            User.role == UserRole.STORE_MANAGER,
            User.assigned_store_id == store_id,
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()
