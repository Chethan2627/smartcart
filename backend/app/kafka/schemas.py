"""
Event contracts and schemas for SmartCart 2.0 Apache Kafka integration.
Defines canonical event envelope (SmartCartEvent) and strongly-typed payload contracts.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, ConfigDict, Field

from app.config import settings


# ---------------- Canonical Event Envelope ----------------

class SmartCartEvent(BaseModel):
    """
    Standard event envelope for all messages published to Aiven Kafka.
    Enforces uniform metadata across all domain aggregates.
    """

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str = Field(..., description="e.g. order.created, order.cancelled, inventory.reservation.created")
    aggregate_type: str = Field(..., description="e.g. order, inventory, product")
    aggregate_id: str = Field(..., description="Identifier of the aggregate root, e.g. order_id, product_id")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: str = Field(default="1.0", description="Contract version")
    payload: Dict[str, Any] = Field(..., description="Domain payload data")

    model_config = ConfigDict(from_attributes=True)

    def to_json_dict(self) -> Dict[str, Any]:
        """Serialize event to a JSON-compatible dictionary with ISO formatted timestamps."""
        data = self.model_dump()
        if isinstance(data.get("timestamp"), datetime):
            data["timestamp"] = data["timestamp"].isoformat()
        return data


# ---------------- Domain Event Payload Contracts ----------------

class OrderItemPayload(BaseModel):
    product_id: UUID
    qty: int = Field(gt=0)
    unit_price_paise: int = Field(ge=0)


class OrderCreatedPayload(BaseModel):
    """Payload contract for order.created / order.placed event."""
    order_id: UUID
    order_number: str
    customer_id: UUID
    store_id: UUID
    total_paise: int = Field(ge=0)
    confirmed_at: datetime
    items: List[OrderItemPayload]


class OrderCancelledPayload(BaseModel):
    """Payload contract for order.cancelled event."""
    order_id: UUID
    customer_id: UUID
    store_id: UUID
    reason: Optional[str] = None
    cancelled_at: datetime


class ReservationCreatedPayload(BaseModel):
    """Payload contract for inventory.reservation.created event."""
    reservation_id: UUID
    customer_id: UUID
    store_id: UUID
    product_id: UUID
    qty: int = Field(gt=0)
    expires_at: datetime
    created_at: datetime


class ReservationExpiredPayload(BaseModel):
    """Payload contract for inventory.reservation.expired event."""
    reservation_id: UUID
    store_id: UUID
    product_id: UUID
    qty: int = Field(gt=0)
    expired_at: datetime


class StockUpdatedPayload(BaseModel):
    """Payload contract for inventory.stock.updated / inventory.changed event."""
    store_id: UUID
    product_id: UUID
    qty_on_hand: int = Field(ge=0)
    qty_reserved: int = Field(ge=0)
    qty_available: int = Field(ge=0)
    updated_at: datetime


# ---------------- Topic Routing Resolution ----------------

def get_topic_for_event(event_type: str) -> str:
    """
    Resolve the canonical Aiven Kafka topic name for a given event_type.
    Maps order events to smartcart.orders, inventory events to smartcart.inventory.
    """
    normalized = (event_type or "").lower().strip()

    if normalized.startswith("order."):
        return settings.KAFKA_TOPIC_ORDERS
    elif normalized.startswith("inventory."):
        return settings.KAFKA_TOPIC_INVENTORY
    elif normalized.startswith("product."):
        return getattr(settings, "KAFKA_TOPIC_PRODUCT_CHANGED", "smartcart.products")
    elif normalized.startswith("search."):
        return getattr(settings, "KAFKA_TOPIC_SEARCH_EVENTS", "smartcart.search")
    elif normalized == "event.dlq" or normalized.startswith("dlq."):
        return getattr(settings, "KAFKA_TOPIC_DLQ", "smartcart.dlq")
    else:
        # Default fallback to orders topic
        return settings.KAFKA_TOPIC_ORDERS
