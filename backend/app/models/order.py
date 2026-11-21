import uuid
from datetime import datetime
from typing import List, Optional, TYPE_CHECKING
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base
from app.models.enums import OrderStatus, order_status_enum

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.store import Store
    from app.models.product import Product
    from app.models.inventory import Reservation
    from app.models.outbox import IdempotencyKey



class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    order_number: Mapped[str] = mapped_column(
        String,
        unique=True,
        nullable=False,
        server_default=text(
            "('SC-' || to_char(clock_timestamp(), 'YYYY') || '-' || "
            "lpad(nextval('order_number_seq'::regclass)::text, 6, '0'))"
        ),
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id"),
        nullable=False,
    )
    store_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stores.id"),
        nullable=False,
    )
    status: Mapped[OrderStatus] = mapped_column(
        order_status_enum,
        nullable=False,
        server_default=text("'PENDING'"),
    )
    total_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
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
        CheckConstraint("total_paise >= 0", name="orders_total_paise_check"),
        Index("orders_customer_idx", "customer_id", text("created_at DESC")),
        Index("orders_store_status_idx", "store_id", "status"),
    )

    # Relationships
    customer: Mapped["Customer"] = relationship("Customer", back_populates="orders")
    store: Mapped["Store"] = relationship("Store", back_populates="orders")
    items: Mapped[List["OrderItem"]] = relationship(
        "OrderItem",
        back_populates="order",
        passive_deletes=True,
    )
    status_history: Mapped[List["OrderStatusHistory"]] = relationship(
        "OrderStatusHistory",
        back_populates="order",
        passive_deletes=True,
    )
    reservations: Mapped[List["Reservation"]] = relationship(
        "Reservation",
        back_populates="order",
    )
    idempotency_keys: Mapped[List["IdempotencyKey"]] = relationship(
        "IdempotencyKey",
        back_populates="order",
    )



class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id"),
        nullable=False,
    )
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)

    __table_args__ = (
        UniqueConstraint("order_id", "product_id", name="order_items_order_product_uniq"),
        CheckConstraint("qty > 0", name="order_items_qty_check"),
        CheckConstraint("unit_price_paise >= 0", name="order_items_unit_price_paise_check"),
        Index("order_items_order_idx", "order_id"),
    )

    # Relationships
    order: Mapped["Order"] = relationship("Order", back_populates="items")
    product: Mapped["Product"] = relationship("Product", back_populates="order_items")


class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    from_status: Mapped[Optional[OrderStatus]] = mapped_column(
        order_status_enum,
        nullable=True,
    )
    to_status: Mapped[OrderStatus] = mapped_column(
        order_status_enum,
        nullable=False,
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.clock_timestamp(),
    )

    __table_args__ = (
        Index("order_status_history_order_idx", "order_id", "changed_at"),
    )

    # Relationships
    order: Mapped["Order"] = relationship("Order", back_populates="status_history")
