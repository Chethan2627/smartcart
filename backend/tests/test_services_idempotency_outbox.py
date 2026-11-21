"""
Unit tests for SmartCart 2.0 Phase 4 Stage 5:
IdempotencyService and OutboxService.
Runs completely offline using mock repositories and async sessions.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import uuid
import pytest
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import (
    ConflictError,
    DuplicateResourceError,
    IdempotencyConflictError,
    NotFoundError,
    ValidationError,
)
from app.models.enums import OutboxStatus
from app.models.outbox import IdempotencyKey, OutboxEvent, ProcessedEvent
from app.services.idempotency import IdempotencyService
from app.services.outbox import OutboxService


class MockAsyncContextManager:
    """Mock for SQLAlchemy async context managers (begin, begin_nested)."""

    def __init__(self, raises_on_exit=None):
        self.entered = False
        self.exited = False
        self.raises_on_exit = raises_on_exit

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.exited = True
        if self.raises_on_exit:
            raise self.raises_on_exit
        return False


# ============================================================================
# 1. IdempotencyService Tests
# ============================================================================

@pytest.mark.asyncio
async def test_idempotency_record_creation_and_hash():
    """Verify IdempotencyService creates pending record with deterministic SHA-256 hash."""
    cust_id = uuid.uuid4()
    key = "checkout-key-001"
    payload = {"store_id": str(uuid.uuid4()), "address": "123 MG Road"}

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.in_transaction = MagicMock(return_value=True)
    mock_session.begin_nested = MagicMock(return_value=MockAsyncContextManager())

    repo = AsyncMock()
    repo.get_by_customer_and_key.return_value = None  # Key does not exist yet

    service = IdempotencyService(idempotency_repo=repo, session=mock_session)

    record, is_replay = await service.start_idempotent_operation(
        customer_id=cust_id,
        key=key,
        request_payload=payload,
    )

    assert is_replay is False
    assert record.customer_id == cust_id
    assert record.key == key
    assert len(record.request_hash) == 64  # SHA-256 hex digest length
    assert record.response is None
    assert record.order_id is None

    mock_session.add.assert_called_once_with(record)
    mock_session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_idempotency_key_validation():
    """Verify IdempotencyService rejects malformed keys."""
    service = IdempotencyService(idempotency_repo=AsyncMock(), session=AsyncMock())

    # Empty key
    with pytest.raises(ValidationError):
        service.validate_key("")

    # Spaces or invalid special characters
    with pytest.raises(ValidationError):
        service.validate_key("invalid key with spaces")

    with pytest.raises(ValidationError):
        service.validate_key("bad@key#$")

    # Key too long (> 255 chars)
    with pytest.raises(ValidationError):
        service.validate_key("a" * 256)

    # Valid keys do not raise
    service.validate_key("valid-Key_12345")


@pytest.mark.asyncio
async def test_idempotency_same_key_same_payload_in_progress():
    """Verify concurrent / repeated request with same key while operation is pending raises ConflictError."""
    cust_id = uuid.uuid4()
    key = "checkout-key-in-progress"
    payload = {"store_id": "STORE-1", "address": "456 Residency Rd"}

    service = IdempotencyService(idempotency_repo=AsyncMock(), session=AsyncMock())
    expected_hash = service.compute_request_hash(payload)

    pending_record = IdempotencyKey(
        customer_id=cust_id,
        key=key,
        request_hash=expected_hash,
        response=None,  # Still pending
        order_id=None,
    )

    repo = AsyncMock()
    repo.get_by_customer_and_key.return_value = pending_record
    service.idempotency_repo = repo

    with pytest.raises(ConflictError) as exc_info:
        await service.start_idempotent_operation(cust_id, key, payload)

    assert "currently being processed" in str(exc_info.value)


@pytest.mark.asyncio
async def test_idempotency_same_key_different_payload_conflict():
    """Verify reusing same key with different payload raises IdempotencyConflictError."""
    cust_id = uuid.uuid4()
    key = "reused-key"
    payload1 = {"store_id": "STORE-1", "items": [{"id": 1}]}
    payload2 = {"store_id": "STORE-1", "items": [{"id": 2}]}

    service = IdempotencyService(idempotency_repo=AsyncMock(), session=AsyncMock())
    hash1 = service.compute_request_hash(payload1)

    existing_record = IdempotencyKey(
        customer_id=cust_id,
        key=key,
        request_hash=hash1,
        response={"status": "confirmed"},
    )

    repo = AsyncMock()
    repo.get_by_customer_and_key.return_value = existing_record
    service.idempotency_repo = repo

    with pytest.raises(IdempotencyConflictError) as exc_info:
        await service.start_idempotent_operation(cust_id, key, payload2)

    assert "differing request body" in str(exc_info.value)


@pytest.mark.asyncio
async def test_idempotency_completed_response_replay():
    """Verify completed idempotent operation returns cached response without reprocessing."""
    cust_id = uuid.uuid4()
    key = "completed-key"
    order_id = uuid.uuid4()
    payload = {"store_id": "STORE-1", "address": "MG Road"}

    service = IdempotencyService(idempotency_repo=AsyncMock(), session=AsyncMock())
    req_hash = service.compute_request_hash(payload)

    completed_record = IdempotencyKey(
        customer_id=cust_id,
        key=key,
        request_hash=req_hash,
        order_id=order_id,
        response={"order_id": str(order_id), "status": "CONFIRMED", "total_paise": 150000},
    )

    repo = AsyncMock()
    repo.get_by_customer_and_key.return_value = completed_record
    service.idempotency_repo = repo

    record, is_replay = await service.start_idempotent_operation(cust_id, key, payload)

    assert is_replay is True
    assert record.response["status"] == "CONFIRMED"
    assert record.order_id == order_id


@pytest.mark.asyncio
async def test_idempotency_completion_and_failure_cleanup():
    """Verify complete_idempotent_operation and fail_idempotent_operation behaviors."""
    cust_id = uuid.uuid4()
    key = "finish-key"
    order_id = uuid.uuid4()

    record = IdempotencyKey(
        customer_id=cust_id,
        key=key,
        request_hash="hash",
        response=None,
    )

    repo = AsyncMock()
    repo.get_by_customer_and_key.return_value = record
    mock_session = AsyncMock()

    service = IdempotencyService(idempotency_repo=repo, session=mock_session)

    # 1. Complete
    resp_data = {"order_id": str(order_id), "status": "CONFIRMED"}
    completed = await service.complete_idempotent_operation(cust_id, key, resp_data, order_id=order_id)
    assert completed.response == resp_data
    assert completed.order_id == order_id
    mock_session.flush.assert_awaited()

    # 2. Fail cleanup on pending record
    pending_record = IdempotencyKey(
        customer_id=cust_id,
        key="pending-to-fail",
        request_hash="hash",
        response=None,
    )
    repo.get_by_customer_and_key.return_value = pending_record
    await service.fail_idempotent_operation(cust_id, "pending-to-fail")
    mock_session.delete.assert_called_once_with(pending_record)


@pytest.mark.asyncio
async def test_idempotency_concurrent_duplicate_key_conflict_handling():
    """Verify IntegrityError on concurrent insert catches conflict and checks existing record."""
    cust_id = uuid.uuid4()
    key = "concurrent-key"
    payload = {"data": "test"}

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.in_transaction = MagicMock(return_value=True)
    mock_session.begin_nested = MagicMock(return_value=MockAsyncContextManager())
    # Flush raises IntegrityError simulating concurrent primary key race
    mock_session.flush.side_effect = IntegrityError("INSERT ... duplicate key", {}, Exception())

    service = IdempotencyService(idempotency_repo=AsyncMock(), session=mock_session)
    req_hash = service.compute_request_hash(payload)

    # First lookup returns None (race window), recheck returns the record inserted concurrently
    winner_record = IdempotencyKey(
        customer_id=cust_id,
        key=key,
        request_hash=req_hash,
        response={"status": "confirmed"},
    )
    repo = AsyncMock()
    repo.get_by_customer_and_key.side_effect = [None, winner_record]
    service.idempotency_repo = repo

    record, is_replay = await service.start_idempotent_operation(cust_id, key, payload)
    assert is_replay is True
    assert record == winner_record


# ============================================================================
# 2. OutboxService Tests
# ============================================================================

@pytest.mark.asyncio
async def test_outbox_event_creation_and_no_commit():
    """Verify OutboxService creates PENDING event without committing the transaction."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()

    service = OutboxService(
        outbox_repo=AsyncMock(),
        processed_repo=AsyncMock(),
        session=mock_session,
    )

    order_id = uuid.uuid4()
    payload = {"order_id": str(order_id), "total_paise": 1799900}

    event = await service.create_event(
        aggregate_type="order",
        aggregate_id=str(order_id),
        event_type="order.placed",
        payload=payload,
    )

    assert event.aggregate_type == "order"
    assert event.aggregate_id == str(order_id)
    assert event.event_type == "order.placed"
    assert event.status == OutboxStatus.PENDING
    assert event.retry_count == 0
    assert event.last_error is None
    assert event.published_at is None

    mock_session.add.assert_called_once_with(event)
    mock_session.flush.assert_awaited()
    # Explicit architectural guarantee: OutboxService NEVER commits!
    mock_session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_outbox_no_premature_published_status():
    """Verify events are NEVER created or marked PUBLISHED without explicit broker acknowledgement."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()

    service = OutboxService(
        outbox_repo=AsyncMock(),
        processed_repo=AsyncMock(),
        session=mock_session,
    )

    event = await service.create_event("order", "123", "order.placed", {"item": 1})
    assert event.status != OutboxStatus.PUBLISHED
    assert event.status == OutboxStatus.PENDING


@pytest.mark.asyncio
async def test_outbox_acknowledge_published():
    """Verify acknowledge_published transitions status to PUBLISHED with published_at timestamp."""
    event_id = uuid.uuid4()
    mock_event = OutboxEvent(
        id=event_id,
        aggregate_type="order",
        aggregate_id="123",
        event_type="order.placed",
        payload={},
        status=OutboxStatus.PENDING,
        retry_count=1,
        last_error="Initial network blip",
    )

    outbox_repo = AsyncMock()
    outbox_repo.get_by_id.return_value = mock_event
    mock_session = AsyncMock()

    service = OutboxService(
        outbox_repo=outbox_repo,
        processed_repo=AsyncMock(),
        session=mock_session,
    )

    acknowledged = await service.acknowledge_published(event_id)

    assert acknowledged.status == OutboxStatus.PUBLISHED
    assert acknowledged.published_at is not None
    assert acknowledged.last_error is None
    mock_session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_outbox_publish_failure_and_retry_exhaustion():
    """Verify publish failure increments retry count, sanitizes errors, and transitions to FAILED when max_retries reached."""
    event_id = uuid.uuid4()
    mock_event = OutboxEvent(
        id=event_id,
        aggregate_type="order",
        aggregate_id="123",
        event_type="order.placed",
        payload={},
        status=OutboxStatus.PENDING,
        retry_count=0,
    )

    outbox_repo = AsyncMock()
    outbox_repo.get_by_id.return_value = mock_event
    mock_session = AsyncMock()

    service = OutboxService(
        outbox_repo=outbox_repo,
        processed_repo=AsyncMock(),
        session=mock_session,
    )

    # Attempt 1: retry_count becomes 1, status remains PENDING for retry
    ev1 = await service.record_publish_failure(event_id, "Broker connection timeout", max_retries=3)
    assert ev1.retry_count == 1
    assert ev1.status == OutboxStatus.PENDING
    assert ev1.last_error == "Broker connection timeout"
    assert ev1.published_at is None

    # Attempt 2: retry_count becomes 2, status remains PENDING
    ev2 = await service.record_publish_failure(event_id, "Broker unavailable", max_retries=3)
    assert ev2.retry_count == 2
    assert ev2.status == OutboxStatus.PENDING

    # Attempt 3: retry_count becomes 3 >= max_retries (3), status transitions to FAILED
    ev3 = await service.record_publish_failure(event_id, "Persistent broker failure", max_retries=3)
    assert ev3.retry_count == 3
    assert ev3.status == OutboxStatus.FAILED


@pytest.mark.asyncio
async def test_outbox_list_pending_and_claiming():
    """Verify listing pending events and safe event claiming with FOR UPDATE SKIP LOCKED."""
    e1 = OutboxEvent(id=uuid.uuid4(), aggregate_type="order", aggregate_id="1", event_type="e1", payload={}, status=OutboxStatus.PENDING)

    outbox_repo = AsyncMock()
    outbox_repo.list_pending.return_value = [e1]

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [e1]
    mock_session.execute.return_value = mock_result

    service = OutboxService(
        outbox_repo=outbox_repo,
        processed_repo=AsyncMock(),
        session=mock_session,
    )

    # 1. list_pending
    pending = await service.list_pending_events(limit=50)
    assert len(pending) == 1
    assert pending[0].aggregate_id == "1"

    # 2. claim_pending
    claimed = await service.claim_pending_events(limit=25)
    assert len(claimed) == 1
    mock_session.execute.assert_awaited()


@pytest.mark.asyncio
async def test_processed_event_deduplication():
    """Verify ProcessedEvent prevents duplicate consumption across consumer groups."""
    event_id = "evt-uuid-123"
    group = "inventory-sync-workers"

    processed_repo = AsyncMock()
    # First check: not processed; second check: already processed
    processed_repo.is_processed.side_effect = [False, True]

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.in_transaction = MagicMock(return_value=True)
    mock_session.begin_nested = MagicMock(return_value=MockAsyncContextManager())

    service = OutboxService(
        outbox_repo=AsyncMock(),
        processed_repo=processed_repo,
        session=mock_session,
    )

    # 1. First processing succeeds
    record = await service.record_event_processed(event_id=event_id, consumer_group=group)
    assert record.event_id == event_id
    assert record.consumer_group == group
    mock_session.add.assert_called_once_with(record)

    # 2. Duplicate processing attempt raises DuplicateResourceError
    with pytest.raises(DuplicateResourceError) as exc_info:
        await service.record_event_processed(event_id=event_id, consumer_group=group)

    assert "already been processed" in str(exc_info.value)
