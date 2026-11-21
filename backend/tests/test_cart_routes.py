"""
Integration and API tests for SmartCart 2.0 Shopping Cart Routes:
- GET /api/v1/cart (active cart state, authoritative prices, TTL earliest_expiration)
- POST /api/v1/cart/items (add item, 10-minute reservation hold, quantity merge)
- PATCH /api/v1/cart/items/{product_id} (update quantity, savepoint rollback on insufficient stock)
- DELETE /api/v1/cart/items/{product_id} (remove item, release reservation)
- DELETE /api/v1/cart (clear cart, release all reservations)
- Single-store cart constraint validation
- Expired reservation exclusion
- Security and tamper-resistance
"""
from datetime import datetime, timedelta, timezone
import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text

from app.db.session import AsyncSessionLocal, async_engine


@pytest_asyncio.fixture(autouse=True)
async def dispose_engine_after_test():
    """Ensure engine connections are cleanly disposed before event loop teardown."""
    yield
    if async_engine is not None:
        await async_engine.dispose()


async def get_test_store_and_products():
    """Fetch active stores and products from seed data."""
    async with AsyncSessionLocal() as session:
        s1 = (await session.execute(text("SELECT id FROM stores WHERE code = 'STORE-001'"))).scalar_one()
        s2 = (await session.execute(text("SELECT id FROM stores WHERE code = 'STORE-002'"))).scalar_one()
        p1 = (await session.execute(text("SELECT id FROM products WHERE sku = 'BT-HEAD-001'"))).scalar_one()
        p2 = (await session.execute(text("SELECT id FROM products WHERE sku = 'PHONE-001'"))).scalar_one()
        return s1, s2, p1, p2


@pytest.fixture
async def customer_token(async_client: AsyncClient):
    """Authenticate and return customer bearer access token."""
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "demo@smartcart.in", "password": "Demo@123"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    # Ensure cart is cleared before test
    await async_client.delete("/api/v1/cart", headers={"Authorization": f"Bearer {token}"})
    return token


@pytest.mark.asyncio
async def test_get_empty_cart(async_client: AsyncClient, customer_token: str):
    """
    Verify customer cart starts empty.
    Checks:
    - HTTP 200 OK
    - items is empty list
    - total_items is 0, total_paise is 0
    - store_id is None
    """
    resp = await async_client.get("/api/v1/cart", headers={"Authorization": f"Bearer {customer_token}"})
    assert resp.status_code == 200
    cart = resp.json()
    assert cart["items"] == []
    assert cart["total_items"] == 0
    assert cart["total_paise"] == 0
    assert cart["store_id"] is None
    assert cart["earliest_expiration"] is None


@pytest.mark.asyncio
async def test_cart_authentication_and_staff_rejection(async_client: AsyncClient):
    """
    Verify cart authorization boundaries:
    - Unauthenticated request is rejected (HTTP 401).
    - Staff / Admin account is rejected (HTTP 403 Forbidden - customer only).
    """
    # 1. Unauthenticated
    r_unauth = await async_client.get("/api/v1/cart")
    assert r_unauth.status_code == 401

    # 2. Administrator
    login_admin = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@smartcart.in", "password": "Demo@123"},
    )
    admin_token = login_admin.json()["access_token"]
    r_admin = await async_client.get("/api/v1/cart", headers={"Authorization": f"Bearer {admin_token}"})
    assert r_admin.status_code == 403
    assert r_admin.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_add_item_to_cart_and_authoritative_pricing(
    async_client: AsyncClient, customer_token: str
):
    """
    Verify adding an item to the cart:
    - Creates a 10-minute reservation in PostgreSQL
    - Unit price matches authoritative database price in paise
    - Line item subtotal and grand total computed accurately
    - earliest_expiration set
    """
    s1, _, p1, _ = await get_test_store_and_products()

    resp = await async_client.post(
        "/api/v1/cart/items",
        headers={"Authorization": f"Bearer {customer_token}"},
        json={"store_id": str(s1), "product_id": str(p1), "qty": 1},
    )
    assert resp.status_code == 201
    cart = resp.json()
    assert cart["store_id"] == str(s1)
    assert cart["total_items"] == 1
    assert cart["total_paise"] == 149900  # ₹1499.00 from DB
    assert cart["earliest_expiration"] is not None

    item = cart["items"][0]
    assert item["product_id"] == str(p1)
    assert item["product_sku"] == "BT-HEAD-001"
    assert item["unit_price_paise"] == 149900
    assert item["qty"] == 1
    assert item["item_subtotal_paise"] == 149900
    assert "expires_at" in item

    # Cleanup
    await async_client.delete("/api/v1/cart", headers={"Authorization": f"Bearer {customer_token}"})


