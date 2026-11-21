import uuid
from datetime import datetime
from typing import List, Optional, TYPE_CHECKING
from sqlalchemy import Boolean, DateTime, Index, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.inventory import Inventory
    from app.models.order import Order


class Store(Base):
    __tablename__ = "stores"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    city: Mapped[str] = mapped_column(String, nullable=False)
    state: Mapped[str] = mapped_column(String, nullable=False)
    address: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.clock_timestamp(),
    )

    __table_args__ = (
        Index("stores_city_state_idx", "state", "city"),
    )

    # Relationships
    assigned_managers: Mapped[List["User"]] = relationship(
        "User",
        foreign_keys="User.assigned_store_id",
        back_populates="assigned_store",
    )
    inventory: Mapped[List["Inventory"]] = relationship(
        "Inventory",
        back_populates="store",
    )
    orders: Mapped[List["Order"]] = relationship(
        "Order",
        back_populates="store",
    )
