"""
Integration tests for SmartCart 2.0 Phase 4 Service Layer.
Tests live PostgreSQL functions, transaction rollback, composite PK idempotency,
transactional outbox events, and high-concurrency reservation safety.

Requires live PostgreSQL database running as configured in DATABASE_URL.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import List
import uuid
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.config import settings
from app.core.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    IdempotencyConflictError,
    InsufficientStockError,
    InvalidStateTransitionError,
    NotFoundError,
)
from app.db.session import AsyncSessionLocal, async_engine
from app.models.customer import Customer
from app.models.enums import OrderStatus, ReservationStatus, UserRole
from app.models.inventory import Inventory, Reservation
from app.models.order import Order, OrderItem
from app.models.product import Product
from app.models.store import Store
from app.models.user import User
from app.repositories import (
    CustomerRepository,
    IdempotencyKeyRepository,
    InventoryRepository,
    OrderRepository,
    OutboxEventRepository,
    ProductRepository,
    ReservationRepository,
    StoreRepository,
    UserRepository,
)
from app.schemas.cart import CartItemResponse, CartResponse
from app.schemas.order import OrderResponse
from app.services.cart import CartService
from app.services.checkout import CheckoutService
from app.services.idempotency import IdempotencyService
from app.services.inventory import InventoryService
from app.services.order import OrderService
from app.services.outbox import OutboxService
from app.services.product import ProductService
from app.services.store import StoreService


@pytest_asyncio.fixture(autouse=True)
async def dispose_engine_after_test():
    """Ensure engine connections are cleanly disposed before event loop teardown."""
    yield
    if async_engine is not None:
        await async_engine.dispose()


@pytest_asyncio.fixture
async def session():
    """Provide a real async database session."""
    assert AsyncSessionLocal is not None, "AsyncSessionLocal must be initialized"
    async with AsyncSessionLocal() as sess:
        yield sess


# ============================================================================
# 1. PostgreSQL Stored Procedure & Lifecycle Verification
# ============================================================================

@pytest.mark.asyncio
async def test_live_postgres_functions_reserve_release_expire(session):
    """
    Verify PostgreSQL functions:
    - reserve_stock()
    - release_reservation()
    - expire_reservations()
    """
    inv_repo = InventoryRepository(session)
    res_repo = ReservationRepository(session)
    inv_service = InventoryService(inv_repo, res_repo, session=session)

    # 1. Fetch an existing seeded store and product
    store_repo = StoreRepository(session)
    prod_repo = ProductRepository(session)
    cust_repo = CustomerRepository(session)
    user_repo = UserRepository(session)

    store = await store_repo.get_by_code("STORE-001")
    prod = await prod_repo.get_by_sku("PHONE-001")
    demo_user = await user_repo.get_by_email("demo@smartcart.in")
    customer = await cust_repo.get_by_user_id(demo_user.id)
    assert store is not None
    assert prod is not None
    assert customer is not None

    cust_id = customer.id
    qty_to_reserve = 1

    # 2. Reserve stock via PostgreSQL reserve_stock()
    res_id = await inv_service.reserve_stock(
        customer_id=cust_id,
        store_id=store.id,
        product_id=prod.id,
        qty=qty_to_reserve,
        ttl_seconds=600,
    )
    assert res_id is not None

    # Verify reservation created in ACTIVE status
    res = await res_repo.get_by_id(res_id)
    assert res is not None
    assert res.status == ReservationStatus.ACTIVE
    assert res.qty == qty_to_reserve

    # 3. Release stock via PostgreSQL release_reservation()
    released = await inv_service.release_reservation(
        reservation_id=res_id,
        customer_id=cust_id,
    )
    assert released is True

    # Verify reservation transitioned to RELEASED
    await session.refresh(res)
    assert res.status == ReservationStatus.RELEASED


@pytest.mark.asyncio
async def test_live_reservation_expiry_and_stock_restoration(session):
    """
    Verify PostgreSQL reservation expiry:
    - Creates a hold with 1-second TTL.
    - Waits for expiration.
    - Calls expire_reservations().
    - Asserts status transitions to EXPIRED and qty_reserved is restored.
    """
    inv_repo = InventoryRepository(session)
    res_repo = ReservationRepository(session)
    inv_service = InventoryService(inv_repo, res_repo, session=session)

    store_repo = StoreRepository(session)
    prod_repo = ProductRepository(session)
    cust_repo = CustomerRepository(session)
    user_repo = UserRepository(session)

    store = await store_repo.get_by_code("STORE-001")
    prod = await prod_repo.get_by_sku("RICE-5KG")
    demo_user = await user_repo.get_by_email("demo@smartcart.in")
    customer = await cust_repo.get_by_user_id(demo_user.id)
    assert store is not None
    assert prod is not None
    assert customer is not None

    initial_stock = await inv_repo.get_stock(store.id, prod.id)
    initial_reserved = initial_stock.qty_reserved

    cust_id = customer.id
    # Reserve with minimal 1-second TTL
    res_id = await inv_service.reserve_stock(
        customer_id=cust_id,
        store_id=store.id,
        product_id=prod.id,
        qty=1,
        ttl_seconds=1,
    )
    assert res_id is not None

    # Wait 2 seconds for TTL to expire
    await asyncio.sleep(2)

    # Invoke expire_reservations()
    expired_count = await inv_service.expire_reservations(batch_size=500)
    assert expired_count >= 1

    # Verify reservation status is EXPIRED
    res = await res_repo.get_by_id(res_id)
    assert res.status == ReservationStatus.EXPIRED

    # Verify inventory qty_reserved returned to initial level
    updated_stock = await inv_repo.get_stock(store.id, prod.id)
    assert updated_stock.qty_reserved == initial_reserved


# ============================================================================
# 2. Idempotency with Real PostgreSQL Composite Primary Key
# ============================================================================

@pytest.mark.asyncio
async def test_live_idempotency_composite_pk_and_replay(session):
    """
    Verify IdempotencyService against PostgreSQL's composite primary key (customer_id, key).
    - Prevents duplicates on composite PK.
    - Returns cached response on replay.
    - Detects differing payloads with IdempotencyConflictError.
    """
    idemp_repo = IdempotencyKeyRepository(session)
    idemp_service = IdempotencyService(idemp_repo, session=session)

    cust_repo = CustomerRepository(session)
    user_repo = UserRepository(session)
    demo_user = await user_repo.get_by_email("demo@smartcart.in")
    customer = await cust_repo.get_by_user_id(demo_user.id)
    assert customer is not None
    cust_id = customer.id

    idemp_key = f"audit-key-{uuid.uuid4()}"
    payload_1 = {"store_id": str(uuid.uuid4()), "address": "123 MG Road"}
    payload_2 = {"store_id": str(uuid.uuid4()), "address": "Different Address"}

    # 1. Start idempotent operation
    record, is_replay = await idemp_service.start_idempotent_operation(
        customer_id=cust_id,
        key=idemp_key,
        request_payload=payload_1,
    )
    assert is_replay is False
    assert record.response is None

    # 2. Complete operation
    response_data = {"order_id": str(uuid.uuid4()), "status": "CONFIRMED", "total_paise": 50000}
    await idemp_service.complete_idempotent_operation(
        customer_id=cust_id,
        key=idemp_key,
        response_data=response_data,
    )
    await session.commit()

    # 3. Same key + same payload -> replay
    replay_record, is_replay_2 = await idemp_service.start_idempotent_operation(
        customer_id=cust_id,
        key=idemp_key,
        request_payload=payload_1,
    )
    assert is_replay_2 is True
    assert replay_record.response == response_data

    # 4. Same key + different payload -> IdempotencyConflictError
    with pytest.raises(IdempotencyConflictError):
        await idemp_service.start_idempotent_operation(
            customer_id=cust_id,
            key=idemp_key,
            request_payload=payload_2,
        )


# ============================================================================
# 3. Transactional Outbox & Order Lifecycle
# ============================================================================

@pytest.mark.asyncio
async def test_live_order_confirmation_outbox_and_cancellation(session):
    """
    Verify that:
    - confirm_order() atomically inserts order.placed into outbox_events.
    - cancel_order() atomically inserts order.cancelled into outbox_events and restores stock.
    """
    store_repo = StoreRepository(session)
    prod_repo = ProductRepository(session)
    cust_repo = CustomerRepository(session)
    inv_repo = InventoryRepository(session)
    order_repo = OrderRepository(session)
    res_repo = ReservationRepository(session)
    outbox_repo = OutboxEventRepository(session)

    store = await store_repo.get_by_code("STORE-001")
    prod = await prod_repo.get_by_sku("PHONE-001")
    user_repo = UserRepository(session)
    demo_user = await user_repo.get_by_email("demo@smartcart.in")
    customer = await cust_repo.get_by_user_id(demo_user.id)

    # 1. Create stock reservation
    inv_service = InventoryService(inv_repo, res_repo, session=session)
    res_id = await inv_service.reserve_stock(
        customer_id=customer.id,
        store_id=store.id,
        product_id=prod.id,
        qty=1,
        ttl_seconds=600,
    )

    # 2. Create pending order
    order_id = uuid.uuid4()
    order = Order(
        id=order_id,
        customer_id=customer.id,
        store_id=store.id,
        status=OrderStatus.PENDING,
        total_paise=prod.price_paise,
    )
    order_item = OrderItem(
        order_id=order_id,
        product_id=prod.id,
        qty=1,
        unit_price_paise=prod.price_paise,
    )
    session.add(order)
    session.add(order_item)
    await session.flush()

    # 3. Link reservation to order via PostgreSQL
    link_stmt = text("SELECT link_reservation_to_order(:res, :ord, :cust)")
    link_res = await session.execute(link_stmt, {"res": res_id, "ord": order_id, "cust": customer.id})
    assert bool(link_res.scalar_one()) is True

    # 4. Confirm order via PostgreSQL confirm_order()
    confirm_stmt = text("SELECT confirm_order(:ord)")
    conf_res = await session.execute(confirm_stmt, {"ord": order_id})
    assert bool(conf_res.scalar_one()) is True
    await session.commit()

    # 5. Verify order.placed event written to outbox_events
    events = await outbox_repo.list_by_aggregate("order", str(order_id))
    placed_event = next((e for e in events if e.event_type == "order.placed"), None)
    assert placed_event is not None
    assert placed_event.payload["order_id"] == str(order_id)
    assert placed_event.payload["total_paise"] == prod.price_paise

    # 6. Cancel order via PostgreSQL cancel_order()
    order_service = OrderService(order_repo, session=session)
    cancelled = await order_service.cancel_order(order_id, customer_id=customer.id, reason="Audit cancellation")
    assert cancelled is True
    await session.commit()

    # 7. Verify order.cancelled event written to outbox_events
    events_after_cancel = await outbox_repo.list_by_aggregate("order", str(order_id))
    cancelled_event = next(
        (e for e in events_after_cancel if e.event_type == "order.cancelled"), None
    )
    assert cancelled_event is not None
    assert cancelled_event.payload["reason"] == "Audit cancellation"


@pytest.mark.asyncio
async def test_live_checkout_transaction_rollback(session):
    """
    Verify checkout transaction rollback:
    When an error occurs during checkout (e.g. reservation expired or confirm fails),
    the atomic transaction rolls back, leaving no orphan orders or line items.
    """
    store_repo = StoreRepository(session)
    prod_repo = ProductRepository(session)
    cust_repo = CustomerRepository(session)
    inv_repo = InventoryRepository(session)
    res_repo = ReservationRepository(session)
    order_repo = OrderRepository(session)
    idemp_repo = IdempotencyKeyRepository(session)

    store = await store_repo.get_by_code("STORE-001")
    prod = await prod_repo.get_by_sku("PHONE-001")
    user_repo = UserRepository(session)
    demo_user = await user_repo.get_by_email("demo@smartcart.in")
    customer = await cust_repo.get_by_user_id(demo_user.id)

    inv_service = InventoryService(inv_repo, res_repo, session=session)
    prod_service = ProductService(prod_repo)
    store_service = StoreService(store_repo)
    cart_service = CartService(inv_service, prod_service, store_service, res_repo, session=session)
    idemp_service = IdempotencyService(idemp_repo, session=session)
    checkout_service = CheckoutService(
        order_repo=order_repo,
        cart_service=cart_service,
        product_service=prod_service,
        store_service=store_service,
        idempotency_service=idemp_service,
        session=session,
    )

    # 1. Add item to cart (active reservation created)
    await cart_service.add_to_cart(customer.id, store.id, prod.id, qty=1)

    # 2. Get customer cart and intentionally tamper with store_id to trigger failure
    store_2 = await store_repo.get_by_code("STORE-002")
    assert store_2 is not None
    unrelated_store_id = store_2.id
    with pytest.raises(BadRequestError):
        await checkout_service.checkout(customer.id, store_id=unrelated_store_id)

    # 3. Assert no order was created for this customer with status PENDING/CONFIRMED
    orders = await order_repo.list_by_customer(customer.id, limit=5)
    unrelated_orders = [o for o in orders if o.store_id == unrelated_store_id]
    assert len(unrelated_orders) == 0

    # Clean up cart
    await cart_service.clear_cart(customer.id)


# ============================================================================
# 4. CRITICAL CONCURRENCY TEST: 50 Concurrent Reservations for Exactly 1 Unit
# ============================================================================


@pytest.mark.asyncio
async def test_critical_concurrency_50_requests_for_single_unit():
    """
    CRITICAL CONCURRENCY TEST:
    - Available inventory: exactly 1 unit.
    - Simulate 50 concurrent reservation requests.
    - Each request attempts to reserve 1 unit.
    - Exactly 1 request must succeed.
    - The remaining 49 must fail with insufficient stock.
    - Final inventory must not become negative (qty_on_hand=1, qty_reserved=1, qty_available=0).
    - No duplicate reservations must be created.
    Uses an isolated store and product, cleaned up cleanly afterward.
    """
    assert AsyncSessionLocal is not None

    isolated_store_id = uuid.uuid4()
    isolated_prod_id = uuid.uuid4()
    run_suffix = uuid.uuid4().hex[:8]
    test_user_ids: List[uuid.UUID] = []
    test_customer_ids: List[uuid.UUID] = []

    # Step 1: Create isolated test store, product, inventory (1 unit), and 50 isolated test customers
    async with AsyncSessionLocal() as init_session:
        test_store = Store(
            id=isolated_store_id,
            code=f"CONCUR-STORE-{run_suffix}",
            name="Concurrency Test Hub",
            city="Bengaluru",
            state="Karnataka",
            is_active=True,
        )
        test_prod = Product(
            id=isolated_prod_id,
            sku=f"CONCUR-PROD-{run_suffix}",
            name="Limited Edition Item (1 unit)",
            price_paise=99900,
            is_active=True,
        )
        test_inv = Inventory(
            store_id=isolated_store_id,
            product_id=isolated_prod_id,
            qty_on_hand=1,
            qty_reserved=0,
            low_stock_threshold=1,
        )
        init_session.add(test_store)
        init_session.add(test_prod)
        init_session.add(test_inv)

        for i in range(50):
            u_id = uuid.uuid4()
            c_id = uuid.uuid4()
            user = User(
                id=u_id,
                email=f"concur_buyer_{i}_{run_suffix}@smartcart.in",
                full_name=f"Concurrency Buyer {i}",
                password_hash="mock_hash_for_concurrency_test",
                role=UserRole.CUSTOMER,
                is_active=True,
            )
            customer = Customer(
                id=c_id,
                user_id=u_id,
                phone=f"+9198765{i:05d}",
                address=f"Flat {i}, Concurrency Towers, Bengaluru",
            )
            init_session.add(user)
            init_session.add(customer)
            test_user_ids.append(u_id)
            test_customer_ids.append(c_id)

        await init_session.commit()

    try:
        # Step 2: Define the reservation attempt task for each concurrent customer
        async def attempt_reservation(customer_idx: int):
            customer_id = test_customer_ids[customer_idx]
            async with AsyncSessionLocal() as task_session:
                inv_repo = InventoryRepository(task_session)
                res_repo = ReservationRepository(task_session)
                inv_service = InventoryService(inv_repo, res_repo, session=task_session)
                try:
                    res_id = await inv_service.reserve_stock(
                        customer_id=customer_id,
                        store_id=isolated_store_id,
                        product_id=isolated_prod_id,
                        qty=1,
                        ttl_seconds=300,
                    )
                    await task_session.commit()
                    return {"success": True, "res_id": res_id, "customer_idx": customer_idx}
                except InsufficientStockError:
                    await task_session.rollback()
                    return {"success": False, "error": "InsufficientStockError", "customer_idx": customer_idx}
                except Exception as exc:
                    await task_session.rollback()
                    return {"success": False, "error": str(exc), "customer_idx": customer_idx}

        # Step 3: Launch exactly 50 concurrent requests simultaneously
        tasks = [attempt_reservation(i) for i in range(50)]
        results = await asyncio.gather(*tasks)

        # Step 4: Verify outcomes
        successes = [r for r in results if r["success"] is True]
        failures = [r for r in results if r["success"] is False]

        # Invariant 1: Exactly 1 request must succeed
        assert len(successes) == 1, f"Expected exactly 1 successful reservation, got {len(successes)}"

        # Invariant 2: Exactly 49 requests must fail with insufficient stock
        assert len(failures) == 49, f"Expected 49 failures, got {len(failures)}"
        for f in failures:
            assert f["error"] == "InsufficientStockError", f"Expected InsufficientStockError but got {f['error']}"

        # Step 5: Verify PostgreSQL final inventory and reservation state
        async with AsyncSessionLocal() as verify_session:
            # Check inventory balance
            inv_repo = InventoryRepository(verify_session)
            final_inv = await inv_repo.get_stock(isolated_store_id, isolated_prod_id)
            assert final_inv is not None
            assert final_inv.qty_on_hand == 1
            assert final_inv.qty_reserved == 1
            available = final_inv.qty_on_hand - final_inv.qty_reserved
            # Invariant 3: Available inventory must be 0 and NEVER negative
            assert available == 0

            # Invariant 4: No duplicate reservations created (exactly 1 reservation in DB)
            res_result = await verify_session.execute(
                text("SELECT count(*) FROM reservations WHERE store_id = :s AND product_id = :p"),
                {"s": isolated_store_id, "p": isolated_prod_id},
            )
            res_count = res_result.scalar_one()
            assert res_count == 1, f"Expected exactly 1 reservation in DB, found {res_count}"

    finally:
        # Step 6: Clean up isolated test data
        async with AsyncSessionLocal() as cleanup_session:
            await cleanup_session.execute(
                text("DELETE FROM reservations WHERE store_id = :s AND product_id = :p"),
                {"s": isolated_store_id, "p": isolated_prod_id},
            )
            await cleanup_session.execute(
                text("DELETE FROM inventory WHERE store_id = :s AND product_id = :p"),
                {"s": isolated_store_id, "p": isolated_prod_id},
            )
            await cleanup_session.execute(
                text("DELETE FROM products WHERE id = :p"),
                {"p": isolated_prod_id},
            )
            await cleanup_session.execute(
                text("DELETE FROM stores WHERE id = :s"),
                {"s": isolated_store_id},
            )
            if test_customer_ids:
                await cleanup_session.execute(
                    text("DELETE FROM customers WHERE id = ANY(:c_ids)"),
                    {"c_ids": test_customer_ids},
                )
            if test_user_ids:
                await cleanup_session.execute(
                    text("DELETE FROM users WHERE id = ANY(:u_ids)"),
                    {"u_ids": test_user_ids},
                )
            await cleanup_session.commit()

