# SmartCart 2.0 – Apache Kafka Integration Plan (Phase 6)

## 1. Overview & Objective
This plan establishes production-ready Apache Kafka integration for SmartCart 2.0 using **Aiven Kafka**, seamlessly building upon the existing PostgreSQL transactional outbox foundation without introducing competing message brokers or duplicating completed functionality.

---

## 2. Existing Implementation Discovery

### 2.1 Database & Schema (`database/01_schema.sql`)
- `outbox_events`:
  - Columns: `id` (UUID), `aggregate_type` (TEXT), `aggregate_id` (TEXT), `event_type` (TEXT), `payload` (JSONB), `status` (`outbox_status`: `PENDING`, `PUBLISHED`, `FAILED`), `retry_count` (INT), `last_error` (TEXT), `created_at` (TIMESTAMPTZ), `published_at` (TIMESTAMPTZ).
  - Partial index `outbox_events_pending_idx` on `(created_at) WHERE status = 'PENDING'`.
  - Stored procedures `confirm_order()` and `cancel_order()` write `order.placed` and `order.cancelled` events inside atomic database transactions.
- `processed_events`:
  - Columns: `event_id` (TEXT), `consumer_group` (TEXT), `processed_at` (TIMESTAMPTZ).
  - Composite primary key `(event_id, consumer_group)` for idempotency deduplication across consumer groups.

### 2.2 Models & Repositories (`backend/app/models/outbox.py`, `backend/app/repositories/`)
- `OutboxEvent` & `ProcessedEvent` SQLAlchemy models mapped to PostgreSQL tables.
- `OutboxEventRepository`: `list_pending(limit)`, `list_by_aggregate(type, id)`.
- `ProcessedEventRepository`: `get_event(id, group)`, `is_processed(id, group)` using composite PK.

### 2.3 Services (`backend/app/services/outbox.py`)
- `OutboxService`:
  - `create_event(...)`: Enqueues outbox event in ambient transaction without premature commit.
  - `claim_pending_events(limit=50)`: Claims batch using `SELECT ... FOR UPDATE SKIP LOCKED` for concurrent multi-worker safety.
  - `acknowledge_published(event_id)`: Marks event as `PUBLISHED` with UTC timestamp after broker acknowledgement.
  - `record_publish_failure(event_id, error, max_retries=5)`: Sanitizes error message, increments retry count, transitions to `FAILED` upon retry exhaustion.
  - `record_event_processed(event_id, consumer_group)`: Idempotently registers processed events using `(event_id, consumer_group)`.

### 2.4 Existing Configuration (`backend/app/config.py`)
- Basic placeholders: `KAFKA_BOOTSTRAP_SERVERS`, `KAFKA_SECURITY_PROTOCOL` (`SSL`), PEM paths and Base64 certs.
- Existing topic name settings: `KAFKA_TOPIC_ORDER_PLACED`, `KAFKA_TOPIC_ORDER_CANCELLED`, `KAFKA_TOPIC_INVENTORY_CHANGED`, etc.

---

## 3. Missing Components to Implement

1. **Aiven Kafka Configuration & Security**:
   - SASL support (`SASL_SSL`, `SASL_PLAINTEXT`, mechanisms: `SCRAM-SHA-256`, `SCRAM-SHA-512`, `PLAIN`).
   - Consumer group configuration, timeouts, backoff, and SSL certificate materialization.
2. **Kafka Producer Service (`backend/app/kafka/producer.py`)**:
   - Connection lifecycle management with Aiven Kafka (SSL / SASL).
   - Structured JSON event publishing with message envelope (ID, type, aggregate, timestamp, version, payload).
   - Synchronous/asynchronous delivery confirmation (waiting for broker ACK).
3. **Transactional Outbox Publisher Worker (`backend/app/kafka/publisher.py`, `backend/app/workers/outbox_publisher.py`)**:
   - Background daemon loop polling and claiming pending events with `FOR UPDATE SKIP LOCKED`.
   - Dispatch to Kafka broker with at-least-once delivery guarantees.
   - Broker ACK $\rightarrow$ `acknowledge_published()`.
   - Delivery failure $\rightarrow$ `record_publish_failure()` and error handling.
4. **Event Topics & Pydantic Event Contracts (`backend/app/kafka/schemas.py`)**:
   - Canonical topics: `smartcart.orders`, `smartcart.inventory`, `smartcart.dlq`.
   - Contracts: `order.created` (alias `order.placed`), `order.cancelled`, `inventory.reservation.created`, `inventory.reservation.expired`, `inventory.stock.updated`.
5. **Kafka Consumer Infrastructure (`backend/app/kafka/consumer.py`, `backend/app/workers/consumer_worker.py`)**:
   - Topic subscription, deserialization, payload validation.
   - Idempotent processing with `ProcessedEventService`.
   - Explicit manual offset commit after database transaction completion.
   - Graceful shutdown handling.
6. **Retry Mechanism & Dead Letter Queue (DLQ) (`backend/app/kafka/dlq.py`)**:
   - Exponential backoff with jitter for transient broker errors.
   - Distinction between retryable (network, timeout) and non-retryable (poison pill, validation) errors.
   - DLQ envelope preserving original event ID, topic, partition, offset, error trace, and failure timestamp.
7. **Independent Worker Scripts**:
   - Standalone CLI execution for outbox publisher and consumer workers, completely decoupled from FastAPI request-response cycles.

---

## 4. Proposed Architecture & Event Flow

