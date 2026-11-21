"""
Transactional outbox domain service for SmartCart 2.0.
Coordinates atomic outbox event persistence, dispatch claiming, acknowledgement,
failure tracking with sanitization, and consumer deduplication.
"""
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Sequence
from uuid import UUID, uuid4
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    DuplicateResourceError,
    NotFoundError,
    ValidationError,
)
from app.models.enums import OutboxStatus
from app.models.outbox import OutboxEvent, ProcessedEvent
from app.repositories.outbox import OutboxEventRepository
from app.repositories.processed_event import ProcessedEventRepository


class OutboxService:
    """Service managing transactional outbox event creation, claiming, and deduplication."""

    def __init__(
        self,
        outbox_repo: OutboxEventRepository,
        processed_repo: ProcessedEventRepository,
        session: Optional[AsyncSession] = None,
    ) -> None:
        self.outbox_repo = outbox_repo
        self.processed_repo = processed_repo
        self.session = session or outbox_repo.session

    async def create_event(
        self,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: Dict[str, Any],
    ) -> OutboxEvent:
        """
        Record a transactional outbox event within the ambient database transaction.
        The event is flushed to the session but NEVER committed here; commitment is
        owned strictly by the enclosing business operation (e.g. order placement).
        """
        if not aggregate_type or not aggregate_type.strip():
            raise ValidationError("aggregate_type must be non-empty")
        if not aggregate_id or not aggregate_id.strip():
            raise ValidationError("aggregate_id must be non-empty")
        if not event_type or not event_type.strip():
            raise ValidationError("event_type must be non-empty")
        if payload is None:
            raise ValidationError("payload must be provided")

        event = OutboxEvent(
            id=uuid4(),
            aggregate_type=aggregate_type.strip(),
            aggregate_id=str(aggregate_id).strip(),
            event_type=event_type.strip(),
            payload=payload,
            status=OutboxStatus.PENDING,
            retry_count=0,
            last_error=None,
        )

        self.session.add(event)
        await self.session.flush()
        return event

    async def list_pending_events(self, limit: int = 100) -> Sequence[OutboxEvent]:
        """Retrieve a chronological batch of PENDING outbox events."""
        return await self.outbox_repo.list_pending(limit=limit)

    async def list_retryable_events(
        self, max_retries: int = 5, limit: int = 100
    ) -> Sequence[OutboxEvent]:
        """
        Retrieve events eligible for dispatch retry (PENDING or FAILED with retry_count < max_retries).
        """
        stmt = (
            select(OutboxEvent)
            .where(
                OutboxEvent.status.in_([OutboxStatus.PENDING, OutboxStatus.FAILED]),
                OutboxEvent.retry_count < max_retries,
            )
            .order_by(OutboxEvent.created_at.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def claim_pending_events(self, limit: int = 50) -> Sequence[OutboxEvent]:
        """
        Claim a batch of PENDING events safely using SELECT ... FOR UPDATE SKIP LOCKED.
        Allows multiple outbox worker processes to dispatch concurrently without collisions.
        """
        stmt = (
            select(OutboxEvent)
            .where(OutboxEvent.status == OutboxStatus.PENDING)
            .order_by(OutboxEvent.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def acknowledge_published(self, event_id: UUID) -> OutboxEvent:
        """
        Mark an event as PUBLISHED upon verified broker acknowledgement.
        Never called prior to confirmation from message bus.
        """
        event = await self.outbox_repo.get_by_id(event_id)
        if event is None:
            raise NotFoundError(f"Outbox event '{event_id}' not found")

        event.status = OutboxStatus.PUBLISHED
        event.published_at = datetime.now(timezone.utc)
        event.last_error = None

        await self.session.flush()
        return event

    async def record_publish_failure(
        self,
        event_id: UUID,
        error_message: str,
        max_retries: int = 5,
    ) -> OutboxEvent:
        """
        Record a dispatch failure attempt and sanitize error diagnostic details.
        Transitions status to FAILED once retry attempts meet or exceed max_retries.
        """
        event = await self.outbox_repo.get_by_id(event_id)
        if event is None:
            raise NotFoundError(f"Outbox event '{event_id}' not found")

        event.retry_count += 1

        # Sanitize error to prevent leaking sensitive internal infrastructure secrets
        sanitized = error_message.strip()[:500] if error_message else "Unknown dispatch error"
        event.last_error = sanitized
        event.published_at = None

        if event.retry_count >= max_retries:
            event.status = OutboxStatus.FAILED
        else:
            event.status = OutboxStatus.PENDING

        await self.session.flush()
        return event

    async def is_event_processed(self, event_id: str, consumer_group: str) -> bool:
        """Check if an event has already been processed by the consumer group."""
        return await self.processed_repo.is_processed(event_id=event_id, consumer_group=consumer_group)

    async def record_event_processed(
        self,
        event_id: str,
        consumer_group: str,
    ) -> ProcessedEvent:
        """
        Atomically record consumer group event deduplication to ensure exactly-once semantics.
        Raises DuplicateResourceError if the event was already processed.
        """
        if not event_id or not event_id.strip():
            raise ValidationError("event_id must be non-empty")
        if not consumer_group or not consumer_group.strip():
            raise ValidationError("consumer_group must be non-empty")

        event_id_str = event_id.strip()
        group_str = consumer_group.strip()

        if await self.is_event_processed(event_id_str, group_str):
            raise DuplicateResourceError(
                f"Event '{event_id_str}' has already been processed by consumer group '{group_str}'"
            )

        processed = ProcessedEvent(
            event_id=event_id_str,
            consumer_group=group_str,
        )

        session = self.session

        async def _persist() -> ProcessedEvent:
            session.add(processed)
            await session.flush()
            return processed

        try:
            if session.in_transaction():
                async with session.begin_nested():
                    return await _persist()
            else:
                async with session.begin():
                    return await _persist()
        except IntegrityError as exc:
            raise DuplicateResourceError(
                f"Event '{event_id_str}' was concurrently processed by consumer group '{group_str}'"
            ) from exc
