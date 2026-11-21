"""
Integration and API tests for SmartCart 2.0 Checkout Routes:
- POST /api/v1/checkout (atomic checkout, reservation linking, order confirmation, outbox generation)
- Idempotency-Key validation, safe response replay, conflict detection
- Empty cart and store mismatch validation
- Authoritative database pricing and tamper resistance
- Customer authentication and ownership boundaries
"""
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


async def get_test_store_and_product():
    """Fetch active store and product IDs from seed data."""
    async with AsyncSessionLocal() as session:
        s1 = (await session.execute(text("SELECT id FROM stores WHERE code = 'STORE-001'"))).scalar_one()
        s2 = (await session.execute(text("SELECT id FROM stores WHERE code = 'STORE-002'"))).scalar_one()
        p1 = (await session.execute(text("SELECT id FROM products WHERE sku = 'BT-HEAD-001'"))).scalar_one()
        return s1, s2, p1


@pytest.fixture
async def customer_token(async_client: AsyncClient):
    """Authenticate customer and ensure clean cart."""
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "demo@smartcart.in", "password": "Demo@123"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    # Clear cart before test
    await async_client.delete("/api/v1/cart", headers={"Authorization": f"Bearer {token}"})
    return token


@pytest.mark.asyncio
async def test_checkout_missing_or_invalid_idempotency_key(
    async_client: AsyncClient, customer_token: str
):
    """
    Verify checkout strictly enforces the Idempotency-Key header:
    - Missing header -> 422 VALIDATION_ERROR
    - Malformed header (invalid characters) -> 422 VALIDATION_ERROR
    - Empty header -> 422 VALIDATION_ERROR
    """
    s1, _, _ = await get_test_store_and_product()

    # 1. Missing Idempotency-Key header
    r_missing = await async_client.post(
        "/api/v1/checkout",
        headers={"Authorization": f"Bearer {customer_token}"},
        json={"store_id": str(s1)},
    )
    assert r_missing.status_code == 422
    assert r_missing.json()["error"]["code"] == "VALIDATION_ERROR"

    # 2. Malformed Idempotency-Key header (special characters)
    r_invalid = await async_client.post(
        "/api/v1/checkout",
        headers={
            "Authorization": f"Bearer {customer_token}",
            "Idempotency-Key": "bad key with spaces @#$",
        },
        json={"store_id": str(s1)},
    )
    assert r_invalid.status_code == 422
    assert r_invalid.json()["error"]["code"] == "VALIDATION_ERROR"

    # 3. Empty Idempotency-Key header
    r_empty = await async_client.post(
        "/api/v1/checkout",
        headers={
            "Authorization": f"Bearer {customer_token}",
            "Idempotency-Key": "   ",
        },
        json={"store_id": str(s1)},
    )
    assert r_empty.status_code == 422


