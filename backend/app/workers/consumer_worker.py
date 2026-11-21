"""
Kafka Consumer Worker for SmartCart 2.0.
Standalone background worker process that subscribes to Aiven Kafka topics,
validates events, deduplicates against PostgreSQL processed_events, and dispatches to handlers.

Usage:
    python -m app.workers.consumer_worker
"""
import asyncio
import logging
import signal
import sys
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import async_session_maker
from app.kafka.consumer import SmartCartKafkaConsumer
from app.kafka.dlq import DeadLetterQueueProducer
from app.kafka.producer import SmartCartKafkaProducer
from app.kafka.schemas import SmartCartEvent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("smartcart.workers.consumer_worker")


# ---------------- Sample Domain Event Handlers ----------------

async def handle_order_placed(event: SmartCartEvent, session: AsyncSession) -> None:
    """Handle order.placed / order.created event."""
    order_id = event.payload.get("order_id")
    customer_id = event.payload.get("customer_id")
    total_paise = event.payload.get("total_paise")
    logger.info(
        "[HANDLER] Processed order confirmation event [order_id=%s, customer_id=%s, total_paise=%s]",
        order_id,
        customer_id,
        total_paise,
    )


async def handle_order_cancelled(event: SmartCartEvent, session: AsyncSession) -> None:
    """Handle order.cancelled event."""
    order_id = event.payload.get("order_id")
    reason = event.payload.get("reason")
    logger.info(
        "[HANDLER] Processed order cancellation event [order_id=%s, reason=%s]",
        order_id,
        reason,
    )


async def handle_reservation_created(event: SmartCartEvent, session: AsyncSession) -> None:
    """Handle inventory.reservation.created event."""
    res_id = event.payload.get("reservation_id")
    product_id = event.payload.get("product_id")
    qty = event.payload.get("qty")
    logger.info(
        "[HANDLER] Processed reservation created event [reservation_id=%s, product_id=%s, qty=%s]",
        res_id,
        product_id,
        qty,
    )


async def handle_reservation_expired(event: SmartCartEvent, session: AsyncSession) -> None:
    """Handle inventory.reservation.expired event."""
    res_id = event.payload.get("reservation_id")
    logger.info(
        "[HANDLER] Processed reservation expired event [reservation_id=%s]",
        res_id,
    )


async def handle_stock_updated(event: SmartCartEvent, session: AsyncSession) -> None:
    """Handle inventory.stock.updated / inventory.changed event."""
    product_id = event.payload.get("product_id")
    qty_available = event.payload.get("qty_available")
    logger.info(
        "[HANDLER] Processed stock update event [product_id=%s, qty_available=%s]",
        product_id,
        qty_available,
    )


# ---------------- Main Worker Execution ----------------

async def main() -> None:
    logger.info("Initializing SmartCart 2.0 Kafka Consumer Worker...")

    producer = SmartCartKafkaProducer()
    dlq_producer = DeadLetterQueueProducer(producer=producer)

    product_topic = getattr(settings, "KAFKA_TOPIC_PRODUCT_CHANGED", "smartcart.products")
    topics = [
        settings.KAFKA_TOPIC_ORDERS,
        settings.KAFKA_TOPIC_INVENTORY,
        product_topic,
    ]

    consumer = SmartCartKafkaConsumer(
        topics=topics,
        session_factory=async_session_maker,
        consumer_group=settings.KAFKA_CONSUMER_GROUP_ID,
        dlq_producer=dlq_producer,
    )

    # Register event handlers
    consumer.register_handler("order.placed", handle_order_placed)
    consumer.register_handler("order.created", handle_order_placed)
    consumer.register_handler("order.cancelled", handle_order_cancelled)
    consumer.register_handler("inventory.reservation.created", handle_reservation_created)
    consumer.register_handler("inventory.reservation.expired", handle_reservation_expired)
    consumer.register_handler("inventory.stock.updated", handle_stock_updated)
    consumer.register_handler("inventory.changed", handle_stock_updated)

    # Register OpenSearch synchronization handlers
    try:
        from app.opensearch.sync import register_opensearch_handlers
        register_opensearch_handlers(consumer)
    except Exception as os_init_err:
        logger.warning("Could not register OpenSearch sync handlers: %s", os_init_err)

    stop_event = asyncio.Event()

    def _handle_signal(*_args: object) -> None:
        logger.info("Shutdown signal received. Stopping consumer worker gracefully...")
        stop_event.set()

    # Register cross-platform signal handlers
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handle_signal)
        except (ValueError, AttributeError):
            pass

    try:
        await producer.astart()
        await consumer.astart()
        logger.info("Consumer worker listening on topics %s (group: %s)...", topics, consumer.consumer_group)
        await consumer.run_loop(poll_interval_seconds=0.5, stop_event=stop_event)
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt detected. Shutting down...")
    finally:
        logger.info("Closing Kafka consumer and producer connections...")
        await consumer.aclose()
        await producer.aclose()
        logger.info("Consumer worker shutdown complete.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)
