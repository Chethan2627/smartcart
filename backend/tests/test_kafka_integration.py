"""
Comprehensive tests for SmartCart 2.0 Apache Kafka integration (Phase 6).
Covers all 12 testing requirements using mocked Kafka clients for 100% offline verification,
with an optional live Aiven integration test when credentials are configured.
"""
import asyncio
from datetime import datetime, timezone
import json
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
import pytest
from pydantic import ValidationError

from app.config import settings
from app.core.exceptions import DuplicateResourceError
from app.kafka.config import KafkaConfigBuilder
from app.kafka.consumer import SmartCartKafkaConsumer
from app.kafka.dlq import (
    DeadLetterQueueProducer,
    NonRetryableError,
    calculate_exponential_backoff,
    is_retryable_error,
)
from app.kafka.producer import (
    KafkaPublishError,
    RecordMetadata,
    SmartCartKafkaProducer,
)
from app.kafka.publisher import OutboxPublisher
from app.kafka.schemas import (
    OrderCancelledPayload,
    OrderCreatedPayload,
    OrderItemPayload,
    ReservationCreatedPayload,
    ReservationExpiredPayload,
    SmartCartEvent,
    StockUpdatedPayload,
    get_topic_for_event,
)
from app.models.enums import OutboxStatus
from app.models.outbox import OutboxEvent


# ============================================================================
# 1. Kafka Configuration Validation
# ============================================================================

def test_kafka_config_builder_ssl_and_sasl():
    """Verify KafkaConfigBuilder correctly handles security protocols, SASL and SSL config."""
    with patch.object(settings, "KAFKA_BOOTSTRAP_SERVERS", "test-broker.aivencloud.com:12345"), \
         patch.object(settings, "KAFKA_SECURITY_PROTOCOL", "SASL_SSL"), \
         patch.object(settings, "KAFKA_SASL_MECHANISM", "SCRAM-SHA-256"), \
         patch.object(settings, "KAFKA_SASL_USERNAME", "test-user"), \
         patch.object(settings, "KAFKA_SASL_PASSWORD", "super-secret-password"):

        producer_config = KafkaConfigBuilder.get_producer_config()

        assert producer_config["bootstrap_servers"] == "test-broker.aivencloud.com:12345"
        assert producer_config["security_protocol"] == "SASL_SSL"
        assert producer_config["sasl_mechanism"] == "SCRAM-SHA-256"
        assert producer_config["sasl_plain_username"] == "test-user"
        assert producer_config["sasl_plain_password"] == "super-secret-password"
        assert producer_config["acks"] == "all"

        # Verify sensitive password is masked in sanitized output
        sanitized = KafkaConfigBuilder.get_sanitized_config(producer_config)
        assert sanitized["sasl_plain_password"] == "********"
        assert sanitized["sasl_plain_username"] == "test-user"


def test_kafka_config_consumer_defaults():
    """Verify KafkaConsumer config disables auto-commit for explicit DB-first offset commits."""
    with patch.object(settings, "KAFKA_CONSUMER_GROUP_ID", "test-group-01"):
        consumer_config = KafkaConfigBuilder.get_consumer_config()
        assert consumer_config["group_id"] == "test-group-01"
        assert consumer_config["enable_auto_commit"] is False
        assert consumer_config["auto_offset_reset"] == "earliest"


# ============================================================================
# 2. Producer Event Serialization & Schemas
# ============================================================================

