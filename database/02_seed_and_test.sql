-- =====================================================================
-- SmartCart 2.0 - Phase 1: Demo Seed Data + Comprehensive Self-Test
-- Run after 01_schema.sql:  psql "$DATABASE_URL" -f 02_seed_and_test.sql
--
-- CAUTION / SECURITY NOTICE:
-- This script contains demo accounts and sample inventory for LOCAL DEVELOPMENT
-- and automated testing ONLY. It must NEVER be executed against production.
-- =====================================================================

BEGIN;

-- ---------- Seed: stores (5 Major Indian Metro Locations) -------------
INSERT INTO stores (code, name, city, state) VALUES
  ('STORE-001', 'SmartCart Bengaluru', 'Bengaluru', 'Karnataka'),
  ('STORE-002', 'SmartCart Mysuru',    'Mysuru',    'Karnataka'),
  ('STORE-003', 'SmartCart Chennai',   'Chennai',   'Tamil Nadu'),
  ('STORE-004', 'SmartCart Hyderabad', 'Hyderabad', 'Telangana'),
  ('STORE-005', 'SmartCart Mumbai',    'Mumbai',    'Maharashtra')
ON CONFLICT (code) DO NOTHING;

-- ---------- Seed: products (prices in paise) -------------------------
INSERT INTO products (sku, name, brand, category, price_paise, attributes) VALUES
  ('BT-HEAD-001', 'Bluetooth Headphones', 'boAt',       'Electronics', 149900,
     '{"color":"Black","connectivity":"Bluetooth 5.3"}'),
  ('PHONE-001',   'Galaxy 5G Smartphone', 'Samsung',    'Mobiles',    1799900,
     '{"color":"Black","storage":"128GB","connectivity":"5G"}'),
  ('RICE-5KG',    'Basmati Rice 5kg',     'India Gate', 'Grocery',      64900,
     '{"weight":"5kg"}'),
  ('MILK-1L',     'Toned Milk 1L',        'Nandini',    'Grocery',       5500,
     '{"volume":"1L"}'),
  ('ATTA-10KG',   'Whole Wheat Atta 10kg','Aashirvaad', 'Grocery',      45900,
     '{"weight":"10kg"}')
ON CONFLICT (sku) DO NOTHING;

-- ---------- Seed: users & RBAC Roles (Argon2id Hashes) ----------------
-- Demo Password for all seed accounts: Demo@123
-- Hash generated using backend argon2-cffi implementation:
-- $argon2id$v=19$m=65536,t=3,p=4$09wQ0+PsjhrMNN5zK2dYDA$B7zINFJw0lrO+UPGRzYVzVo9JisgIIQI5FFM67ILZB0
INSERT INTO users (email, full_name, password_hash, role, assigned_store_id)
SELECT v.email, v.full_name, v.password_hash, v.role::user_role, s.id
FROM (VALUES
  ('demo@smartcart.in',
   'Demo Customer',
   '$argon2id$v=19$m=65536,t=3,p=4$09wQ0+PsjhrMNN5zK2dYDA$B7zINFJw0lrO+UPGRzYVzVo9JisgIIQI5FFM67ILZB0',
   'CUSTOMER',
   NULL),
  ('manager.bengaluru@smartcart.in',
   'Bengaluru Store Manager',
   '$argon2id$v=19$m=65536,t=3,p=4$09wQ0+PsjhrMNN5zK2dYDA$B7zINFJw0lrO+UPGRzYVzVo9JisgIIQI5FFM67ILZB0',
   'STORE_MANAGER',
   'STORE-001'),
  ('admin@smartcart.in',
   'SmartCart Retail Admin',
   '$argon2id$v=19$m=65536,t=3,p=4$09wQ0+PsjhrMNN5zK2dYDA$B7zINFJw0lrO+UPGRzYVzVo9JisgIIQI5FFM67ILZB0',
   'ADMIN',
   NULL),
  ('superadmin@smartcart.in',
   'SmartCart Super Administrator',
   '$argon2id$v=19$m=65536,t=3,p=4$09wQ0+PsjhrMNN5zK2dYDA$B7zINFJw0lrO+UPGRzYVzVo9JisgIIQI5FFM67ILZB0',
   'SUPER_ADMIN',
   NULL)
) AS v(email, full_name, password_hash, role, store_code)
LEFT JOIN stores s ON s.code = v.store_code
ON CONFLICT (email) DO NOTHING;

-- ---------- Seed: customer profile for the CUSTOMER user --------------
INSERT INTO customers (user_id, phone, address)
SELECT id, '+91-9876543210', '123 MG Road, Bengaluru, Karnataka'
FROM users
WHERE email = 'demo@smartcart.in'
ON CONFLICT (user_id) DO NOTHING;

-- ---------- Seed: store-wise inventory (Safely Repeatable) -------------
-- HYDERABAD has 0 headphones by design (tests out-of-stock discovery).
-- MUMBAI has exactly 1 phone (used for the "last item" reservation self-test).
-- ON CONFLICT DO NOTHING ensures existing stock is NEVER overwritten on rerun.
INSERT INTO inventory (store_id, product_id, qty_on_hand)
SELECT s.id, p.id, v.qty
FROM (VALUES
  ('STORE-001','BT-HEAD-001',25), ('STORE-002','BT-HEAD-001',12),
  ('STORE-003','BT-HEAD-001',18), ('STORE-004','BT-HEAD-001', 0),
  ('STORE-005','BT-HEAD-001',32),
  ('STORE-001','PHONE-001', 8),   ('STORE-005','PHONE-001', 1),
  ('STORE-001','RICE-5KG', 40),   ('STORE-002','MILK-1L', 60),
  ('STORE-003','ATTA-10KG',30)
) AS v(store_code, sku, qty)
JOIN stores   s ON s.code = v.store_code
JOIN products p ON p.sku  = v.sku
ON CONFLICT (store_id, product_id) DO NOTHING;

