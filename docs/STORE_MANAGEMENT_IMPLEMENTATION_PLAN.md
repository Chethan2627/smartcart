# SmartCart 2.0 – Phase 6.5: Store Manager Product & Inventory Management
## Implementation Plan & Inspection Analysis

---

## 1. Executive Summary & Scope

SmartCart 2.0 is a multi-store e-commerce platform. This plan details the architecture and implementation for **Store Manager Product & Inventory Management (Phase 6.5)**.

The objective is to provide complete backend capabilities for `STORE_MANAGER` (and Admin/Super Admin) roles to manage store-specific inventory, stock adjustments, low-stock monitoring, product catalogue creation and lifecycle updates, Cloudinary-based product image uploads, and inventory audit logs, all while emitting transactional outbox events to Aiven Apache Kafka.

---

## 2. Codebase & Database Inspection Findings

### 2.1 Database Schema Inspection
An in-depth inspection of `database/01_schema.sql` revealed:

1. **`products` Table (`01_schema.sql:85-115`):**
   - Columns: `id` (UUID PK), `sku` (UNIQUE), `name`, `description`, `brand`, `category`, `price_paise` (BIGINT, >= 0), `attributes` (JSONB, default `'{}'::jsonb`), `is_active` (BOOL), `created_at`, `updated_at`.
   - Index: GIN index on `attributes` (`products_attributes_gin`).
   - **Crucial Finding:** `price_paise` is a column on the `products` table, meaning product pricing is currently **global across all stores**.

2. **`inventory` Table (`01_schema.sql:235-255`):**
   - Composite Primary Key: `(store_id, product_id)`.
   - Columns: `qty_on_hand` (INTEGER, >= 0), `qty_reserved` (INTEGER, >= 0), `low_stock_threshold` (INTEGER, default 5, >= 0), `updated_at`.
   - Constraint: `CheckConstraint("qty_reserved <= qty_on_hand", name="inventory_check")`.
   - **Crucial Finding:** Store-specific inventory and `low_stock_threshold` are already natively supported in the schema. Available stock is `qty_on_hand - qty_reserved`.

3. **`inventory_audit_log` Table & Trigger (`01_schema.sql:289-324`):**
   - Columns: `id` (BIGSERIAL PK), `store_id`, `product_id`, `old_on_hand`, `new_on_hand`, `old_reserved`, `new_reserved`, `reason` (TEXT), `changed_at`.
   - Trigger: `inventory_audit` fires `AFTER UPDATE OF qty_on_hand, qty_reserved ON inventory`.
   - Trigger Function: `log_inventory_change()` executes:
     ```sql
     INSERT INTO inventory_audit_log (...)
     VALUES (..., COALESCE(NULLIF(current_setting('app.change_reason', true), ''), 'UNSPECIFIED'));
     ```
   - **Crucial Finding:** Setting the session-level setting `SET LOCAL app.change_reason = :reason` prior to an update automatically records the reason in the PostgreSQL audit log table without requiring duplicate manual insert logic.

4. **`users` Table & Store Assignment (`01_schema.sql:15-39`):**
   - Columns: `id`, `email`, `role` (`CUSTOMER`, `STORE_MANAGER`, `ADMIN`, `SUPER_ADMIN`), `assigned_store_id` (UUID FK to `stores.id`), `is_active`.
   - Constraint: `check_store_manager_assignment` mandates `assigned_store_id IS NOT NULL` for `STORE_MANAGER`.

5. **`outbox_events` Table (`01_schema.sql:328-344`):**
   - Columns: `id`, `aggregate_type`, `aggregate_id`, `event_type`, `payload`, `status` (`PENDING`), `retry_count`, `last_error`, `created_at`.
   - Supports atomic persistence of Kafka domain events in the same PostgreSQL transaction.

