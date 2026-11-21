"""
Kafka integration package for SmartCart 2.0.
Provides Aiven Kafka configuration, producer, outbox publisher,
event contracts, consumer handlers, and Dead Letter Queue (DLQ).
"""
from app.kafka.schemas import SmartCartEvent
from app.kafka.producer import SmartCartKafkaProducer
from app.kafka.publisher import OutboxPublisher
from app.kafka.consumer import SmartCartKafkaConsumer
from app.kafka.dlq import DeadLetterQueueProducer

__all__ = [
    "SmartCartEvent",
    "SmartCartKafkaProducer",
    "OutboxPublisher",
    "SmartCartKafkaConsumer",
    "DeadLetterQueueProducer",
]