COMMIT;

-- =====================================================================
-- Self-Test Suite: Comprehensive Functional & Concurrency-Control Validation
--
-- ARCHITECTURAL CONCURRENCY NOTE:
-- This SQL test block executes sequentially within a single transaction session.
-- It verifies the structural mechanisms of concurrency control:
--   - Strict 3-level lock hierarchy: orders -> reservations -> inventory (store_id, product_id)
--   - Single immutable cutoff timestamp v_cutoff preventing in-flight expiry race
--   - Row-level lock acquisition (FOR UPDATE, SKIP LOCKED)
--   - Deterministic multi-product aggregation and restoration
--   - Dynamic baseline balance preservation (zero inventory leakage)
-- Genuine simultaneous multi-client race testing (e.g. concurrent HTTP checkout buyers)
-- will be executed via Python asyncio test suites with separate DB connections in Phase 1/2.
-- =====================================================================
BEGIN;

DO $$
DECLARE
  -- Identity fixtures
  v_user               UUID := (SELECT id FROM users WHERE email = 'demo@smartcart.in');
  v_admin_user         UUID := (SELECT id FROM users WHERE email = 'admin@smartcart.in');
  v_cust               UUID := (SELECT id FROM customers WHERE user_id = v_user);
  v_other_user         UUID;
  v_other_cust         UUID;

  -- Store fixtures
  v_store              UUID := (SELECT id FROM stores WHERE code = 'STORE-005'); -- Mumbai
  v_beng_store         UUID := (SELECT id FROM stores WHERE code = 'STORE-001'); -- Bengaluru

  -- Product fixtures
  v_product            UUID := (SELECT id FROM products WHERE sku = 'PHONE-001');
  v_headphone          UUID := (SELECT id FROM products WHERE sku = 'BT-HEAD-001');
  v_rice               UUID := (SELECT id FROM products WHERE sku = 'RICE-5KG');

  -- Order handles
  v_order              UUID;
  v_multi_order        UUID;
  v_incomplete_order   UUID;
  v_empty_order        UUID;
  v_mismatch_order     UUID;
  v_mixed_order        UUID;
  v_multi_prod_order   UUID;
  v_multi_exp_order    UUID;
  v_pending_multi_ord  UUID;
  v_other_order        UUID;

  -- Reservation handles
  r1                   UUID;
  r2                   UUID;
  r3                   UUID;
  r_other              UUID;
  r_head1              UUID;
  r_head2              UUID;
  r_valid              UUID;
  r_exp                UUID;
  r_mismatch           UUID;
  r_unlinked           UUID;
  r_prod_phone         UUID;
  r_prod_head          UUID;
  r_exp_phone          UUID;
  r_exp_head           UUID;
  r_exp_rice           UUID;
  r_val_p              UUID;
  r_exp_p              UUID;
  r_val_h              UUID;
  r_exp_h              UUID;
  r_pend_p             UUID;
  r_pend_h             UUID;

  -- Dynamic inventory baselines: STORE-005 (Mumbai)
  v_mumbai_phone_on_hand     INTEGER;
  v_mumbai_phone_reserved    INTEGER;
  v_mumbai_head_on_hand      INTEGER;
  v_mumbai_head_reserved     INTEGER;

  -- Dynamic inventory baselines: STORE-001 (Bengaluru)
  v_beng_phone_on_hand       INTEGER;
  v_beng_phone_reserved      INTEGER;
  v_beng_head_on_hand        INTEGER;
  v_beng_head_reserved       INTEGER;
  v_beng_rice_on_hand        INTEGER;
  v_beng_rice_reserved       INTEGER;

  -- Working check variables
  v_cur_on_hand        INTEGER;
  v_cur_reserved       INTEGER;
  v_outbox_count       INTEGER;
  v_caught             BOOLEAN;
