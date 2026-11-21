"""
Transactional Outbox Publisher Worker for SmartCart 2.0.
Standalone background worker process that claims PENDING outbox events using
FOR UPDATE SKIP LOCKED and publishes them to Aiven Kafka.

Usage:
    python -m app.workers.outbox_publisher
"""
import asyncio
import logging
import signal
import sys

from app.db.session import async_session_maker
from app.kafka.dlq import DeadLetterQueueProducer
from app.kafka.producer import SmartCartKafkaProducer
from app.kafka.publisher import OutboxPublisher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("smartcart.workers.outbox_publisher")


async def main() -> None:
    logger.info("Initializing SmartCart 2.0 Outbox Publisher Worker...")

    producer = SmartCartKafkaProducer()
    dlq_producer = DeadLetterQueueProducer(producer=producer)
    publisher = OutboxPublisher(
        session_factory=async_session_maker,
        producer=producer,
        dlq_producer=dlq_producer,
    )

    stop_event = asyncio.Event()

    def _handle_signal(*_args: object) -> None:
        logger.info("Shutdown signal received. Stopping outbox publisher gracefully...")
        stop_event.set()

    # Register cross-platform signal handlers
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handle_signal)
        except (ValueError, AttributeError):
            pass

    try:
        await producer.astart()
        logger.info("Outbox publisher connected to Aiven Kafka. Beginning dispatch loop...")
        await publisher.run_loop(poll_interval_seconds=1.0, stop_event=stop_event)
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt detected. Shutting down...")
    finally:
        logger.info("Flushing and closing Kafka producer connections...")
        await producer.aclose()
        logger.info("Outbox publisher shutdown complete.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)