def test_producer_event_serialization_and_contracts():
    """Verify SmartCartEvent envelope and domain payload schemas serialize cleanly."""
    order_id = uuid.uuid4()
    cust_id = uuid.uuid4()
    store_id = uuid.uuid4()
    prod_id = uuid.uuid4()

    # 1. OrderCreatedPayload validation
    order_payload = OrderCreatedPayload(
        order_id=order_id,
        order_number="ORD-2026-TEST",
        customer_id=cust_id,
        store_id=store_id,
        total_paise=150000,
        confirmed_at=datetime.now(timezone.utc),
        items=[OrderItemPayload(product_id=prod_id, qty=2, unit_price_paise=75000)],
    )

    event = SmartCartEvent(
        event_id=str(uuid.uuid4()),
        event_type="order.placed",
        aggregate_type="order",
        aggregate_id=str(order_id),
        payload=order_payload.model_dump(),
    )

    json_dict = event.to_json_dict()
    assert json_dict["aggregate_type"] == "order"
    assert json_dict["aggregate_id"] == str(order_id)
    assert json_dict["schema_version"] == "1.0"
    assert isinstance(json_dict["timestamp"], str)  # ISO string

    # 2. Topic routing resolution
    assert get_topic_for_event("order.placed") == settings.KAFKA_TOPIC_ORDERS
    assert get_topic_for_event("order.cancelled") == settings.KAFKA_TOPIC_ORDERS
    assert get_topic_for_event("inventory.reservation.created") == settings.KAFKA_TOPIC_INVENTORY
    assert get_topic_for_event("inventory.stock.updated") == settings.KAFKA_TOPIC_INVENTORY


def test_payload_contract_validations():
    """Verify schema enforcement rejects invalid payloads (negative prices, zero quantity)."""
    with pytest.raises(ValidationError):
        OrderItemPayload(product_id=uuid.uuid4(), qty=0, unit_price_paise=100)  # qty must be > 0

    with pytest.raises(ValidationError):
        OrderItemPayload(product_id=uuid.uuid4(), qty=1, unit_price_paise=-50)  # price must be >= 0

    # StockUpdatedPayload
    stock_payload = StockUpdatedPayload(
        store_id=uuid.uuid4(),
        product_id=uuid.uuid4(),
        qty_on_hand=10,
        qty_reserved=2,
        qty_available=8,
        updated_at=datetime.now(timezone.utc),
    )
    assert stock_payload.qty_available == 8


# ============================================================================
# 3. Successful Publishing & Broker ACK
# ============================================================================

@pytest.mark.asyncio
async def test_producer_successful_publishing():
    """Verify SmartCartKafkaProducer publishes event and awaits broker acknowledgement."""
    mock_future = MagicMock()
    mock_record_md = MagicMock()
    mock_record_md.topic = "smartcart.orders"
    mock_record_md.partition = 1
    mock_record_md.offset = 42
    mock_record_md.timestamp = 1700000000000
    mock_future.get.return_value = mock_record_md

    mock_raw_producer = MagicMock()
    mock_raw_producer.send.return_value = mock_future

    producer = SmartCartKafkaProducer(producer=mock_raw_producer)

    event = SmartCartEvent(
        event_id=str(uuid.uuid4()),
        event_type="order.placed",
        aggregate_type="order",
        aggregate_id="ord-100",
        payload={"order_id": "ord-100"},
    )

    result_md = await producer.publish(topic="smartcart.orders", event=event, key="ord-100")

    assert result_md.topic == "smartcart.orders"
    assert result_md.partition == 1
    assert result_md.offset == 42
    mock_raw_producer.send.assert_called_once()
    mock_future.get.assert_called_once()


# ============================================================================
# 4. Kafka Connection & Publishing Failure
# ============================================================================

@pytest.mark.asyncio
async def test_producer_connection_and_publish_failure():
    """Verify SmartCartKafkaProducer raises KafkaPublishError on broker timeouts or errors."""
    from kafka.errors import KafkaTimeoutError

    mock_future = MagicMock()
    mock_future.get.side_effect = KafkaTimeoutError("Broker timed out after 10000ms")

    mock_raw_producer = MagicMock()
    mock_raw_producer.send.return_value = mock_future

    producer = SmartCartKafkaProducer(producer=mock_raw_producer)

    event = SmartCartEvent(
        event_id=str(uuid.uuid4()),
        event_type="order.placed",
        aggregate_type="order",
        aggregate_id="ord-err",
        payload={},
    )

    with pytest.raises(KafkaPublishError) as exc_info:
        await producer.publish(topic="smartcart.orders", event=event)

    assert "Timed out waiting for broker ACK" in str(exc_info.value)


