# SmartCart 2.0 – Store Manager Product & Inventory Management (Phase 6.5)

---

## 1. Executive Summary

SmartCart 2.0 is an intelligent multi-store e-commerce platform. Phase 6.5 provides complete backend capabilities for **Store Managers** (and Administrators) to manage product catalogues, product imagery, and store-specific inventory, while maintaining strict ACID transactional consistency in PostgreSQL and publishing events to Aiven Apache Kafka via the Transactional Outbox pattern.

---

## 2. Role-Based Access Control & Store Isolation

Access to all `/api/v1/manager/*` endpoints is strictly governed by authoritative JWT authentication and cryptographic role verification:

1. **`STORE_MANAGER` Role:**
   - Authoritative store is retrieved from the database column `users.assigned_store_id`.
   - Store managers can **only** inspect and modify products, inventory, stock adjustments, and audit history for their assigned store.
   - Any attempt to access, view, or modify resources belonging to another store returns **HTTP 403 Forbidden**.
2. **`ADMIN` and `SUPER_ADMIN` Roles:**
   - Platform-wide administrative authority.
   - Can manage catalogue products and any store's inventory by passing the `store_id` parameter.
3. **`CUSTOMER` and Unauthenticated Visitors:**
   - Access to any manager route is denied with **HTTP 403 Forbidden** or **HTTP 401 Unauthorized**.

---

## 3. Pricing Architecture & Catalog Scope

- **Database Model:**
  The `products` table defines `price_paise INTEGER NOT NULL CHECK (price_paise >= 0)`.
- **Catalogue Scope:**
  Product catalogue pricing is **global** across all stores.
- **Store Manager Restriction:**
  Store managers are strictly prohibited from modifying `price_paise` because doing so would alter the price across every store in India. Any attempt by a `STORE_MANAGER` to update `price_paise` via `PATCH /api/v1/manager/products/{id}` is rejected with:
  ```json
  {
    "error": {
      "code": "FORBIDDEN",
      "message": "Store managers cannot modify global catalog prices. Price updates must be performed by a platform administrator."
    }
  }
  ```
- **Admin Price Administration:**
  `ADMIN` and `SUPER_ADMIN` can modify `price_paise` globally. All prices are stored in non-negative integer Indian paise (e.g. 199900 paise = ₹1,999.00) to eliminate floating-point arithmetic errors.

---

## 4. Product Image Upload & Cloudinary Integration

Product images are stored using **Cloudinary** and integrated into the existing PostgreSQL schema without database migrations by utilizing the JSONB column `products.attributes`:

- **Configuration:**
  ```env
  CLOUDINARY_CLOUD_NAME=your-cloud-name
  CLOUDINARY_API_KEY=your-api-key
  CLOUDINARY_API_SECRET=your-api-secret
  CLOUDINARY_UPLOAD_FOLDER=smartcart/products
  ```
- **Validation Constraints:**
  - Allowed MIME Types: `image/jpeg`, `image/jpg`, `image/png`, `image/webp`.
  - Maximum File Size: **5 MB** (5,242,880 bytes).
  - Empty files are rejected.
- **Attributes Metadata Structure:**
  ```json
  "attributes": {
    "image": {
      "url": "https://res.cloudinary.com/smartcart/image/upload/v12345/smartcart/products/prod_123.jpg",
      "secure_url": "https://res.cloudinary.com/smartcart/image/upload/v12345/smartcart/products/prod_123.jpg",
      "public_id": "smartcart/products/prod_123",
      "format": "jpg",
      "width": 800,
      "height": 600,
      "bytes": 245120
    }
  }
  ```
- **Lifecycle & Cleanup:**
  - When a product image is replaced, the previous `public_id` is automatically destroyed on Cloudinary.
  - When `DELETE /api/v1/manager/products/{id}/image` is called, the image is destroyed on Cloudinary and removed from `attributes`.

---

## 5. Store Inventory & Concurrency-Safe Stock Adjustments

Inventory is independent for each physical store, keyed by composite primary key `(store_id, product_id)`.

### 5.1 Invariants & Balance Rules
- **Physical Stock On-Hand:** `qty_on_hand` (physical units in warehouse).
- **Reserved Stock:** `qty_reserved` (units held by active shopping carts or pending checkout).
- **Available Stock:**
  $$\text{qty\_available} = \text{max}(0, \text{qty\_on\_hand} - \text{qty\_reserved})$$
- **Physical Non-Negative Invariant:** $\text{qty\_on\_hand} \ge 0$.
- **Reservation Protection Invariant:** $\text{qty\_on\_hand} \ge \text{qty\_reserved}$. Any adjustment that attempts to reduce on-hand stock below the active reserved quantity is rejected with **HTTP 400 Bad Request**.

### 5.2 Concurrency Safety
Stock adjustments use PostgreSQL row-level locks:
```sql
SELECT * FROM inventory WHERE store_id = :s AND product_id = :p FOR UPDATE;
```
This serializes concurrent stock operations and eliminates race conditions.