### 2.2 Existing Codebase Inspection
- **Models:** `Product`, `Inventory`, `Reservation`, `InventoryAuditLog` are already fully defined in SQLAlchemy (`backend/app/models/product.py` and `backend/app/models/inventory.py`).
- **Repositories:** `ProductRepository` and `InventoryRepository` already exist with core lookup methods. An `InventoryAuditLogRepository` will be added to query the audit history with filtering and pagination.
- **Dependencies (`backend/app/api/deps.py`):**
  - `verify_store_manager_access(user, store_id)` and `require_store_access` are already implemented.
  - Role checkers `require_store_manager`, `require_admin`, `require_staff` are already available.
- **Kafka Integration (`backend/app/kafka/`):**
  - Event schemas, `SmartCartEvent`, `OutboxPublisher`, and topic routing (`smartcart.products`, `smartcart.inventory`) are already implemented from Phase 6.

---

## 3. Core Architectural Decisions

### 3.1 Pricing Model Discovery & Scope (Zero Schema Changes)
- **Finding:** Pricing (`price_paise`) is a column on the `products` table, not the `inventory` table.
- **Policy Enforcement:** A store manager MUST NOT be able to change a global catalog price that impacts all stores in the platform. Modifying global `price_paise` is restricted exclusively to `ADMIN` and `SUPER_ADMIN`.
- **Store Manager Scope:** Store managers can create products (which requires Admin approval or default global pricing) or update product metadata (name, description, brand, category, attributes), but any attempt by a `STORE_MANAGER` to modify `price_paise` will be rejected with `ForbiddenError` (HTTP 403).
- **Result:** **Zero database schema changes required**.

### 3.2 Product Image Storage Strategy (Zero Schema Changes)
- **Storage Provider:** Cloudinary using official Python SDK (`cloudinary>=1.41.0`).
- **Data Persistence:** Cloudinary image metadata (`url`, `secure_url`, `public_id`, `format`, `width`, `height`, `bytes`) will be stored within the existing JSONB column `products.attributes["image"]` and `products.attributes["images"]`.
- **Validation:**
  - Allowed MIME types: `image/jpeg`, `image/png`, `image/webp`.
  - Maximum file size: 5 MB (5 * 1024 * 1024 bytes).
- **Replacement & Deletion:**
  - When a product image is replaced, the previous image is deleted from Cloudinary using `public_id`.
  - When a product image is deleted via API, it is destroyed on Cloudinary and cleared from `attributes`.
- **Result:** **Zero database schema changes required**.

### 3.3 Inventory Adjustment & Reservation Protection
- **Transaction & Concurrency Safety:**
  - All stock adjustments will execute `SELECT * FROM inventory WHERE store_id = :s AND product_id = :p FOR UPDATE` to prevent race conditions.
  - Stock updates must preserve:
    $$\text{qty\_available} = \text{qty\_on\_hand} - \text{qty\_reserved}$$
  - Negative physical stock is strictly forbidden: $\text{qty\_on\_hand} \ge 0$.
  - Negative available stock is strictly forbidden: $\text{qty\_on\_hand} \ge \text{qty\_reserved}$.
  - Any adjustment that would cause $\text{qty\_on\_hand} < \text{qty\_reserved}$ will be rejected with `BadRequestError` ("Cannot reduce stock below currently reserved quantity").
- **Audit Logging via PostgreSQL Trigger:**
  - Before updating `inventory`, the service sets `SET LOCAL app.change_reason = :reason`.
  - The native PostgreSQL trigger `inventory_audit` automatically inserts the change record into `inventory_audit_log` with the exact previous and new quantities and reason.
- **Outbox Event:**
  - Atomically writes `inventory.stock.updated` event into `outbox_events`.

### 3.4 Low-Stock Monitoring Strategy
- **Threshold:** Configurable per store/product via `inventory.low_stock_threshold` (default: 5).
- **Alert Generation:**
  - When stock is adjusted such that $\text{qty\_available} \le \text{low\_stock\_threshold}$, an `inventory.low_stock` event is written to `outbox_events`.
  - If the item was already below threshold before the adjustment and remains below threshold, duplicate low-stock alerts are suppressed to prevent spamming notification consumers.
- **Management API:**
  - Dedicated endpoint `GET /api/v1/manager/inventory/low-stock` returning all items currently at or below their low-stock threshold for the manager's assigned store.