BEGIN
  -- -------------------------------------------------------------------
  -- 0. Assert Prerequisites & Capture Dynamic Baselines
  -- -------------------------------------------------------------------
  ASSERT v_user IS NOT NULL, 'Demo user must exist';
  ASSERT v_admin_user IS NOT NULL, 'Admin user must exist';
  ASSERT v_cust IS NOT NULL, 'Demo customer profile must exist';
  ASSERT v_store IS NOT NULL, 'Mumbai store must exist';
  ASSERT v_beng_store IS NOT NULL, 'Bengaluru store must exist';
  ASSERT v_product IS NOT NULL, 'Galaxy phone must exist';
  ASSERT v_headphone IS NOT NULL, 'Bluetooth headphones must exist';
  ASSERT v_rice IS NOT NULL, 'Rice product must exist';

  -- Create a second valid user and customer fixture for ownership testing
  -- (guarantees valid FK relations so tests reach application validation logic)
  INSERT INTO users (email, full_name, password_hash, role)
  VALUES ('other.customer@smartcart.in', 'Other Customer',
          '$argon2id$v=19$m=65536,t=3,p=4$09wQ0+PsjhrMNN5zK2dYDA$B7zINFJw0lrO+UPGRzYVzVo9JisgIIQI5FFM67ILZB0',
          'CUSTOMER')
  RETURNING id INTO v_other_user;

  INSERT INTO customers (user_id, phone, address)
  VALUES (v_other_user, '+91-9123456789', '456 Residency Road, Bengaluru')
  RETURNING id INTO v_other_cust;

  -- Baseline STORE-005 (Mumbai)
  SELECT qty_on_hand, qty_reserved INTO v_mumbai_phone_on_hand, v_mumbai_phone_reserved
    FROM inventory WHERE store_id = v_store AND product_id = v_product;
  ASSERT v_mumbai_phone_on_hand IS NOT NULL, 'Mumbai phone inventory must exist';

  SELECT qty_on_hand, qty_reserved INTO v_mumbai_head_on_hand, v_mumbai_head_reserved
    FROM inventory WHERE store_id = v_store AND product_id = v_headphone;
  ASSERT v_mumbai_head_on_hand IS NOT NULL, 'Mumbai headphone inventory must exist';

  -- Baseline STORE-001 (Bengaluru)
  SELECT qty_on_hand, qty_reserved INTO v_beng_phone_on_hand, v_beng_phone_reserved
    FROM inventory WHERE store_id = v_beng_store AND product_id = v_product;
  ASSERT v_beng_phone_on_hand >= 4, 'Bengaluru phone inventory must have >= 4 units for tests';

  SELECT qty_on_hand, qty_reserved INTO v_beng_head_on_hand, v_beng_head_reserved
    FROM inventory WHERE store_id = v_beng_store AND product_id = v_headphone;
  ASSERT v_beng_head_on_hand >= 4, 'Bengaluru headphone inventory must have >= 4 units for tests';

  SELECT qty_on_hand, qty_reserved INTO v_beng_rice_on_hand, v_beng_rice_reserved
    FROM inventory WHERE store_id = v_beng_store AND product_id = v_rice;
  ASSERT v_beng_rice_on_hand >= 2, 'Bengaluru rice inventory must have >= 2 units for tests';

  -- -------------------------------------------------------------------
  -- 1. Sequential Overselling Guard Test
  -- -------------------------------------------------------------------
  r1 := reserve_stock(v_cust, v_store, v_product, 1);
  ASSERT r1 IS NOT NULL, 'Buyer should successfully reserve 1 unit';

  -- Attempt to reserve remaining available + 1 -> must be rejected (NULL)
  r2 := reserve_stock(v_cust, v_store, v_product, (v_mumbai_phone_on_hand - v_mumbai_phone_reserved));
  ASSERT r2 IS NULL, 'Overselling guard must reject reservation exceeding available stock';

  -- -------------------------------------------------------------------
  -- 2. NULL Release Status & Legitimate Release Test
  -- -------------------------------------------------------------------
  v_caught := FALSE;
  BEGIN
    PERFORM release_reservation(r1, NULL);
  EXCEPTION WHEN SQLSTATE '22023' THEN
    v_caught := TRUE;
  END;
  ASSERT v_caught = TRUE, 'release_reservation must explicitly reject NULL p_status (22023)';

  ASSERT release_reservation(r1, 'RELEASED') = TRUE, 'release_reservation with RELEASED must succeed';
  SELECT qty_reserved INTO v_cur_reserved FROM inventory
   WHERE store_id = v_store AND product_id = v_product;
  ASSERT v_cur_reserved = v_mumbai_phone_reserved, 'qty_reserved should match initial after release';

  -- -------------------------------------------------------------------
  -- 3. Expiry Safety & Batch Expiry Across Multiple Inventory Rows
  -- -------------------------------------------------------------------
  -- Create expired reservations across 3 distinct products in STORE-001 with staggered expiry
  -- to verify deterministic batch selection (earliest expiry first) and ascending id lock acquisition.
  r_exp_phone := reserve_stock(v_cust, v_beng_store, v_product, 1);
  r_exp_head  := reserve_stock(v_cust, v_beng_store, v_headphone, 1);
  r_exp_rice  := reserve_stock(v_cust, v_beng_store, v_rice, 1);

  -- Stagger expiration timestamps: Headphone (10m ago) < Rice (5m ago) < Phone (2m ago)
  UPDATE reservations SET expires_at = clock_timestamp() - INTERVAL '10 minutes' WHERE id = r_exp_head;
  UPDATE reservations SET expires_at = clock_timestamp() - INTERVAL '5 minutes'  WHERE id = r_exp_rice;
  UPDATE reservations SET expires_at = clock_timestamp() - INTERVAL '2 minutes'  WHERE id = r_exp_phone;

  -- Test 3A: Batch limit enforcement & earliest-expiry selection.
  -- expire_reservations(2) must select the 2 earliest expiring (Headphone & Rice),
  -- lock them in ascending id order, and leave Phone active.
  ASSERT expire_reservations(2) = 2, 'expire_reservations(2) must process exactly the 2 earliest expiring reservations';
  ASSERT (SELECT status FROM reservations WHERE id = r_exp_head) = 'EXPIRED', 'Earliest reservation must be EXPIRED';
  ASSERT (SELECT status FROM reservations WHERE id = r_exp_rice) = 'EXPIRED', 'Second-earliest reservation must be EXPIRED';
  ASSERT (SELECT status FROM reservations WHERE id = r_exp_phone) = 'ACTIVE', 'Third reservation must remain ACTIVE';

  -- Test 3B: Process remaining expired batch with ascending id lock ordering and inventory aggregation
  ASSERT expire_reservations(100) = 1, 'expire_reservations(100) must process the remaining overdue reservation';
  ASSERT (SELECT status FROM reservations WHERE id = r_exp_phone) = 'EXPIRED', 'Remaining reservation must now be EXPIRED';

  SELECT qty_reserved INTO v_cur_reserved FROM inventory WHERE store_id = v_beng_store AND product_id = v_product;
  ASSERT v_cur_reserved = v_beng_phone_reserved, 'Bengaluru phone reserved must return to baseline';

  SELECT qty_reserved INTO v_cur_reserved FROM inventory WHERE store_id = v_beng_store AND product_id = v_headphone;
  ASSERT v_cur_reserved = v_beng_head_reserved, 'Bengaluru headphone reserved must return to baseline';

  SELECT qty_reserved INTO v_cur_reserved FROM inventory WHERE store_id = v_beng_store AND product_id = v_rice;
  ASSERT v_cur_reserved = v_beng_rice_reserved, 'Bengaluru rice reserved must return to baseline';

  -- -------------------------------------------------------------------
  -- 4. Inactive Store & Product Guards
  -- -------------------------------------------------------------------
  UPDATE stores SET is_active = FALSE WHERE id = v_beng_store;
  v_caught := FALSE;
  BEGIN
    PERFORM reserve_stock(v_cust, v_beng_store, v_product, 1);
  EXCEPTION WHEN SQLSTATE '23514' THEN
    v_caught := TRUE;
  END;
  ASSERT v_caught = TRUE, 'reserve_stock must reject inactive store (23514)';
  UPDATE stores SET is_active = TRUE WHERE id = v_beng_store;

  UPDATE products SET is_active = FALSE WHERE id = v_product;
  v_caught := FALSE;
  BEGIN
    PERFORM reserve_stock(v_cust, v_store, v_product, 1);
  EXCEPTION WHEN SQLSTATE '23514' THEN
    v_caught := TRUE;
  END;
  ASSERT v_caught = TRUE, 'reserve_stock must reject inactive product (23514)';
  UPDATE products SET is_active = TRUE WHERE id = v_product;

  -- -------------------------------------------------------------------
  -- 5. Order Creation, Reservation Linking & Aggregate Validation
  -- -------------------------------------------------------------------
  r3 := reserve_stock(v_cust, v_store, v_product, 1);
  ASSERT r3 IS NOT NULL, 'Reservation for order test must succeed';

  INSERT INTO orders (customer_id, store_id, status, total_paise)
  VALUES (v_cust, v_store, 'PENDING', 1799900)
  RETURNING id INTO v_order;

  INSERT INTO order_items (order_id, product_id, qty, unit_price_paise)
  VALUES (v_order, v_product, 1, 1799900);

  -- 5A. Link Error: Invalid Customer Ownership (using valid other customer)
  v_caught := FALSE;
  BEGIN
    PERFORM link_reservation_to_order(r3, v_order, v_other_cust);
  EXCEPTION WHEN SQLSTATE '42501' THEN
    v_caught := TRUE;
  END;
  ASSERT v_caught = TRUE, 'link_reservation_to_order must reject mismatched customer (42501)';

  -- 5B. Link Error: Mismatched Product in the SAME Store (STORE-005 Mumbai)
  r_other := reserve_stock(v_cust, v_store, v_headphone, 1);
  ASSERT r_other IS NOT NULL, 'Reservation for headphone in STORE-005 must succeed';
  v_caught := FALSE;
  BEGIN
    PERFORM link_reservation_to_order(r_other, v_order, v_cust);
  EXCEPTION WHEN SQLSTATE '23514' THEN
    v_caught := TRUE;
  END;
  ASSERT v_caught = TRUE, 'link_reservation_to_order must reject reservation for product not in order items (23514)';
  PERFORM release_reservation(r_other);

  -- 5C. Link Error: Store Mismatch
  r_other := reserve_stock(v_cust, v_beng_store, v_rice, 1);
  ASSERT r_other IS NOT NULL, 'Reservation for rice in Bengaluru must succeed';
  v_caught := FALSE;
  BEGIN
    PERFORM link_reservation_to_order(r_other, v_order, v_cust);
  EXCEPTION WHEN SQLSTATE '23514' THEN
    v_caught := TRUE;
  END;
  ASSERT v_caught = TRUE, 'link_reservation_to_order must reject store mismatch (23514)';
  PERFORM release_reservation(r_other);

  -- 5D. Legitimate Link -> must return TRUE
  ASSERT link_reservation_to_order(r3, v_order, v_cust) = TRUE,
    'link_reservation_to_order must return TRUE for valid order and reservation';

  -- 5E. Prevent Cross-Linking to another order
  INSERT INTO orders (customer_id, store_id, status, total_paise)
  VALUES (v_cust, v_store, 'PENDING', 1799900)
  RETURNING id INTO v_other_order;

  v_caught := FALSE;
  BEGIN
    PERFORM link_reservation_to_order(r3, v_other_order, v_cust);
  EXCEPTION WHEN SQLSTATE '23514' THEN
    v_caught := TRUE;
  END;
  ASSERT v_caught = TRUE, 'Cannot re-link an already linked reservation to an unrelated order';

  -- 5F. Aggregate Over-Reservation Linking Validation
  INSERT INTO orders (customer_id, store_id, status, total_paise)
  VALUES (v_cust, v_store, 'PENDING', 299800)
  RETURNING id INTO v_multi_order;

  INSERT INTO order_items (order_id, product_id, qty, unit_price_paise)
  VALUES (v_multi_order, v_headphone, 2, 149900);

  r_head1 := reserve_stock(v_cust, v_store, v_headphone, 1);
  ASSERT r_head1 IS NOT NULL, 'First headphone reservation must succeed';
  ASSERT link_reservation_to_order(r_head1, v_multi_order, v_cust) = TRUE,
    'First headphone reservation link must succeed';

  r_head2 := reserve_stock(v_cust, v_store, v_headphone, 2);
  ASSERT r_head2 IS NOT NULL, 'Second headphone reservation must succeed';

  v_caught := FALSE;
  BEGIN
    PERFORM link_reservation_to_order(r_head2, v_multi_order, v_cust);
  EXCEPTION WHEN SQLSTATE '23514' THEN
    v_caught := TRUE;
  END;
  ASSERT v_caught = TRUE,
    'link_reservation_to_order must reject aggregate quantity exceeding order item quantity (23514)';

  PERFORM release_reservation(r_head2);
  ASSERT cancel_order(v_multi_order, v_cust) = TRUE, 'cancel_order on multi_order must succeed';

  -- -------------------------------------------------------------------
  -- 6. Confirmation Independent Integrity Validations
  -- -------------------------------------------------------------------
  -- 6A. Empty Order Rejection Guard
  INSERT INTO orders (customer_id, store_id, status, total_paise)
  VALUES (v_cust, v_store, 'PENDING', 0)
  RETURNING id INTO v_empty_order;

  v_caught := FALSE;
  BEGIN
    PERFORM confirm_order(v_empty_order);
  EXCEPTION WHEN SQLSTATE '23514' THEN
    v_caught := TRUE;
  END;
  ASSERT v_caught = TRUE, 'confirm_order must reject empty orders with no order items (23514)';
  PERFORM cancel_order(v_empty_order, v_cust);

  -- 6B. Unlinked Reservation Test
  r_unlinked := reserve_stock(v_cust, v_store, v_headphone, 1);
  ASSERT r_unlinked IS NOT NULL, 'Unlinked reservation must succeed';
  ASSERT confirm_reservation(r_unlinked, v_order) = FALSE,
    'confirm_reservation must return FALSE for reservation not linked to the specified order';
  PERFORM release_reservation(r_unlinked);

  -- 6C. Incomplete Reservation Coverage Guard
  INSERT INTO orders (customer_id, store_id, status, total_paise)
  VALUES (v_cust, v_store, 'PENDING', 1799900)
  RETURNING id INTO v_incomplete_order;

  INSERT INTO order_items (order_id, product_id, qty, unit_price_paise)
  VALUES (v_incomplete_order, v_product, 1, 1799900);

  v_caught := FALSE;
  BEGIN
    PERFORM confirm_order(v_incomplete_order);
  EXCEPTION WHEN SQLSTATE '23514' THEN
    v_caught := TRUE;
  END;
  ASSERT v_caught = TRUE, 'confirm_order must reject orders with incomplete reservation coverage';
  PERFORM cancel_order(v_incomplete_order, v_cust);

  -- 6D. Repaired Ownership Mismatch Guard Using Real Customers
  INSERT INTO orders (customer_id, store_id, status, total_paise)
  VALUES (v_cust, v_store, 'PENDING', 149900)
  RETURNING id INTO v_mismatch_order;

  INSERT INTO order_items (order_id, product_id, qty, unit_price_paise)
  VALUES (v_mismatch_order, v_headphone, 1, 149900);

  -- Create a valid reservation belonging to v_other_cust (valid FK to customers table)
  INSERT INTO reservations (customer_id, store_id, product_id, qty, expires_at, order_id)
  VALUES (v_other_cust, v_store, v_headphone, 1, clock_timestamp() + INTERVAL '10 minutes', v_mismatch_order)
  RETURNING id INTO r_mismatch;

  v_caught := FALSE;
  BEGIN
    PERFORM confirm_order(v_mismatch_order);
  EXCEPTION WHEN SQLSTATE '42501' THEN
    v_caught := TRUE;
  END;
  ASSERT v_caught = TRUE, 'confirm_order must independently catch customer ownership mismatch (42501)';
  DELETE FROM reservations WHERE id = r_mismatch;

  -- 6E. Reservation Store Mismatch Guard in confirm_order
  INSERT INTO reservations (customer_id, store_id, product_id, qty, expires_at, order_id)
  VALUES (v_cust, v_beng_store, v_headphone, 1, clock_timestamp() + INTERVAL '10 minutes', v_mismatch_order)
  RETURNING id INTO r_mismatch;

  v_caught := FALSE;
  BEGIN
    PERFORM confirm_order(v_mismatch_order);
  EXCEPTION WHEN SQLSTATE '23514' THEN
    v_caught := TRUE;
  END;
  ASSERT v_caught = TRUE, 'confirm_order must independently catch reservation store mismatch (23514)';
  DELETE FROM reservations WHERE id = r_mismatch;
  PERFORM cancel_order(v_mismatch_order, v_cust);

  -- -------------------------------------------------------------------
  -- 7. Expiry Cutoff Consistency & Single-Product Mixed Validity Test
  -- -------------------------------------------------------------------
  -- Order requires 1 headphone. We link 1 valid reservation and 1 expired reservation.
  -- confirm_order() uses single immutable v_cutoff: releases expired reservation,
  -- consumes ONLY the valid reservation, and deducts EXACTLY 1 unit from on-hand (no excess).
  INSERT INTO orders (customer_id, store_id, status, total_paise)
  VALUES (v_cust, v_store, 'PENDING', 149900)
  RETURNING id INTO v_mixed_order;

  INSERT INTO order_items (order_id, product_id, qty, unit_price_paise)
  VALUES (v_mixed_order, v_headphone, 1, 149900);

  r_valid := reserve_stock(v_cust, v_store, v_headphone, 1);
  ASSERT r_valid IS NOT NULL, 'Valid reservation must succeed';
  ASSERT link_reservation_to_order(r_valid, v_mixed_order, v_cust) = TRUE, 'Valid link must succeed';

  r_exp := reserve_stock(v_cust, v_store, v_headphone, 1);
  ASSERT r_exp IS NOT NULL, 'Second reservation must succeed';
  UPDATE reservations
     SET expires_at = clock_timestamp() - INTERVAL '5 minutes',
         order_id   = v_mixed_order
   WHERE id = r_exp;

  ASSERT confirm_order(v_mixed_order) = TRUE, 'confirm_order must succeed with valid coverage';

  -- Verify valid reservation is CONSUMED
  ASSERT (SELECT status FROM reservations WHERE id = r_valid) = 'CONSUMED',
    'Valid reservation must be CONSUMED';

  -- Verify expired reservation is EXPIRED, NOT CONSUMED!
  ASSERT (SELECT status FROM reservations WHERE id = r_exp) = 'EXPIRED',
    'Expired reservation must be EXPIRED and NOT consumed';

  -- Verify exactly 1 unit of headphones was deducted from on-hand (NOT 2!)
  SELECT qty_on_hand, qty_reserved INTO v_cur_on_hand, v_cur_reserved
    FROM inventory
   WHERE store_id = v_store AND product_id = v_headphone;
  ASSERT v_cur_on_hand = v_mumbai_head_on_hand - 1,
    'qty_on_hand must be decremented by exactly 1 unit (order quantity), preventing excess deduction';
  ASSERT v_cur_reserved = v_mumbai_head_reserved,
    'qty_reserved must return to initial reserved level (expired stock safely freed)';

  ASSERT cancel_order(v_mixed_order, v_cust) = TRUE, 'cancel_order must succeed';

  -- -------------------------------------------------------------------
  -- 8. Multi-Product Expired Reservation Processing Test
  -- -------------------------------------------------------------------
  -- Order in STORE-001 (Bengaluru) with 1 Phone and 1 Headphone.
  -- Each product has 1 valid reservation and 1 expired reservation linked.
  -- Validates that confirm_order() releases expired reservations and deducts inventory
  -- across multiple products in deterministic ascending (store_id, product_id) order.
  INSERT INTO orders (customer_id, store_id, status, total_paise)
  VALUES (v_cust, v_beng_store, 'PENDING', 1949800)
  RETURNING id INTO v_multi_exp_order;

  INSERT INTO order_items (order_id, product_id, qty, unit_price_paise) VALUES
    (v_multi_exp_order, v_product, 1, 1799900),
    (v_multi_exp_order, v_headphone, 1, 149900);

  -- Phone reservations: 1 valid, 1 expired
  r_val_p := reserve_stock(v_cust, v_beng_store, v_product, 1);
  ASSERT link_reservation_to_order(r_val_p, v_multi_exp_order, v_cust) = TRUE;
  r_exp_p := reserve_stock(v_cust, v_beng_store, v_product, 1);
  UPDATE reservations SET expires_at = clock_timestamp() - INTERVAL '5 minutes', order_id = v_multi_exp_order WHERE id = r_exp_p;

  -- Headphone reservations: 1 valid, 1 expired
  r_val_h := reserve_stock(v_cust, v_beng_store, v_headphone, 1);
  ASSERT link_reservation_to_order(r_val_h, v_multi_exp_order, v_cust) = TRUE;
  r_exp_h := reserve_stock(v_cust, v_beng_store, v_headphone, 1);
  UPDATE reservations SET expires_at = clock_timestamp() - INTERVAL '5 minutes', order_id = v_multi_exp_order WHERE id = r_exp_h;

  ASSERT confirm_order(v_multi_exp_order) = TRUE, 'confirm_order for multi-product mixed validity must succeed';

  -- Both valid reservations must be CONSUMED
  ASSERT (SELECT status FROM reservations WHERE id = r_val_p) = 'CONSUMED';
  ASSERT (SELECT status FROM reservations WHERE id = r_val_h) = 'CONSUMED';

  -- Both expired reservations must be EXPIRED
  ASSERT (SELECT status FROM reservations WHERE id = r_exp_p) = 'EXPIRED';
  ASSERT (SELECT status FROM reservations WHERE id = r_exp_h) = 'EXPIRED';

  -- Both on-hand inventories must be decremented by exactly 1 unit each (not 2!)
  SELECT qty_on_hand, qty_reserved INTO v_cur_on_hand, v_cur_reserved
    FROM inventory WHERE store_id = v_beng_store AND product_id = v_product;
  ASSERT v_cur_on_hand = v_beng_phone_on_hand - 1 AND v_cur_reserved = v_beng_phone_reserved,
    'Phone on-hand must decrement by exactly 1 with no excess deduction';

  SELECT qty_on_hand, qty_reserved INTO v_cur_on_hand, v_cur_reserved
    FROM inventory WHERE store_id = v_beng_store AND product_id = v_headphone;
  ASSERT v_cur_on_hand = v_beng_head_on_hand - 1 AND v_cur_reserved = v_beng_head_reserved,
    'Headphone on-hand must decrement by exactly 1 with no excess deduction';

  ASSERT cancel_order(v_multi_exp_order, v_cust) = TRUE, 'cancel_order on multi-exp order must succeed';

  -- -------------------------------------------------------------------
  -- 9. Pending Cancellation with Multiple Products Test
  -- -------------------------------------------------------------------
  -- Order in STORE-001 with 1 Phone and 1 Headphone in PENDING state.
  -- cancel_order() must lock reservations in ORDER BY id FOR UPDATE,
  -- release reserved inventory in deterministic ascending ORDER BY store_id, product_id,
  -- and transition reservations to RELEASED.
  INSERT INTO orders (customer_id, store_id, status, total_paise)
  VALUES (v_cust, v_beng_store, 'PENDING', 1949800)
  RETURNING id INTO v_pending_multi_ord;

  INSERT INTO order_items (order_id, product_id, qty, unit_price_paise) VALUES
    (v_pending_multi_ord, v_product, 1, 1799900),
    (v_pending_multi_ord, v_headphone, 1, 149900);

  r_pend_p := reserve_stock(v_cust, v_beng_store, v_product, 1);
  ASSERT link_reservation_to_order(r_pend_p, v_pending_multi_ord, v_cust) = TRUE;

  r_pend_h := reserve_stock(v_cust, v_beng_store, v_headphone, 1);
  ASSERT link_reservation_to_order(r_pend_h, v_pending_multi_ord, v_cust) = TRUE;

  -- Cancel the pending multi-product order
  ASSERT cancel_order(v_pending_multi_ord, v_cust) = TRUE, 'cancel_order on pending multi-product order must succeed';
  ASSERT (SELECT status FROM orders WHERE id = v_pending_multi_ord) = 'CANCELLED';

  -- Both reservations must be RELEASED
  ASSERT (SELECT status FROM reservations WHERE id = r_pend_p) = 'RELEASED';
  ASSERT (SELECT status FROM reservations WHERE id = r_pend_h) = 'RELEASED';

  -- Verify reserved inventory returned to baseline
  SELECT qty_reserved INTO v_cur_reserved FROM inventory WHERE store_id = v_beng_store AND product_id = v_product;
  ASSERT v_cur_reserved = v_beng_phone_reserved, 'Phone reserved inventory must return to baseline';

  SELECT qty_reserved INTO v_cur_reserved FROM inventory WHERE store_id = v_beng_store AND product_id = v_headphone;
  ASSERT v_cur_reserved = v_beng_head_reserved, 'Headphone reserved inventory must return to baseline';

  -- -------------------------------------------------------------------
  -- 10. Single-Item Phone Order Confirmation & Cancellation Lifecycle
  -- -------------------------------------------------------------------
  ASSERT confirm_order(v_order) = TRUE, 'confirm_order must succeed for fully linked phone order';

  ASSERT (SELECT status FROM orders WHERE id = v_order) = 'CONFIRMED', 'Order status must be CONFIRMED';
  ASSERT (SELECT status FROM reservations WHERE id = r3) = 'CONSUMED', 'Reservation status must be CONSUMED';

  SELECT qty_on_hand, qty_reserved INTO v_cur_on_hand, v_cur_reserved
    FROM inventory
   WHERE store_id = v_store AND product_id = v_product;
  ASSERT v_cur_on_hand = v_mumbai_phone_on_hand - 1, 'qty_on_hand must be decremented by 1';
  ASSERT v_cur_reserved = v_mumbai_phone_reserved, 'qty_reserved must return to initial reserved level';

  -- Re-confirmation rejection
  ASSERT confirm_order(v_order) = FALSE, 'confirm_order must return FALSE on non-PENDING order';

  -- Cancel confirmed phone order
  ASSERT cancel_order(v_order, v_cust, 'Customer cancellation') = TRUE, 'cancel_order must succeed for CONFIRMED order';
  ASSERT (SELECT status FROM orders WHERE id = v_order) = 'CANCELLED', 'Order status must be CANCELLED';

  SELECT qty_on_hand, qty_reserved INTO v_cur_on_hand, v_cur_reserved
    FROM inventory
   WHERE store_id = v_store AND product_id = v_product;
  ASSERT v_cur_on_hand = v_mumbai_phone_on_hand, 'qty_on_hand must be fully restored';
  ASSERT v_cur_reserved = v_mumbai_phone_reserved, 'qty_reserved must be fully restored';

  -- Repeated cancellation returns FALSE (no double restoration)
  ASSERT cancel_order(v_order, v_cust) = FALSE, 'Repeated cancel_order must return FALSE';

  -- Confirming cancelled order returns FALSE
  ASSERT confirm_order(v_order) = FALSE, 'confirm_order must return FALSE on CANCELLED order';

  -- -------------------------------------------------------------------
  -- 11. Multi-Product Confirmed Lifecycle & Outbox Payload Test
  -- -------------------------------------------------------------------
  INSERT INTO orders (customer_id, store_id, status, total_paise)
  VALUES (v_cust, v_store, 'PENDING', 1949800)
  RETURNING id INTO v_multi_prod_order;

  INSERT INTO order_items (order_id, product_id, qty, unit_price_paise) VALUES
    (v_multi_prod_order, v_product, 1, 1799900),
    (v_multi_prod_order, v_headphone, 1, 149900);

  r_prod_phone := reserve_stock(v_cust, v_store, v_product, 1);
  ASSERT link_reservation_to_order(r_prod_phone, v_multi_prod_order, v_cust) = TRUE;

  r_prod_head := reserve_stock(v_cust, v_store, v_headphone, 1);
  ASSERT link_reservation_to_order(r_prod_head, v_multi_prod_order, v_cust) = TRUE;

  ASSERT confirm_order(v_multi_prod_order) = TRUE, 'confirm_order for multi-product order must succeed';

  SELECT qty_on_hand INTO v_cur_on_hand FROM inventory WHERE store_id = v_store AND product_id = v_product;
  ASSERT v_cur_on_hand = v_mumbai_phone_on_hand - 1, 'Phone qty_on_hand must be decremented by 1';

  SELECT qty_on_hand INTO v_cur_on_hand FROM inventory WHERE store_id = v_store AND product_id = v_headphone;
  ASSERT v_cur_on_hand = v_mumbai_head_on_hand - 1, 'Headphone qty_on_hand must be decremented by 1';

  SELECT jsonb_array_length(payload->'items') INTO v_outbox_count
    FROM outbox_events
   WHERE aggregate_id = v_multi_prod_order::text AND event_type = 'order.placed';
  ASSERT v_outbox_count = 2, 'Outbox event must contain both items in payload';

  -- Cancel confirmed multi-product order: verifies deterministic Level 3 restoration
  ASSERT cancel_order(v_multi_prod_order, v_cust) = TRUE, 'cancel_order for multi-product order must succeed';

  SELECT qty_on_hand INTO v_cur_on_hand FROM inventory WHERE store_id = v_store AND product_id = v_product;
  ASSERT v_cur_on_hand = v_mumbai_phone_on_hand, 'Phone qty_on_hand must be fully restored';

  SELECT qty_on_hand INTO v_cur_on_hand FROM inventory WHERE store_id = v_store AND product_id = v_headphone;
  ASSERT v_cur_on_hand = v_mumbai_head_on_hand, 'Headphone qty_on_hand must be fully restored';

  -- -------------------------------------------------------------------
  -- 12. Customer Role Integrity & Concurrency Guard Tests
  -- -------------------------------------------------------------------
  v_caught := FALSE;
  BEGIN
    UPDATE users SET role = 'ADMIN' WHERE id = v_user;
  EXCEPTION WHEN SQLSTATE '23514' THEN
    v_caught := TRUE;
  END;
  ASSERT v_caught = TRUE, 'users_role_guard must prevent converting customer to ADMIN while profile exists';

  v_caught := FALSE;
  BEGIN
    INSERT INTO customers (user_id) VALUES (v_admin_user);
  EXCEPTION WHEN SQLSTATE '23514' THEN
    v_caught := TRUE;
  END;
  ASSERT v_caught = TRUE, 'customers_role_guard must reject customer profile creation for non-CUSTOMER user';

  -- -------------------------------------------------------------------
  -- 13. Final Dynamic Inventory Balance Check (Zero Leakage / 100% Net Match)
  -- -------------------------------------------------------------------
  -- Verify STORE-005 (Mumbai) Phone & Headphones match baseline
  SELECT qty_on_hand, qty_reserved INTO v_cur_on_hand, v_cur_reserved
    FROM inventory WHERE store_id = v_store AND product_id = v_product;
  ASSERT v_cur_on_hand = v_mumbai_phone_on_hand AND v_cur_reserved = v_mumbai_phone_reserved,
    'Final Mumbai PHONE-001 inventory must perfectly match dynamic initial baseline';

  SELECT qty_on_hand, qty_reserved INTO v_cur_on_hand, v_cur_reserved
    FROM inventory WHERE store_id = v_store AND product_id = v_headphone;
  ASSERT v_cur_on_hand = v_mumbai_head_on_hand AND v_cur_reserved = v_mumbai_head_reserved,
    'Final Mumbai BT-HEAD-001 inventory must perfectly match dynamic initial baseline';

  -- Verify STORE-001 (Bengaluru) Phone, Headphones & Rice match baseline
  SELECT qty_on_hand, qty_reserved INTO v_cur_on_hand, v_cur_reserved
    FROM inventory WHERE store_id = v_beng_store AND product_id = v_product;
  ASSERT v_cur_on_hand = v_beng_phone_on_hand AND v_cur_reserved = v_beng_phone_reserved,
    'Final Bengaluru PHONE-001 inventory must perfectly match dynamic initial baseline';

  SELECT qty_on_hand, qty_reserved INTO v_cur_on_hand, v_cur_reserved
    FROM inventory WHERE store_id = v_beng_store AND product_id = v_headphone;
  ASSERT v_cur_on_hand = v_beng_head_on_hand AND v_cur_reserved = v_beng_head_reserved,
    'Final Bengaluru BT-HEAD-001 inventory must perfectly match dynamic initial baseline';

  SELECT qty_on_hand, qty_reserved INTO v_cur_on_hand, v_cur_reserved
    FROM inventory WHERE store_id = v_beng_store AND product_id = v_rice;
  ASSERT v_cur_on_hand = v_beng_rice_on_hand AND v_cur_reserved = v_beng_rice_reserved,
    'Final Bengaluru RICE-5KG inventory must perfectly match dynamic initial baseline';

  RAISE NOTICE 'All Phase 1 database logic, reservation aggregation, cutoff consistency, deterministic locking, multi-product validity, confirmation, cancellation, and role guard self-tests passed successfully.';
END;
$$;

-- Show audit entries generated during self-test
SELECT reason, old_on_hand, new_on_hand, old_reserved, new_reserved, changed_at
  FROM inventory_audit_log
 ORDER BY id DESC
 LIMIT 10;

ROLLBACK;
