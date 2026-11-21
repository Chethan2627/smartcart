# SmartCart 2.0 – Phase 7: OpenSearch Product Discovery & Search Architecture

## 1. Executive Summary & Core Architectural Principles

Phase 7 introduces high-performance, typo-tolerant, store-aware product discovery for SmartCart 2.0 using **Aiven OpenSearch**.

### Architectural Tenets
1. **PostgreSQL is the Sole Authoritative Source of Truth**:
   All catalog metadata, inventory balances, reservations, and prices originate and reside authoritatively in PostgreSQL. OpenSearch is strictly a **read-only search projection** optimized for low-latency queries, faceted filtering, fuzzy text search, and autocomplete suggestions.
2. **Fail-Safe Decoupling**:
   Checkout, cart operations, atomic stock reservations (`reserve_stock()`), and payment flows depend solely on PostgreSQL and row-level locking. OpenSearch outages or network partitions have **zero impact** on transactional order completion or inventory consistency.
3. **Store-Aware Document Model**:
   SmartCart is a multi-store platform. Customers shop at a specific physical store. Documents are indexed using a composite key: `{product_id}_{store_id}`. This isolates store inventories, eliminates cross-store write locks, and prevents inventory leakage between stores.
4. **Authoritative Event-Driven Synchronization**:
   Kafka events (`product.*`, `inventory.*`) trigger downstream OpenSearch updates. To prevent race conditions and stale overwrites, the consumer retrieves canonical state directly from PostgreSQL using the event entity's ID before writing to OpenSearch. Stale update protection compares event timestamps against document versions.
5. **Zero-Downtime Index Migrations**:
   The application interacts with an index alias (`smartcart_products`). Schema changes use versioned indexes (`smartcart_products_v1`, `smartcart_products_v2`) and atomic alias switches (`_aliases` API) without search interruption.

---

## 2. Store-Aware Composite Document Model

Each OpenSearch document represents the availability of a specific product at a specific physical store:

```json
{
  "id": "86d6548c-7b44-492b-bf60-292c378e9cf3_9cdc8883-31ad-4ab7-b07e-182f0a01d033",
  "product_id": "86d6548c-7b44-492b-bf60-292c378e9cf3",
  "store_id": "9cdc8883-31ad-4ab7-b07e-182f0a01d033",
  "sku": "BT-HEAD-001",
  "name": "boAt Rockerz 450 Bluetooth Headphones",
  "brand": "boAt",
  "category": "Electronics",
  "description": "Wireless Bluetooth over-ear headphones with 15 hours battery backup",
  "price_paise": 149900,
  "qty_on_hand": 25,
  "qty_reserved": 2,
  "qty_available": 23,
  "is_in_stock": true,
  "low_stock_threshold": 5,
  "is_active": true,
  "image_url": "https://res.cloudinary.com/smartcart/image/upload/v1/products/boat_450.jpg",
  "created_at": "2026-11-20T10:00:00Z",
  "updated_at": "2026-11-22T00:15:00Z"
}
```

### Document Schema Fields
| Field Name | Type | Description / Analyzer |
| :--- | :--- | :--- |
| `id` | `keyword` | Deterministic composite ID: `{product_id}_{store_id}` |
| `product_id` | `keyword` | UUID of the product catalog entity |
| `store_id` | `keyword` | UUID of the physical store location |
| `sku` | `keyword` | Stock Keeping Unit (exact matches, boosted $\times 4$) |
| `name` | `text` + `keyword` + `autocomplete` | Product title. Multi-field with edge n-gram autocomplete analyzer |
| `brand` | `keyword` + `text` | Brand name. Exact keyword filtering and fuzzy search |
| `category` | `keyword` + `text` | Product category for filtering and facets |
| `description` | `text` | Product long description analyzed with English stemmer |
| `price_paise` | `integer` | Authoritative price in paise (₹1.00 = 100 paise) |
| `qty_on_hand` | `integer` | Physical units on store shelves |
| `qty_reserved` | `integer` | Units locked in active carts or in-flight checkout |
| `qty_available` | `integer` | $\max(0, \text{qty\_on\_hand} - \text{qty\_reserved})$ |
| `is_in_stock` | `boolean` | True if $\text{qty\_available} > 0$ |
| `is_active` | `boolean` | False if product or store is deactivated |
| `image_url` | `keyword` | Primary Cloudinary CDN image URL |
| `created_at` | `date` | Timestamp of product creation |
| `updated_at` | `date` | Timestamp of latest inventory or catalog update |

---

## 3. Index Mappings & Custom Analyzers

Defined in `backend/app/opensearch/mappings.py`.

### Analyzers & Token Filters
1. **`autocomplete_analyzer`**:
   - Tokenizer: `standard`
   - Token Filters: `lowercase`, `edge_ngram_filter` (`min_gram: 2`, `max_gram: 15`)
   - Purpose: Powers real-time prefix suggestions as the user types (e.g. typing `"boat"` matches `"boAt Rockerz"` on 2 keystrokes).