@pytest.mark.asyncio
async def test_add_same_product_merges_quantity(
    async_client: AsyncClient, customer_token: str
):
    """
    Verify adding an already-present product merges quantities and preserves single line item.
    """
    s1, _, p1, _ = await get_test_store_and_products()

    # Add 1 unit
    r1 = await async_client.post(
        "/api/v1/cart/items",
        headers={"Authorization": f"Bearer {customer_token}"},
        json={"store_id": str(s1), "product_id": str(p1), "qty": 1},
    )
    assert r1.status_code == 201

    # Add 2 more units of same product
    r2 = await async_client.post(
        "/api/v1/cart/items",
        headers={"Authorization": f"Bearer {customer_token}"},
        json={"store_id": str(s1), "product_id": str(p1), "qty": 2},
    )
    assert r2.status_code == 200 or r2.status_code == 201
    cart = r2.json()
    assert len(cart["items"]) == 1
    assert cart["items"][0]["qty"] == 3
    assert cart["total_items"] == 3
    assert cart["total_paise"] == 3 * 149900

    # Cleanup
    await async_client.delete("/api/v1/cart", headers={"Authorization": f"Bearer {customer_token}"})


@pytest.mark.asyncio
async def test_single_store_cart_constraint(
    async_client: AsyncClient, customer_token: str
):
    """
    Verify cart rejects adding an item from a different fulfillment store.
    """
    s1, s2, p1, p2 = await get_test_store_and_products()

    # Add item from Store 1
    r1 = await async_client.post(
        "/api/v1/cart/items",
        headers={"Authorization": f"Bearer {customer_token}"},
        json={"store_id": str(s1), "product_id": str(p1), "qty": 1},
    )
    assert r1.status_code == 201

    # Attempt to add item from Store 2 -> Rejected with HTTP 400 Bad Request
    r2 = await async_client.post(
        "/api/v1/cart/items",
        headers={"Authorization": f"Bearer {customer_token}"},
        json={"store_id": str(s2), "product_id": str(p2), "qty": 1},
    )
    assert r2.status_code == 400
    assert r2.json()["error"]["code"] == "BAD_REQUEST"
    assert "different store" in r2.json()["error"]["message"].lower()

    # Cleanup
    await async_client.delete("/api/v1/cart", headers={"Authorization": f"Bearer {customer_token}"})


