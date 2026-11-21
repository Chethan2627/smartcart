"""
Dead Letter Queue (DLQ) service for SmartCart 2.0.
Captures permanently unprocessable or retry-exhausted events, preserving
comprehensive diagnostic metadata for inspection and manual replay.
"""
import logging
import random
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union
from uuid import UUID, uuid4

from pydantic import ValidationError

from app.config import settings
from app.kafka.producer import SmartCartKafkaProducer
from app.kafka.schemas import SmartCartEvent

logger = logging.getLogger("smartcart.kafka.dlq")


class NonRetryableError(Exception):
    """Signals that a failure cannot succeed on subsequent retries (e.g. poison pills, validation errors)."""


def is_retryable_error(exc: Exception) -> bool:
    """
    Determine whether an error is transient/retryable (network, broker timeout)
    versus permanent/non-retryable (corrupted payload, missing schema fields).
    """
    if isinstance(exc, (ValidationError, ValueError, KeyError, TypeError, NonRetryableError)):
        return False
    return True


def calculate_exponential_backoff(
    attempt: int,
    base_backoff_ms: int = 500,
    max_backoff_ms: int = 30000,
    jitter: bool = True,
) -> float:
    """
    Compute exponential backoff duration in seconds.
    duration = min(max_backoff_ms, base_backoff_ms * (2 ** (attempt - 1))) + jitter
    """
    exp_factor = 2 ** max(0, attempt - 1)
    backoff_ms = min(max_backoff_ms, base_backoff_ms * exp_factor)
    if jitter:
        backoff_ms = backoff_ms * random.uniform(0.8, 1.2)
    return backoff_ms / 1000.0


class DeadLetterQueueProducer:
    """
    Dispatches failed messages to the canonical SmartCart Dead Letter Queue (smartcart.dlq).
    Preserves original event metadata, error diagnosis, attempt count, and payload.
    """

    def __init__(
        self,
        producer: SmartCartKafkaProducer,
        dlq_topic: Optional[str] = None,
    ) -> None:
        self.producer = producer
        self.dlq_topic = dlq_topic or getattr(settings, "KAFKA_TOPIC_DLQ", "smartcart.dlq")

    async def send_to_dlq(
        self,
        event: Union[SmartCartEvent, Dict[str, Any]],
        error: Exception,
        original_topic: Optional[str] = None,
        partition: Optional[int] = None,
        offset: Optional[int] = None,
        attempt_count: int = 1,
    ) -> Optional[Any]:
        """
        Package failed event into a DLQ envelope and publish to smartcart.dlq.
        Catches broker delivery errors gracefully to prevent crashing worker loops.
        """
        event_dict = event.to_json_dict() if isinstance(event, SmartCartEvent) else dict(event)
        event_id = str(event_dict.get("event_id") or uuid4())
        event_type = str(event_dict.get("event_type") or "unknown")

        sanitized_error = str(error)[:1000] if error else "Unspecified processing error"
        dlq_id = str(uuid4())

        dlq_payload = {
            "dlq_id": dlq_id,
            "original_event_id": event_id,
            "original_event_type": event_type,
            "original_topic": original_topic or "unknown",
            "original_partition": partition,
            "original_offset": offset,
            "error_type": error.__class__.__name__,
            "error_message": sanitized_error,
            "attempt_count": attempt_count,
            "failed_at": datetime.now(timezone.utc).isoformat(),
            "original_payload": event_dict,
        }

        dlq_event = SmartCartEvent(
            event_id=dlq_id,
            event_type="event.dlq",
            aggregate_type="dlq",
            aggregate_id=event_id,
            payload=dlq_payload,
        )

        try:
            logger.warning(
                "Routing event to DLQ [dlq_id=%s, original_event_id=%s, original_topic=%s, error=%s]",
                dlq_id,
                event_id,
                original_topic,
                sanitized_error,
            )
            return await self.producer.publish(
                topic=self.dlq_topic,
                event=dlq_event,
                key=event_id,
            )
        except Exception as dlq_exc:
            logger.critical(
                "CRITICAL: Failed to publish message to Dead Letter Queue topic '%s': %s. Original event ID: %s",
                self.dlq_topic,
                dlq_exc,
                event_id,
            )
            return None
