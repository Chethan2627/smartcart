-- =====================================================================
-- SmartCart 2.0 - Phase 1: PostgreSQL Foundation (Aiven PostgreSQL 14+)
-- Store-wise inventory, atomic stock reservation, order state machine,
-- checkout idempotency, inventory audit log, transactional outbox,
-- and RBAC identity design.
--
-- Target: Clean baseline schema for empty development/testing database.
-- Future schema evolutions across Phases 2-10 will be managed via Alembic.
-- =====================================================================

BEGIN;

-- ---------- Types ----------------------------------------------------
CREATE TYPE user_role AS ENUM
  ('CUSTOMER', 'STORE_MANAGER', 'ADMIN', 'SUPER_ADMIN');

CREATE TYPE order_status AS ENUM
  ('PENDING', 'CONFIRMED', 'PACKED', 'SHIPPED', 'DELIVERED', 'CANCELLED');

CREATE TYPE reservation_status AS ENUM
  ('ACTIVE', 'CONSUMED', 'RELEASED', 'EXPIRED');

CREATE TYPE outbox_status AS ENUM
  ('PENDING', 'PUBLISHED', 'FAILED');

-- ---------- Generic helper -------------------------------------------
CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS trigger AS $$
BEGIN
  NEW.updated_at := clock_timestamp();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ---------- Stores ---------------------------------------------------
CREATE TABLE stores (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code       TEXT NOT NULL UNIQUE,            -- e.g. STORE-001
  name       TEXT NOT NULL,
  city       TEXT NOT NULL,
  state      TEXT NOT NULL,
  address    TEXT,
  is_active  BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX stores_city_state_idx ON stores (state, city);

-- ---------- Users & RBAC Identity ------------------------------------
-- Unified authentication and platform identity table.
CREATE TABLE users (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email             TEXT NOT NULL UNIQUE,
  full_name         TEXT NOT NULL,
  password_hash     TEXT NOT NULL,            -- Argon2id hash (never plain text)
  role              user_role NOT NULL DEFAULT 'CUSTOMER',
  assigned_store_id UUID REFERENCES stores (id),
  is_active         BOOLEAN NOT NULL DEFAULT TRUE,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),

  -- Constraint: A STORE_MANAGER must be assigned to exactly one physical store.
  -- Other roles (CUSTOMER, ADMIN, SUPER_ADMIN) must not have a store assignment.
  CONSTRAINT check_store_manager_assignment CHECK (
    (role = 'STORE_MANAGER' AND assigned_store_id IS NOT NULL) OR
    (role <> 'STORE_MANAGER' AND assigned_store_id IS NULL)
  )
);
CREATE INDEX users_role_idx ON users (role);
CREATE INDEX users_assigned_store_idx ON users (assigned_store_id)
  WHERE assigned_store_id IS NOT NULL;
CREATE TRIGGER users_touch BEFORE UPDATE ON users
  FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