### 3.5 Safe Product Deactivation (Soft Delete)
- Hard deletion of products (`DELETE FROM products`) would violate foreign key constraints on `order_items` and historical reservations.
- Deleting a product via `DELETE /api/v1/manager/products/{product_id}` performs a **safe deactivation** (`is_active = False`), preserving full transactional order history while removing the product from customer-facing catalog browsing.
- Emits `product.deactivated` transactional outbox event.

---

## 4. RBAC & Store Isolation Architecture

1. **`STORE_MANAGER` Role:**
   - Authoritative store is retrieved from `user.assigned_store_id`.
   - Store managers can ONLY view and manage products, inventory, stock adjustments, and audit history for their own store.
   - Any request targeting another store ID is rejected with `ForbiddenError` (HTTP 403).
2. **`ADMIN` / `SUPER_ADMIN` Roles:**
   - Platform-wide authority: can manage any store's inventory by passing `store_id` query/body parameter, or perform platform-level catalogue administration (including global `price_paise` updates).
3. **`CUSTOMER` & Unauthenticated Roles:**
   - Access to any `/api/v1/manager/*` endpoint is rejected with `ForbiddenError` (HTTP 403) or `AuthenticationError` (HTTP 401).

---

## 5. API Endpoints Specification (`/api/v1/manager/`)

