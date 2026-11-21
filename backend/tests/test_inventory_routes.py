"""
Integration and API tests for SmartCart 2.0 Inventory Management and Reservation Routes:
- GET /api/v1/inventory/{store_id}/{product_id} (balance lookup, store-manager isolation)
- POST /api/v1/inventory/reservations (atomic PostgreSQL reserve_stock, 10-minute hold)
- GET /api/v1/inventory/reservations/{reservation_id} (details, customer ownership)
- DELETE /api/v1/inventory/reservations/{reservation_id} (release reservation, restore stock)
- Concurrency and insufficient stock conflict handling (HTTP 409)
"""
import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text

from app.core.security import create_access_token
from app.db.session import AsyncSessionLocal, async_engine
from app.models.enums import UserRole
from app.models.store import Store
from app.models.user import User


@pytest_asyncio.fixture(autouse=True)
async def dispose_engine_after_test():
    """Ensure engine connections are cleanly disposed before event loop teardown."""
    yield
    if async_engine is not None:
        await async_engine.dispose()


async def get_seed_identifiers():
    """Fetch active store and product IDs from seed data."""
    async with AsyncSessionLocal() as session:
        store_res = await session.execute(text("SELECT id FROM stores WHERE code = 'STORE-001'"))
        store_id = store_res.scalar_one()

        prod_res = await session.execute(text("SELECT id FROM products WHERE sku = 'BT-HEAD-001'"))
        product_id = prod_res.scalar_one()
        return store_id, product_id


@pytest.mark.asyncio
async def test_get_stock_balance_success(async_client: AsyncClient):
    """
    Verify public/customer callers can query physical and available stock balances.
    Checks:
    - HTTP 200 OK
    - Valid StockResponse schema
    - qty_available == qty_on_hand - qty_reserved
    """
    store_id, product_id = await get_seed_identifiers()

    resp = await async_client.get(f"/api/v1/inventory/{store_id}/{product_id}")
    assert resp.status_code == 200
    stock = resp.json()
    assert stock["store_id"] == str(store_id)
    assert stock["product_id"] == str(product_id)
    assert isinstance(stock["qty_on_hand"], int)
    assert isinstance(stock["qty_reserved"], int)
    assert stock["qty_available"] == max(0, stock["qty_on_hand"] - stock["qty_reserved"])
    assert isinstance(stock["is_low_stock"], bool)
    assert "updated_at" in stock