# ============================================================================
# 5. Outbox Event Claiming (FOR UPDATE SKIP LOCKED)
# ============================================================================

@pytest.mark.asyncio
async def test_outbox_event_claiming_and_dispatch():
    """Verify OutboxPublisher claims pending events with row-level locks and dispatches to Kafka."""
    event_id = uuid.uuid4()
    mock_event = OutboxEvent(
        id=event_id,
        aggregate_type="order",
        aggregate_id="ord-999",
        event_type="order.placed",
        payload={"total_paise": 50000},
        status=OutboxStatus.PENDING,
        retry_count=0,
        created_at=datetime.now(timezone.utc),
    )

    mock_session = AsyncMock()
    mock_session_factory = MagicMock(return_value=mock_session)
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = False

    # Mock OutboxService inside publisher
    with patch("app.kafka.publisher.OutboxService") as mock_outbox_service_cls:
        service_instance = mock_outbox_service_cls.return_value
        service_instance.claim_pending_events.return_value = [mock_event]
        service_instance.acknowledge_published = AsyncMock()

        mock_producer = AsyncMock()
        mock_producer.publish.return_value = RecordMetadata("smartcart.orders", 0, 10)

        publisher = OutboxPublisher(
            session_factory=mock_session_factory,
            producer=mock_producer,
            batch_size=10,
        )

        count = await publisher.publish_batch()

        assert count == 1
        service_instance.claim_pending_events.assert_called_once_with(limit=10)
        mock_producer.publish.assert_awaited_once()
        service_instance.acknowledge_published.assert_awaited_once_with(event_id)
        mock_session.commit.assert_awaited_once()


# ============================================================================
# 6. Outbox Acknowledgement After Broker ACK
# ============================================================================

@pytest.mark.asyncio
async def test_outbox_acknowledgement_strict_order():
    """Verify outbox event is marked PUBLISHED only AFTER broker acknowledgement."""
    mock_session = AsyncMock()
    mock_session_factory = MagicMock(return_value=mock_session)
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = False

    call_order = []

    mock_producer = AsyncMock()
    async def mock_publish(*args, **kwargs):
        call_order.append("kafka_ack")
        return RecordMetadata("smartcart.orders", 0, 1)
    mock_producer.publish.side_effect = mock_publish

    event_id = uuid.uuid4()
    mock_event = OutboxEvent(
        id=event_id,
        aggregate_type="order",
        aggregate_id="1",
        event_type="order.placed",
        payload={},
        status=OutboxStatus.PENDING,
        created_at=datetime.now(timezone.utc),
    )

    with patch("app.kafka.publisher.OutboxService") as mock_service_cls:
        service_inst = mock_service_cls.return_value
        service_inst.claim_pending_events.return_value = [mock_event]

        async def mock_ack(*args, **kwargs):
            call_order.append("db_ack")
            return mock_event
        service_inst.acknowledge_published.side_effect = mock_ack

        publisher = OutboxPublisher(session_factory=mock_session_factory, producer=mock_producer)
        await publisher.publish_batch()

        # Strict ordering: Kafka broker ACK MUST occur before DB acknowledgement
        assert call_order == ["kafka_ack", "db_ack"]


# ============================================================================
# 7. Failed Publishing, Retries & DLQ Routing
# ============================================================================

