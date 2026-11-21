from typing import Optional, Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.product import Product
from app.repositories.base import BaseRepository


class ProductRepository(BaseRepository[Product]):
    """Repository for Product entity."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Product, session)

    async def get_by_sku(self, sku: str) -> Optional[Product]:
        """Retrieve a product by unique SKU."""
        stmt = select(Product).where(Product.sku == sku)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_active(
        self, skip: int = 0, limit: int = 100
    ) -> Sequence[Product]:
        """Retrieve active products."""
        stmt = select(Product).where(Product.is_active == True).offset(skip).limit(limit)  # noqa: E712
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_by_category(
        self, category: str, skip: int = 0, limit: int = 100
    ) -> Sequence[Product]:
        """Retrieve products by category."""
        stmt = (
            select(Product)
            .where(Product.category == category, Product.is_active == True)  # noqa: E712
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