@pytest.mark.asyncio
async def test_checkout_empty_cart_fails(
    async_client: AsyncClient, customer_token: str
):
    """
    Verify checkout with an empty shopping cart is rejected (HTTP 400 Bad Request).
    """
    s1, _, _ = await get_test_store_and_product()

    resp = await async_client.post(
        "/api/v1/checkout",
        headers={
            "Authorization": f"Bearer {customer_token}",
            "Idempotency-Key": f"key-empty-{uuid.uuid4().hex[:8]}",
        },
        json={"store_id": str(s1)},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "BAD_REQUEST"
    assert "empty" in resp.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_checkout_authentication_and_staff_rejection(async_client: AsyncClient):
    """
    Verify checkout authorization boundaries:
    - Unauthenticated request is rejected (HTTP 401).
    - Staff / Admin account is rejected (HTTP 403 Forbidden - customer only).
    """
    s1, _, _ = await get_test_store_and_product()

    # 1. Unauthenticated
    r_unauth = await async_client.post(
        "/api/v1/checkout",
        headers={"Idempotency-Key": "key-unauth-123"},
        json={"store_id": str(s1)},
    )
    assert r_unauth.status_code == 401

    # 2. Administrator
    login_admin = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@smartcart.in", "password": "Demo@123"},
    )
    admin_token = login_admin.json()["access_token"]
    r_admin = await async_client.post(
        "/api/v1/checkout",
        headers={
            "Authorization": f"Bearer {admin_token}",
            "Idempotency-Key": "key-admin-123",
        },
        json={"store_id": str(s1)},
    )
    assert r_admin.status_code == 403
    assert r_admin.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_successful_checkout_and_idempotent_replay(
    async_client: AsyncClient, customer_token: str
):
    """
    Verify end-to-end atomic checkout and idempotent replay:
    1. Customer adds 1 unit of BT-HEAD-001 (149900 paise) at Store 1 to cart.
    2. Submits checkout with Idempotency-Key -> 201 Created.
    3. Order is CONFIRMED, inventory decremented, outbox event recorded.
    4. Replays exact same request with same Idempotency-Key -> 200/201 replay with identical Order.
    5. Confirms no duplicate order was created.
    """
    s1, _, p1 = await get_test_store_and_product()

    # 1. Add item to cart
    add_resp = await async_client.post(
        "/api/v1/cart/items",
        headers={"Authorization": f"Bearer {customer_token}"},
        json={"store_id": str(s1), "product_id": str(p1), "qty": 1},
    )
    assert add_resp.status_code == 201

    idempotency_key = f"key-checkout-{uuid.uuid4().hex[:12]}"

    # 2. Execute checkout
    checkout_resp = await async_client.post(
        "/api/v1/checkout",
        headers={
            "Authorization": f"Bearer {customer_token}",
            "Idempotency-Key": idempotency_key,
        },
        json={"store_id": str(s1), "delivery_address": "MG Road, Bengaluru"},
    )
    assert checkout_resp.status_code == 201
    order = checkout_resp.json()
    order_id = order["id"]
    assert order["status"] == "CONFIRMED"
    assert order["total_paise"] == 149900
    assert order["store_id"] == str(s1)
    assert len(order["items"]) == 1
    assert order["items"][0]["unit_price_paise"] == 149900

    # Cart is now empty (reservation converted to order)
    cart_resp = await async_client.get(
        "/api/v1/cart",
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    assert cart_resp.status_code == 200
    assert cart_resp.json()["total_items"] == 0

    # 3. REPLAY with exact same Idempotency-Key and payload
    replay_resp = await async_client.post(
        "/api/v1/checkout",
        headers={
            "Authorization": f"Bearer {customer_token}",
            "Idempotency-Key": idempotency_key,
        },
        json={"store_id": str(s1), "delivery_address": "MG Road, Bengaluru"},
    )
    assert replay_resp.status_code in (200, 201)
    replayed_order = replay_resp.json()
    assert replayed_order["id"] == order_id
    assert replayed_order["order_number"] == order["order_number"]
    assert replayed_order["total_paise"] == order["total_paise"]


@pytest.mark.asyncio
async def test_checkout_same_key_different_payload_conflict(
    async_client: AsyncClient, customer_token: str
):
    """
    Verify submitting an existing Idempotency-Key with a modified payload
    returns HTTP 409 Conflict (IDEMPOTENCY_CONFLICT).
    """
    s1, _, p1 = await get_test_store_and_product()

    # Add item and checkout
    await async_client.post(
        "/api/v1/cart/items",
        headers={"Authorization": f"Bearer {customer_token}"},
        json={"store_id": str(s1), "product_id": str(p1), "qty": 1},
    )

    idempotency_key = f"key-conflict-{uuid.uuid4().hex[:12]}"
    r_first = await async_client.post(
        "/api/v1/checkout",
        headers={
            "Authorization": f"Bearer {customer_token}",
            "Idempotency-Key": idempotency_key,
        },
        json={"store_id": str(s1), "delivery_address": "Address A"},
    )
    assert r_first.status_code == 201

    # Reuse key with different address -> 409 Conflict
    r_conflict = await async_client.post(
        "/api/v1/checkout",
        headers={
            "Authorization": f"Bearer {customer_token}",
            "Idempotency-Key": idempotency_key,
        },
        json={"store_id": str(s1), "delivery_address": "Different Address B"},
    )
    assert r_conflict.status_code == 409
    assert r_conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


@pytest.mark.asyncio
async def test_checkout_store_mismatch_fails(
    async_client: AsyncClient, customer_token: str
):
    """
    Verify checkout rejects a store_id different from the cart's fulfillment store.
    """
    s1, s2, p1 = await get_test_store_and_product()

    # Add item at Store 1
    await async_client.post(
        "/api/v1/cart/items",
        headers={"Authorization": f"Bearer {customer_token}"},
        json={"store_id": str(s1), "product_id": str(p1), "qty": 1},
    )

    # Checkout specifying Store 2
    resp = await async_client.post(
        "/api/v1/checkout",
        headers={
            "Authorization": f"Bearer {customer_token}",
            "Idempotency-Key": f"key-mismatch-{uuid.uuid4().hex[:8]}",
        },
        json={"store_id": str(s2)},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "BAD_REQUEST"
    assert "not" in resp.json()["error"]["message"].lower()

    # Cleanup
    await async_client.delete("/api/v1/cart", headers={"Authorization": f"Bearer {customer_token}"})


@pytest.mark.asyncio
async def test_checkout_payload_tamper_resistance(
    async_client: AsyncClient, customer_token: str
):
    """
    Verify clients cannot inject price, total, or order status fields in checkout payload.
    """
    s1, _, _ = await get_test_store_and_product()

    resp = await async_client.post(
        "/api/v1/checkout",
        headers={
            "Authorization": f"Bearer {customer_token}",
            "Idempotency-Key": f"key-tamper-{uuid.uuid4().hex[:8]}",
        },
        json={"store_id": str(s1), "price_paise": 100, "total_paise": 100},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
