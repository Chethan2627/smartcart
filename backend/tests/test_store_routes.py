"""
Integration and API tests for SmartCart 2.0 Store Catalogue Routes:
- GET /api/v1/stores (active store listing, pagination, state/city location filtering)
- GET /api/v1/stores/{store_id} (store details, inactive store restrictions, admin access)
- Store manager isolation
- Error response standardization and input validation
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


@pytest.mark.asyncio
async def test_list_active_stores_unauthenticated(async_client: AsyncClient):
    """
    Verify public visitors can list active fulfillment stores.
    Checks:
    - HTTP 200 OK
    - Inactive stores are omitted
    - Expected fields present
    - No sensitive internal fields exposed
    """
    resp = await async_client.get("/api/v1/stores")
    assert resp.status_code == 200
    stores = resp.json()
    assert isinstance(stores, list)
    assert len(stores) >= 5

    for store in stores:
        assert "id" in store
        assert "code" in store
        assert "name" in store
        assert "city" in store
        assert "state" in store
        assert store["is_active"] is True
        assert "created_at" in store
        # Ensure no sensitive credentials or internal keys leak
        assert "password" not in store
        assert "secret" not in store


@pytest.mark.asyncio
async def test_list_stores_location_filtering(async_client: AsyncClient):
    """
    Verify store listing filters correctly by state and city.
    """
    # Filter by state
    resp = await async_client.get("/api/v1/stores?state=Karnataka")
    assert resp.status_code == 200
    stores = resp.json()
    assert len(stores) >= 2
    for s in stores:
        assert s["state"] == "Karnataka"

    # Filter by state and city
    resp_city = await async_client.get("/api/v1/stores?state=Karnataka&city=Bengaluru")
    assert resp_city.status_code == 200
    stores_city = resp_city.json()
    assert len(stores_city) == 1
    assert stores_city[0]["city"] == "Bengaluru"
    assert stores_city[0]["code"] == "STORE-001"

    # Nonexistent location
    resp_empty = await async_client.get("/api/v1/stores?state=NonExistentState")
    assert resp_empty.status_code == 200
    assert resp_empty.json() == []


@pytest.mark.asyncio
async def test_list_stores_pagination(async_client: AsyncClient):
    """
    Verify pagination offsets and limits function correctly.
    """
    resp_all = await async_client.get("/api/v1/stores?skip=0&limit=5")
    assert resp_all.status_code == 200
    all_stores = resp_all.json()
    assert len(all_stores) >= 3

    resp_paged = await async_client.get("/api/v1/stores?skip=1&limit=2")
    assert resp_paged.status_code == 200
    paged_stores = resp_paged.json()
    assert len(paged_stores) == 2
    assert paged_stores[0]["id"] == all_stores[1]["id"]
    assert paged_stores[1]["id"] == all_stores[2]["id"]


@pytest.mark.asyncio
async def test_list_stores_invalid_query_parameters(async_client: AsyncClient):
    """
    Verify validation rejection for invalid query parameters:
    - Negative skip (skip < 0)
    - Zero or negative limit (limit < 1)
    - Exceeded limit (limit > 100)
    - Non-integer skip
    """
    # Negative skip
    r1 = await async_client.get("/api/v1/stores?skip=-1")
    assert r1.status_code == 422
    assert r1.json()["error"]["code"] == "VALIDATION_ERROR"

    # Zero limit
    r2 = await async_client.get("/api/v1/stores?limit=0")
    assert r2.status_code == 422
    assert r2.json()["error"]["code"] == "VALIDATION_ERROR"

    # Excess limit (> 100)
    r3 = await async_client.get("/api/v1/stores?limit=101")
    assert r3.status_code == 422
    assert r3.json()["error"]["code"] == "VALIDATION_ERROR"

    # Non-integer skip
    r4 = await async_client.get("/api/v1/stores?skip=abc")
    assert r4.status_code == 422
    assert r4.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_get_store_by_id_success(async_client: AsyncClient):
    """
    Verify retrieving an active store by valid UUID.
    """
    list_resp = await async_client.get("/api/v1/stores")
    first_store = list_resp.json()[0]
    store_id = first_store["id"]

    resp = await async_client.get(f"/api/v1/stores/{store_id}")
    assert resp.status_code == 200
    store = resp.json()
    assert store["id"] == store_id
    assert store["code"] == first_store["code"]
    assert store["name"] == first_store["name"]
    assert store["is_active"] is True


@pytest.mark.asyncio
async def test_get_store_by_id_not_found(async_client: AsyncClient):
    """
    Verify requesting a nonexistent store UUID returns HTTP 404 NOT_FOUND.
    """
    missing_id = str(uuid.uuid4())
    resp = await async_client.get(f"/api/v1/stores/{missing_id}")
    assert resp.status_code == 404
    data = resp.json()
    assert data["error"]["code"] == "NOT_FOUND"
    assert "not found" in data["error"]["message"].lower()


@pytest.mark.asyncio
async def test_get_store_invalid_uuid(async_client: AsyncClient):
    """
    Verify passing a malformed UUID in the path returns HTTP 422 VALIDATION_ERROR.
    """
    resp = await async_client.get("/api/v1/stores/not-a-valid-uuid")
    assert resp.status_code == 422
    data = resp.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_inactive_store_restrictions_and_admin_access(async_client: AsyncClient):
    """
    Verify inactive store handling:
    - Public visitors and customers cannot view inactive stores (returns HTTP 400).
    - Inactive stores do not appear in public listings.
    - Administrators CAN view inactive stores.
    """
    inactive_id = uuid.uuid4()
    inactive_code = f"STORE-INACT-{uuid.uuid4().hex[:6].upper()}"

    # Insert an inactive store into PostgreSQL
    async with AsyncSessionLocal() as session:
        inactive_store = Store(
            id=inactive_id,
            code=inactive_code,
            name="Inactive Test Warehouse",
            city="Panaji",
            state="Goa",
            is_active=False,
        )
        session.add(inactive_store)
        await session.commit()

    try:
        # 1. Public listing must NOT include inactive store
        list_resp = await async_client.get("/api/v1/stores?state=Goa")
        assert list_resp.status_code == 200
        assert not any(s["code"] == inactive_code for s in list_resp.json())

        # 2. Public direct lookup must return HTTP 400 Bad Request
        direct_resp = await async_client.get(f"/api/v1/stores/{inactive_id}")
        assert direct_resp.status_code == 400
        assert direct_resp.json()["error"]["code"] == "BAD_REQUEST"
        assert "is inactive" in direct_resp.json()["error"]["message"]

        # 3. Customer direct lookup must also return HTTP 400 Bad Request
        login_cust = await async_client.post(
            "/api/v1/auth/login",
            json={"email": "demo@smartcart.in", "password": "Demo@123"},
        )
        cust_token = login_cust.json()["access_token"]
        cust_resp = await async_client.get(
            f"/api/v1/stores/{inactive_id}",
            headers={"Authorization": f"Bearer {cust_token}"},
        )
        assert cust_resp.status_code == 400
        assert cust_resp.json()["error"]["code"] == "BAD_REQUEST"

        # 4. Administrator CAN view inactive store
        login_admin = await async_client.post(
            "/api/v1/auth/login",
            json={"email": "admin@smartcart.in", "password": "Demo@123"},
        )
        admin_token = login_admin.json()["access_token"]
        admin_resp = await async_client.get(
            f"/api/v1/stores/{inactive_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert admin_resp.status_code == 200
        assert admin_resp.json()["id"] == str(inactive_id)
        assert admin_resp.json()["is_active"] is False

        # 5. Administrator can list inactive stores by location with is_active=false
        admin_list_resp = await async_client.get(
            "/api/v1/stores?state=Goa&is_active=false",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert admin_list_resp.status_code == 200
        assert any(s["code"] == inactive_code for s in admin_list_resp.json())

    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(text("DELETE FROM stores WHERE id = :id"), {"id": inactive_id})
            await session.commit()


@pytest.mark.asyncio
async def test_store_manager_isolation_on_inactive_store(async_client: AsyncClient):
    """
    Verify store manager isolation:
    - A store manager CAN view their own assigned store even if inactive.
    - A store manager CANNOT view another store that is inactive (HTTP 400 Bad Request).
    """
    store_a_id = uuid.uuid4()
    store_b_id = uuid.uuid4()
    code_a = f"STR-A-{uuid.uuid4().hex[:6].upper()}"
    code_b = f"STR-B-{uuid.uuid4().hex[:6].upper()}"

    manager_user_id = uuid.uuid4()
    manager_email = f"manager_{uuid.uuid4().hex[:6]}@smartcart.in"

    async with AsyncSessionLocal() as session:
        # Create Store A (inactive) and Store B (inactive)
        store_a = Store(id=store_a_id, code=code_a, name="Store A", city="Pune", state="MH", is_active=False)
        store_b = Store(id=store_b_id, code=code_b, name="Store B", city="Nagpur", state="MH", is_active=False)
        session.add_all([store_a, store_b])

        # Create Store Manager assigned to Store A
        manager = User(
            id=manager_user_id,
            email=manager_email,
            full_name="Store Manager Test",
            password_hash="argon2id$mocked",
            role=UserRole.STORE_MANAGER,
            assigned_store_id=store_a_id,
            is_active=True,
        )
        session.add(manager)
        await session.commit()

    try:
        manager_token = create_access_token(
            data={
                "sub": str(manager_user_id),
                "role": UserRole.STORE_MANAGER.value,
                "store_id": str(store_a_id),
            }
        )

        # 1. Manager views assigned Store A (inactive) -> Success 200 OK
        resp_a = await async_client.get(
            f"/api/v1/stores/{store_a_id}",
            headers={"Authorization": f"Bearer {manager_token}"},
        )
        assert resp_a.status_code == 200
        assert resp_a.json()["id"] == str(store_a_id)
        assert resp_a.json()["is_active"] is False

        # 2. Manager views unassigned Store B (inactive) -> Rejected 400 Bad Request
        resp_b = await async_client.get(
            f"/api/v1/stores/{store_b_id}",
            headers={"Authorization": f"Bearer {manager_token}"},
        )
        assert resp_b.status_code == 400
        assert resp_b.json()["error"]["code"] == "BAD_REQUEST"
        assert "is inactive" in resp_b.json()["error"]["message"]

    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(text("DELETE FROM users WHERE id = :id"), {"id": manager_user_id})
            await session.execute(
                text("DELETE FROM stores WHERE id IN (:id_a, :id_b)"),
                {"id_a": store_a_id, "id_b": store_b_id},
            )
            await session.commit()
