import uuid
from datetime import datetime
from typing import List, Optional, TYPE_CHECKING
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base
from app.models.enums import ReservationStatus, reservation_status_enum

if TYPE_CHECKING:
    from app.models.store import Store
    from app.models.product import Product
    from app.models.customer import Customer
    from app.models.order import Order


class Inventory(Base):
    __tablename__ = "inventory"

    store_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stores.id"),
        primary_key=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id"),
        primary_key=True,
    )
    qty_on_hand: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    qty_reserved: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    low_stock_threshold: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("5"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.clock_timestamp(),
    )

    __table_args__ = (
        CheckConstraint("qty_on_hand >= 0", name="inventory_qty_on_hand_check"),
        CheckConstraint("qty_reserved >= 0", name="inventory_qty_reserved_check"),
        CheckConstraint("low_stock_threshold >= 0", name="inventory_low_stock_threshold_check"),
        CheckConstraint("qty_reserved <= qty_on_hand", name="inventory_check"),
        Index("inventory_product_idx", "product_id"),
    )

    # Relationships
    store: Mapped["Store"] = relationship("Store", back_populates="inventory")
    product: Mapped["Product"] = relationship("Product", back_populates="inventory_items")
    reservations: Mapped[List["Reservation"]] = relationship(
        "Reservation",
        primaryjoin="and_(Reservation.store_id == Inventory.store_id, Reservation.product_id == Inventory.product_id)",
        foreign_keys="[Reservation.store_id, Reservation.product_id]",
        back_populates="inventory",
    )


class Reservation(Base):
    __tablename__ = "reservations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id"),
        nullable=False,
    )
    store_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ReservationStatus] = mapped_column(
        reservation_status_enum,
        nullable=False,
        server_default=text("'ACTIVE'"),
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    order_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id"),
        nullable=True,
    )
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
        ForeignKeyConstraint(
            ["store_id", "product_id"],
            ["inventory.store_id", "inventory.product_id"],
            name="reservations_store_id_product_id_fkey",
        ),
        CheckConstraint("qty > 0", name="reservations_qty_check"),
        Index(
            "reservations_active_expiry_idx",
            "expires_at",
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        Index("reservations_customer_idx", "customer_id"),
        Index(
            "reservations_order_idx",
            "order_id",
            postgresql_where=text("order_id IS NOT NULL"),
        ),
    )

    # Relationships
    customer: Mapped["Customer"] = relationship("Customer", back_populates="reservations")
    order: Mapped[Optional["Order"]] = relationship("Order", back_populates="reservations")
    inventory: Mapped["Inventory"] = relationship(
        "Inventory",
        primaryjoin="and_(Reservation.store_id == Inventory.store_id, Reservation.product_id == Inventory.product_id)",
        foreign_keys="[Reservation.store_id, Reservation.product_id]",
        back_populates="reservations",
    )


class InventoryAuditLog(Base):
    __tablename__ = "inventory_audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    store_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    old_on_hand: Mapped[int] = mapped_column(Integer, nullable=False)
    new_on_hand: Mapped[int] = mapped_column(Integer, nullable=False)
    old_reserved: Mapped[int] = mapped_column(Integer, nullable=False)
    new_reserved: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.clock_timestamp(),
    )

    __table_args__ = (
        Index("inventory_audit_item_idx", "store_id", "product_id", text("changed_at DESC")),
    )
