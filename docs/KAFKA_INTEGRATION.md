# SmartCart 2.0 – Apache Kafka Integration Specification (Phase 6)

## 1. Overview
SmartCart 2.0 uses **Aiven Apache Kafka** as its enterprise-grade asynchronous event backbone. The architecture decouples synchronous REST requests (checkout, inventory mutations) from asynchronous consumers (analytics, notification, search index projections).

To guarantee consistency and eliminate dual-write vulnerabilities between PostgreSQL and Apache Kafka, SmartCart 2.0 implements the **Transactional Outbox Pattern** with **At-Least-Once Delivery** and **Idempotent Consumer Deduplication**.

---

## 2. Architectural Design

```
+---------------------------------------------------------------------------------------+
|                               FASTAPI / DATABASE LAYER                                |
|                                                                                       |
|  POST /api/v1/checkout                                                                |
|         |                                                                             |
|         v                                                                             |
|  BEGIN TRANSACTION                                                                    |
|    1. Deduct stock & create Order (CONFIRMED)                                         |
|    2. INSERT INTO outbox_events (status='PENDING', event_type='order.placed', ...)    |
|  COMMIT TRANSACTION                                                                   |
+---------------------------------------------------------------------------------------+
                                        |
                   (Asynchronous poll via FOR UPDATE SKIP LOCKED)
                                        v
+---------------------------------------------------------------------------------------+
|                               OUTBOX PUBLISHER WORKER                                 |
|                                                                                       |
|  1. Claim batch of PENDING records via OutboxService.claim_pending_events()           |
|  2. Convert to SmartCartEvent envelope with ISO-8601 timestamp                        |
|  3. Dispatch to canonical Kafka topic (smartcart.orders)                              |
|  4. Wait for broker acknowledgement (acks='all')                                      |
|  5. On ACK: Mark outbox_events.status = 'PUBLISHED'                                   |
|  6. On Failure: Increment retry count; route to DLQ if max retries exceeded           |
+---------------------------------------------------------------------------------------+
                                        | (Produce message)
                                        v
+---------------------------------------------------------------------------------------+
|                                  AIVEN KAFKA CLUSTER                                  |
|                                                                                       |
|      Topic: smartcart.orders         Topic: smartcart.inventory      Topic: smartcart.dlq
+---------------------------------------------------------------------------------------+
                                        | (Consume message)
                                        v
+---------------------------------------------------------------------------------------+
|                                KAFKA CONSUMER WORKER                                  |
|                                                                                       |
|  1. Poll record batch (enable_auto_commit=False)                                      |
|  2. Validate SmartCartEvent envelope and payload schema                               |
|  3. Check deduplication: ProcessedEventRepository.is_processed(event_id, group)       |
|     - If already processed: Commit offset immediately and skip execution              |
|  4. Invoke registered domain event handler inside DB transaction                      |
|  5. In same DB transaction: INSERT INTO processed_events (event_id, consumer_group)   |
|  6. Commit DB transaction                                                             |
|  7. Commit Kafka offset ONLY after DB transaction commits                             |
|  8. On unrecoverable error: Route to smartcart.dlq and advance offset                 |
+---------------------------------------------------------------------------------------+
```

---

## 3. Topics & Event Contracts

### 3.1 Canonical Topics
| Topic Name | Purpose | Partition Key |
| :--- | :--- | :--- |
| `smartcart.orders` | Order creation, confirmation, and cancellations | `aggregate_id` (`order_id`) |
| `smartcart.inventory` | Stock holds, releases, and replenishment events | `aggregate_id` (`store_id:product_id`) |
| `smartcart.dlq` | Dead Letter Queue capturing failed / unprocessable messages | `original_event_id` |

### 3.2 Event Envelope (`SmartCartEvent`)
Every message adheres to the canonical JSON envelope:
```json
{
  "event_id": "c1f7b055-635d-4f6c-84cb-35919e1ef002",
  "event_type": "order.placed",
  "aggregate_type": "order",
  "aggregate_id": "a9d3c5f4-3079-4d8e-9023-e578fa2163b7",
  "timestamp": "2026-11-21T22:30:00.000000+00:00",
  "schema_version": "1.0",
  "payload": {
    "order_id": "a9d3c5f4-3079-4d8e-9023-e578fa2163b7",
    "order_number": "ORD-20261121-001",
    "customer_id": "893c5f4a-3079-4d8e-9023-e578fa2163b1",
    "store_id": "11111111-1111-1111-1111-111111111111",
    "total_paise": 299900,
    "confirmed_at": "2026-11-21T22:30:00.000000+00:00",
    "items": [
      {
        "product_id": "22222222-2222-2222-2222-222222222222",
        "qty": 1,
        "unit_price_paise": 299900
      }
    ]
  }
}
```