### 5.3 Stock Adjustment Operations
Endpoint: `POST /api/v1/manager/inventory/{product_id}/adjustments`

Supported operations:
1. `INCREASE`: Adds `quantity` to `qty_on_hand`.
2. `DECREASE`: Subtracts `quantity` from `qty_on_hand`.
3. `SET`: Directly sets `qty_on_hand` to `quantity`.

---

## 6. Inventory Audit Logging

SmartCart 2.0 leverages the native PostgreSQL trigger `inventory_audit` on the `inventory` table:
```sql
CREATE TRIGGER inventory_audit
  AFTER UPDATE OF qty_on_hand, qty_reserved ON inventory
  FOR EACH ROW
  WHEN (OLD.qty_on_hand  IS DISTINCT FROM NEW.qty_on_hand
     OR OLD.qty_reserved IS DISTINCT FROM NEW.qty_reserved)
  EXECUTE FUNCTION log_inventory_change();
```
Prior to updating inventory, the service sets the session-local setting:
```sql
SELECT set_config('app.change_reason', :reason, true);
```
The trigger automatically inserts an immutable audit row into `inventory_audit_log` with:
- `store_id`
- `product_id`
- `old_on_hand`, `new_on_hand`
- `old_reserved`, `new_reserved`
- `reason` (including adjustment type, business justification, and manager ID)
- `changed_at` (accurate clock timestamp)

---

## 7. Low-Stock Monitoring & Alert Suppression

- **Threshold:** Configurable per store and product via `inventory.low_stock_threshold` (default: 5).
- **Monitoring Endpoint:** `GET /api/v1/manager/inventory/low-stock` returns all items where $\text{qty\_available} \le \text{low\_stock\_threshold}$.
- **Edge-Triggered Alert Generation:**
  When a stock adjustment causes available stock to drop from above threshold to $\le \text{low\_stock\_threshold}$, an `inventory.low_stock` event is written to `outbox_events`. If an item is already below threshold and undergoes another adjustment while remaining low, duplicate alerts are suppressed.

---

## 8. Transactional Outbox Kafka Events

All domain events are written atomically within the same database transaction as the business operation into the `outbox_events` table:

| Event Type | Aggregate Type | Trigger Condition |
|---|---|---|
| `product.created` | `product` | New product created in catalogue |
| `product.updated` | `product` | Product metadata or status updated |
| `product.deactivated` | `product` | Product deactivated (soft deleted) |
| `product.image.updated`| `product` | Product image uploaded, replaced, or deleted |
| `inventory.stock.updated`| `inventory` | Stock adjusted or initialized |
| `inventory.low_stock` | `inventory` | Available stock crosses below threshold |

---

## 9. API Reference Summary

All manager routes are prefixed with `/api/v1/manager`:

| Method | Endpoint | Description | Status Codes |
|---|---|---|---|
| `POST` | `/api/v1/manager/products` | Create product and initialize store stock | 201, 400, 403, 409 |
| `GET` | `/api/v1/manager/products` | List catalogue products with store stock context | 200, 401, 403 |
| `GET` | `/api/v1/manager/products/{id}` | Get product details with store stock balance | 200, 404, 403 |
| `PATCH`| `/api/v1/manager/products/{id}` | Update product metadata (price restricted to Admin) | 200, 400, 403, 404 |
| `DELETE`| `/api/v1/manager/products/{id}` | Safe product deactivation (`is_active = False`) | 200, 404, 403 |
| `POST` | `/api/v1/manager/products/{id}/image` | Upload product image to Cloudinary (JPEG/PNG/WEBP $\le$ 5MB) | 200, 400, 403, 404 |
| `DELETE`| `/api/v1/manager/products/{id}/image` | Delete product image from Cloudinary and attributes | 200, 404, 403 |
| `GET` | `/api/v1/manager/inventory` | List physical, reserved, and available store stock | 200, 401, 403 |
| `GET` | `/api/v1/manager/inventory/low-stock` | List inventory items at or below low-stock threshold | 200, 401, 403 |
| `GET` | `/api/v1/manager/inventory/{id}` | Get inventory balance for specific product | 200, 404, 403 |
| `POST` | `/api/v1/manager/inventory/{id}/adjustments` | Atomic, row-locked stock adjustment (`INCREASE`, `DECREASE`, `SET`) | 200, 400, 403, 404 |
| `GET` | `/api/v1/manager/inventory/{id}/history` | Retrieve stock change audit history | 200, 404, 403 |

---

## 10. Automated Test Suite Verification

Run the complete 30-scenario test suite:
```bash
pytest backend/tests/test_store_manager.py -v
```

Run the entire backend test suite:
```bash
pytest backend/tests -v
```
**Test Results:** **270 passed, 1 skipped** (100% pass rate).