| Method | Endpoint | Description | Roles |
|---|---|---|---|
| `POST` | `/api/v1/manager/products` | Create a new product in catalogue (and optionally initialize inventory in manager's store) | Manager, Admin |
| `GET` | `/api/v1/manager/products` | List products with store inventory context and filtering | Manager, Admin |
| `GET` | `/api/v1/manager/products/{product_id}` | Get product details including image and store inventory | Manager, Admin |
| `PATCH` | `/api/v1/manager/products/{product_id}` | Update product information (name, description, brand, category, attributes) | Manager, Admin |
| `DELETE` | `/api/v1/manager/products/{product_id}` | Safe deactivation of product (preserves historical orders) | Manager, Admin |
| `POST` | `/api/v1/manager/products/{product_id}/image` | Upload / replace product image via Cloudinary | Manager, Admin |
| `DELETE` | `/api/v1/manager/products/{product_id}/image` | Remove product image from Cloudinary and product attributes | Manager, Admin |
| `GET` | `/api/v1/manager/inventory` | List store inventory (on-hand, reserved, available, threshold) | Manager, Admin |
| `GET` | `/api/v1/manager/inventory/low-stock` | List inventory items at or below low-stock threshold | Manager, Admin |
| `GET` | `/api/v1/manager/inventory/{product_id}` | Get single product inventory balance in manager's store | Manager, Admin |
| `POST` | `/api/v1/manager/inventory/{product_id}/adjustments` | Perform transactional stock adjustment (`INCREASE`, `DECREASE`, `SET`) | Manager, Admin |
| `GET` | `/api/v1/manager/inventory/{product_id}/history` | Retrieve inventory audit log history for product | Manager, Admin |

---

## 6. Implementation Components

1. **Storage Service Abstraction (`backend/app/services/storage.py`):**
   - Abstract `ImageStorageService` interface.
   - `CloudinaryImageStorageService` implementation using `cloudinary.uploader.upload` and `cloudinary.uploader.destroy`.
   - Mock-ready for automated tests without live network calls.
2. **Audit Log Repository (`backend/app/repositories/inventory_audit_log.py`):**
   - Query `inventory_audit_log` by `store_id`, `product_id` with ordering (`changed_at DESC`) and pagination (`skip`, `limit`).
3. **Store Manager Domain Service (`backend/app/services/store_manager.py`):**
   - Business orchestration: product management, Cloudinary image operations, row-locked stock adjustments, audit trigger execution, low-stock evaluation, and outbox event publishing.
4. **Manager Request & Response Schemas (`backend/app/schemas/manager.py`):**
   - `ProductCreateManagerRequest`, `ProductUpdateManagerRequest`, `StockAdjustmentRequest`, `StockAdjustmentResponse`, `StoreInventoryResponse`, `LowStockItemResponse`, `ProductImageUploadResponse`.
5. **API Endpoints Router (`backend/app/api/v1/endpoints/manager.py`):**
   - FastAPI APIRouter registered under `/api/v1/manager`.
6. **Outbox Event Integration:**
   - Atomic recording in `outbox_events` table for:
     - `product.created`
     - `product.updated`
     - `product.deactivated`
     - `product.image.updated`
     - `inventory.stock.updated`
     - `inventory.low_stock`

---

## 7. Comprehensive Test Plan (30 Test Cases)

| Category | # | Test Case | Expected Behavior |
|---|---|---|---|
| **Auth** | 1 | Manager can access assigned store | 200 OK |
| **Auth** | 2 | Manager cannot access another store | 403 Forbidden |
| **Auth** | 3 | Customer cannot access manager endpoints | 403 Forbidden |
| **Auth** | 4 | Admin access follows existing permissions | 200 OK across stores |
| **Product** | 5 | Product creation by Manager | 201 Created + Outbox event |
| **Product** | 6 | Duplicate SKU handling | 409 Conflict |
| **Product** | 7 | Product metadata update | 200 OK + Outbox event |
| **Product** | 8 | Price validation & Manager global price restriction | 403 for Manager, 200 for Admin |
| **Product** | 9 | Safe product deactivation | 200 OK (`is_active=False`) |
| **Product** | 10 | Historical order references remain intact after deactivation | Order item lookups succeed |
| **Image** | 11 | Valid image upload | 200 OK, URL in attributes, Cloudinary upload called |
| **Image** | 12 | Unsupported file type rejection | 400 Bad Request (e.g. text/pdf) |
| **Image** | 13 | Oversized file rejection (>5MB) | 400 Bad Request |
| **Image** | 14 | Cloudinary upload failure handling | 502 / 500 error gracefully mapped |
| **Image** | 15 | Image replacement cleans old image | Previous `public_id` destroyed on Cloudinary |
| **Image** | 16 | Image deletion endpoint | 200 OK, image removed from attributes & Cloudinary |
| **Inventory**| 17 | Initial stock creation | 201/200 OK, inventory row created |
| **Inventory**| 18 | Stock increase (`INCREASE`) | `qty_on_hand` increases, audit logged |
| **Inventory**| 19 | Stock decrease (`DECREASE`) | `qty_on_hand` decreases, audit logged |
| **Inventory**| 20 | Negative stock rejection | 400 Bad Request if final stock < 0 |
| **Inventory**| 21 | Outstanding reservation protection | 400 Bad Request if decreasing below `qty_reserved` |
| **Inventory**| 22 | Concurrent stock adjustments | Row-locking `FOR UPDATE` prevents lost updates |
| **Inventory**| 23 | Audit history correctness | `inventory_audit_log` records exact old/new/reason |
| **Inventory**| 24 | Cross-store isolation | Manager cannot view/adjust other store's stock |
| **Inventory**| 25 | Low-stock detection | Low-stock endpoint returns items $\le$ threshold |
| **Kafka** | 26 | Product event generation | Outbox records `product.created`/`updated` |
| **Kafka** | 27 | Inventory event generation | Outbox records `inventory.stock.updated` |
| **Kafka** | 28 | Outbox transactional consistency | Rolled back transaction produces NO outbox event |
| **Kafka** | 29 | Low stock event generation | Outbox records `inventory.low_stock` |
| **Kafka** | 30 | Duplicate low-stock suppression | No duplicate `inventory.low_stock` if already low |

---

## 8. Summary of Database Schema Impact

- **Database Changes Proposed:** **NONE**.
- All necessary tables (`products`, `inventory`, `inventory_audit_log`, `outbox_events`, `users`) already contain the necessary fields, constraints, and triggers.
- Product images are stored within `products.attributes` JSONB.
- Product pricing is kept global and restricted to `ADMIN`/`SUPER_ADMIN`.
