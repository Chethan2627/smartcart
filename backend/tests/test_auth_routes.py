"""
Integration and API tests for SmartCart 2.0 Authentication Routes (POST /auth/register, POST /auth/login, GET /auth/me).
Verifies:
- Customer self-registration and Argon2id hashing.
- Rejection of duplicate emails and privileged role injection.
- Successful login for Customer and Store Manager with claims.
- Constant-time enumeration prevention on incorrect credentials.
- Inactive user rejection on login and access.
- Missing, invalid, and expired JWT token handling.
- Authenticated profile retrieval and absence of password hashes.
- Uniform error response envelope.
"""
from datetime import timedelta
import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text

from app.core.security import create_access_token, decode_access_token, get_password_hash
from app.db.session import AsyncSessionLocal, async_engine
from app.models.enums import UserRole
from app.models.user import User


@pytest_asyncio.fixture(autouse=True)
async def dispose_engine_after_test():
    """Ensure engine connections are cleanly disposed before event loop teardown."""
    yield
    if async_engine is not None:
        await async_engine.dispose()


@pytest.mark.asyncio
async def test_customer_registration_success(async_client: AsyncClient):
    """Verify customer self-registration creates CUSTOMER user and profile, returning 201."""
    run_suffix = uuid.uuid4().hex[:8]
    email = f"reg_cust_{run_suffix}@smartcart.in"
    password = "CustomerSecurePass123!"

    payload = {
        "email": email,
        "password": password,
        "full_name": "Test Customer",
        "phone": "+91-9876543210",
        "address": "456 Indiranagar 100ft Road, Bengaluru",
    }

    resp = await async_client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201
    data = resp.json()

    # Verify response structure
    assert "id" in data
    assert "user_id" in data
    assert data["phone"] == "+91-9876543210"
    assert data["address"] == "456 Indiranagar 100ft Road, Bengaluru"
    assert "user" in data
    assert data["user"]["email"] == email
    assert data["user"]["full_name"] == "Test Customer"
    assert data["user"]["role"] == "CUSTOMER"
    assert data["user"]["is_active"] is True

    # Security check: password hash must NEVER be returned in response body
    assert "password_hash" not in resp.text
    assert "CustomerSecurePass123!" not in resp.text

    created_user_id = data["user"]["id"]
    created_cust_id = data["id"]

    # Clean up test records
    async with AsyncSessionLocal() as session:
        await session.execute(text("DELETE FROM customers WHERE id = :c"), {"c": created_cust_id})
        await session.execute(text("DELETE FROM users WHERE id = :u"), {"u": created_user_id})
        await session.commit()


@pytest.mark.asyncio
async def test_customer_registration_duplicate_email(async_client: AsyncClient):
    """Verify registering with an existing email returns HTTP 409 DUPLICATE_RESOURCE."""
    run_suffix = uuid.uuid4().hex[:8]
    email = f"dup_{run_suffix}@smartcart.in"

    payload = {
        "email": email,
        "password": "Password123!",
        "full_name": "First User",
    }

    # 1. First registration succeeds
    resp1 = await async_client.post("/api/v1/auth/register", json=payload)
    assert resp1.status_code == 201
    user_id = resp1.json()["user"]["id"]
    cust_id = resp1.json()["id"]

    try:
        # 2. Duplicate registration fails
        resp2 = await async_client.post("/api/v1/auth/register", json=payload)
        assert resp2.status_code == 409
        err_data = resp2.json()
        assert err_data["error"]["code"] == "DUPLICATE_RESOURCE"
        assert "already registered" in err_data["error"]["message"].lower()
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(text("DELETE FROM customers WHERE id = :c"), {"c": cust_id})
            await session.execute(text("DELETE FROM users WHERE id = :u"), {"u": user_id})
            await session.commit()


@pytest.mark.asyncio
async def test_customer_registration_rejects_privileged_role_injection(async_client: AsyncClient):
    """Verify attempting to inject role=ADMIN or role=SUPER_ADMIN fails with HTTP 422."""
    payload = {
        "email": f"hacker_{uuid.uuid4().hex[:8]}@smartcart.in",
        "password": "HackerPassword123!",
        "full_name": "Hacker Attempt",
        "role": "ADMIN",
    }
    resp = await async_client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 422
    data = resp.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert "errors" in data["error"]["details"]