-- ---------- Customers Profile ----------------------------------------
-- Dedicated shopping profile for CUSTOMER users only.
-- Store Managers, Admins, and Super Admins do not have customer records.
CREATE TABLE customers (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    UUID NOT NULL UNIQUE REFERENCES users (id) ON DELETE CASCADE,
  phone      TEXT,
  address    TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- Guard 1: Concurrency-safe customer profile role verification.
-- Locks the referenced users row (FOR UPDATE) to eliminate race conditions
-- against concurrent role conversions.
CREATE OR REPLACE FUNCTION check_customer_user_role() RETURNS trigger AS $$
DECLARE
  v_role user_role;
BEGIN
  SELECT role INTO v_role
    FROM users
   WHERE id = NEW.user_id
     FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Referenced user % does not exist', NEW.user_id
      USING ERRCODE = '23503';
  END IF;

  IF v_role <> 'CUSTOMER' THEN
    RAISE EXCEPTION 'User % has role %, only users with role CUSTOMER can have a customer profile',
      NEW.user_id, v_role USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER customers_role_guard BEFORE INSERT OR UPDATE OF user_id ON customers
  FOR EACH ROW EXECUTE FUNCTION check_customer_user_role();

-- Guard 2: Prevent changing a user's role away from CUSTOMER while a customer profile exists.
CREATE OR REPLACE FUNCTION guard_user_role_change() RETURNS trigger AS $$
BEGIN
  IF OLD.role = 'CUSTOMER' AND NEW.role <> 'CUSTOMER' THEN
    IF EXISTS (SELECT 1 FROM customers WHERE user_id = OLD.id) THEN
      RAISE EXCEPTION 'Cannot change user % role from CUSTOMER to % while a customer profile exists. Delete or archive the customer profile first.',
        OLD.id, NEW.role USING ERRCODE = '23514';
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER users_role_guard BEFORE UPDATE OF role ON users
  FOR EACH ROW EXECUTE FUNCTION guard_user_role_change();

-- ---------- Products -------------------------------------------------
-- Money is stored in paise (BIGINT) to avoid floating-point errors.
CREATE TABLE products (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  sku         TEXT NOT NULL UNIQUE,
  name        TEXT NOT NULL,
  description TEXT,
  brand       TEXT,
  category    TEXT,
  price_paise BIGINT NOT NULL CHECK (price_paise >= 0),
  attributes  JSONB NOT NULL DEFAULT '{}'::jsonb,   -- color, storage, ...
  is_active   BOOLEAN NOT NULL DEFAULT TRUE,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX products_category_idx   ON products (category);
CREATE INDEX products_brand_idx      ON products (brand);
CREATE INDEX products_attributes_gin ON products USING GIN (attributes);
CREATE TRIGGER products_touch BEFORE UPDATE ON products
  FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

-- ---------- Orders ---------------------------------------------------
CREATE SEQUENCE order_number_seq START 1;

CREATE TABLE orders (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  order_number TEXT NOT NULL UNIQUE DEFAULT
                 ('SC-' || to_char(clock_timestamp(), 'YYYY') || '-' ||
                  lpad(nextval('order_number_seq')::text, 6, '0')),
  customer_id  UUID NOT NULL REFERENCES customers (id),
  store_id     UUID NOT NULL REFERENCES stores (id),   -- fulfilling store
  status       order_status NOT NULL DEFAULT 'PENDING',
  total_paise  BIGINT NOT NULL CHECK (total_paise >= 0),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX orders_customer_idx ON orders (customer_id, created_at DESC);
CREATE INDEX orders_store_status_idx ON orders (store_id, status);
CREATE TRIGGER orders_touch BEFORE UPDATE ON orders
  FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

CREATE TABLE order_items (
  id               BIGSERIAL PRIMARY KEY,
  order_id         UUID NOT NULL REFERENCES orders (id) ON DELETE CASCADE,
  product_id       UUID NOT NULL REFERENCES products (id),
  qty              INTEGER NOT NULL CHECK (qty > 0),
  unit_price_paise BIGINT NOT NULL CHECK (unit_price_paise >= 0),
  CONSTRAINT order_items_order_product_uniq UNIQUE (order_id, product_id)
);
CREATE INDEX order_items_order_idx ON order_items (order_id);

-- Status history (also feeds live order tracking via SSE)
CREATE TABLE order_status_history (
  id          BIGSERIAL PRIMARY KEY,
  order_id    UUID NOT NULL REFERENCES orders (id) ON DELETE CASCADE,
  from_status order_status,
  to_status   order_status NOT NULL,
  changed_at  TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX order_status_history_order_idx
  ON order_status_history (order_id, changed_at);

-- Log the first status on insert
CREATE OR REPLACE FUNCTION log_initial_order_status() RETURNS trigger AS $$
BEGIN
  INSERT INTO order_status_history (order_id, from_status, to_status)
  VALUES (NEW.id, NULL, NEW.status);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER orders_initial_status AFTER INSERT ON orders
  FOR EACH ROW EXECUTE FUNCTION log_initial_order_status();

-- Enforce the order state machine and record every change
CREATE OR REPLACE FUNCTION enforce_order_transition() RETURNS trigger AS $$
BEGIN
  IF NEW.status = OLD.status THEN
    RETURN NEW;
  END IF;

  IF NOT (
       (OLD.status = 'PENDING'   AND NEW.status IN ('CONFIRMED', 'CANCELLED'))
    OR (OLD.status = 'CONFIRMED' AND NEW.status IN ('PACKED', 'CANCELLED'))
    OR (OLD.status = 'PACKED'    AND NEW.status = 'SHIPPED')
    OR (OLD.status = 'SHIPPED'   AND NEW.status = 'DELIVERED')
  ) THEN
    RAISE EXCEPTION 'Invalid order transition % -> %', OLD.status, NEW.status
      USING ERRCODE = '23514';
  END IF;

  INSERT INTO order_status_history (order_id, from_status, to_status)
  VALUES (OLD.id, OLD.status, NEW.status);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER orders_status_guard BEFORE UPDATE OF status ON orders
  FOR EACH ROW EXECUTE FUNCTION enforce_order_transition();

-- ---------- Store-wise inventory -------------------------------------
-- available = qty_on_hand - qty_reserved
CREATE TABLE inventory (
  store_id            UUID NOT NULL REFERENCES stores (id),
  product_id          UUID NOT NULL REFERENCES products (id),
  qty_on_hand         INTEGER NOT NULL DEFAULT 0 CHECK (qty_on_hand >= 0),
  qty_reserved        INTEGER NOT NULL DEFAULT 0 CHECK (qty_reserved >= 0),
  low_stock_threshold INTEGER NOT NULL DEFAULT 5 CHECK (low_stock_threshold >= 0),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (store_id, product_id),
  CHECK (qty_reserved <= qty_on_hand)         -- can never reserve more than we have
);
CREATE INDEX inventory_product_idx ON inventory (product_id);
CREATE TRIGGER inventory_touch BEFORE UPDATE ON inventory
  FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

CREATE VIEW inventory_available AS
SELECT store_id,
       product_id,
       qty_on_hand,
       qty_reserved,
       (qty_on_hand - qty_reserved)                         AS qty_available,
       (qty_on_hand - qty_reserved) <= low_stock_threshold  AS is_low_stock
FROM inventory;

-- ---------- Reservations ---------------------------------------------
CREATE TABLE reservations (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  customer_id UUID NOT NULL REFERENCES customers (id),
  store_id    UUID NOT NULL,
  product_id  UUID NOT NULL,
  qty         INTEGER NOT NULL CHECK (qty > 0),
  status      reservation_status NOT NULL DEFAULT 'ACTIVE',
  expires_at  TIMESTAMPTZ NOT NULL,
  order_id    UUID REFERENCES orders (id),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  FOREIGN KEY (store_id, product_id) REFERENCES inventory (store_id, product_id)
);
-- Fast lookup for the expiry job: only ACTIVE rows are indexed
CREATE INDEX reservations_active_expiry_idx
  ON reservations (expires_at) WHERE status = 'ACTIVE';
CREATE INDEX reservations_customer_idx ON reservations (customer_id);
CREATE INDEX reservations_order_idx ON reservations (order_id) WHERE order_id IS NOT NULL;
CREATE TRIGGER reservations_touch BEFORE UPDATE ON reservations
  FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

-- ---------- Checkout idempotency -------------------------------------
-- The API sends an Idempotency-Key header. Same key => same result,
-- never a second order.
CREATE TABLE idempotency_keys (
  customer_id  UUID NOT NULL REFERENCES customers (id),
  key          TEXT NOT NULL,
  request_hash TEXT NOT NULL,                 -- detects key reuse with a different body
  order_id     UUID REFERENCES orders (id),
  response     JSONB,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (customer_id, key)
);

-- ---------- Inventory audit log --------------------------------------
CREATE TABLE inventory_audit_log (
  id           BIGSERIAL PRIMARY KEY,
  store_id     UUID NOT NULL,
  product_id   UUID NOT NULL,
  old_on_hand  INTEGER NOT NULL,
  new_on_hand  INTEGER NOT NULL,
  old_reserved INTEGER NOT NULL,
  new_reserved INTEGER NOT NULL,
  reason       TEXT NOT NULL,
  changed_at   TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX inventory_audit_item_idx
  ON inventory_audit_log (store_id, product_id, changed_at DESC);

-- The reason comes from a transaction-local setting that the stock
-- functions below set (RESERVE, CONFIRM, RELEASE, EXPIRE, ORDER_CANCELLED).
CREATE OR REPLACE FUNCTION log_inventory_change() RETURNS trigger AS $$
BEGIN
  INSERT INTO inventory_audit_log
    (store_id, product_id, old_on_hand, new_on_hand,
     old_reserved, new_reserved, reason)
  VALUES
    (NEW.store_id, NEW.product_id, OLD.qty_on_hand, NEW.qty_on_hand,
     OLD.qty_reserved, NEW.qty_reserved,
     COALESCE(NULLIF(current_setting('app.change_reason', true), ''), 'UNSPECIFIED'));
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER inventory_audit
  AFTER UPDATE OF qty_on_hand, qty_reserved ON inventory
  FOR EACH ROW
  WHEN (OLD.qty_on_hand  IS DISTINCT FROM NEW.qty_on_hand
     OR OLD.qty_reserved IS DISTINCT FROM NEW.qty_reserved)
  EXECUTE FUNCTION log_inventory_change();

-- ---------- Transactional Outbox (Aiven Kafka Integration) -----------
-- Master Plan Phase 5: Written atomically in the same PostgreSQL transaction
-- as orders and inventory changes, eliminating dual-write failure.
CREATE TABLE outbox_events (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  aggregate_type TEXT NOT NULL,                -- 'order', 'inventory', 'product'
  aggregate_id   TEXT NOT NULL,                -- e.g. order_id, product_id
  event_type     TEXT NOT NULL,                -- 'order.placed', 'order.cancelled', 'inventory.changed'
  payload        JSONB NOT NULL,
  status         outbox_status NOT NULL DEFAULT 'PENDING',
  retry_count    INTEGER NOT NULL DEFAULT 0,
  last_error     TEXT,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  published_at   TIMESTAMPTZ
);
CREATE INDEX outbox_events_pending_idx
  ON outbox_events (created_at) WHERE status = 'PENDING';
CREATE INDEX outbox_events_aggregate_idx
  ON outbox_events (aggregate_type, aggregate_id);

-- ---------- Consumer Idempotency Deduplication ------------------------
-- Ensures consumers processing Kafka events do not repeat business side-effects.
CREATE TABLE processed_events (
  event_id       TEXT NOT NULL,
  consumer_group TEXT NOT NULL,
  processed_at   TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (event_id, consumer_group)
);

-- =====================================================================
-- Stock and Order Functions: Atomic, Concurrency-Safe & Lock-Ordered
-- Strict Lock Hierarchy: ORDERS -> RESERVATIONS -> INVENTORY
-- =====================================================================

-- Reserve stock. Returns reservation id, or NULL if insufficient available stock.
-- Strict validation on positive quantity, positive TTL, and active store/product.
CREATE OR REPLACE FUNCTION reserve_stock(
  p_customer UUID,
  p_store    UUID,
  p_product  UUID,
  p_qty      INTEGER,
  p_ttl      INTERVAL DEFAULT INTERVAL '10 minutes'
) RETURNS UUID AS $$
DECLARE
  v_id UUID;
BEGIN
  -- 1. Parameter Validation
  IF p_qty IS NULL OR p_qty <= 0 THEN
    RAISE EXCEPTION 'qty must be positive' USING ERRCODE = '22023';
  END IF;

  IF p_ttl IS NULL OR p_ttl <= INTERVAL '0 seconds' THEN
    RAISE EXCEPTION 'TTL must be positive' USING ERRCODE = '22023';
  END IF;

  -- 2. Customer profile existence check
  IF NOT EXISTS (SELECT 1 FROM customers WHERE id = p_customer) THEN
    RAISE EXCEPTION 'Customer % does not exist', p_customer USING ERRCODE = '23503';
  END IF;

  -- 3. Active Store Validation
  IF NOT EXISTS (SELECT 1 FROM stores WHERE id = p_store AND is_active = TRUE) THEN
    IF EXISTS (SELECT 1 FROM stores WHERE id = p_store) THEN
      RAISE EXCEPTION 'Store % is inactive', p_store USING ERRCODE = '23514';
    ELSE
      RAISE EXCEPTION 'Store % does not exist', p_store USING ERRCODE = '23503';
    END IF;
  END IF;

  -- 4. Active Product Validation
  IF NOT EXISTS (SELECT 1 FROM products WHERE id = p_product AND is_active = TRUE) THEN
    IF EXISTS (SELECT 1 FROM products WHERE id = p_product) THEN
      RAISE EXCEPTION 'Product % is inactive', p_product USING ERRCODE = '23514';
    ELSE
      RAISE EXCEPTION 'Product % does not exist', p_product USING ERRCODE = '23503';
    END IF;
  END IF;

  PERFORM set_config('app.change_reason', 'RESERVE', true);

  -- 5. Atomic reservation update with row-level lock on inventory
  UPDATE inventory
     SET qty_reserved = qty_reserved + p_qty
   WHERE store_id   = p_store
     AND product_id = p_product
     AND qty_on_hand - qty_reserved >= p_qty;   -- the atomic overselling guard

  IF NOT FOUND THEN
    RETURN NULL;
  END IF;

  INSERT INTO reservations (customer_id, store_id, product_id, qty, expires_at)
  VALUES (p_customer, p_store, p_product, p_qty, clock_timestamp() + p_ttl)
  RETURNING id INTO v_id;

  RETURN v_id;
END;
$$ LANGUAGE plpgsql;

-- Link active reservations to a pending order during checkout.
-- Validates aggregate reservation quantities: SUM(qty) cannot exceed order item qty.
-- Strict Lock Order: ORDERS -> RESERVATIONS
CREATE OR REPLACE FUNCTION link_reservation_to_order(
  p_reservation UUID,
  p_order       UUID,
  p_customer    UUID
) RETURNS BOOLEAN AS $$
DECLARE
  v_order        RECORD;
  v_res          RECORD;
  v_order_qty    INTEGER;
  v_existing_qty INTEGER;
BEGIN
  -- 1. STRICT LOCK ORDER: Lock the order row FIRST
  SELECT id, customer_id, store_id, status INTO v_order
    FROM orders
   WHERE id = p_order
   FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Order % does not exist', p_order USING ERRCODE = '23503';
  END IF;

  -- 2. Verify order status is PENDING
  IF v_order.status <> 'PENDING' THEN
    RAISE EXCEPTION 'Cannot link reservation to order in % status (must be PENDING)', v_order.status
      USING ERRCODE = '23514';
  END IF;

  -- 3. Verify order.customer_id matches the supplied customer
  IF v_order.customer_id <> p_customer THEN
    RAISE EXCEPTION 'Order customer mismatch: order % belongs to % but supplied %',
      p_order, v_order.customer_id, p_customer USING ERRCODE = '42501';
  END IF;

  -- 4. STRICT LOCK ORDER: Lock the reservation row SECOND
  SELECT * INTO v_res
    FROM reservations
   WHERE id = p_reservation
   FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Reservation % does not exist', p_reservation USING ERRCODE = '23503';
  END IF;

  -- 5. Verify reservation status and real wall-clock expiry
  IF v_res.status <> 'ACTIVE' OR v_res.expires_at <= clock_timestamp() THEN
    RETURN FALSE; -- Cannot link inactive or expired reservation
  END IF;

  -- 6. Verify reservation customer ownership
  IF v_res.customer_id <> p_customer THEN
    RAISE EXCEPTION 'Reservation % belongs to customer %, not %',
      p_reservation, v_res.customer_id, p_customer USING ERRCODE = '42501';
  END IF;

  -- 7. Verify reservation store matches order store
  IF v_res.store_id <> v_order.store_id THEN
    RAISE EXCEPTION 'Reservation store % does not match order store %',
      v_res.store_id, v_order.store_id USING ERRCODE = '23514';
  END IF;

  -- 8. Prevent linking an already-linked reservation to an unrelated order
  IF v_res.order_id IS NOT NULL AND v_res.order_id <> p_order THEN
    RAISE EXCEPTION 'Reservation % is already linked to order %',
      p_reservation, v_res.order_id USING ERRCODE = '23514';
  END IF;

  -- 9. Check product existence in order and calculate total required quantity
  SELECT COALESCE(SUM(qty), 0) INTO v_order_qty
    FROM order_items
   WHERE order_id   = p_order
     AND product_id = v_res.product_id;

  IF v_order_qty = 0 THEN
    RAISE EXCEPTION 'Reserved product % is not part of order %', v_res.product_id, p_order
      USING ERRCODE = '23514';
  END IF;

  -- 10. Aggregate Quantity Validation:
  -- Sum all other ACTIVE linked reservations for this product on this order
  SELECT COALESCE(SUM(qty), 0) INTO v_existing_qty
    FROM reservations
   WHERE order_id   = p_order
     AND product_id = v_res.product_id
     AND id        <> p_reservation
     AND status     = 'ACTIVE'
     AND expires_at > clock_timestamp();

  IF v_existing_qty + v_res.qty > v_order_qty THEN
    RAISE EXCEPTION 'Cannot link reservation %: combined reserved quantity (%) exceeds order item quantity (%) for product %',
      p_reservation, (v_existing_qty + v_res.qty), v_order_qty, v_res.product_id
      USING ERRCODE = '23514';
  END IF;

  -- 11. Link reservation to order
  UPDATE reservations
     SET order_id = p_order
   WHERE id = p_reservation;

  RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

-- Atomically confirm an entire order upon successful checkout / payment.
-- Validates complete reservation coverage, consumes only valid unexpired reservations,
-- deducts inventory deterministically, transitions order to CONFIRMED, and writes order.placed outbox event.
-- Uses an immutable cutoff timestamp captured after acquiring order and reservation locks,
-- guaranteeing consistent expiration evaluation across all validation and deduction steps.
-- Strict Lock Order: ORDERS (by id) -> RESERVATIONS (by id) -> INVENTORY (by store_id, product_id)
CREATE OR REPLACE FUNCTION confirm_order(
  p_order_id UUID
) RETURNS BOOLEAN AS $$
DECLARE
  v_order         orders%ROWTYPE;
  v_item          RECORD;
  v_inv           RECORD;
  v_reserved_qty  INTEGER;
  v_cutoff        TIMESTAMPTZ;
  v_order_payload JSONB;
BEGIN
  -- 1. STRICT LOCK ORDER (Level 1): Lock the order row FIRST
  SELECT * INTO v_order
    FROM orders
   WHERE id = p_order_id
   FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Order % does not exist', p_order_id USING ERRCODE = '23503';
  END IF;

  -- 2. Verify order status is PENDING
  IF v_order.status <> 'PENDING' THEN
    RETURN FALSE; -- Cannot confirm an order that is already CONFIRMED or CANCELLED
  END IF;

  -- 3. Reject empty orders with no order items
  IF NOT EXISTS (SELECT 1 FROM order_items WHERE order_id = p_order_id) THEN
    RAISE EXCEPTION 'Order % has no order items', p_order_id USING ERRCODE = '23514';
  END IF;

  -- 4. STRICT LOCK ORDER (Level 2): Deterministically lock all linked reservations in ascending order by id
  PERFORM id
     FROM reservations
    WHERE order_id = p_order_id
    ORDER BY id
    FOR UPDATE;

  -- 5. CAPTURE SINGLE EXPIRATION CUTOFF TIMESTAMP
  -- Captured immediately after acquiring Level 1 (order) and Level 2 (reservations) locks.
  -- This single immutable timestamp v_cutoff is used CONSISTENTLY across all subsequent steps:
  -- expired reservation identification, coverage validation, inventory deduction, and consumption.
  v_cutoff := clock_timestamp();

  -- 6. Independent Relationship & Integrity Validations
  -- 6A. Verify customer ownership of all linked reservations
  IF EXISTS (
    SELECT 1 FROM reservations
     WHERE order_id = p_order_id
       AND customer_id <> v_order.customer_id
  ) THEN
    RAISE EXCEPTION 'Order % has linked reservations belonging to a different customer', p_order_id
      USING ERRCODE = '42501';
  END IF;

  -- 6B. Verify fulfilling store matches for all linked reservations
  IF EXISTS (
    SELECT 1 FROM reservations
     WHERE order_id = p_order_id
       AND store_id <> v_order.store_id
  ) THEN
    RAISE EXCEPTION 'Order % has linked reservations from a different store', p_order_id
      USING ERRCODE = '23514';
  END IF;

  -- 6C. Verify every linked reservation product belongs to an order item
  IF EXISTS (
    SELECT 1 FROM reservations r
     WHERE r.order_id = p_order_id
       AND NOT EXISTS (
         SELECT 1 FROM order_items oi
          WHERE oi.order_id = p_order_id
            AND oi.product_id = r.product_id
       )
  ) THEN
    RAISE EXCEPTION 'Order % has linked reservations for products not in order items', p_order_id
      USING ERRCODE = '23514';
  END IF;

  -- 7. Deterministically release any expired active reservations linked to this order
  -- Uses the exact immutable v_cutoff timestamp.
  -- Aggregates expired quantities by (store_id, product_id) and updates inventory
  -- in strictly deterministic ascending ORDER BY store_id, product_id (Level 3 lock ordering).
  PERFORM set_config('app.change_reason', 'EXPIRE', true);

  FOR v_inv IN
    SELECT store_id, product_id, SUM(qty) AS total_qty
      FROM reservations
     WHERE order_id   = p_order_id
       AND status     = 'ACTIVE'
       AND expires_at <= v_cutoff
     GROUP BY store_id, product_id
     ORDER BY store_id, product_id
  LOOP
    UPDATE inventory
       SET qty_reserved = qty_reserved - v_inv.total_qty
     WHERE store_id   = v_inv.store_id
       AND product_id = v_inv.product_id;
  END LOOP;

  UPDATE reservations
     SET status = 'EXPIRED'
   WHERE order_id   = p_order_id
     AND status     = 'ACTIVE'
     AND expires_at <= v_cutoff;

  -- 8. Validate complete active unexpired reservation coverage for EVERY line item
  -- Evaluated against the exact same immutable v_cutoff timestamp.
  FOR v_item IN
    SELECT product_id, qty
      FROM order_items
     WHERE order_id = p_order_id
     ORDER BY product_id
  LOOP
    SELECT COALESCE(SUM(qty), 0) INTO v_reserved_qty
      FROM reservations
     WHERE order_id   = p_order_id
       AND product_id = v_item.product_id
       AND status     = 'ACTIVE'
       AND expires_at > v_cutoff;

    IF v_reserved_qty <> v_item.qty THEN
      RAISE EXCEPTION 'Order % item % requires qty %, but active valid linked reservation total is %',
        p_order_id, v_item.product_id, v_item.qty, v_reserved_qty
        USING ERRCODE = '23514';
    END IF;
  END LOOP;

  -- 9. STRICT LOCK ORDER (Level 3): Deterministic Inventory Deduction & Reservation Consumption
  -- Aggregate valid unexpired reservation quantities (using the exact same v_cutoff)
  -- and acquire/update inventory rows in deterministic ascending ORDER BY store_id, product_id.
  PERFORM set_config('app.change_reason', 'CONFIRM', true);

  FOR v_inv IN
    SELECT store_id, product_id, SUM(qty) AS total_qty
      FROM reservations
     WHERE order_id   = p_order_id
       AND status     = 'ACTIVE'
       AND expires_at > v_cutoff
     GROUP BY store_id, product_id
     ORDER BY store_id, product_id
  LOOP
    UPDATE inventory
       SET qty_on_hand  = qty_on_hand  - v_inv.total_qty,
           qty_reserved = qty_reserved - v_inv.total_qty
     WHERE store_id   = v_inv.store_id
       AND product_id = v_inv.product_id;
  END LOOP;

  -- Transition only the valid unexpired reservations to CONSUMED
  UPDATE reservations
     SET status = 'CONSUMED'
   WHERE order_id   = p_order_id
     AND status     = 'ACTIVE'
     AND expires_at > v_cutoff;

  -- 10. Transition Order Status to CONFIRMED
  UPDATE orders
     SET status = 'CONFIRMED'
   WHERE id = p_order_id;

  -- 11. Insert order.placed event into outbox_events in the SAME transaction
  SELECT jsonb_build_object(
    'order_id', v_order.id,
    'order_number', v_order.order_number,
    'customer_id', v_order.customer_id,
    'store_id', v_order.store_id,
    'total_paise', v_order.total_paise,
    'confirmed_at', v_cutoff,
    'items', (
      SELECT jsonb_agg(
        jsonb_build_object(
          'product_id', oi.product_id,
          'qty', oi.qty,
          'unit_price_paise', oi.unit_price_paise
        )
      )
      FROM order_items oi
      WHERE oi.order_id = p_order_id
    )
  ) INTO v_order_payload;

  INSERT INTO outbox_events (aggregate_type, aggregate_id, event_type, payload)
  VALUES ('order', p_order_id::text, 'order.placed', v_order_payload);

  RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

-- Backward-compatibility wrapper for single-reservation call sites.
-- Validates reservation linkage and unexpired status before delegating to atomic order-level confirmation.
CREATE OR REPLACE FUNCTION confirm_reservation(
  p_reservation UUID,
  p_order       UUID
) RETURNS BOOLEAN AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM reservations
     WHERE id = p_reservation
       AND order_id = p_order
       AND status = 'ACTIVE'
       AND expires_at > clock_timestamp()
  ) THEN
    RETURN FALSE;
  END IF;

  RETURN confirm_order(p_order);
END;
$$ LANGUAGE plpgsql;

-- Give stock back (payment failed, cart abandoned, or expired).
-- Explicitly validates non-NULL status (RELEASED or EXPIRED).
-- Rechecks clock_timestamp() if releasing for EXPIRED to prevent race conditions.
CREATE OR REPLACE FUNCTION release_reservation(
  p_reservation UUID,
  p_status      reservation_status DEFAULT 'RELEASED'
) RETURNS BOOLEAN AS $$
DECLARE
  r reservations%ROWTYPE;
BEGIN
  IF p_status IS NULL OR p_status NOT IN ('RELEASED', 'EXPIRED') THEN
    RAISE EXCEPTION 'p_status must be RELEASED or EXPIRED' USING ERRCODE = '22023';
  END IF;

  SELECT * INTO r
    FROM reservations
   WHERE id = p_reservation AND status = 'ACTIVE'
   FOR UPDATE;

  IF NOT FOUND THEN
    RETURN FALSE;
  END IF;

  -- If releasing because of expiration, verify that it is indeed expired right now
  IF p_status = 'EXPIRED' AND r.expires_at > clock_timestamp() THEN
    RETURN FALSE;
  END IF;

  PERFORM set_config('app.change_reason',
                     CASE WHEN p_status = 'EXPIRED' THEN 'EXPIRE' ELSE 'RELEASE' END,
                     true);

  UPDATE inventory
     SET qty_reserved = qty_reserved - r.qty
   WHERE store_id = r.store_id AND product_id = r.product_id;

  UPDATE reservations SET status = p_status WHERE id = p_reservation;
  RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

-- Release every reservation whose time is up. Safe to run from several
-- workers at once (SKIP LOCKED). Returns how many were expired.
-- Deterministic Lock Ordering:
-- 1. Selects candidate earliest-expiring active reservation IDs using ORDER BY expires_at, id LIMIT p_batch.
-- 2. Acquires Level 2 row locks in deterministic ascending ORDER BY r.id FOR UPDATE OF r SKIP LOCKED,
--    guaranteeing identical lock acquisition sequence with confirm_order() and cancel_order().
-- 3. Aggregates expired quantities by (store_id, product_id) in ascending order.
-- 4. Updates inventory qty_reserved in deterministic ascending ORDER BY store_id, product_id (Level 3).
CREATE OR REPLACE FUNCTION expire_reservations(p_batch INTEGER DEFAULT 500)
RETURNS INTEGER AS $$
DECLARE
  v_count  INTEGER := 0;
  v_inv    RECORD;
  v_cutoff TIMESTAMPTZ;
BEGIN
  IF p_batch IS NULL OR p_batch <= 0 THEN
    RAISE EXCEPTION 'p_batch must be positive' USING ERRCODE = '22023';
  END IF;
  p_batch := LEAST(p_batch, 5000);

  v_cutoff := clock_timestamp();

  PERFORM set_config('app.change_reason', 'EXPIRE', true);

  FOR v_inv IN
    WITH candidate_ids AS (
      SELECT id
        FROM reservations
       WHERE status = 'ACTIVE'
         AND expires_at <= v_cutoff
       ORDER BY expires_at, id
       LIMIT p_batch
    ),
    locked_candidates AS (
      SELECT r.id, r.store_id, r.product_id, r.qty
        FROM reservations r
        JOIN candidate_ids c ON c.id = r.id
       WHERE r.status = 'ACTIVE'
         AND r.expires_at <= v_cutoff
       ORDER BY r.id
         FOR UPDATE OF r SKIP LOCKED
    )
    SELECT store_id, product_id, SUM(qty) AS total_qty, array_agg(id) AS res_ids
      FROM locked_candidates
     GROUP BY store_id, product_id
     ORDER BY store_id, product_id
  LOOP
    UPDATE inventory
       SET qty_reserved = qty_reserved - v_inv.total_qty
     WHERE store_id   = v_inv.store_id
       AND product_id = v_inv.product_id;

    UPDATE reservations
       SET status = 'EXPIRED'
     WHERE id = ANY(v_inv.res_ids);

    v_count := v_count + cardinality(v_inv.res_ids);
  END LOOP;

  RETURN v_count;
END;
$$ LANGUAGE plpgsql;

-- Cancel an order atomically, restoring inventory exactly once.
-- Handles multiple products, ownership validation, and concurrent requests safely.
-- Strict Lock Order: ORDERS (by id) -> RESERVATIONS (by id) -> INVENTORY (by store_id, product_id)
CREATE OR REPLACE FUNCTION cancel_order(
  p_order_id    UUID,
  p_customer_id UUID DEFAULT NULL,  -- Optional: customer ownership check
  p_reason      TEXT DEFAULT 'Order cancelled'
) RETURNS BOOLEAN AS $$
DECLARE
  v_order RECORD;
  v_item  RECORD;
  v_res   RECORD;
BEGIN
  -- 1. STRICT LOCK ORDER (Level 1): Lock the order row FIRST
  SELECT * INTO v_order
    FROM orders
   WHERE id = p_order_id
     FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Order % not found', p_order_id USING ERRCODE = 'P0002';
  END IF;

  -- 2. Customer ownership verification (if customer_id provided)
  IF p_customer_id IS NOT NULL AND v_order.customer_id <> p_customer_id THEN
    RAISE EXCEPTION 'Unauthorized: order does not belong to specified customer'
      USING ERRCODE = '42501';
  END IF;

  -- 3. Idempotent check: if already cancelled, return FALSE without double restoration
  IF v_order.status = 'CANCELLED' THEN
    RETURN FALSE;
  END IF;

  -- 4. Status validation: can only cancel PENDING or CONFIRMED orders
  IF v_order.status NOT IN ('PENDING', 'CONFIRMED') THEN
    RAISE EXCEPTION 'Cannot cancel order in % state', v_order.status
      USING ERRCODE = '23514';
  END IF;

  -- 5. Transition order status to CANCELLED (triggers enforce_order_transition)
  UPDATE orders
     SET status = 'CANCELLED'
   WHERE id = p_order_id;

  -- 6. STRICT LOCK ORDER (Level 3): Inventory Restoration
  IF v_order.status = 'CONFIRMED' THEN
    -- Confirmed orders had stock deducted from qty_on_hand. Restore it!
    -- Aggregate and lock/update inventory deterministically by product_id (store_id is fixed)
    PERFORM set_config('app.change_reason', 'ORDER_CANCELLED', true);

    FOR v_item IN
      SELECT product_id, SUM(qty) AS total_qty
        FROM order_items
       WHERE order_id = p_order_id
       GROUP BY product_id
       ORDER BY product_id
    LOOP
      UPDATE inventory
         SET qty_on_hand = qty_on_hand + v_item.total_qty
       WHERE store_id   = v_order.store_id
         AND product_id = v_item.product_id;
    END LOOP;

  ELSIF v_order.status = 'PENDING' THEN
    -- STRICT LOCK ORDER (Level 2): Lock linked reservations deterministically
    PERFORM id
       FROM reservations
      WHERE order_id = p_order_id
        AND status   = 'ACTIVE'
      ORDER BY id
      FOR UPDATE;

    -- STRICT LOCK ORDER (Level 3): Aggregate and release inventory in deterministic ORDER BY store_id, product_id
    PERFORM set_config('app.change_reason', 'ORDER_CANCELLED', true);

    FOR v_item IN
      SELECT store_id, product_id, SUM(qty) AS total_qty
        FROM reservations
       WHERE order_id = p_order_id
         AND status   = 'ACTIVE'
       GROUP BY store_id, product_id
       ORDER BY store_id, product_id
    LOOP
      UPDATE inventory
         SET qty_reserved = qty_reserved - v_item.total_qty
       WHERE store_id   = v_item.store_id
         AND product_id = v_item.product_id;
    END LOOP;

    -- Update linked active reservations to RELEASED
    UPDATE reservations
       SET status = 'RELEASED'
     WHERE order_id = p_order_id
       AND status   = 'ACTIVE';
  END IF;

  -- 7. Record outbox event for Kafka (order.cancelled)
  INSERT INTO outbox_events (aggregate_type, aggregate_id, event_type, payload)
  VALUES (
    'order',
    p_order_id::text,
    'order.cancelled',
    jsonb_build_object(
      'order_id', p_order_id,
      'customer_id', v_order.customer_id,
      'store_id', v_order.store_id,
      'reason', p_reason,
      'cancelled_at', clock_timestamp()
    )
  );

  RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

COMMIT;
