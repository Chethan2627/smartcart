import uuid
from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base
from app.models.enums import UserRole, user_role_enum

if TYPE_CHECKING:
    from app.models.store import Store
    from app.models.customer import Customer


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[UserRole] = mapped_column(
        user_role_enum,
        nullable=False,
        server_default=text("'CUSTOMER'"),
    )
    assigned_store_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stores.id"),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.clock_timestamp(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.clock_timestamp(),
    )

    __table_args__ = (
        CheckConstraint(
            "((role = 'STORE_MANAGER' AND assigned_store_id IS NOT NULL) OR (role <> 'STORE_MANAGER' AND assigned_store_id IS NULL))",
            name="check_store_manager_assignment",
        ),
        Index("users_role_idx", "role"),
        Index(
            "users_assigned_store_idx",
            "assigned_store_id",
            postgresql_where=text("assigned_store_id IS NOT NULL"),
        ),
    )

    # Relationships
    assigned_store: Mapped[Optional["Store"]] = relationship(
        "Store",
        foreign_keys=[assigned_store_id],
        back_populates="assigned_managers",
    )
    customer_profile: Mapped[Optional["Customer"]] = relationship(
        "Customer",
        uselist=False,
        foreign_keys="Customer.user_id",
        back_populates="user",
        passive_deletes=True,
    )