@pytest.mark.asyncio
async def test_add_item_insufficient_stock(
    async_client: AsyncClient, customer_token: str
):
    """
    Verify adding excessive quantity returns HTTP 409 Conflict (INSUFFICIENT_STOCK).
    """
    s1, _, p1, _ = await get_test_store_and_products()

    resp = await async_client.post(
        "/api/v1/cart/items",
        headers={"Authorization": f"Bearer {customer_token}"},
        json={"store_id": str(s1), "product_id": str(p1), "qty": 999999},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "INSUFFICIENT_STOCK"


@pytest.mark.asyncio
async def test_update_cart_quantity_lifecycle_and_safety(
    async_client: AsyncClient, customer_token: str
):
    """
    Verify quantity update and transaction safety:
    1. Update quantity to 2 -> Success
    2. Attempt to update quantity to 999999 -> Insufficient stock (HTTP 409)
    3. Verify original hold of 2 units is preserved without loss via savepoint rollback
    """
    s1, _, p1, _ = await get_test_store_and_products()

    # Add initial 1 unit
    await async_client.post(
        "/api/v1/cart/items",
        headers={"Authorization": f"Bearer {customer_token}"},
        json={"store_id": str(s1), "product_id": str(p1), "qty": 1},
    )

    # 1. Update quantity to 2
    update_resp = await async_client.patch(
        f"/api/v1/cart/items/{p1}",
        headers={"Authorization": f"Bearer {customer_token}"},
        json={"qty": 2},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["total_items"] == 2
    assert update_resp.json()["items"][0]["qty"] == 2

    # 2. Update with excessive quantity -> Fails with 409 Conflict
    excess_resp = await async_client.patch(
        f"/api/v1/cart/items/{p1}",
        headers={"Authorization": f"Bearer {customer_token}"},
        json={"qty": 999999},
    )
    assert excess_resp.status_code == 409
    assert excess_resp.json()["error"]["code"] == "INSUFFICIENT_STOCK"

    # 3. Verify original 2 units remain safe in cart
    cart_resp = await async_client.get(
        "/api/v1/cart",
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    assert cart_resp.status_code == 200
    assert cart_resp.json()["total_items"] == 2
    assert cart_resp.json()["items"][0]["qty"] == 2

    # Cleanup
    await async_client.delete("/api/v1/cart", headers={"Authorization": f"Bearer {customer_token}"})


@pytest.mark.asyncio
async def test_remove_cart_item_and_clear_cart(
    async_client: AsyncClient, customer_token: str
):
    """
    Verify line item removal and full cart clearing.
    """
    s1, _, p1, p2 = await get_test_store_and_products()

    # Add 2 items
    await async_client.post(
        "/api/v1/cart/items",
        headers={"Authorization": f"Bearer {customer_token}"},
        json={"store_id": str(s1), "product_id": str(p1), "qty": 1},
    )
    await async_client.post(
        "/api/v1/cart/items",
        headers={"Authorization": f"Bearer {customer_token}"},
        json={"store_id": str(s1), "product_id": str(p2), "qty": 1},
    )

    # 1. Remove item 1
    r_rem = await async_client.delete(
        f"/api/v1/cart/items/{p1}",
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    assert r_rem.status_code == 200
    cart_after_rem = r_rem.json()
    assert cart_after_rem["total_items"] == 1
    assert cart_after_rem["items"][0]["product_id"] == str(p2)

    # 2. Clear entire cart
    r_clear = await async_client.delete(
        "/api/v1/cart",
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    assert r_clear.status_code == 200
    assert r_clear.json()["total_items"] == 0
    assert r_clear.json()["items"] == []


@pytest.mark.asyncio
async def test_expired_reservations_excluded_from_cart(
    async_client: AsyncClient, customer_token: str
):
    """
    Verify reservations whose expires_at is in the past are automatically excluded from the cart.
    """
    s1, _, p1, _ = await get_test_store_and_products()
    expired_res_id = uuid.uuid4()

    # Insert an expired reservation into DB directly
    async with AsyncSessionLocal() as session:
        cust_res = await session.execute(
            text("SELECT id FROM customers WHERE user_id = (SELECT id FROM users WHERE email = 'demo@smartcart.in')")
        )
        cust_id = cust_res.scalar_one()

        expired_time = datetime.now(timezone.utc) - timedelta(minutes=15)
        await session.execute(
            text(
                "INSERT INTO reservations (id, customer_id, store_id, product_id, qty, status, expires_at) "
                "VALUES (:id, :c, :s, :p, 1, 'ACTIVE', :exp)"
            ),
            {"id": expired_res_id, "c": cust_id, "s": s1, "p": p1, "exp": expired_time},
        )
        await session.commit()

    try:
        # GET /cart should exclude the expired reservation
        cart_resp = await async_client.get(
            "/api/v1/cart",
            headers={"Authorization": f"Bearer {customer_token}"},
        )
        assert cart_resp.status_code == 200
        assert not any(i["reservation_id"] == str(expired_res_id) for i in cart_resp.json()["items"])

    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(text("DELETE FROM reservations WHERE id = :id"), {"id": expired_res_id})
            await session.commit()


@pytest.mark.asyncio
async def test_cart_tamper_resistance_and_validation(
    async_client: AsyncClient, customer_token: str
):
    """
    Verify client cannot tamper with prices or pass invalid quantities:
    - Extra fields like 'price_paise' rejected with HTTP 422
    - Zero or negative quantities rejected with HTTP 422
    """
    s1, _, p1, _ = await get_test_store_and_products()

    # Injected price parameter
    r1 = await async_client.post(
        "/api/v1/cart/items",
        headers={"Authorization": f"Bearer {customer_token}"},
        json={"store_id": str(s1), "product_id": str(p1), "qty": 1, "price_paise": 10},
    )
    assert r1.status_code == 422
    assert r1.json()["error"]["code"] == "VALIDATION_ERROR"

    # Zero quantity
    r2 = await async_client.post(
        "/api/v1/cart/items",
        headers={"Authorization": f"Bearer {customer_token}"},
        json={"store_id": str(s1), "product_id": str(p1), "qty": 0},
    )
    assert r2.status_code == 422

    # Negative quantity in update
    r3 = await async_client.patch(
        f"/api/v1/cart/items/{p1}",
        headers={"Authorization": f"Bearer {customer_token}"},
        json={"qty": -1},
    )
    assert r3.status_code == 422