2. **`text_search_analyzer`**:
   - Tokenizer: `standard`
   - Token Filters: `lowercase`, `english_stemmer`
   - Purpose: Normalizes plurals and conjugations (e.g. `"headphones"`, `"headphone"` match identically).
3. **`lowercase_normalizer`**:
   - Character Filter: None
   - Filter: `lowercase`
   - Purpose: Enables case-insensitive exact matching and clean aggregation facet keys on `keyword` fields.

---

## 4. Natural Language Search Parser

Implemented in `backend/app/opensearch/nlp.py`.

Users frequently enter natural language phrases rather than keyword lists. The `NaturalLanguageSearchParser` extracts filters and sort intents before query execution:

| Input Query | Parsed Filter / Sort | Cleaned Search Query |
| :--- | :--- | :--- |
| `"bluetooth headphones under 2000"` | `max_price_paise: 200000` | `"bluetooth headphones"` |
| `"smartphones between 10000 and 20000"` | `min_price_paise: 1000000`, `max_price_paise: 2000000` | `"smartphones"` |
| `"nike shoes in stock"` | `only_in_stock: True` | `"nike shoes"` |
| `"cheapest wireless earbuds"` | `sort_by: "price_asc"` | `"wireless earbuds"` |
| `"latest gaming laptops"` | `sort_by: "created_desc"` | `"gaming laptops"` |

---

## 5. Search Query Construction & Multi-Field Relevance Boosting

Implemented in `backend/app/opensearch/search.py` (`ProductSearchService`).

### Multi-Field Boosting Hierarchy
When a user searches for a term:
- `sku^4`: Exact match on SKU has highest priority.
- `name^3`: Matches in product title are boosted $\times 3$.
- `brand^2`: Matches in brand are boosted $\times 2$.
- `category^2`: Matches in category are boosted $\times 2$.
- `description^1`: Full-text description matches provide base relevance.

### Typo Tolerance & Fuzzy Matching
- Fuzziness: `AUTO:4,7` (0 edits for $\le 3$ characters, 1 edit for 4–7 characters, 2 edits for $>7$ characters).
- `prefix_length: 2`: Prevents noisy mutations on the first two letters.
- `operator: "OR"`: Allows multi-token queries to match partially, scored by relevance.

### Mandatory Store Scoping & Active Filters
Every search query includes strict filter clauses:
```json
{
  "bool": {
    "filter": [
      { "term": { "store_id": "<SELECTED_STORE_UUID>" } },
      { "term": { "is_active": true } }
    ]
  }
}
```
Optional filters (`category`, `brand`, `is_in_stock`, `price_paise` ranges) are added as additional boolean filter clauses without impacting BM25 relevance scores.

---

## 6. Asynchronous Kafka-to-OpenSearch Synchronization

Implemented in `backend/app/opensearch/sync.py` and connected via `backend/app/workers/consumer_worker.py`.

```
PostgreSQL (Source of Truth)
     │
     ▼ (Outbox Transaction)
outbox_events
     │
     ▼ (Outbox Publisher)
Apache Kafka Topics (Aiven)
  - smartcart.products
  - smartcart.inventory
     │
     ▼ (SmartCartKafkaConsumer)
OpenSearchSyncService
     │
     ├── 1. Read authoritative current row from PostgreSQL
     ├── 2. Verify timestamp >= existing doc updated_at (Stale Protection)
     └── 3. Index or Update OpenSearch Document
```

### Event Handlers
| Kafka Event Type | Synchronizer Action |
| :--- | :--- |
| `product.created` | Reads canonical product from PostgreSQL; indexes documents across all active stores with inventory balances. |
| `product.updated` | Updates metadata (`name`, `brand`, `category`, `price_paise`, `description`) across all store documents for that product. |
| `product.image.updated`| Updates `image_url` on all store documents for that product. |
| `product.deactivated` | Sets `is_active = false` across all store documents for that product. |
| `inventory.stock.updated`| Reads current `qty_on_hand` and `qty_reserved` from PostgreSQL `inventory` table and updates `qty_available` and `is_in_stock`. |
| `inventory.changed` | Recomputes available balance from PostgreSQL and updates the store-product document. |
| `inventory.low_stock` | Updates stock counters and logs a warning for store operations. |

### Stale Update Protection
Network delays or consumer rebalances can deliver out-of-order Kafka events. The synchronizer protects against stale updates:
- Before executing a partial update, `ProductIndexService.update_stock()` checks `updated_at`.
- If an existing OpenSearch document has `updated_at` newer than the incoming event's timestamp, the update is safely discarded.

---

## 7. Reindexer CLI & Zero-Downtime Reindexing

Implemented in `backend/app/workers/reindexer.py`.

The reindexer utility allows administrators to create indexes, populate documents from PostgreSQL in bulk, or execute blue-green alias swaps with zero downtime:

