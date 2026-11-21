from typing import Any, Generic, Optional, Sequence, Type, TypeVar
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """
    Generic asynchronous SQLAlchemy 2.x repository.
    Provides safe, transaction-neutral read operations.
    Transaction commits/rollbacks are explicitly controlled by route or service layers.
    """

    def __init__(self, model: Type[ModelType], session: AsyncSession) -> None:
        self.model = model
        self.session = session

    async def get_by_id(self, id: Any) -> Optional[ModelType]:
        """
        Fetch a single record by its single-column primary key.
        Uses session.get().
        """
        return await self.session.get(self.model, id)

    async def get_by_pk(self, *pk_values: Any) -> Optional[ModelType]:
        """
        Fetch a single record by primary key (supports both single and composite primary keys).
        For single PK: await repo.get_by_pk(id)
        For composite PK: await repo.get_by_pk(store_id, product_id)
        Uses session.get() with the appropriate scalar or tuple identity.
        """
        if not pk_values:
            raise ValueError("At least one primary key value must be provided to get_by_pk")

        ident: Any = pk_values[0] if len(pk_values) == 1 else pk_values
        return await self.session.get(self.model, ident)

    async def get_all(self, skip: int = 0, limit: int = 100) -> Sequence[ModelType]:
        """
        Retrieve records with pagination offset and limit.
        """
        stmt = select(self.model).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def exists(self, *pk_values: Any) -> bool:
        """
        Check if a record exists by primary key.
        """
        record = await self.get_by_pk(*pk_values)
        return record is not None

    async def count(self) -> int:
        """
        Count total records for the model.
        """
        stmt = select(func.count()).select_from(self.model)
        result = await self.session.execute(stmt)
        return result.scalar_one()