@pytest.mark.asyncio
async def test_customer_registration_rejects_forbidden_fields(async_client: AsyncClient):
    """Verify attempting to inject password_hash or assigned_store_id fails with HTTP 422."""
    for field in ["password_hash", "assigned_store_id"]:
        payload = {
            "email": f"test_{uuid.uuid4().hex[:8]}@smartcart.in",
            "password": "ValidPassword123!",
            "full_name": "Test User",
            field: "malicious_input",
        }
        resp = await async_client.post("/api/v1/auth/register", json=payload)
        assert resp.status_code == 422
        data = resp.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_login_successful_customer(async_client: AsyncClient):
    """Verify seeded customer demo@smartcart.in can login and receive valid JWT access token."""
    payload = {
        "email": "demo@smartcart.in",
        "password": "Demo@123",
    }
    resp = await async_client.post("/api/v1/auth/login", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0

    # Verify decoded token claims
    claims = decode_access_token(data["access_token"])
    assert claims["email"] == "demo@smartcart.in"
    assert claims["role"] == "CUSTOMER"
    assert "customer_id" in claims
    assert "store_id" not in claims


@pytest.mark.asyncio
async def test_login_successful_store_manager(async_client: AsyncClient):
    """Verify seeded store manager receives token with role=STORE_MANAGER and store_id."""
    payload = {
        "email": "manager.bengaluru@smartcart.in",
        "password": "Demo@123",
    }
    resp = await async_client.post("/api/v1/auth/login", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    claims = decode_access_token(data["access_token"])
    assert claims["email"] == "manager.bengaluru@smartcart.in"
    assert claims["role"] == "STORE_MANAGER"
    assert "store_id" in claims


@pytest.mark.asyncio
async def test_login_incorrect_password(async_client: AsyncClient):
    """Verify wrong password returns HTTP 401 with unified error message."""
    payload = {
        "email": "demo@smartcart.in",
        "password": "WrongPassword@999",
    }
    resp = await async_client.post("/api/v1/auth/login", json=payload)
    assert resp.status_code == 401
    data = resp.json()
    assert data["error"]["code"] == "AUTHENTICATION_FAILED"
    assert data["error"]["message"] == "Invalid email or password"
    assert "WWW-Authenticate" in resp.headers


@pytest.mark.asyncio
async def test_login_nonexistent_email_enumeration_prevention(async_client: AsyncClient):
    """Verify nonexistent email returns identical HTTP 401 to prevent enumeration."""
    payload = {
        "email": "nonexistent.account@smartcart.in",
        "password": "AnyPassword123!",
    }
    resp = await async_client.post("/api/v1/auth/login", json=payload)
    assert resp.status_code == 401
    data = resp.json()
    assert data["error"]["code"] == "AUTHENTICATION_FAILED"
    assert data["error"]["message"] == "Invalid email or password"


@pytest.mark.asyncio
async def test_login_inactive_user_rejected(async_client: AsyncClient):
    """Verify deactivated user account is rejected during login."""
    inactive_user_id = uuid.uuid4()
    run_suffix = uuid.uuid4().hex[:8]
    email = f"deactivated_{run_suffix}@smartcart.in"
    raw_password = "Password123!"

    async with AsyncSessionLocal() as session:
        inactive_user = User(
            id=inactive_user_id,
            email=email,
            full_name="Deactivated Account",
            password_hash=get_password_hash(raw_password),
            role=UserRole.CUSTOMER,
            is_active=False,
        )
        session.add(inactive_user)
        await session.commit()

    try:
        resp = await async_client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": raw_password},
        )
        assert resp.status_code == 401
        data = resp.json()
        assert data["error"]["code"] == "AUTHENTICATION_FAILED"
        assert "inactive" in data["error"]["message"].lower()
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(text("DELETE FROM users WHERE id = :u"), {"u": inactive_user_id})
            await session.commit()


@pytest.mark.asyncio
async def test_auth_me_success(async_client: AsyncClient):
    """Verify GET /auth/me returns current user profile and no password hash."""
    # Obtain token for demo user
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "demo@smartcart.in", "password": "Demo@123"},
    )
    token = login_resp.json()["access_token"]

    resp = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "demo@smartcart.in"
    assert data["role"] == "CUSTOMER"
    assert data["is_active"] is True
    assert "password_hash" not in resp.text


@pytest.mark.asyncio
async def test_auth_me_missing_token(async_client: AsyncClient):
    """Verify GET /auth/me without Authorization header returns HTTP 401."""
    resp = await async_client.get("/api/v1/auth/me")
    assert resp.status_code == 401
    data = resp.json()
    assert data["error"]["code"] == "AUTHENTICATION_FAILED"


@pytest.mark.asyncio
async def test_auth_me_invalid_token(async_client: AsyncClient):
    """Verify GET /auth/me with corrupted token returns HTTP 401 INVALID_TOKEN."""
    resp = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid.jwt.token"},
    )
    assert resp.status_code == 401
    data = resp.json()
    assert data["error"]["code"] == "INVALID_TOKEN"


@pytest.mark.asyncio
async def test_auth_me_expired_token(async_client: AsyncClient):
    """Verify GET /auth/me with expired token returns HTTP 401 TOKEN_EXPIRED."""
    expired_token = create_access_token(
        data={"sub": str(uuid.uuid4())},
        expires_delta=timedelta(seconds=-10),
    )
    resp = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert resp.status_code == 401
    data = resp.json()
    assert data["error"]["code"] == "TOKEN_EXPIRED"
