import enum
from sqlalchemy.dialects import postgresql


class UserRole(str, enum.Enum):
    CUSTOMER = "CUSTOMER"
    STORE_MANAGER = "STORE_MANAGER"
    ADMIN = "ADMIN"
    SUPER_ADMIN = "SUPER_ADMIN"


class OrderStatus(str, enum.Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    PACKED = "PACKED"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


class ReservationStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    CONSUMED = "CONSUMED"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"


class OutboxStatus(str, enum.Enum):
    PENDING = "PENDING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


user_role_enum = postgresql.ENUM(
    UserRole,
    name="user_role",
    create_type=False,
    values_callable=lambda enum_cls: [item.value for item in enum_cls],
)

order_status_enum = postgresql.ENUM(
    OrderStatus,
    name="order_status",
    create_type=False,
    values_callable=lambda enum_cls: [item.value for item in enum_cls],
)

reservation_status_enum = postgresql.ENUM(
    ReservationStatus,
    name="reservation_status",
    create_type=False,
    values_callable=lambda enum_cls: [item.value for item in enum_cls],
)

outbox_status_enum = postgresql.ENUM(
    OutboxStatus,
    name="outbox_status",
    create_type=False,
    values_callable=lambda enum_cls: [item.value for item in enum_cls],
)