@pytest.mark.asyncio
async def test_get_stock_not_found(async_client: AsyncClient):
    """
    Verify nonexistent store or product returns HTTP 404 NOT_FOUND.
    """
    store_id, product_id = await get_seed_identifiers()
    missing_id = uuid.uuid4()

    # Missing store
    r1 = await async_client.get(f"/api/v1/inventory/{missing_id}/{product_id}")
    assert r1.status_code == 404
    assert r1.json()["error"]["code"] == "NOT_FOUND"

    # Missing product
    r2 = await async_client.get(f"/api/v1/inventory/{store_id}/{missing_id}")
    assert r2.status_code == 404
    assert r2.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_get_stock_invalid_uuid(async_client: AsyncClient):
    """
    Verify malformed UUID in path returns HTTP 422 VALIDATION_ERROR.
    """
    resp = await async_client.get("/api/v1/inventory/invalid-uuid/invalid-uuid")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_get_stock_store_manager_isolation(async_client: AsyncClient):
    """
    Verify store-manager isolation on inventory lookups:
    - Store manager can query inventory at their assigned store.
    - Store manager cannot query inventory at another store (HTTP 403 Forbidden).
    """
    store_a_id = uuid.uuid4()
    store_b_id = uuid.uuid4()
    prod_id = uuid.uuid4()
    manager_id = uuid.uuid4()
    manager_email = f"sm_{uuid.uuid4().hex[:6]}@smartcart.in"

    async with AsyncSessionLocal() as session:
        s_a = Store(id=store_a_id, code=f"SA-{uuid.uuid4().hex[:4]}", name="Store A", city="Pune", state="MH", is_active=True)
        s_b = Store(id=store_b_id, code=f"SB-{uuid.uuid4().hex[:4]}", name="Store B", city="Nagpur", state="MH", is_active=True)
        session.add_all([s_a, s_b])

        manager = User(
            id=manager_id,
            email=manager_email,
            full_name="Store Manager Isolation",
            password_hash="argon2id$mocked",
            role=UserRole.STORE_MANAGER,
            assigned_store_id=store_a_id,
            is_active=True,
        )
        session.add(manager)
        await session.commit()

        # Seed inventory for store A
        await session.execute(
            text(
                "INSERT INTO inventory (store_id, product_id, qty_on_hand, qty_reserved, low_stock_threshold) "
                "VALUES (:s, (SELECT id FROM products LIMIT 1), 50, 0, 5)"
            ),
            {"s": store_a_id},
        )
        prod_row = await session.execute(text("SELECT id FROM products LIMIT 1"))
        prod_id = prod_row.scalar_one()
        await session.commit()

    try:
        manager_token = create_access_token(
            data={"sub": str(manager_id), "role": UserRole.STORE_MANAGER.value, "store_id": str(store_a_id)}
        )

        # 1. Manager queries assigned Store A -> 200 OK
        r_assigned = await async_client.get(
            f"/api/v1/inventory/{store_a_id}/{prod_id}",
            headers={"Authorization": f"Bearer {manager_token}"},
        )
        assert r_assigned.status_code == 200

        # 2. Manager queries unassigned Store B -> 403 Forbidden
        r_other = await async_client.get(
            f"/api/v1/inventory/{store_b_id}/{prod_id}",
            headers={"Authorization": f"Bearer {manager_token}"},
        )
        assert r_other.status_code == 403
        assert r_other.json()["error"]["code"] == "FORBIDDEN"

    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(text("DELETE FROM inventory WHERE store_id = :s"), {"s": store_a_id})
            await session.execute(text("DELETE FROM users WHERE id = :u"), {"u": manager_id})
            await session.execute(text("DELETE FROM stores WHERE id IN (:a, :b)"), {"a": store_a_id, "b": store_b_id})
            await session.commit()


@pytest.mark.asyncio
async def test_create_and_release_reservation_flow(async_client: AsyncClient):
    """
    Verify complete stock reservation lifecycle:
    - Customer creates reservation via PostgreSQL reserve_stock()
    - Physical stock is held (qty_reserved incremented)
    - Customer inspects reservation details
    - Customer releases reservation via PostgreSQL release_reservation()
    - Stock is immediately restored
    """
    store_id, product_id = await get_seed_identifiers()

    # Authenticate customer
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "demo@smartcart.in", "password": "Demo@123"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]

    # Check available stock before
    stock_before_resp = await async_client.get(f"/api/v1/inventory/{store_id}/{product_id}")
    avail_before = stock_before_resp.json()["qty_available"]

    # 1. Create reservation for 2 units
    res_resp = await async_client.post(
        "/api/v1/inventory/reservations",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "store_id": str(store_id),
            "product_id": str(product_id),
            "qty": 2,
            "ttl_seconds": 600,
        },
    )
    assert res_resp.status_code == 201
    res_data = res_resp.json()
    reservation_id = res_data["id"]
    assert res_data["qty"] == 2
    assert res_data["status"] == "ACTIVE"
    assert "expires_at" in res_data

    # Check available stock decreased by 2
    stock_mid_resp = await async_client.get(f"/api/v1/inventory/{store_id}/{product_id}")
    assert stock_mid_resp.json()["qty_available"] == avail_before - 2

    # 2. Inspect reservation details
    get_res_resp = await async_client.get(
        f"/api/v1/inventory/reservations/{reservation_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_res_resp.status_code == 200
    assert get_res_resp.json()["id"] == reservation_id

    # 3. Release reservation
    del_resp = await async_client.delete(
        f"/api/v1/inventory/reservations/{reservation_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 204

    # Check available stock restored
    stock_after_resp = await async_client.get(f"/api/v1/inventory/{store_id}/{product_id}")
    assert stock_after_resp.json()["qty_available"] == avail_before


@pytest.mark.asyncio
async def test_create_reservation_insufficient_stock_conflict(async_client: AsyncClient):
    """
    Verify attempting to reserve more units than available returns HTTP 409 Conflict.
    """
    store_id, product_id = await get_seed_identifiers()

    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "demo@smartcart.in", "password": "Demo@123"},
    )
    token = login_resp.json()["access_token"]

    resp = await async_client.post(
        "/api/v1/inventory/reservations",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "store_id": str(store_id),
            "product_id": str(product_id),
            "qty": 999999,  # Far exceeds available stock
            "ttl_seconds": 600,
        },
    )
    assert resp.status_code == 409
    data = resp.json()
    assert data["error"]["code"] == "INSUFFICIENT_STOCK"
    assert "insufficient" in data["error"]["message"].lower()


