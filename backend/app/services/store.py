"""
Store domain service for SmartCart 2.0.
Handles store querying, location filtering, manager assignment lookups,
and active status validation.
"""
from typing import Optional, Sequence
from uuid import UUID

from app.core.exceptions import BadRequestError, NotFoundError
from app.models.store import Store
from app.models.user import User
from app.repositories.store import StoreRepository
from app.repositories.user import UserRepository


class StoreService:
    """Service handling store operations and status validation."""

    def __init__(
        self,
        store_repo: StoreRepository,
        user_repo: Optional[UserRepository] = None,
    ) -> None:
        self.store_repo = store_repo
        self.user_repo = user_repo

    async def get_store_by_id(self, store_id: UUID, require_active: bool = False) -> Store:
        """
        Retrieve store by primary key UUID.
        Raises NotFoundError if store does not exist.
        Raises BadRequestError if require_active is True and store is inactive.
        """
        store = await self.store_repo.get_by_id(store_id)
        if store is None:
            raise NotFoundError(f"Store with id '{store_id}' not found")

        if require_active and not store.is_active:
            raise BadRequestError(f"Store '{store.name}' ({store.code}) is inactive")

        return store

    async def get_store_by_code(self, code: str, require_active: bool = False) -> Store:
        """
        Retrieve store by unique store code.
        Raises NotFoundError if store does not exist.
        Raises BadRequestError if require_active is True and store is inactive.
        """
        store = await self.store_repo.get_by_code(code)
        if store is None:
            raise NotFoundError(f"Store with code '{code}' not found")

        if require_active and not store.is_active:
            raise BadRequestError(f"Store '{store.name}' ({code}) is inactive")

        return store

    async def list_active_stores(self, skip: int = 0, limit: int = 100) -> Sequence[Store]:
        """List active stores with pagination."""
        return await self.store_repo.list_active(skip=skip, limit=limit)

    async def list_stores_by_location(
        self, state: str, city: Optional[str] = None, require_active: bool = True
    ) -> Sequence[Store]:
        """Retrieve stores by state and optional city, filtering active if required."""
        stores = await self.store_repo.list_by_state_and_city(state=state, city=city)
        if require_active:
            return [s for s in stores if s.is_active]
        return stores

    async def get_store_managers(self, store_id: UUID) -> Sequence[User]:
        """Retrieve all assigned managers for a given store."""
        # Ensure store exists first
        await self.get_store_by_id(store_id)

        if self.user_repo is not None:
            manager = await self.user_repo.get_manager_for_store(store_id)
            return [manager] if manager is not None else []
        return []
