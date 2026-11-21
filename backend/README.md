# SmartCart 2.0 – Backend Services & Kafka Workers

## Overview
This directory contains the FastAPI backend, SQLAlchemy transactional repositories, domain services, and standalone Apache Kafka workers for SmartCart 2.0.

---

## Directory Layout
```
backend/
├── app/
│   ├── api/             # FastAPI endpoints & route dependencies
│   ├── core/            # Security, password hashing, custom exceptions
│   ├── db/              # Database engine, session lifecycle, declarative base
│   ├── kafka/           # Kafka producer, consumer, outbox publisher, DLQ, schemas
│   ├── models/          # SQLAlchemy async ORM models
│   ├── opensearch/      # OpenSearch client, mappings, indexing, search, NLP query parser, sync
│   ├── repositories/    # Data access layer with row-level locking
│   ├── schemas/         # Pydantic request/response validation schemas
│   ├── services/        # Domain business logic & orchestration
│   ├── workers/         # Standalone daemon processes (outbox publisher, consumer, reindexer)
│   ├── config.py        # Central Pydantic settings & environment configuration
│   └── main.py          # FastAPI application root & middleware
├── certs/               # Aiven Kafka SSL certificates (ca.pem, service.cert, service.key)
├── tests/               # Unit, integration, and concurrency test suite
└── requirements.txt     # Python production and development dependencies
```

---

## Running the Services

### 1. Start FastAPI API Application
```powershell
uvicorn app.main:app --port 8000 --reload
```
Swagger UI will be available at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

### 2. Start Transactional Outbox Publisher Worker
Polls PostgreSQL `outbox_events` table using `FOR UPDATE SKIP LOCKED` and publishes to Aiven Kafka:
```powershell
python -m app.workers.outbox_publisher
```

### 3. Start Kafka Consumer Worker
Subscribes to `smartcart.orders`, `smartcart.inventory`, and `smartcart.products` topics with deduplication and syncs downstream to OpenSearch:
```powershell
python -m app.workers.consumer_worker
```

### 4. OpenSearch Reindexer CLI
Create versioned index, seed from PostgreSQL, or run zero-downtime reindexing:
```powershell
python -m app.workers.reindexer --status
python -m app.workers.reindexer --create-index
python -m app.workers.reindexer --bulk-index
python -m app.workers.reindexer --reindex-all
```

---

## Running Tests
Run the entire offline test suite:
```powershell
pytest tests/ -v --ignore=tests/test_database_integration.py --ignore=tests/test_repositories_integration.py --ignore=tests/test_services_integration.py
```

Run Kafka-specific integration tests:
```powershell
pytest tests/test_kafka_integration.py -v
```

Run Store Manager product and inventory management tests:
```powershell
pytest tests/test_store_manager.py -v
```

Run OpenSearch integration and search tests:
```powershell
pytest tests/test_opensearch.py -v
```

---

## Store Manager Product & Inventory Management (Phase 6.5)
- Store manager operations are available under `/api/v1/manager/`.
- Strict store isolation: `STORE_MANAGER` can only manage their `assigned_store_id`.
- Global catalog prices are protected: only `ADMIN` / `SUPER_ADMIN` can modify `price_paise`.
- Image upload to Cloudinary (JPEG, PNG, WEBP $\le$ 5MB) persists metadata inside `products.attributes["image"]`.
- Concurrency-safe stock adjustments (`INCREASE`, `DECREASE`, `SET`) enforce `qty_on_hand >= qty_reserved` and trigger automatic `inventory_audit_log` records via PostgreSQL triggers.
- Low-stock monitoring endpoint `/api/v1/manager/inventory/low-stock`.
- Detailed documentation available at `docs/STORE_MANAGEMENT.md`.

---

## OpenSearch Product Discovery & Search (Phase 7)
- Fast, typo-tolerant, store-aware product discovery backed by Aiven OpenSearch.
- **Architectural Single Source of Truth**: PostgreSQL remains the authoritative database; OpenSearch acts as a read-only search projection.
- **Composite Document ID**: `{product_id}_{store_id}` format completely isolates store inventory balances and prevents cross-store concurrency collisions.
- **Natural Language Query Parser**: Automatically detects price constraints (*"under ₹500"*, *"between ₹1000 and ₹3000"*), in-stock intent, and sort orders (*"cheapest"*, *"latest"*).
- **Multi-Field Boosting**: Query weights configured as `sku^4`, `name^3`, `brand^2`, `category^2`, and `description^1` with `AUTO:4,7` fuzziness and edge-ngram autocomplete.
- **Authoritative Asynchronous Sync**: Kafka consumer handles `product.*` and `inventory.*` events by fetching canonical current state directly from PostgreSQL, preventing stale update regressions.
- **Endpoints**: `/api/v1/search/products`, `/api/v1/search/suggestions`, `/api/v1/search/filters`, and `/api/v1/search/health` (Admin protected).
- Detailed documentation available at `docs/OPENSEARCH_INTEGRATION.md`.
