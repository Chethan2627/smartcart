"""
Product domain service for SmartCart 2.0.
Handles catalogue browsing, SKU lookups, category/brand filtering,
active status checks, and authoritative database price verification.
"""
from typing import Optional, Sequence
from uuid import UUID
from sqlalchemy import select

from app.core.exceptions import BadRequestError, NotFoundError
from app.models.product import Product
from app.repositories.product import ProductRepository


class ProductService:
    """Service handling product catalogue operations and authoritative price verification."""

    def __init__(self, product_repo: ProductRepository) -> None:
        self.product_repo = product_repo

    async def get_product_by_id(self, product_id: UUID, require_active: bool = False) -> Product:
        """
        Retrieve product by UUID.
        Raises NotFoundError if not found.
        Raises BadRequestError if require_active is True and product is inactive.
        """
        product = await self.product_repo.get_by_id(product_id)
        if product is None:
            raise NotFoundError(f"Product with id '{product_id}' not found")

        if require_active and not product.is_active:
            raise BadRequestError(f"Product '{product.name}' ({product.sku}) is currently inactive")

        return product

    async def get_product_by_sku(self, sku: str, require_active: bool = False) -> Product:
        """
        Retrieve product by unique SKU.
        Raises NotFoundError if not found.
        Raises BadRequestError if require_active is True and product is inactive.
        """
        product = await self.product_repo.get_by_sku(sku)
        if product is None:
            raise NotFoundError(f"Product with SKU '{sku}' not found")

        if require_active and not product.is_active:
            raise BadRequestError(f"Product '{product.name}' ({sku}) is currently inactive")

        return product

    async def list_active_products(self, skip: int = 0, limit: int = 100) -> Sequence[Product]:
        """List active catalogue products with pagination."""
        return await self.product_repo.list_active(skip=skip, limit=limit)

    async def list_products_by_category(
        self, category: str, skip: int = 0, limit: int = 100
    ) -> Sequence[Product]:
        """List active products within a specific category."""
        return await self.product_repo.list_by_category(category=category, skip=skip, limit=limit)

    async def list_products_filtered(
        self,
        category: Optional[str] = None,
        brand: Optional[str] = None,
        is_active: Optional[bool] = True,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[Product]:
        """List products filtered by category, brand, and active status."""
        stmt = select(Product)
        if is_active is not None:
            stmt = stmt.where(Product.is_active == is_active)
        if category:
            stmt = stmt.where(Product.category == category)
        if brand:
            stmt = stmt.where(Product.brand == brand)
        stmt = stmt.offset(skip).limit(limit)

        result = await self.product_repo.session.execute(stmt)
        return result.scalars().all()

    async def get_verified_price(self, product_id: UUID) -> int:
        """
        Retrieve the official database price for a product in Indian paise.
        Strictly prevents client-supplied price tampering by validating active status
        and retrieving canonical price from the authoritative database record.
        """
        product = await self.get_product_by_id(product_id, require_active=True)
        return product.price_paise
