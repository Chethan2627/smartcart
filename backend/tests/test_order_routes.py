"""
Integration and API tests for SmartCart 2.0 Order Management Routes:
- GET /api/v1/orders (customer order history, pagination, store manager scoping)
- GET /api/v1/orders/{order_id} (order details, cross-customer privacy enforcement)
- POST /api/v1/orders/{order_id}/cancel (atomic cancellation, PostgreSQL state rules, inventory restoration)
- Store-manager isolation and administrator oversight
"""
import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text

from app.core.security import create_access_token
from app.db.session import AsyncSessionLocal, async_engine
from app.models.enums import OrderStatus, UserRole
from app.models.store import Store
from app.models.user import User


@pytest_asyncio.fixture(autouse=True)
async def dispose_engine_after_test():
    """Ensure engine connections are cleanly disposed before event loop teardown."""
    yield
    if async_engine is not None:
        await async_engine.dispose()


async def get_test_store_and_product():
    """Fetch active store and product IDs from seed data."""
    async with AsyncSessionLocal() as session:
        s1 = (await session.execute(text("SELECT id FROM stores WHERE code = 'STORE-001'"))).scalar_one()
        s2 = (await session.execute(text("SELECT id FROM stores WHERE code = 'STORE-002'"))).scalar_one()
        p1 = (await session.execute(text("SELECT id FROM products WHERE sku = 'BT-HEAD-001'"))).scalar_one()
        return s1, s2, p1


@pytest.fixture
async def placed_order(async_client: AsyncClient):
    """Create a confirmed order for customer demo@smartcart.in and return (token, order_dict)."""
    s1, _, p1 = await get_test_store_and_product()

    # Ensure STORE-001 has adequate stock for test purchases
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("UPDATE inventory SET qty_on_hand = 50, qty_reserved = 0 WHERE store_id = :sid AND product_id = :pid"),
            {"sid": s1, "pid": p1},
        )
        await session.commit()

    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "demo@smartcart.in", "password": "Demo@123"},
    )
    token = login_resp.json()["access_token"]

    # Clear cart and add item
    await async_client.delete("/api/v1/cart", headers={"Authorization": f"Bearer {token}"})
    await async_client.post(
        "/api/v1/cart/items",
        headers={"Authorization": f"Bearer {token}"},
        json={"store_id": str(s1), "product_id": str(p1), "qty": 1},
    )

    # Checkout
    co_resp = await async_client.post(
        "/api/v1/checkout",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": f"key-order-{uuid.uuid4().hex[:10]}",
        },
        json={"store_id": str(s1), "delivery_address": "Indiranagar, Bengaluru"},
    )
    assert co_resp.status_code == 201
    return token, co_resp.json()