@pytest.mark.asyncio
async def test_outbox_publish_failure_and_dlq_routing():
    """Verify failed publishing records failure attempt and routes to DLQ upon retry exhaustion."""
    mock_session = AsyncMock()
    mock_session_factory = MagicMock(return_value=mock_session)
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = False

    event_id = uuid.uuid4()
    mock_event = OutboxEvent(
        id=event_id,
        aggregate_type="order",
        aggregate_id="1",
        event_type="order.placed",
        payload={},
        status=OutboxStatus.PENDING,
        retry_count=4,
        created_at=datetime.now(timezone.utc),
    )

    mock_failed_event = OutboxEvent(
        id=event_id,
        aggregate_type="order",
        aggregate_id="1",
        event_type="order.placed",
        payload={},
        status=OutboxStatus.FAILED,  # Max retries (5) reached
        retry_count=5,
        created_at=datetime.now(timezone.utc),
    )

    mock_producer = AsyncMock()
    mock_producer.publish.side_effect = KafkaPublishError("Kafka broker unreachable")

    mock_dlq = AsyncMock()

    with patch("app.kafka.publisher.OutboxService") as mock_service_cls:
        service_inst = mock_service_cls.return_value
        service_inst.claim_pending_events.return_value = [mock_event]
        service_inst.record_publish_failure.return_value = mock_failed_event

        publisher = OutboxPublisher(
            session_factory=mock_session_factory,
            producer=mock_producer,
            dlq_producer=mock_dlq,
            max_retries=5,
        )

        count = await publisher.publish_batch()

        assert count == 0
        service_inst.record_publish_failure.assert_called_once()
        # DLQ called because status transitioned to FAILED
        mock_dlq.send_to_dlq.assert_awaited_once()
        mock_session.commit.assert_awaited_once()


# ============================================================================
# 8. Consumer Duplicate Event Deduplication
# ============================================================================

@pytest.mark.asyncio
async def test_consumer_duplicate_event_deduplication():
    """Verify consumer checks ProcessedEvent and skips handler if event was already processed."""
    mock_session = AsyncMock()
    mock_session_factory = MagicMock(return_value=mock_session)
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = False

    handler_called = []
    async def sample_handler(event, session):
        handler_called.append(event.event_id)

    consumer = SmartCartKafkaConsumer(
        topics=["smartcart.orders"],
        session_factory=mock_session_factory,
        consumer_group="analytics-group",
        consumer=MagicMock(),
    )
    consumer.register_handler("order.placed", sample_handler)

    event_id = str(uuid.uuid4())
    event_data = {
        "event_id": event_id,
        "event_type": "order.placed",
        "aggregate_type": "order",
        "aggregate_id": "ord-dup-1",
        "payload": {},
    }

    mock_record = MagicMock()
    mock_record.value = event_data
    mock_record.topic = "smartcart.orders"
    mock_record.partition = 0
    mock_record.offset = 100

    with patch("app.kafka.consumer.OutboxService") as mock_outbox_service_cls:
        service_inst = mock_outbox_service_cls.return_value
        # Simulate that event IS already processed
        service_inst.is_event_processed.return_value = True

        consumer._sync_commit_offset = MagicMock()

        success = await consumer.process_message(mock_record)

        assert success is True
        assert len(handler_called) == 0  # Handler was skipped!
        # Offset was committed immediately to advance past the duplicate message
        consumer._sync_commit_offset.assert_called_once_with("smartcart.orders", 0, 100)


# ============================================================================
# 9. Consumer Offset Commit After DB Commit
# ============================================================================

@pytest.mark.asyncio
async def test_consumer_offset_committed_only_after_db_commit():
    """Verify consumer commits Kafka offset ONLY after DB transaction successfully commits."""
    mock_session = AsyncMock()
    mock_session_factory = MagicMock(return_value=mock_session)
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = False

    call_sequence = []

    async def mock_commit():
        call_sequence.append("db_commit")
    mock_session.commit.side_effect = mock_commit

    consumer = SmartCartKafkaConsumer(
        topics=["smartcart.orders"],
        session_factory=mock_session_factory,
        consumer_group="inventory-group",
        consumer=MagicMock(),
    )

    def mock_kafka_commit(topic, partition, offset):
        call_sequence.append("kafka_offset_commit")
    consumer._sync_commit_offset = mock_kafka_commit

    event_id = str(uuid.uuid4())
    event_data = {
        "event_id": event_id,
        "event_type": "order.placed",
        "aggregate_type": "order",
        "aggregate_id": "ord-order-commit",
        "payload": {},
    }

    mock_record = MagicMock()
    mock_record.value = event_data
    mock_record.topic = "smartcart.orders"
    mock_record.partition = 0
    mock_record.offset = 50

    with patch("app.kafka.consumer.OutboxService") as mock_service_cls:
        service_inst = mock_service_cls.return_value
        service_inst.is_event_processed.return_value = False
        service_inst.record_event_processed = AsyncMock()

        success = await consumer.process_message(mock_record)

        assert success is True
        assert call_sequence == ["db_commit", "kafka_offset_commit"]


