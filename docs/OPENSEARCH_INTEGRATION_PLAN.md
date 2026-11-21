# SmartCart 2.0 – Phase 7: OpenSearch Integration Plan
## Production-Oriented Product Search & Discovery Architecture

---

## 1. Executive Summary & Objective

SmartCart 2.0 is an intelligent multi-store e-commerce platform built for high-concurrency retail across India. Customers need to find products quickly even when they make spelling mistakes, enter partial names, or type conversational natural-language queries (e.g. *"Show wireless headphones under 3000"*).

- **Aiven PostgreSQL** remains the single authoritative source of truth for catalogue products, pricing, and store inventory.
- **Aiven OpenSearch** functions as a read-optimized, typo-tolerant search and discovery index.
- **Aiven Apache Kafka** serves as the asynchronous event-driven synchronization backbone, streaming product and inventory mutations from PostgreSQL outbox events into OpenSearch.

This plan details the complete architectural inspection and implementation strategy for Phase 7 while preserving all completed functionality from Phases 0–6.5.

---

## 2. Current Architecture & Existing Components Inspection

### 2.1 Database Entities & Authoritative Source of Truth
An in-depth inspection of PostgreSQL models and database scripts confirms:

1. **`Product` ([backend/app/models/product.py](file:///c:/Users/msche/Desktop/smartcart/backend/app/models/product.py))**:
   - `id`: UUID Primary Key
   - `sku`: String (unique index)
   - `name`: String
   - `description`: String (nullable)
   - `brand`: String (nullable, indexed)
   - `category`: String (nullable, indexed)
   - `price_paise`: BigInteger (global catalog price in Indian paise, $\ge 0$)
   - `attributes`: JSONB (GIN indexed, stores Cloudinary image metadata in `attributes["image"]`)
   - `is_active`: Boolean (soft deletion indicator)
   - `created_at`, `updated_at`: Timestamps with timezone
2. **`Inventory` ([backend/app/models/inventory.py](file:///c:/Users/msche/Desktop/smartcart/backend/app/models/inventory.py))**:
   - Composite Primary Key: `(store_id, product_id)`
   - `qty_on_hand`: Integer ($\ge 0$)
   - `qty_reserved`: Integer ($\ge 0$)
   - `low_stock_threshold`: Integer (default 5, $\ge 0$)
   - Derived Available Stock: $\text{qty\_available} = \max(0, \text{qty\_on\_hand} - \text{qty\_reserved})$
   - `updated_at`: Timestamp with timezone
3. **`Store` ([backend/app/models/store.py](file:///c:/Users/msche/Desktop/smartcart/backend/app/models/store.py))**:
   - `id`: UUID Primary Key
   - `code`: String (unique)
   - `name`: String
   - `city`: String, `state`: String (indexed)
   - `is_active`: Boolean
4. **`outbox_events` & `processed_events` ([backend/app/models/outbox.py](file:///c:/Users/msche/Desktop/smartcart/backend/app/models/outbox.py))**:
   - Outbox table captures domain events written in the same database transaction as orders, products, and inventory adjustments.
   - `processed_events` table tracks `(event_id, consumer_group)` for exactly-once consumer deduplication.

### 2.2 Phase 6.5 Outbox Events Inspection
A rigorous code audit of [StoreManagerService](file:///c:/Users/msche/Desktop/smartcart/backend/app/services/store_manager.py) confirmed the exact event types, aggregate keys, and payloads currently generated:

| Event Type | Aggregate Type | Aggregate ID | Payload Schema |
|---|---|---|---|
| `product.created` | `product` | `product_id` | `{"product_id", "sku", "name", "brand", "category", "price_paise", "store_id", "initial_stock"}` |
| `product.updated` | `product` | `product_id` | `{"product_id", "sku", "name", "price_paise", "is_active", "updated_at"}` |
| `product.deactivated` | `product` | `product_id` | `{"product_id", "sku"}` |
| `product.image.updated`| `product` | `product_id` | `{"product_id", "image_url", "public_id"}` |
| `inventory.stock.updated`| `inventory` | `"{store_id}:{product_id}"` | `{"store_id", "product_id", "old_on_hand", "new_on_hand", "qty_reserved", "qty_available", "adjustment_type", "reason", "updated_at"}` |
| `inventory.low_stock` | `inventory` | `"{store_id}:{product_id}"` | `{"store_id", "product_id", "product_name", "qty_available", "threshold", "alert_at"}` |

### 2.3 Existing Kafka Infrastructure (Phase 6)
- **`SmartCartKafkaProducer`**: Asynchronous producer configured with `acks='all'`, retries, exponential backoff, and SSL/SASL authentication.
- **`SmartCartKafkaConsumer`**: Modular consumer supporting manual commit offsets, event envelope validation (`SmartCartEvent`), and PostgreSQL `processed_events` deduplication.
- **`DeadLetterQueueProducer`**: Unprocessable or repeatedly failing messages are captured to `smartcart.dlq`.
- **`OutboxPublisher`**: Background worker polling `outbox_events` using `FOR UPDATE SKIP LOCKED` and dispatching to Kafka.
- **Topic Routing ([schemas.py](file:///c:/Users/msche/Desktop/smartcart/backend/app/kafka/schemas.py))**:
  - `product.*` $\rightarrow$ `smartcart.products`
  - `inventory.*` $\rightarrow$ `smartcart.inventory`
  - `order.*` $\rightarrow$ `smartcart.orders`

---

## 3. Missing Components to Implement in Phase 7

1. **OpenSearch Connection & Client Module (`backend/app/opensearch/client.py`)**:
   - Connection lifecycle manager supporting HTTP Basic Auth, TLS certificate verification, connection pooling, retries, and clean disposal.
2. **Product Search Index Mapping (`backend/app/opensearch/mappings.py`)**:
   - Versioned index schema (`smartcart_products_v1`) managed via canonical alias (`smartcart_products`).
   - Custom analyzers: edge n-gram autocomplete analyzer, text search analyzer with lowercase/asciifolding, and exact keyword normalizers.
3. **Product Indexing Service (`backend/app/opensearch/indexing.py`)**:
   - High-throughput indexing service: single document indexing, partial updates, deactivations, batch bulk indexing (`helpers.bulk`), index creation, alias switching, and cluster health monitoring.
4. **Kafka-to-OpenSearch Synchronization Service (`backend/app/opensearch/sync.py`)**:
   - Consumer handler subscribing to `smartcart.products` and `smartcart.inventory`.
   - Authoritative PostgreSQL snapshot lookups to prevent stale writes.
   - Versioning / update timestamp safeguards preventing out-of-order event overwrites.
   - Idempotent deduplication via `processed_events`.
   - DLQ error routing on persistent indexing failures.
5. **Product Search Service (`backend/app/opensearch/search.py`)**:
   - Multi-field boosted search (`name^3`, `sku^4`, `brand^2`, `category^2`, `description^1`).
   - Typo-tolerant controlled fuzzy matching (`fuzziness="AUTO:4,7"`, prefix length 2).
   - Fast autocomplete prefix suggestions.
   - Store availability, category, brand, and price range filters.
   - Relevance, price, and newest sorting with cursor/offset pagination.
6. **Natural Language Query Parser (`backend/app/opensearch/nlp.py`)**:
   - Deterministic rule-based NLP extraction for budgets ("under 3000", "between 10000 and 30000"), categories, brands, sort hints ("affordable", "premium"), and availability constraints without external LLM dependencies.
7. **FastAPI Search Router (`backend/app/api/v1/endpoints/search.py`)**:
   - `GET /api/v1/search/products`: Core search with typo-tolerance, NLP, and filters.
   - `GET /api/v1/search/suggestions`: Low-latency autocomplete endpoint.
   - `GET /api/v1/search/filters`: Aggregations endpoint returning available categories, brands, price stats.
   - `GET /api/v1/search/health`: Diagnostic health check returning cluster state (green/yellow/red).
8. **Initial Indexing & Reindex Management Utility (`backend/app/workers/reindexer.py`)**:
   - Standalone CLI command for zero-downtime index migration, bulk population from PostgreSQL, and alias swapping.

---

## 4. OpenSearch Index Design (Store-Aware Product Discovery)

### 4.1 Multi-Store Indexing Architecture
In SmartCart 2.0, customer shopping, cart management, and inventory reservations are strictly store-scoped. Inventory levels differ across physical stores.

#### Document Architecture: Store-Product Document Model
To ensure that store-specific inventory is represented independently without race conditions or contention:
- Each index document represents a **Store-Product Pair**:
  $$\text{Document ID} = \texttt{\{product\_id\}\_\{store\_id\}}$$
- For products not yet allocated to a specific store, a catalog document with $\texttt{\{product\_id\}\_global}$ is maintained.

**Key Advantages:**
1. **Zero Contention**: A stock adjustment in Store A only updates document `{product_id}_{store_a_id}`, without locking, contending with, or reindexing Store B's documents.
2. **Simple, Fast Filtering**: Filtering by store is a direct, indexed term filter on `store_id`.
3. **Exact Database Parity**: Directly mirrors PostgreSQL composite primary key `(store_id, product_id)`.
4. **Independent Stock Values**: Stock quantities (`qty_on_hand`, `qty_reserved`, `qty_available`, `is_in_stock`) are physically isolated per store document—guaranteeing no cross-store stock mixing.

### 4.2 Document Schema Definition
```json
{
  "product_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "store_id": "e500404a-e2f1-443a-a2b2-9ed77d70187c",
  "sku": "ELEC-APPL-IPH16",
  "name": "Apple iPhone 16",
  "description": "Latest flagship smartphone with A18 Bionic and camera control.",
  "brand": "Apple",
  "category": "Electronics",
  "price_paise": 7990000,
  "image_url": "https://res.cloudinary.com/smartcart/image/upload/v1/smartcart/products/iphone16.jpg",
  "is_active": true,
  "qty_on_hand": 25,
  "qty_reserved": 3,
  "qty_available": 22,
  "is_in_stock": true,
  "low_stock_threshold": 5,
  "created_at": "2026-11-21T18:00:00Z",
  "updated_at": "2026-11-21T18:30:00Z"
}
```

### 4.3 Custom Analyzers & Tokenizers
The index settings define specialized analyzers:

1. **`autocomplete_analyzer` (Index Time)**:
   - Tokenizer: `standard`
   - Token Filters: `lowercase`, `asciifolding`, `edge_ngram_filter` (`min_gram: 2`, `max_gram: 15`).
   - Purpose: Generates prefix tokens (`"ip"`, `"iph"`, `"ipho"`, `"iphon"`, `"iphone"`) for instant autocomplete suggestions as the user types.
2. **`autocomplete_search_analyzer` (Search Time)**:
   - Tokenizer: `standard`
   - Token Filters: `lowercase`, `asciifolding`.
   - Purpose: Searches prefix queries against generated n-grams without re-splitting search terms.
3. **`text_search_analyzer`**:
   - Tokenizer: `standard`
   - Token Filters: `lowercase`, `asciifolding`.
   - Purpose: Clean, case-insensitive, diacritic-folded text matching across product names, descriptions, categories, and brands.
4. **`lowercase_normalizer`**:
   - For keyword fields (`sku`, `brand`, `category`) to ensure case-insensitive exact and facet matching.

---

## 5. Kafka Synchronization Design (Transactional Outbox to OpenSearch)

```
[ PostgreSQL ] (Authoritative Source of Truth)
      |
      | 1. Product/Inventory changes committed in PostgreSQL transaction
      v
[ outbox_events ]
      |
      | 2. OutboxPublisher claims pending batch via FOR UPDATE SKIP LOCKED
      v
[ Aiven Apache Kafka ]
      ├── Topic: smartcart.products  (product.created, product.updated, product.deactivated, product.image.updated)
      └── Topic: smartcart.inventory (inventory.stock.updated, inventory.low_stock)
      |
      | 3. SmartCartKafkaConsumer polls messages
      v
[ OpenSearch Sync Handler ]
      ├── 4. Check processed_events table: If already processed -> skip (Idempotency)
      ├── 5. Query PostgreSQL for authoritative, current Product & Inventory state
      ├── 6. Compare event updated_at timestamp vs existing document updated_at
      │      (Drop out-of-order stale events)
      ├── 7. Execute OpenSearch index/update/delete operation
      └── 8. Record event in processed_events table
      |
      | 9. Commit Kafka offset ONLY after OpenSearch write & DB record succeed
      v
[ OpenSearch Index ] (Alias: smartcart_products -> smartcart_products_v1)
```

### 5.1 Reliability & Concurrency Rules
1. **Authoritative Snapshot Retrieval**: When handling an event, the worker fetches the current database record from PostgreSQL. This ensures that even if an event payload was delayed or partial, the OpenSearch index always reflects verified database truth.
2. **Timestamp Version Guard**: Every document carries `updated_at`. If an incoming event has a timestamp strictly older than the document's current `updated_at`, it is discarded to prevent out-of-order writes.
3. **Deduplication**: Uses PostgreSQL `processed_events` table with unique constraint `(event_id, consumer_group)` to guarantee duplicate Kafka redeliveries produce zero duplicate side effects.
4. **Retry & DLQ Routing**: Transient connection errors are retried up to 5 times with exponential backoff. Poison-pill or malformed events are routed to `smartcart.dlq`.
5. **No Premature Offset Commits**: Offsets are committed to Kafka **only after** both the OpenSearch index write and the PostgreSQL deduplication record have completed successfully.

---

## 6. Search Service & Typo-Tolerant Query Strategy

### 6.1 Multi-Field Boosting & Scoring
Queries are executed with weighted field importance:
- `sku^4`: Exact or prefix SKU matches receive the highest relevance score.
- `name^3`: Product name matches receive high relevance score.
- `name.suggest^2`: Prefix autocomplete matches.
- `brand^2`: Brand matches.
- `category^2`: Category matches.
- `description^1`: General body text matches.

### 6.2 Controlled Typo-Tolerant Fuzzy Search
Typo tolerance is configured with careful bounds to avoid irrelevant noise:
- `fuzziness="AUTO:4,7"`:
  - 0–3 characters: Exact matching only (no typos allowed for very short words).
  - 4–6 characters: Maximum 1 edit distance allowed (`iphnoe` $\rightarrow$ `iPhone`).
  - 7+ characters: Maximum 2 edit distances allowed (`wireles heaphone` $\rightarrow$ `Wireless Headphone`).
- `prefix_length=2`: First 2 characters must match exactly to prevent phonetic drifting.
- `max_expansions=50`: Caps term expansions to preserve sub-50ms response latencies.

### 6.3 Structured Filtering
- **Store Isolation**: `{"term": {"store_id": store_id}}` ensures customers only view items available in their selected store.
- **Active Status**: `{"term": {"is_active": true}}` filters out soft-deleted products.
- **Stock Filter**: `{"term": {"is_in_stock": true}}` (when `in_stock=true` is requested).
- **Price Range**: `{"range": {"price_paise": {"gte": min_price, "lte": max_price}}}`.
- **Category & Brand**: Exact term filtering on keyword subfields.

### 6.4 Sorting & Pagination
- **Relevance**: `_score` descending (default).
- **Price**: `price_paise: asc` or `price_paise: desc`.
- **Newest**: `created_at: desc`.
- **Pagination**: Zero-based `from = (page - 1) * page_size`, `size = page_size` (max 100).

---

## 7. Natural-Language Query Strategy (Rule-Based, Zero-LLM)

Customers frequently search using natural language phrases. A deterministic, rule-based NLP parser (`NaturalLanguageSearchParser`) parses constraints without external API dependencies or latency costs:

### 7.1 Extraction Rules
1. **Budget / Price Constraints**:
   - `under|below|less than|up to|max\s*:?\s*(?:rs\.?|inr|₹)?\s*(\d+)` $\rightarrow$ `max_price = int(val) * 100` (paise)
   - `above|over|more than|min\s*:?\s*(?:rs\.?|inr|₹)?\s*(\d+)` $\rightarrow$ `min_price = int(val) * 100` (paise)
   - `between\s*(?:rs\.?|inr|₹)?\s*(\d+)\s*(?:and|to|-)\s*(?:rs\.?|inr|₹)?\s*(\d+)` $\rightarrow$ `min_price`, `max_price`
2. **Availability Intent**:
   - `in stock|available|ready to ship|in store` $\rightarrow$ `in_stock = True`
3. **Sort Intent**:
   - `cheap|cheapest|affordable|budget|low price` $\rightarrow$ `sort_by = "price_asc"`
   - `expensive|premium|costly|high end` $\rightarrow$ `sort_by = "price_desc"`
   - `new|newest|latest|recent` $\rightarrow$ `sort_by = "newest"`
4. **Category & Brand Resolution**:
   - Dictionary lookup against canonical catalogue categories and brands.
   - Extracted terms are moved into structured filters, preventing them from diluting free-text search scoring.
5. **Residual Keywords**:
   - Conversational stop words (`show`, `find`, `get`, `me`, `products`, `items`, `in`, `my`, `store`, `for`) and extracted constraint tokens are stripped.
   - Residual clean keywords are passed to the multi-field fuzzy query.
6. **Graceful Fallback**:
   - If no structured intent is detected, the raw user query is forwarded directly to the standard OpenSearch fuzzy query.

---

## 8. FastAPI Search Endpoints Specification

### 8.1 Routes (`/api/v1/search/*`)
1. **`GET /api/v1/search/products`**:
   - Parameters: `q` (string), `store_id` (UUID), `category` (string), `brand` (string), `min_price` (int), `max_price` (int), `in_stock` (bool), `sort_by` (string), `page` (int, default 1), `page_size` (int, default 20), `nlp` (bool, default true).
   - Response:
     ```json
     {
       "query": "wireless headphones under 3000",
       "clean_query": "wireless headphones",
       "total": 12,
       "page": 1,
       "page_size": 20,
       "total_pages": 1,
       "applied_filters": {
         "store_id": "e500404a-e2f1-443a-a2b2-9ed77d70187c",
         "max_price": 300000,
         "in_stock": true
       },
       "took_ms": 14,
       "products": [ ... ]
     }
     ```
2. **`GET /api/v1/search/suggestions`**:
   - Parameters: `q` (string, min 2 chars), `store_id` (UUID optional), `limit` (int, default 10).
   - Response: Autocomplete suggestions list with title, category, and brand.
3. **`GET /api/v1/search/filters`**:
   - Parameters: `store_id` (UUID optional), `category` (string optional).
   - Response: Available categories, brands, price min/max/average aggregations.
4. **`GET /api/v1/search/health`**:
   - Returns OpenSearch cluster status (`green`/`yellow`), alias existence, document count, and response time.
   - If OpenSearch is down, returns controlled **HTTP 503 Service Unavailable** with standardized error envelope.

---

## 9. Initial Indexing & Zero-Downtime Reindexing

### 9.1 Management Commands
A dedicated utility module [backend/app/workers/reindexer.py](file:///c:/Users/msche/Desktop/smartcart/backend/app/workers/reindexer.py) provides CLI commands:
```powershell
# Create index with version smartcart_products_v1 and configure alias
python -m app.workers.reindexer --create-index

# Initial bulk indexing from PostgreSQL database in chunks of 500
python -m app.workers.reindexer --bulk-index

# Zero-downtime full reindex to new version (v2) and atomic alias swap
python -m app.workers.reindexer --reindex-all --target-version v2

# Check index document count and alias status
python -m app.workers.reindexer --status
```

---

## 10. Comprehensive Testing Strategy (26 Scenarios)

| # | Test Category | Scenario | Expected Behavior |
|---|---|---|---|
| 1 | Configuration | OpenSearch client builder with SSL/TLS and auth | Correct host, port, credentials formatted |
| 2 | Client Lifecycle | Client connection, ping, and close | Successful cluster connection & cleanup |
| 3 | Index Creation | Create versioned index with analyzers | Index exists with autocomplete & search analyzers |
| 4 | Index Mappings | Mapping verification | Fields correctly mapped (keyword, text, long, date) |
| 5 | Serialization | PostgreSQL model to OpenSearch document | Correct store-product document serialization |
| 6 | Single Indexing | Index single store product | Document retrievable by ID |
| 7 | Product Update | Update metadata in OpenSearch document | Field values updated |
| 8 | Product Deactivation | Deactivate product in OpenSearch | `is_active` set to false, excluded from customer queries |
| 9 | Inventory Indexing | Update stock for specific store | Store stock updated without affecting other stores |
| 10 | Bulk Indexing | Batch indexing 500 records via `helpers.bulk` | All documents indexed efficiently |
| 11 | Basic Search | Multi-field search across name, sku, description | Relevant products returned |
| 12 | Typo Tolerance | Search with misspelling (`iphnoe`, `samsng`, `lapotp`) | Correct products matched with relevance score |
| 13 | Autocomplete | Prefix query (`"hea"`, `"sam"`) | Fast suggestions returned from `name.suggest` |
| 14 | Price Filtering | Filter with `min_price` and `max_price` | Only products in price range returned |
| 15 | Category Filtering | Filter by category | Only products in category returned |
| 16 | Store Filtering | Filter by `store_id` | Only products belonging to specified store returned |
| 17 | Availability Filter | Filter by `in_stock=true` | Only products with `qty_available > 0` returned |
| 18 | Sorting | Sort by price ascending, descending, newest | Correctly ordered result sets |
| 19 | Pagination | Page and page size offsets | Correct page slices and `total_pages` calculation |
| 20 | NLP Parser | Parse "Show headphones under 3000" | Extracts `max_price=300000`, `clean_query="headphones"` |
| 21 | Kafka Event Sync | Process `product.created` event | New OpenSearch document created |
| 22 | Duplicate Event | Re-deliver same event ID | Handled idempotently via `processed_events` |
| 23 | Stale Event | Event with older `updated_at` | Stale update ignored |
| 24 | Indexing Failure | OpenSearch error during sync | Retried with exponential backoff |
| 25 | DLQ Routing | Repeatedly failing event | Message published to `smartcart.dlq` |
| 26 | Cluster Unavailable | OpenSearch down / connection refused | Controlled HTTP 503 response returned |

---

## 11. Files to Create and Modify

### Files to Create:
1. `backend/app/opensearch/config.py`: OpenSearch connection configuration helper.
2. `backend/app/opensearch/client.py`: Thread-safe OpenSearch client factory and lifecycle manager.
3. `backend/app/opensearch/mappings.py`: Index mappings, settings, and analyzer definitions.
4. `backend/app/opensearch/indexing.py`: `ProductIndexService` for CRUD, bulk indexing, and reindexing.
5. `backend/app/opensearch/search.py`: `ProductSearchService` handling fuzzy search, autocomplete, filters, sorting.
6. `backend/app/opensearch/nlp.py`: `NaturalLanguageSearchParser` rule-based query parser.
7. `backend/app/opensearch/sync.py`: Kafka event consumer handler synchronizing changes to OpenSearch.
8. `backend/app/schemas/search.py`: Pydantic request and response schemas for search APIs.
9. `backend/app/api/v1/endpoints/search.py`: FastAPI endpoints router.
10. `backend/app/workers/reindexer.py`: Standalone CLI indexing and alias management utility.
11. `backend/tests/test_opensearch.py`: Comprehensive test suite covering all 26 test scenarios.
12. `docs/OPENSEARCH_INTEGRATION.md`: Full architecture, mapping, and operational documentation.

### Files to Modify:
1. `backend/app/api/v1/api.py`: Register `search_router` under `/api/v1`.
2. `backend/app/api/deps.py`: Add OpenSearch service dependencies (`get_opensearch_client`, `get_search_service`, `get_indexing_service`).
3. `backend/app/workers/consumer_worker.py`: Wire OpenSearch synchronization handler to `smartcart.products` and `smartcart.inventory`.
4. `backend/app/config.py`: Verify OpenSearch settings.
5. `.env.example`: Update OpenSearch environment variable placeholders.
6. `backend/README.md`: Document OpenSearch commands, workers, and search endpoints.

---

## 12. Verification & Baseline Protection

- **Phase 6.5 Baseline**: **270 passed, 1 skipped**.
- Full test suite will be executed following Phase 7 implementation to verify **zero regressions**.
