"""
Integration and API tests for SmartCart 2.0 User Management Routes:
- GET /api/v1/users/me (current user profile)
- GET /api/v1/users/me/customer (current customer profile)
- GET /api/v1/users/{user_id} (authorized user lookup and privacy enforcement)
- PATCH /api/v1/users/{user_id}/status (admin-only activation/deactivation)
- PUT /api/v1/users/{user_id}/store-manager (admin-only store manager assignment)
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
from app.repositories import StoreRepository, UserRepository


@pytest_asyncio.fixture(autouse=True)
async def dispose_engine_after_test():
    """Ensure engine connections are cleanly disposed before event loop teardown."""
    yield
    if async_engine is not None:
        await async_engine.dispose()


@pytest.mark.asyncio
async def test_get_users_me_success(async_client: AsyncClient):
    """Verify GET /users/me returns authenticated user's profile and no password hash."""
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "demo@smartcart.in", "password": "Demo@123"},
    )
    token = login_resp.json()["access_token"]

    resp = await async_client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "demo@smartcart.in"
    assert data["role"] == "CUSTOMER"
    assert data["is_active"] is True
    assert "password_hash" not in resp.text


@pytest.mark.asyncio
async def test_get_users_me_customer_profile(async_client: AsyncClient):
    """Verify GET /users/me/customer returns full customer profile for CUSTOMER accounts."""
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "demo@smartcart.in", "password": "Demo@123"},
    )
    token = login_resp.json()["access_token"]

    resp = await async_client.get(
        "/api/v1/users/me/customer",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert "user_id" in data
    assert "phone" in data
    assert "address" in data
    assert "user" in data
    assert data["user"]["email"] == "demo@smartcart.in"
    assert "password_hash" not in resp.text


@pytest.mark.asyncio
async def test_get_users_me_customer_profile_non_customer_rejected(async_client: AsyncClient):
    """Verify non-customer accounts calling /users/me/customer receive HTTP 403 FORBIDDEN."""
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@smartcart.in", "password": "Demo@123"},
    )
    token = login_resp.json()["access_token"]

    resp = await async_client.get(
        "/api/v1/users/me/customer",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
    data = resp.json()
    assert data["error"]["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_user_lookup_authorization_rules(async_client: AsyncClient):
    """
    Verify GET /users/{user_id} privacy enforcement:
    - Admin can view any user by ID.
    - Customer can view own user ID.
    - Customer is forbidden (403) from viewing another user ID.
    - Non-existent user ID returns 404.
    """
    async with AsyncSessionLocal() as session:
        user_repo = UserRepository(session)
        demo_user = await user_repo.get_by_email("demo@smartcart.in")
        admin_user = await user_repo.get_by_email("admin@smartcart.in")
        mgr_user = await user_repo.get_by_email("manager.bengaluru@smartcart.in")

    token_cust = create_access_token(data={"sub": str(demo_user.id)})
    token_admin = create_access_token(data={"sub": str(admin_user.id)})

    # 1. Customer looks up their OWN ID -> 200 OK
    resp1 = await async_client.get(
        f"/api/v1/users/{demo_user.id}",
        headers={"Authorization": f"Bearer {token_cust}"},
    )
    assert resp1.status_code == 200
    assert resp1.json()["email"] == "demo@smartcart.in"
    assert "password_hash" not in resp1.text

    # 2. Customer looks up manager's ID -> 403 FORBIDDEN
    resp2 = await async_client.get(
        f"/api/v1/users/{mgr_user.id}",
        headers={"Authorization": f"Bearer {token_cust}"},
    )
    assert resp2.status_code == 403
    assert resp2.json()["error"]["code"] == "FORBIDDEN"

    # 3. Admin looks up demo user's ID -> 200 OK
    resp3 = await async_client.get(
        f"/api/v1/users/{demo_user.id}",
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert resp3.status_code == 200
    assert resp3.json()["id"] == str(demo_user.id)

    # 4. Admin looks up nonexistent ID -> 404 NOT_FOUND
    ghost_id = uuid.uuid4()
    resp4 = await async_client.get(
        f"/api/v1/users/{ghost_id}",
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert resp4.status_code == 404
    assert resp4.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_update_user_status_admin_only(async_client: AsyncClient):
    """
    Verify PATCH /users/{user_id}/status:
    - Admin can deactivate and reactivate a customer account.
    - Admin cannot deactivate their own account (400 Bad Request).
    - Non-admin callers receive 403 FORBIDDEN.
    """
    target_user_id = uuid.uuid4()
    run_suffix = uuid.uuid4().hex[:8]
    email = f"status_test_{run_suffix}@smartcart.in"

    async with AsyncSessionLocal() as session:
        user_repo = UserRepository(session)
        admin_user = await user_repo.get_by_email("admin@smartcart.in")
        demo_user = await user_repo.get_by_email("demo@smartcart.in")

        target_user = User(
            id=target_user_id,
            email=email,
            full_name="Status Target User",
            password_hash="mock_hash",
            role=UserRole.CUSTOMER,
            is_active=True,
        )
        session.add(target_user)
        await session.commit()

    token_admin = create_access_token(data={"sub": str(admin_user.id)})
    token_cust = create_access_token(data={"sub": str(demo_user.id)})

    try:
        # 1. Customer attempts status change -> 403 FORBIDDEN
        resp1 = await async_client.patch(
            f"/api/v1/users/{target_user_id}/status",
            json={"is_active": False},
            headers={"Authorization": f"Bearer {token_cust}"},
        )
        assert resp1.status_code == 403
        assert resp1.json()["error"]["code"] == "FORBIDDEN"

        # 2. Admin attempts to deactivate self -> 400 BAD_REQUEST
        resp2 = await async_client.patch(
            f"/api/v1/users/{admin_user.id}/status",
            json={"is_active": False},
            headers={"Authorization": f"Bearer {token_admin}"},
        )
        assert resp2.status_code == 400
        assert resp2.json()["error"]["code"] == "BAD_REQUEST"
        assert "cannot deactivate their own account" in resp2.json()["error"]["message"]

        # 3. Admin deactivates target user -> 200 OK
        resp3 = await async_client.patch(
            f"/api/v1/users/{target_user_id}/status",
            json={"is_active": False},
            headers={"Authorization": f"Bearer {token_admin}"},
        )
        assert resp3.status_code == 200
        assert resp3.json()["is_active"] is False

        # 4. Admin reactivates target user -> 200 OK
        resp4 = await async_client.patch(
            f"/api/v1/users/{target_user_id}/status",
            json={"is_active": True},
            headers={"Authorization": f"Bearer {token_admin}"},
        )
        assert resp4.status_code == 200
        assert resp4.json()["is_active"] is True
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(text("DELETE FROM users WHERE id = :u"), {"u": target_user_id})
            await session.commit()


@pytest.mark.asyncio
async def test_assign_store_manager_admin_only(async_client: AsyncClient):
    """
    Verify PUT /users/{user_id}/store-manager:
    - Admin can assign a customer to be STORE_MANAGER for an active store.
    - Assignment to an inactive store raises 400 BAD_REQUEST.
    - Assignment to a non-existent store raises 404 NOT_FOUND.
    - Customer caller receives 403 FORBIDDEN.
    """
    target_user_id = uuid.uuid4()
    run_suffix = uuid.uuid4().hex[:8]
    email = f"mgr_target_{run_suffix}@smartcart.in"

    async with AsyncSessionLocal() as session:
        user_repo = UserRepository(session)
        store_repo = StoreRepository(session)
        admin_user = await user_repo.get_by_email("admin@smartcart.in")
        demo_user = await user_repo.get_by_email("demo@smartcart.in")
        store_2 = await store_repo.get_by_code("STORE-002")

        target_user = User(
            id=target_user_id,
            email=email,
            full_name="Future Manager",
            password_hash="mock_hash",
            role=UserRole.CUSTOMER,
            is_active=True,
        )
        session.add(target_user)
        await session.commit()

    token_admin = create_access_token(data={"sub": str(admin_user.id)})
    token_cust = create_access_token(data={"sub": str(demo_user.id)})

    try:
        # 1. Customer attempts promotion -> 403 FORBIDDEN
        resp1 = await async_client.put(
            f"/api/v1/users/{target_user_id}/store-manager",
            json={"assigned_store_id": str(store_2.id)},
            headers={"Authorization": f"Bearer {token_cust}"},
        )
        assert resp1.status_code == 403

        # 2. Admin assigns non-existent store -> 404 NOT_FOUND
        ghost_store_id = uuid.uuid4()
        resp2 = await async_client.put(
            f"/api/v1/users/{target_user_id}/store-manager",
            json={"assigned_store_id": str(ghost_store_id)},
            headers={"Authorization": f"Bearer {token_admin}"},
        )
        assert resp2.status_code == 404
        assert resp2.json()["error"]["code"] == "NOT_FOUND"

        # 3. Admin assigns valid STORE-002 -> 200 OK
        resp3 = await async_client.put(
            f"/api/v1/users/{target_user_id}/store-manager",
            json={"assigned_store_id": str(store_2.id)},
            headers={"Authorization": f"Bearer {token_admin}"},
        )
        assert resp3.status_code == 200
        data = resp3.json()
        assert data["role"] == "STORE_MANAGER"
        assert data["assigned_store_id"] == str(store_2.id)
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(text("DELETE FROM users WHERE id = :u"), {"u": target_user_id})
            await session.commit()
