"""
Transactional Outbox Publisher for SmartCart 2.0.
Polls and claims pending outbox events from PostgreSQL using FOR UPDATE SKIP LOCKED,
dispatches them to Aiven Kafka topics, and transitions status to PUBLISHED upon broker ACK.
"""
import asyncio
import inspect
import logging
from typing import Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.kafka.dlq import DeadLetterQueueProducer
from app.kafka.producer import SmartCartKafkaProducer
from app.kafka.schemas import SmartCartEvent, get_topic_for_event
from app.repositories.outbox import OutboxEventRepository
from app.repositories.processed_event import ProcessedEventRepository
from app.services.outbox import OutboxService

logger = logging.getLogger("smartcart.kafka.publisher")


async def _maybe_await(res: Any) -> Any:
    if inspect.iscoroutine(res):
        return await res
    return res


class OutboxPublisher:
    """
    Coordinates claiming pending outbox events from PostgreSQL and dispatching to Aiven Kafka.
    Guarantees at-least-once message delivery.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        producer: SmartCartKafkaProducer,
        dlq_producer: Optional[DeadLetterQueueProducer] = None,
        batch_size: int = 50,
        max_retries: int = 5,
    ) -> None:
        self.session_factory = session_factory
        self.producer = producer
        self.dlq_producer = dlq_producer
        self.batch_size = batch_size
        self.max_retries = max_retries

    async def publish_batch(self) -> int:
        """
        Execute a single polling and dispatch batch:
        1. Open PostgreSQL transaction.
        2. Claim pending outbox records using SELECT ... FOR UPDATE SKIP LOCKED.
        3. Dispatch each record to its canonical Kafka topic and await broker ACK.
        4. On ACK: Mark event status = 'PUBLISHED'.
        5. On Failure: Increment retry count, sanitize error; if retries exhausted, route to DLQ.
        6. Commit database transaction.
        """
        published_count = 0

        async with self.session_factory() as session:
            outbox_repo = OutboxEventRepository(session)
            processed_repo = ProcessedEventRepository(session)
            outbox_service = OutboxService(outbox_repo, processed_repo, session)

            try:
                # 1. Claim batch with row locks skipping locked rows
                claimed_events = await _maybe_await(outbox_service.claim_pending_events(limit=self.batch_size))
                if not claimed_events:
                    return 0

                logger.debug("Claimed %d pending outbox events for Kafka dispatch", len(claimed_events))

                for event in claimed_events:
                    topic = get_topic_for_event(event.event_type)
                    smartcart_event = SmartCartEvent(
                        event_id=str(event.id),
                        event_type=event.event_type,
                        aggregate_type=event.aggregate_type,
                        aggregate_id=event.aggregate_id,
                        timestamp=event.created_at,
                        payload=event.payload,
                    )

                    try:
                        # 2. Publish to Kafka and wait for broker acknowledgement
                        await self.producer.publish(
                            topic=topic,
                            event=smartcart_event,
                            key=event.aggregate_id,
                        )

                        # 3. Mark as PUBLISHED only after broker ACK
                        await _maybe_await(outbox_service.acknowledge_published(event.id))
                        published_count += 1
                        logger.info(
                            "Outbox event published [id=%s type=%s topic=%s]",
                            event.id,
                            event.event_type,
                            topic,
                        )

                    except Exception as exc:
                        # 4. Handle publish failure
                        logger.error(
                            "Failed to publish outbox event [id=%s type=%s topic=%s]: %s",
                            event.id,
                            event.event_type,
                            topic,
                            exc,
                        )
                        updated_event = await _maybe_await(
                            outbox_service.record_publish_failure(
                                event_id=event.id,
                                error_message=str(exc),
                                max_retries=self.max_retries,
                            )
                        )

                        # 5. Route to DLQ if max retries exhausted
                        if updated_event.status.value == "FAILED" and self.dlq_producer:
                            logger.warning(
                                "Outbox event %s exhausted %d retries. Routing to DLQ.",
                                event.id,
                                self.max_retries,
                            )
                            await self.dlq_producer.send_to_dlq(
                                event=smartcart_event,
                                error=exc,
                                original_topic=topic,
                                attempt_count=updated_event.retry_count,
                            )

                # Commit all status updates in PostgreSQL
                await session.commit()

            except Exception as batch_exc:
                await session.rollback()
                logger.error("Error processing outbox publisher batch: %s", batch_exc)
                raise batch_exc

        return published_count

    async def run_loop(
        self,
        poll_interval_seconds: float = 1.0,
        stop_event: Optional[asyncio.Event] = None,
    ) -> None:
        """
        Continuously run the outbox polling loop until stop_event is set or cancelled.
        """
        logger.info("Starting outbox publisher polling loop (interval=%.2fs)...", poll_interval_seconds)

        while stop_event is None or not stop_event.is_set():
            try:
                published = await self.publish_batch()
                if published == 0:
                    await asyncio.sleep(poll_interval_seconds)
            except asyncio.CancelledError:
                logger.info("Outbox publisher loop received cancellation request.")
                break
            except Exception as exc:
                logger.error("Outbox publisher loop encountered error: %s. Backing off...", exc)
                await asyncio.sleep(poll_interval_seconds * 2)

        logger.info("Outbox publisher loop stopped.")