# ============================================================================
# 10. Retry & Exponential Backoff
# ============================================================================

def test_retry_and_exponential_backoff_calculations():
    """Verify error classification and backoff formula with exponential scaling and jitter."""
    # 1. Error classification
    assert is_retryable_error(ConnectionError("Network reset")) is True
    assert is_retryable_error(TimeoutError("Kafka request timeout")) is True
    assert is_retryable_error(ValueError("Invalid integer conversion")) is False
    assert is_retryable_error(KeyError("Missing required payload field")) is False
    assert is_retryable_error(NonRetryableError("Corrupt payload")) is False

    # 2. Exponential backoff calculation
    b1 = calculate_exponential_backoff(attempt=1, base_backoff_ms=500, jitter=False)
    assert b1 == 0.5  # 500ms * 2^0 = 500ms = 0.5s

    b2 = calculate_exponential_backoff(attempt=2, base_backoff_ms=500, jitter=False)
    assert b2 == 1.0  # 500ms * 2^1 = 1000ms = 1.0s

    b3 = calculate_exponential_backoff(attempt=3, base_backoff_ms=500, jitter=False)
    assert b3 == 2.0  # 500ms * 2^2 = 2000ms = 2.0s


# ============================================================================
# 11. Dead Letter Queue (DLQ) Publishing
# ============================================================================

@pytest.mark.asyncio
async def test_dlq_publishing_and_resilience():
    """Verify DeadLetterQueueProducer packages diagnostic metadata and publishes to smartcart.dlq."""
    mock_producer = AsyncMock()
    mock_producer.publish.return_value = RecordMetadata("smartcart.dlq", 0, 5)

    dlq = DeadLetterQueueProducer(producer=mock_producer, dlq_topic="smartcart.dlq")

    failed_event = {
        "event_id": "fail-123",
        "event_type": "order.placed",
        "aggregate_type": "order",
        "aggregate_id": "ord-fail",
        "payload": {"item": "xyz"},
    }

    error = ValueError("Missing mandatory customer address")

    await dlq.send_to_dlq(
        event=failed_event,
        error=error,
        original_topic="smartcart.orders",
        partition=2,
        offset=99,
        attempt_count=3,
    )

    mock_producer.publish.assert_awaited_once()
    publish_args = mock_producer.publish.call_args[1]

    assert publish_args["topic"] == "smartcart.dlq"
    dlq_event = publish_args["event"]
    assert dlq_event.event_type == "event.dlq"
    assert dlq_event.payload["original_event_id"] == "fail-123"
    assert dlq_event.payload["original_topic"] == "smartcart.orders"
    assert dlq_event.payload["original_partition"] == 2
    assert dlq_event.payload["original_offset"] == 99
    assert dlq_event.payload["error_type"] == "ValueError"
    assert "Missing mandatory customer address" in dlq_event.payload["error_message"]
    assert dlq_event.payload["attempt_count"] == 3


@pytest.mark.asyncio
async def test_dlq_broker_failure_resilience():
    """Verify failure to write to DLQ topic itself is handled gracefully without crashing."""
    mock_producer = AsyncMock()
    mock_producer.publish.side_effect = KafkaPublishError("DLQ topic unavailable")

    dlq = DeadLetterQueueProducer(producer=mock_producer, dlq_topic="smartcart.dlq")

    # Should not raise exception
    res = await dlq.send_to_dlq(event={"event_id": "test"}, error=RuntimeError("Test error"))
    assert res is None


