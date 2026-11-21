import uuid
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models.customer import Customer
from app.repositories.base import BaseRepository


class CustomerRepository(BaseRepository[Customer]):
    """Repository for Customer entity."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Customer, session)

    async def get_by_user_id(self, user_id: uuid.UUID) -> Optional[Customer]:
        """Retrieve a customer profile by associated user_id."""
        stmt = select(Customer).where(Customer.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_with_user(self, customer_id: uuid.UUID) -> Optional[Customer]:
        """Retrieve customer along with eager-loaded user account."""
        stmt = (
            select(Customer)
            .options(selectinload(Customer.user))
            .where(Customer.id == customer_id)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()
