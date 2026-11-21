import uuid
from datetime import datetime
from typing import Optional, Sequence
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.enums import ReservationStatus
from app.models.inventory import Reservation
from app.repositories.base import BaseRepository


class ReservationRepository(BaseRepository[Reservation]):
    """
    Repository for Reservation entity.
    Reservation state transitions and expiry logic are executed via PostgreSQL functions.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Reservation, session)

    async def list_active_by_customer(
        self, customer_id: uuid.UUID
    ) -> Sequence[Reservation]:
        """Retrieve all currently ACTIVE reservations for a customer."""
        stmt = select(Reservation).where(
            Reservation.customer_id == customer_id,
            Reservation.status == ReservationStatus.ACTIVE,
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_active_by_order(
        self, order_id: uuid.UUID
    ) -> Sequence[Reservation]:
        """Retrieve reservations associated with a specific order."""
        stmt = select(Reservation).where(Reservation.order_id == order_id)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_expired(
        self, reference_time: Optional[datetime] = None
    ) -> Sequence[Reservation]:
        """
        Retrieve ACTIVE reservations whose expires_at timestamp has passed.
        Used by background expiration cleanup workers.
        """
        cutoff = reference_time if reference_time is not None else func.clock_timestamp()
        stmt = select(Reservation).where(
            Reservation.status == ReservationStatus.ACTIVE,
            Reservation.expires_at < cutoff,
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