@pytest.mark.asyncio
async def test_reservation_customer_ownership_restrictions(async_client: AsyncClient):
    """
    Verify customer ownership security:
    - Customer A creates reservation.
    - Customer B is forbidden (HTTP 403) from inspecting or releasing Customer A's reservation.
    """
    store_id, product_id = await get_seed_identifiers()

    # Customer A (demo@smartcart.in)
    login_a = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "demo@smartcart.in", "password": "Demo@123"},
    )
    token_a = login_a.json()["access_token"]

    # Register Customer B
    email_b = f"customer_b_{uuid.uuid4().hex[:6]}@smartcart.in"
    reg_b = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": email_b,
            "password": "Password@123",
            "full_name": "Customer B",
            "phone": "9876543210",
        },
    )
    assert reg_b.status_code == 201

    login_b = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email_b, "password": "Password@123"},
    )
    token_b = login_b.json()["access_token"]

    # Customer A creates reservation
    res_resp = await async_client.post(
        "/api/v1/inventory/reservations",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"store_id": str(store_id), "product_id": str(product_id), "qty": 1},
    )
    assert res_resp.status_code == 201
    res_id = res_resp.json()["id"]

    try:
        # Customer B tries to GET Customer A's reservation -> 403 Forbidden
        r_get = await async_client.get(
            f"/api/v1/inventory/reservations/{res_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert r_get.status_code == 403
        assert r_get.json()["error"]["code"] == "FORBIDDEN"

        # Customer B tries to DELETE Customer A's reservation -> 403 Forbidden
        r_del = await async_client.delete(
            f"/api/v1/inventory/reservations/{res_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert r_del.status_code == 403
        assert r_del.json()["error"]["code"] == "FORBIDDEN"

    finally:
        # Customer A cleans up reservation
        await async_client.delete(
            f"/api/v1/inventory/reservations/{res_id}",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        # Cleanup user B from DB
        async with AsyncSessionLocal() as session:
            await session.execute(text("DELETE FROM customers WHERE user_id IN (SELECT id FROM users WHERE email = :e)"), {"e": email_b})
            await session.execute(text("DELETE FROM users WHERE email = :e"), {"e": email_b})
            await session.commit()


@pytest.mark.asyncio
async def test_reservation_validation_rejections(async_client: AsyncClient):
    """
    Verify schema validation rejections:
    - Negative or zero quantity
    - Excess TTL (> 3600s)
    - Extra unexpected fields
    """
    store_id, product_id = await get_seed_identifiers()
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "demo@smartcart.in", "password": "Demo@123"},
    )
    token = login_resp.json()["access_token"]

    # Zero quantity
    r1 = await async_client.post(
        "/api/v1/inventory/reservations",
        headers={"Authorization": f"Bearer {token}"},
        json={"store_id": str(store_id), "product_id": str(product_id), "qty": 0},
    )
    assert r1.status_code == 422

    # Excess TTL (> 3600 seconds)
    r2 = await async_client.post(
        "/api/v1/inventory/reservations",
        headers={"Authorization": f"Bearer {token}"},
        json={"store_id": str(store_id), "product_id": str(product_id), "qty": 1, "ttl_seconds": 7200},
    )
    assert r2.status_code == 422

    # Extra unexpected parameter
    r3 = await async_client.post(
        "/api/v1/inventory/reservations",
        headers={"Authorization": f"Bearer {token}"},
        json={"store_id": str(store_id), "product_id": str(product_id), "qty": 1, "price_paise": 100},
    )
    assert r3.status_code == 422