```powershell
# Check index status and doc count
python -m app.workers.reindexer --status

# Create a new versioned index (e.g. smartcart_products_v1)
python -m app.workers.reindexer --create-index --version v1

# Bulk index all products and stores from PostgreSQL
python -m app.workers.reindexer --bulk-index --batch-size 500

# Full zero-downtime reindexing workflow (creates next version, indexes docs, swaps alias)
python -m app.workers.reindexer --reindex-all
```

---

## 8. FastAPI API Endpoints Reference

All search routes are registered under `/api/v1/search/`:

### 1. `GET /api/v1/search/products`
Store-scoped product discovery with natural language processing and faceted filtering.
- **Parameters**:
  - `store_id` (UUID, required): The target store.
  - `q` (string, optional): Search query (e.g., `"wireless boAt headphones under 2000"`).
  - `category` (string, optional): Exact category filter.
  - `brand` (string, optional): Exact brand filter.
  - `min_price` (integer, optional): Min price in paise.
  - `max_price` (integer, optional): Max price in paise.
  - `only_in_stock` (boolean, default `false`): Filter out-of-stock items.
  - `sort_by` (enum: `relevance`, `price_asc`, `price_desc`, `created_desc`, default `relevance`).
  - `page` (integer, default `1`), `size` (integer, default `20`).
- **Response**: Paginated product list, matched total, pagination metadata, and facet aggregations (`categories`, `brands`, `price_stats`).

### 2. `GET /api/v1/search/suggestions`
Low-latency autocomplete for search-as-you-type inputs.
- **Parameters**: `store_id` (UUID, required), `q` (string, required, $\ge 2$ chars), `limit` (integer, default `10`).
- **Response**: Array of product suggestions with `id`, `name`, `sku`, `brand`, `category`, `price_paise`, and `is_in_stock`.

### 3. `GET /api/v1/search/filters`
Retrieves store-specific facet filters without requiring a search query.
- **Parameters**: `store_id` (UUID, required).
- **Response**: Available categories with counts, available brands with counts, and min/max prices.

### 4. `GET /api/v1/search/health`
Detailed cluster and index health check.
- **Security**: Strictly protected by `require_admin` dependency. Rejects unauthenticated requests (HTTP 401) and customer/store-manager accounts (HTTP 403).
- **Response**: Cluster status (`green`, `yellow`, `red`), node count, shard metrics, index document count, and index size.

---

## 9. Test Suite Verification & Coverage Matrix

A comprehensive test suite of 26 dedicated test scenarios is implemented in `backend/tests/test_opensearch.py`:

| Test Scenario | Description | Verification Method |
| :--- | :--- | :--- |
| `test_01` | OpenSearch client initialization via ConfigBuilder | Mock client / ConfigBuilder |
| `test_02` | Credential sanitization in logs and URL builders | Unit string inspection |
| `test_03` | Host, port, scheme, and URL parsing | Builder protocol matrix |
| `test_04` | Mapping schema structure, tokenizers, analyzers | Schema dictionary validation |
| `test_05` | Store-product composite ID format `{prod}_{store}` | UUID combination assertion |
| `test_06` | Versioned index creation and alias setup | MockIndicesClient lifecycle |
| `test_07` | Store-product indexing with stock calculation | OpenSearch document storage |
| `test_08` | Document retrieval and `NotFoundError` handling | Get document inspection |
| `test_09` | Stock update with available calculation | OpenSearch update API |
| `test_10` | Stale stock update rejection via timestamps | Timestamp comparison assertion |
| `test_11` | Cross-store product metadata updates | Multi-document script update |
| `test_12` | Product deactivation (`is_active = false`) | Term update inspection |
| `test_13` | Bulk indexing using `opensearchpy.helpers.bulk` | Streaming bulk validation |
| `test_14` | Atomic alias swap for zero-downtime reindexing | `update_aliases` execution |
| `test_15` | NLP query parser: price bounds detection | Regex extraction matrix |
| `test_16` | NLP query parser: stock and sort intent detection | Intent extraction matrix |
| `test_17` | Search query builder boosting and store scoping | Query DSL structure check |
| `test_18` | Search product store isolation | Cross-store query evaluation |
| `test_19` | Search typo tolerance and facet filtering | Simulated search execution |
| `test_20` | Autocomplete prefix suggestions | Phrase prefix match check |
| `test_21` | Filter facets and price statistics aggregation | Bucket aggregation check |
| `test_22` | Admin-only search health endpoint authorization | HTTP 401/403/200 validation |
| `test_23` | Kafka synchronization: `product.created`/`updated` | Live PostgreSQL + SyncService |
| `test_24` | Kafka synchronization: `inventory.stock.updated` | Live PostgreSQL + SyncService |
| `test_25` | Reindexer worker bulk index from PostgreSQL | Live PostgreSQL + Reindexer |
| `test_26` | Checkout and reservation fail-safe independence | Simulated OpenSearch outage + live DB |

### Test Execution Summary
- **OpenSearch Test Suite**: 26 passed in 1.90s (100% pass rate).
- **Full Backend Suite**: **296 passed, 1 skipped in 26.31s** (0 failures, 0 errors).