```
+---------------------------------------------------------------------------------------+
|                                FASTAPI / DATABASE TIER                                |
|                                                                                       |
|  [ Checkout / Cancel Order ]                                                         |
|         |                                                                             |
|         v                                                                             |
|  BEGIN TRANSACTION                                                                    |
|    INSERT INTO orders ...                                                             |
|    UPDATE inventory ...                                                               |
|    INSERT INTO outbox_events (status='PENDING', event_type='order.placed', ...)       |
|  COMMIT TRANSACTION (Atomic dual-write prevention)                                    |
+---------------------------------------------------------------------------------------+
                                        | (Poll via FOR UPDATE SKIP LOCKED)
                                        v
+---------------------------------------------------------------------------------------+
|                               OUTBOX PUBLISHER WORKER                                 |
|                                                                                       |
|  1. Claim batch of PENDING events (outbox_repo.claim_pending_events)                   |
|  2. Transform to canonical SmartCartEvent envelope                                    |
|  3. Produce to Aiven Kafka topic (e.g., smartcart.orders)                              |
|  4. On Broker ACK: Mark outbox event status = 'PUBLISHED'                             |
|  5. On Error: Record retry attempt, or route to DLQ if max retries exceeded           |
+---------------------------------------------------------------------------------------+
                                        | (Produce message)
                                        v
+---------------------------------------------------------------------------------------+
|                                  AIVEN KAFKA CLUSTER                                  |
|                                                                                       |
|     [ smartcart.orders ]            [ smartcart.inventory ]          [ smartcart.dlq ]|
+---------------------------------------------------------------------------------------+
                                        | (Subscribe with consumer group)
                                        v
+---------------------------------------------------------------------------------------+
|                                KAFKA CONSUMER WORKER                                  |
|                                                                                       |
|  1. Poll message from Kafka topic                                                     |
|  2. Validate JSON envelope against Pydantic schema                                    |
|  3. Deduplication Check: ProcessedEventRepository.is_processed(event_id, group)       |
|     - If already processed: Log info and commit offset immediately.                   |
|  4. Execute Domain Event Handler (e.g., Analytics / Notifications / Search Projections)|
|  5. In Same DB Transaction:                                                           |
|     - Apply domain mutation (if applicable)                                           |
|     - Record ProcessedEvent(event_id, consumer_group)                                 |
|  6. Commit Kafka offset ONLY after DB transaction commits                             |
|  7. On Unrecoverable Failure: Publish to smartcart.dlq, commit offset to unblock queue |
+---------------------------------------------------------------------------------------+
```

---

## 5. Files to Create or Modify

### A. Configuration & Environment
- **`backend/app/config.py`**: Add SASL configuration (`KAFKA_SASL_USERNAME`, `KAFKA_SASL_PASSWORD`, `KAFKA_SASL_MECHANISM`), consumer settings, timeouts, and topic naming defaults.
- **`.env.example`**: Document all Kafka environment variables with placeholders.

### B. Kafka Domain Layer (`backend/app/kafka/`)
- `backend/app/kafka/__init__.py`: Package export.
- `backend/app/kafka/config.py`: Kafka connection builder (SSL context resolution from files or base64, SASL configuration).
- `backend/app/kafka/schemas.py`: Canonical event envelope (`SmartCartKafkaEvent`) and event payload contracts (`OrderCreatedPayload`, `OrderCancelledPayload`, `ReservationCreatedPayload`, `ReservationExpiredPayload`, `StockUpdatedPayload`).
- `backend/app/kafka/producer.py`: Production-ready `SmartCartKafkaProducer` with broker ACK verification, error handling, and clean teardown.
- `backend/app/kafka/publisher.py`: `OutboxPublisher` orchestrating `OutboxService` $\leftrightarrow$ `SmartCartKafkaProducer`.
- `backend/app/kafka/consumer.py`: `SmartCartKafkaConsumer` with subscription, batch polling, deduplication, handler dispatch, and manual commit.
- `backend/app/kafka/dlq.py`: `DeadLetterQueueProducer` with error diagnostic encapsulation and recovery documentation.

### C. Workers (`backend/app/workers/`)
- `backend/app/workers/__init__.py`: Package export.
- `backend/app/workers/outbox_publisher.py`: Standalone CLI worker daemon for publishing outbox events.
- `backend/app/workers/consumer_worker.py`: Standalone CLI worker daemon for consuming events.

### D. Documentation
- `docs/KAFKA_INTEGRATION_PLAN.md`: (This document).
- `docs/KAFKA_INTEGRATION.md`: Full architectural and operational reference.
- `backend/README.md`: Updated startup instructions for workers.

---

## 6. Testing Strategy

1. **Unit Tests (100% Offline with Mocks)**:
   - Kafka configuration resolution (SSL cert extraction, SASL properties).
   - Event envelope serialization, validation, and Pydantic schema validation.
   - Producer publishing and delivery callback verification.
   - Outbox event claiming (`FOR UPDATE SKIP LOCKED`) and state transitions (`PENDING` $\rightarrow$ `PUBLISHED`).
   - Failure retry recording and transition to `FAILED`.
   - Consumer message deduplication via `ProcessedEvent`.
   - Consumer manual offset commit verification (only after DB commit).
   - DLQ message structure and emission on failure.
   - Graceful shutdown signal handling.
2. **Optional Live Integration Tests**:
   - Conditional integration test running when `KAFKA_BOOTSTRAP_SERVERS` is set and accessible.
   - Validates live Aiven Kafka handshake, topic production, and consumption.
