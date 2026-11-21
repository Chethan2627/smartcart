"""
Kafka producer service for SmartCart 2.0.
Publishes structured JSON events to Aiven Kafka with broker ACK verification,
robust error handling, and clean asynchronous execution.
"""
import asyncio
import json
import logging
from typing import Any, Dict, Optional, Union
from uuid import UUID

from kafka import KafkaProducer
from kafka.errors import KafkaError, KafkaTimeoutError

from app.core.exceptions import SmartCartError
from app.kafka.config import KafkaConfigBuilder
from app.kafka.schemas import SmartCartEvent

logger = logging.getLogger("smartcart.kafka.producer")


class KafkaConnectionError(SmartCartError):
    """Raised when failing to establish connection to Aiven Kafka cluster."""


class KafkaPublishError(SmartCartError):
    """Raised when publishing a message to Kafka fails or ACK times out."""


class RecordMetadata:
    """Encapsulates broker delivery acknowledgement details."""

    def __init__(self, topic: str, partition: int, offset: int, timestamp: Optional[int] = None) -> None:
        self.topic = topic
        self.partition = partition
        self.offset = offset
        self.timestamp = timestamp

    def __repr__(self) -> str:
        return f"RecordMetadata(topic='{self.topic}', partition={self.partition}, offset={self.offset})"


class SmartCartKafkaProducer:
    """
    Production-ready Kafka producer service for SmartCart 2.0.
    Supports asynchronous event publishing to Aiven Kafka with strict broker ACK verification.
    """

    def __init__(self, producer: Optional[Any] = None) -> None:
        self._producer: Optional[Any] = producer
        self._is_started: bool = producer is not None

    def _create_producer(self) -> KafkaProducer:
        """Instantiate KafkaProducer using KafkaConfigBuilder."""
        config = KafkaConfigBuilder.get_producer_config()
        sanitized = KafkaConfigBuilder.get_sanitized_config(config)
        logger.info("Initializing Aiven KafkaProducer with bootstrap_servers=%s", sanitized.get("bootstrap_servers"))

        try:
            return KafkaProducer(
                value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
                key_serializer=lambda k: str(k).encode("utf-8") if k is not None else None,
                **config,
            )
        except Exception as exc:
            logger.error("Failed to initialize Aiven KafkaProducer: %s", exc)
            raise KafkaConnectionError(f"Failed to connect to Aiven Kafka: {exc}") from exc

    def start(self) -> None:
        """Start the producer client synchronously."""
        if not self._is_started:
            if self._producer is None:
                self._producer = self._create_producer()
            self._is_started = True
            logger.info("Aiven KafkaProducer started successfully.")

    async def astart(self) -> None:
        """Start the producer asynchronously."""
        if not self._is_started:
            await asyncio.to_thread(self.start)

    def _sync_publish(
        self,
        topic: str,
        value: Dict[str, Any],
        key: Optional[str] = None,
        timeout: float = 10.0,
    ) -> RecordMetadata:
        """Synchronously send event to Kafka broker and wait for ISR acknowledgement."""
        if self._producer is None:
            self.start()

        try:
            future = self._producer.send(topic, key=key, value=value)
            # future.get() blocks until broker ACK or timeout
            record_md = future.get(timeout=timeout)
            return RecordMetadata(
                topic=record_md.topic,
                partition=record_md.partition,
                offset=record_md.offset,
                timestamp=getattr(record_md, "timestamp", None),
            )
        except KafkaTimeoutError as exc:
            msg = f"Timed out waiting for broker ACK on topic '{topic}': {exc}"
            logger.error(msg)
            raise KafkaPublishError(msg) from exc
        except KafkaError as exc:
            msg = f"Broker delivery error on topic '{topic}': {exc}"
            logger.error(msg)
            raise KafkaPublishError(msg) from exc
        except Exception as exc:
            msg = f"Unexpected failure publishing to topic '{topic}': {exc}"
            logger.error(msg)
            raise KafkaPublishError(msg) from exc

    async def publish(
        self,
        topic: str,
        event: Union[SmartCartEvent, Dict[str, Any]],
        key: Optional[Union[str, UUID]] = None,
        timeout: float = 10.0,
    ) -> RecordMetadata:
        """
        Asynchronously publish a SmartCartEvent to Aiven Kafka.
        Awaits broker delivery confirmation in a worker thread without blocking the event loop.
        """
        if isinstance(event, SmartCartEvent):
            payload_dict = event.to_json_dict()
            publish_key = str(key or event.aggregate_id)
        else:
            payload_dict = dict(event)
            publish_key = str(key) if key is not None else None

        record_md = await asyncio.to_thread(
            self._sync_publish,
            topic=topic,
            value=payload_dict,
            key=publish_key,
            timeout=timeout,
        )

        logger.debug(
            "Event published to Kafka [topic=%s partition=%s offset=%s key=%s]",
            record_md.topic,
            record_md.partition,
            record_md.offset,
            publish_key,
        )
        return record_md

    def flush(self, timeout: Optional[float] = None) -> None:
        """Flush pending producer messages."""
        if self._producer is not None:
            self._producer.flush(timeout=timeout)

    def close(self, timeout: Optional[float] = 5.0) -> None:
        """Close producer connections cleanly."""
        if self._producer is not None:
            try:
                self._producer.flush(timeout=timeout)
                self._producer.close(timeout=timeout)
                logger.info("Aiven KafkaProducer closed cleanly.")
            except Exception as exc:
                logger.warning("Error during KafkaProducer shutdown: %s", exc)
            finally:
                self._producer = None
                self._is_started = False

    async def aclose(self, timeout: Optional[float] = 5.0) -> None:
        """Asynchronously close producer connections cleanly."""
        await asyncio.to_thread(self.close, timeout=timeout)