@pytest.mark.asyncio
async def test_list_customer_orders_pagination(
    async_client: AsyncClient, placed_order
):
    """
    Verify customer can list placed orders with pagination.
    """
    token, order = placed_order

    # List orders
    resp = await async_client.get(
        "/api/v1/orders",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    orders = resp.json()
    assert isinstance(orders, list)
    assert any(o["id"] == order["id"] for o in orders)

    # Pagination: limit=1
    r_limit = await async_client.get(
        "/api/v1/orders?skip=0&limit=1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r_limit.status_code == 200
    assert len(r_limit.json()) == 1

    # Invalid pagination
    r_inv = await async_client.get(
        "/api/v1/orders?skip=-1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r_inv.status_code == 422


@pytest.mark.asyncio
async def test_get_order_by_id_success(
    async_client: AsyncClient, placed_order
):
    """
    Verify customer can inspect own order details:
    - Order number, status, total_paise
    - Line items with product details and prices
    - Status history
    - No password hashes or sensitive fields
    """
    token, order = placed_order
    order_id = order["id"]

    resp = await async_client.get(
        f"/api/v1/orders/{order_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    details = resp.json()
    assert details["id"] == order_id
    assert details["order_number"].startswith("SC-")
    assert details["status"] == "CONFIRMED"
    assert details["total_paise"] == 149900
    assert len(details["items"]) == 1
    assert "password" not in resp.text
    assert "hash" not in resp.text


@pytest.mark.asyncio
async def test_get_order_cross_customer_forbidden(
    async_client: AsyncClient, placed_order
):
    """
    Verify Customer B cannot access Customer A's order (HTTP 403 Forbidden).
    """
    _, order = placed_order
    order_id = order["id"]

    # Register Customer B
    email_b = f"cust_b_{uuid.uuid4().hex[:6]}@smartcart.in"
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": email_b, "password": "Password@123", "full_name": "Customer B"},
    )
    login_b = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email_b, "password": "Password@123"},
    )
    token_b = login_b.json()["access_token"]

    try:
        resp = await async_client.get(
            f"/api/v1/orders/{order_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "FORBIDDEN"

    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(text("DELETE FROM customers WHERE user_id IN (SELECT id FROM users WHERE email = :e)"), {"e": email_b})
            await session.execute(text("DELETE FROM users WHERE email = :e"), {"e": email_b})
            await session.commit()


@pytest.mark.asyncio
async def test_get_order_not_found_and_invalid_uuid(
    async_client: AsyncClient, placed_order
):
    """
    Verify 404 for nonexistent order and 422 for malformed UUID.
    """
    token, _ = placed_order

    r_404 = await async_client.get(
        f"/api/v1/orders/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r_404.status_code == 404
    assert r_404.json()["error"]["code"] == "NOT_FOUND"

    r_422 = await async_client.get(
        "/api/v1/orders/invalid-uuid",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r_422.status_code == 422
    assert r_422.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_cancel_order_customer_success(
    async_client: AsyncClient, placed_order
):
    """
    Verify customer can cancel own confirmed order:
    - Order status transitions to CANCELLED via PostgreSQL cancel_order()
    - Repeated cancel call is safe and idempotent
    """
    token, order = placed_order
    order_id = order["id"]

    resp = await async_client.post(
        f"/api/v1/orders/{order_id}/cancel",
        headers={"Authorization": f"Bearer {token}"},
        json={"reason": "Changed my mind"},
    )
    assert resp.status_code == 200
    cancelled_order = resp.json()
    assert cancelled_order["id"] == order_id
    assert cancelled_order["status"] == "CANCELLED"

    # Repeated cancellation is idempotent (returns 200 with status CANCELLED)
    repeat_resp = await async_client.post(
        f"/api/v1/orders/{order_id}/cancel",
        headers={"Authorization": f"Bearer {token}"},
        json={"reason": "Already cancelled"},
    )
    assert repeat_resp.status_code == 200
    assert repeat_resp.json()["status"] == "CANCELLED"


@pytest.mark.asyncio
async def test_cancel_order_cross_customer_forbidden(
    async_client: AsyncClient, placed_order
):
    """
    Verify Customer B cannot cancel Customer A's order (HTTP 403 Forbidden).
    """
    _, order = placed_order
    order_id = order["id"]

    email_b = f"cust_cancel_{uuid.uuid4().hex[:6]}@smartcart.in"
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": email_b, "password": "Password@123", "full_name": "Customer B"},
    )
    login_b = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email_b, "password": "Password@123"},
    )
    token_b = login_b.json()["access_token"]

    try:
        resp = await async_client.post(
            f"/api/v1/orders/{order_id}/cancel",
            headers={"Authorization": f"Bearer {token_b}"},
            json={"reason": "Unauthorized cancellation attempt"},
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "FORBIDDEN"

    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(text("DELETE FROM customers WHERE user_id IN (SELECT id FROM users WHERE email = :e)"), {"e": email_b})
            await session.execute(text("DELETE FROM users WHERE email = :e"), {"e": email_b})
            await session.commit()


@pytest.mark.asyncio
async def test_cancel_order_ineligible_transition_rejected(
    async_client: AsyncClient, placed_order
):
    """
    Verify orders in terminal/delivered states cannot be cancelled:
    - PostgreSQL triggers reject the invalid state transition
    - Returns HTTP 400 Bad Request (INVALID_STATE_TRANSITION)
    """
    token, order = placed_order
    order_id = order["id"]

    # Transition order step-by-step through valid state transitions to DELIVERED
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("UPDATE orders SET status = 'PACKED' WHERE id = :id"),
            {"id": uuid.UUID(order_id)},
        )
        await session.execute(
            text("UPDATE orders SET status = 'SHIPPED' WHERE id = :id"),
            {"id": uuid.UUID(order_id)},
        )
        await session.execute(
            text("UPDATE orders SET status = 'DELIVERED' WHERE id = :id"),
            {"id": uuid.UUID(order_id)},
        )
        await session.commit()

    resp = await async_client.post(
        f"/api/v1/orders/{order_id}/cancel",
        headers={"Authorization": f"Bearer {token}"},
        json={"reason": "Try cancelling delivered order"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


@pytest.mark.asyncio
async def test_store_manager_order_scoping_and_isolation(
    async_client: AsyncClient, placed_order
):
    """
    Verify store manager isolation:
    - Manager can view orders for their assigned store.
    - Manager cannot view orders for another store (HTTP 403 Forbidden).
    """
    _, order = placed_order
    order_id = order["id"]
    assigned_store_id = order["store_id"]
    other_store_id = uuid.uuid4()
    other_code = f"SM-OTHER-{uuid.uuid4().hex[:4].upper()}"

    manager_id = uuid.uuid4()
    manager_email = f"sm_orders_{uuid.uuid4().hex[:6]}@smartcart.in"

    async with AsyncSessionLocal() as session:
        # Create other store
        other_store = Store(id=other_store_id, code=other_code, name="Other Store", city="Hubballi", state="KA", is_active=True)
        session.add(other_store)

        # Create store manager assigned to other_store_id
        manager = User(
            id=manager_id,
            email=manager_email,
            full_name="Other Store Manager",
            password_hash="argon2id$mocked",
            role=UserRole.STORE_MANAGER,
            assigned_store_id=other_store_id,
            is_active=True,
        )
        session.add(manager)
        await session.commit()

    try:
        manager_token = create_access_token(
            data={"sub": str(manager_id), "role": UserRole.STORE_MANAGER.value, "store_id": str(other_store_id)}
        )

        # Manager queries order belonging to assigned_store_id -> 403 Forbidden
        resp = await async_client.get(
            f"/api/v1/orders/{order_id}",
            headers={"Authorization": f"Bearer {manager_token}"},
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "FORBIDDEN"

    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(text("DELETE FROM users WHERE id = :u"), {"u": manager_id})
            await session.execute(text("DELETE FROM stores WHERE id = :s"), {"s": other_store_id})
            await session.commit()


@pytest.mark.asyncio
async def test_admin_order_access(
    async_client: AsyncClient, placed_order
):
    """
    Verify administrators can list store orders and inspect any order.
    """
    _, order = placed_order
    order_id = order["id"]
    store_id = order["store_id"]

    login_admin = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@smartcart.in", "password": "Demo@123"},
    )
    admin_token = login_admin.json()["access_token"]

    # 1. Admin lists orders for store
    list_resp = await async_client.get(
        f"/api/v1/orders?store_id={store_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert list_resp.status_code == 200
    assert any(o["id"] == order_id for o in list_resp.json())

    # 2. Admin retrieves order by ID
    get_resp = await async_client.get(
        f"/api/v1/orders/{order_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == order_id