### 3.3 Event Types
- `order.placed` / `order.created`: Emitted when an order is confirmed upon checkout.
- `order.cancelled`: Emitted when an order is cancelled and stock released.
- `inventory.reservation.created`: Emitted when a 10-minute cart reservation hold is placed.
- `inventory.reservation.expired`: Emitted when an overdue reservation is reclaimed.
- `inventory.stock.updated`: Emitted when physical on-hand or available balance changes.

---

## 4. Aiven Kafka Security & Configuration

SmartCart 2.0 supports two authentication models for Aiven Kafka:

### A. SSL / mTLS Authentication (Certificates)
```env
KAFKA_BOOTSTRAP_SERVERS=kafka-service-hackhive-cit.aivencloud.com:12345
KAFKA_SECURITY_PROTOCOL=SSL
KAFKA_SSL_CA_PEM_PATH=./backend/certs/ca.pem
KAFKA_SSL_CERT_PEM_PATH=./backend/certs/service.cert
KAFKA_SSL_KEY_PEM_PATH=./backend/certs/service.key
```
*Cloud Deployment (e.g., Render/Containers)*: Alternatively supply base64 strings:
`KAFKA_SSL_CA_B64`, `KAFKA_SSL_CERT_B64`, `KAFKA_SSL_KEY_B64`.

### B. SASL_SSL Authentication (SCRAM / PLAIN)
```env
KAFKA_BOOTSTRAP_SERVERS=kafka-service-hackhive-cit.aivencloud.com:12345
KAFKA_SECURITY_PROTOCOL=SASL_SSL
KAFKA_SASL_MECHANISM=SCRAM-SHA-256
KAFKA_SASL_USERNAME=avnadmin
KAFKA_SASL_PASSWORD=your-secret-password
```

---

## 5. Worker Startup Commands

Workers run as standalone asynchronous background daemons, independent of the FastAPI web application.

### 1. Start FastAPI API Application
```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --port 8000 --reload
```

### 2. Start Transactional Outbox Publisher Worker
```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m app.workers.outbox_publisher
```

### 3. Start Kafka Consumer Worker
```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m app.workers.consumer_worker
```

All workers listen for `SIGINT` (Ctrl+C) and `SIGTERM` signals and execute clean shutdowns, flushing in-flight records and committing consumer offsets.

---

## 6. Reliability & Failure Handling

### 6.1 Transactional Outbox Guarantees
- **Zero Dual-Write Inconsistency**: Outbox events are written into `outbox_events` in the exact same database transaction as the business order/reservation.
- **Concurrent Polling**: Multiple instances of `outbox_publisher` can run concurrently without collision by using `SELECT ... FOR UPDATE SKIP LOCKED`.
- **Strict ACK Ordering**: Status is transitioned to `PUBLISHED` only after the Kafka broker returns an acknowledgement (`acks='all'`).

### 6.2 Consumer Idempotency Deduplication
- Every consumer maintains an atomic deduplication check against the `processed_events` table using composite primary key `(event_id, consumer_group)`.
- If a duplicate message is received due to network retransmission or worker restart, the consumer detects the entry, skips business logic, and commits the offset immediately.

### 6.3 Retry Policy & Dead Letter Queue (DLQ)
- **Retry Mechanism**: Transient failures (network timeout, broker unavailability) use exponential backoff:
  $$\text{duration} = \min(\text{max\_backoff}, \text{base\_backoff} \times 2^{\text{attempt}-1}) \pm \text{jitter}$$
- **Non-Retryable Errors**: Deserialization failures, corrupt JSON, or schema validation violations bypass retry loops and route directly to `smartcart.dlq`.
- **DLQ Replay**: Failed events retain the complete original payload, topic, partition, offset, failure timestamp, and error stack trace in `smartcart.dlq`. Operators can inspect and replay these events using standard consumer tooling.

---

## 7. Testing Strategy
- **Offline Automated Tests**: The test suite uses mocked Kafka clients and runs 100% offline without requiring external network connectivity or cloud credentials:
  ```powershell
  pytest backend/tests/test_kafka_integration.py -v
  ```
- **Optional Live Integration Test**: If `KAFKA_BOOTSTRAP_SERVERS` is set in the environment, the suite runs `test_optional_live_aiven_kafka_integration` to verify live broker handshake and end-to-end messaging.
