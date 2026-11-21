"""
Kafka consumer service for SmartCart 2.0.
Subscribes to Aiven Kafka topics, validates event envelopes, deduplicates events using
PostgreSQL processed_events table, executes domain handlers, and performs manual offset commits.
"""
import asyncio
import inspect
import json
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional
from kafka import KafkaConsumer, TopicPartition, OffsetAndMetadata
from kafka.errors import KafkaError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.core.exceptions import DuplicateResourceError
from app.kafka.config import KafkaConfigBuilder
from app.kafka.dlq import DeadLetterQueueProducer, calculate_exponential_backoff, is_retryable_error
from app.kafka.schemas import SmartCartEvent
from app.repositories.outbox import OutboxEventRepository
from app.repositories.processed_event import ProcessedEventRepository
from app.services.outbox import OutboxService

logger = logging.getLogger("smartcart.kafka.consumer")

HandlerFunc = Callable[[SmartCartEvent, AsyncSession], Awaitable[None]]


async def _maybe_await(res: Any) -> Any:
    if inspect.iscoroutine(res):
        return await res
    return res


class SmartCartKafkaConsumer:
    """
    Production-ready Kafka consumer service for SmartCart 2.0.
    Enforces manual offset commits strictly after database transactions commit.
    """

    def __init__(
        self,
        topics: List[str],
        session_factory: async_sessionmaker[AsyncSession],
        consumer_group: Optional[str] = None,
        consumer: Optional[Any] = None,
        dlq_producer: Optional[DeadLetterQueueProducer] = None,
        max_retries: int = 3,
    ) -> None:
        self.topics = topics
        self.session_factory = session_factory
        self.consumer_group = consumer_group or settings.KAFKA_CONSUMER_GROUP_ID
        self._consumer = consumer
        self.dlq_producer = dlq_producer
        self.max_retries = max_retries
        self._handlers: Dict[str, HandlerFunc] = {}
        self._is_started = consumer is not None

    def register_handler(self, event_type: str, handler: HandlerFunc) -> None:
        """Register an async handler function for a specific event type."""
        self._handlers[event_type.strip().lower()] = handler
        logger.debug("Registered consumer handler for event type: %s", event_type)

    def _create_consumer(self) -> KafkaConsumer:
        """Instantiate KafkaConsumer using KafkaConfigBuilder."""
        config = KafkaConfigBuilder.get_consumer_config(group_id=self.consumer_group)
        sanitized = KafkaConfigBuilder.get_sanitized_config(config)
        logger.info(
            "Initializing Aiven KafkaConsumer for topics %s, group_id=%s, bootstrap_servers=%s",
            self.topics,
            self.consumer_group,
            sanitized.get("bootstrap_servers"),
        )

        return KafkaConsumer(
            *self.topics,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            key_deserializer=lambda k: k.decode("utf-8") if k is not None else None,
            **config,
        )

    def start(self) -> None:
        """Start the consumer client synchronously."""
        if not self._is_started:
            if self._consumer is None:
                self._consumer = self._create_consumer()
            self._is_started = True
            logger.info("Aiven KafkaConsumer started successfully.")

    async def astart(self) -> None:
        """Start the consumer asynchronously."""
        if not self._is_started:
            await asyncio.to_thread(self.start)

    def _sync_poll(self, timeout_ms: int = 1000, max_records: int = 50) -> Dict[Any, List[Any]]:
        """Synchronously poll messages from Kafka broker."""
        if self._consumer is None:
            self.start()
        return self._consumer.poll(timeout_ms=timeout_ms, max_records=max_records)

    def _sync_commit_offset(self, topic: str, partition: int, offset: int) -> None:
        """Commit specific offset for partition manually."""
        if self._consumer is not None:
            tp = TopicPartition(topic, partition)
            # Offset committed should be next offset to read (offset + 1)
            self._consumer.commit({tp: OffsetAndMetadata(offset + 1, None)})

    async def process_message(self, record: Any) -> bool:
        """
        Process a single Kafka record:
        1. Validate JSON and deserialize event envelope into SmartCartEvent.
        2. Verify event deduplication using ProcessedEventService.
        3. If already processed: commit offset immediately and skip.
        4. Execute registered domain handler.
        5. In same DB transaction: record event_id in processed_events.
        6. Commit DB transaction.
        7. Commit Kafka offset manually ONLY after DB commit.
        8. On failure: retry or route to DLQ without halting partition processing.
        """
        raw_val = getattr(record, "value", None)
        topic = getattr(record, "topic", "unknown")
        partition = getattr(record, "partition", 0)
        offset = getattr(record, "offset", 0)

        # 1. Parse and validate event envelope
        try:
            if isinstance(raw_val, dict):
                event = SmartCartEvent.model_validate(raw_val)
            else:
                event = SmartCartEvent.model_validate_json(raw_val)
        except Exception as parse_exc:
            logger.error(
                "Malformed message on [topic=%s partition=%s offset=%s]: %s",
                topic,
                partition,
                offset,
                parse_exc,
            )
            if self.dlq_producer:
                await self.dlq_producer.send_to_dlq(
                    event={"raw_value": str(raw_val)},
                    error=parse_exc,
                    original_topic=topic,
                    partition=partition,
                    offset=offset,
                )
            # Commit offset to avoid poison pill blocking consumer queue
            await asyncio.to_thread(self._sync_commit_offset, topic, partition, offset)
            return False

        # 2. Filter synthetic test events from production consumer processing
        event_type = event.event_type.strip().lower()
        event_id = event.event_id

        is_synthetic = (
            event_type.startswith("test.")
            or event.aggregate_type in ("test", "synthetic_test", "test_probe", "system")
            or (isinstance(event.payload, dict) and event.payload.get("is_synthetic_test") is True)
        )
        is_production_group = (
            not self.consumer_group
            or self.consumer_group == settings.KAFKA_CONSUMER_GROUP_ID
            or not self.consumer_group.startswith("smartcart-test-")
        )

        if is_synthetic and is_production_group:
            logger.info(
                "Filtered synthetic test event %s [%s] from production consumer group '%s'. Committing offset.",
                event_id,
                event_type,
                self.consumer_group,
            )
            await asyncio.to_thread(self._sync_commit_offset, topic, partition, offset)
            return True

        # 3. Process with deduplication
        for attempt in range(1, self.max_retries + 1):
            async with self.session_factory() as session:
                outbox_repo = OutboxEventRepository(session)
                processed_repo = ProcessedEventRepository(session)
                outbox_service = OutboxService(outbox_repo, processed_repo, session)

                try:
                    # Check deduplication
                    if await _maybe_await(outbox_service.is_event_processed(event_id, self.consumer_group)):
                        logger.info(
                            "Event '%s' already processed by group '%s'. Skipping handler.",
                            event_id,
                            self.consumer_group,
                        )
                        await asyncio.to_thread(self._sync_commit_offset, topic, partition, offset)
                        return True

                    # Execute handler if registered
                    handler = self._handlers.get(event_type)
                    if handler is not None:
                        logger.debug("Executing handler for event %s [%s]", event_id, event_type)
                        await handler(event, session)
                    else:
                        logger.debug("No handler registered for event type '%s'", event_type)

                    # Atomically mark event as processed in database
                    try:
                        await _maybe_await(outbox_service.record_event_processed(event_id, self.consumer_group))
                    except DuplicateResourceError:
                        logger.info("Concurrent deduplication caught for event '%s'.", event_id)

                    # Commit DB transaction
                    await session.commit()

                    # Commit Kafka offset ONLY after DB commit succeeds
                    await asyncio.to_thread(self._sync_commit_offset, topic, partition, offset)
                    logger.debug(
                        "Processed & committed event %s [topic=%s partition=%s offset=%s]",
                        event_id,
                        topic,
                        partition,
                        offset,
                    )
                    return True

                except Exception as exc:
                    await session.rollback()
                    logger.error(
                        "Error processing event %s (attempt %d/%d): %s",
                        event_id,
                        attempt,
                        self.max_retries,
                        exc,
                    )

                    if not is_retryable_error(exc) or attempt >= self.max_retries:
                        # Non-retryable error or retries exhausted -> Route to DLQ
                        if self.dlq_producer:
                            await self.dlq_producer.send_to_dlq(
                                event=event,
                                error=exc,
                                original_topic=topic,
                                partition=partition,
                                offset=offset,
                                attempt_count=attempt,
                            )
                        # Commit offset so poison message doesn't permanently stall partition
                        await asyncio.to_thread(self._sync_commit_offset, topic, partition, offset)
                        return False

                    # Backoff before retrying
                    backoff = calculate_exponential_backoff(attempt)
                    await asyncio.sleep(backoff)

        return False

    async def poll_and_process(self, timeout_ms: int = 1000) -> int:
        """Poll a batch of messages from subscribed topics and process them."""
        records_dict = await asyncio.to_thread(self._sync_poll, timeout_ms=timeout_ms)
        processed_count = 0

        for tp, records in records_dict.items():
            for record in records:
                success = await self.process_message(record)
                if success:
                    processed_count += 1

        return processed_count

    async def run_loop(
        self,
        poll_interval_seconds: float = 0.5,
        stop_event: Optional[asyncio.Event] = None,
    ) -> None:
        """
        Continuously poll and process events until stop_event is set or cancelled.
        """
        logger.info(
            "Starting consumer worker loop for topics %s (group: %s)...",
            self.topics,
            self.consumer_group,
        )

        while stop_event is None or not stop_event.is_set():
            try:
                count = await self.poll_and_process(timeout_ms=int(poll_interval_seconds * 1000))
                if count == 0:
                    await asyncio.sleep(poll_interval_seconds)
            except asyncio.CancelledError:
                logger.info("Kafka consumer worker loop received cancellation request.")
                break
            except Exception as exc:
                logger.error("Consumer worker loop error: %s. Continuing...", exc)
                await asyncio.sleep(poll_interval_seconds * 2)

        logger.info("Kafka consumer worker loop stopped.")

    def close(self) -> None:
        """Close KafkaConsumer cleanly."""
        if self._consumer is not None:
            try:
                self._consumer.close()
                logger.info("Aiven KafkaConsumer closed cleanly.")
            except Exception as exc:
                logger.warning("Error during KafkaConsumer close: %s", exc)
            finally:
                self._consumer = None
                self._is_started = False

    async def aclose(self) -> None:
        """Asynchronously close consumer cleanly."""
        await asyncio.to_thread(self.close)