# ============================================================================
# 12. Graceful Shutdown
# ============================================================================

@pytest.mark.asyncio
async def test_graceful_shutdown_publisher_and_consumer():
    """Verify workers respond to stop_event and shut down connections cleanly."""
    mock_producer = AsyncMock()
    stop_event = asyncio.Event()

    publisher = OutboxPublisher(
        session_factory=MagicMock(),
        producer=mock_producer,
    )
    publisher.publish_batch = AsyncMock(return_value=0)

    # Set stop_event after brief execution
    async def _trigger_stop():
        await asyncio.sleep(0.05)
        stop_event.set()

    asyncio.create_task(_trigger_stop())

    # Run loop should cleanly terminate when stop_event is set
    await publisher.run_loop(poll_interval_seconds=0.01, stop_event=stop_event)

    # Test producer and consumer clean close
    producer = SmartCartKafkaProducer(producer=MagicMock())
    producer.close()
    assert producer._producer is None

    consumer = SmartCartKafkaConsumer(
        topics=["smartcart.orders"],
        session_factory=MagicMock(),
        consumer=MagicMock(),
    )
    consumer.close()
    assert consumer._consumer is None


# ============================================================================
# 13. Synthetic Event Filtering in Production Consumer Groups
# ============================================================================

@pytest.mark.asyncio
async def test_consumer_filters_synthetic_events_in_production_group():
    """Verify production consumer commits offset and skips DB processing for synthetic events."""
    mock_raw_consumer = MagicMock()
    mock_session_factory = MagicMock()

    consumer = SmartCartKafkaConsumer(
        topics=["smartcart.orders"],
        session_factory=mock_session_factory,
        consumer_group=settings.KAFKA_CONSUMER_GROUP_ID,
        consumer=mock_raw_consumer,
    )

    synthetic_event = SmartCartEvent(
        event_id=str(uuid.uuid4()),
        event_type="test.synthetic.probe",
        aggregate_type="test_probe",
        aggregate_id="probe-123",
        payload={"is_synthetic_test": True, "probe_id": "test-1"},
    )

    mock_record = MagicMock()
    mock_record.topic = "smartcart.orders"
    mock_record.partition = 0
    mock_record.offset = 100
    mock_record.value = synthetic_event.to_json_dict()

    success = await consumer.process_message(mock_record)
    assert success is True

    # Database session factory should NEVER be called for synthetic test events in production groups
    mock_session_factory.assert_not_called()

    # Verify offset commit was still executed to advance queue
    mock_raw_consumer.commit.assert_called_once()


# ============================================================================
# 14. Live Aiven Kafka Integration Test
# ============================================================================

@pytest.mark.asyncio
async def test_live_aiven_kafka_integration():
    """
    Live integration test against real Aiven Kafka cluster.
    Publishes a synthetic probe event with acks=all and verifies delivery metadata.
    """
    common_cfg = KafkaConfigBuilder.get_common_config()
    bootstrap = common_cfg.get("bootstrap_servers")
    if not bootstrap or bootstrap in ("localhost:9092", "127.0.0.1:9092"):
        pytest.skip("Aiven Kafka bootstrap servers not configured. Skipping live test.")

    producer = SmartCartKafkaProducer()
    test_event_id = str(uuid.uuid4())
    try:
        await producer.astart()
        test_event = SmartCartEvent(
            event_id=test_event_id,
            event_type="test.synthetic.probe",
            aggregate_type="test_probe",
            aggregate_id=test_event_id,
            payload={
                "message": "SmartCart live Aiven Kafka handshake test",
                "is_synthetic_test": True,
            },
        )
        md = await producer.publish(
            topic=settings.KAFKA_TOPIC_ORDERS,
            event=test_event,
            timeout=10.0,
        )
        assert md.topic == settings.KAFKA_TOPIC_ORDERS
        assert md.partition in (0, 1)
        assert md.offset >= 0
    finally:
        await producer.aclose()
