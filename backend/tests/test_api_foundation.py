"""
Unit and integration tests for SmartCart 2.0 Phase 5 Stage 7.1:
FastAPI Foundation & Dependency Injection.

Tests:
1. Router registration and API v1 version prefix.
2. Health endpoint compatibility (/health, /api/health, /api/v1/health).
3. Centralized domain exception-to-HTTP mapping and uniform error envelope.
4. JWT authentication dependency and token verification.
5. Missing or invalid tokens (tampered, malformed, non-UUID sub).
6. Expired token rejection.
7. Inactive user rejection.
8. Role-based authorization dependencies (CUSTOMER, STORE_MANAGER, ADMIN, SUPER_ADMIN).
9. Store-manager store isolation and scoping.
10. Customer resource ownership validation.
11. Database session dependency lifecycle.
12. Service and repository dependency factories.
13. Idempotency header extraction and validation.
"""
from datetime import timedelta
from typing import Any, Dict, Optional
import uuid
from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio
from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_auth_service,
    get_cart_service,
    get_checkout_service,
    get_current_active_user,
    get_current_customer,
    get_current_user,
    get_customer_repository,
    get_db,
    get_idempotency_key,
    get_idempotency_repository,
    get_idempotency_service,
    get_inventory_repository,
    get_inventory_service,
    get_order_repository,
    get_order_service,
    get_outbox_repository,
    get_outbox_service,
    get_processed_event_repository,
    get_product_repository,
    get_product_service,
    get_reservation_repository,
    get_store_repository,
    get_store_service,
    get_token_payload,
    get_user_repository,
    get_user_service,
    require_admin,
    require_customer,
    require_customer_ownership,
    require_roles,
    require_staff,
    require_store_access,
    require_store_manager,
    require_super_admin,
    verify_customer_ownership,
    verify_store_manager_access,
)
from app.api.v1.api import api_router
from app.config import settings
from app.core.exceptions import (
    AuthenticationError,
    BadRequestError,
    ConflictError,
    DuplicateResourceError,
    ForbiddenError,
    IdempotencyConflictError,
    InsufficientStockError,
    InvalidStateTransitionError,
    InvalidTokenError,
    NotFoundError,
    SmartCartError,
    TokenExpiredError,
    ValidationError,
)
from app.core.security import create_access_token
from app.db.session import AsyncSessionLocal, async_engine
from app.main import app
from app.models.customer import Customer
from app.models.enums import UserRole
from app.models.user import User
from app.repositories import CustomerRepository, StoreRepository, UserRepository
from app.services.auth import AuthService
from app.services.cart import CartService
from app.services.checkout import CheckoutService
from app.services.idempotency import IdempotencyService
from app.services.inventory import InventoryService
from app.services.order import OrderService
from app.services.outbox import OutboxService
from app.services.product import ProductService
from app.services.store import StoreService
from app.services.user import UserService


@pytest_asyncio.fixture(autouse=True)
async def dispose_engine_after_test():
    """Ensure engine connections are cleanly disposed before event loop teardown."""
    yield
    if async_engine is not None:
        await async_engine.dispose()


# Helper router for testing foundation dependencies and exception mapping
foundation_test_router = APIRouter(prefix="/api/v1/test-foundation", tags=["Test Foundation"])


class SamplePayload(BaseModel):
    name: str = Field(min_length=3)
    qty: int = Field(gt=0)


@foundation_test_router.get("/user-me")
async def endpoint_user_me(user: User = Depends(get_current_user)):
    return {"user_id": str(user.id), "email": user.email, "role": user.role.value}


@foundation_test_router.get("/customer-me")
async def endpoint_customer_me(customer: Customer = Depends(get_current_customer)):
    return {"customer_id": str(customer.id), "user_id": str(customer.user_id)}


@foundation_test_router.get("/role-customer")
async def endpoint_role_customer(user: User = Depends(require_customer)):
    return {"authorized": True, "role": user.role.value}


@foundation_test_router.get("/role-store-manager")
async def endpoint_role_store_manager(user: User = Depends(require_store_manager)):
    return {"authorized": True, "role": user.role.value}


@foundation_test_router.get("/role-admin")
async def endpoint_role_admin(user: User = Depends(require_admin)):
    return {"authorized": True, "role": user.role.value}


@foundation_test_router.get("/role-super-admin")
async def endpoint_role_super_admin(user: User = Depends(require_super_admin)):
    return {"authorized": True, "role": user.role.value}


@foundation_test_router.get("/stores/{store_id}/manage")
async def endpoint_manage_store(
    store_id: uuid.UUID,
    user: User = Depends(require_store_access),
):
    return {"store_id": str(store_id), "manager_id": str(user.id)}


@foundation_test_router.get("/customers/{customer_id}/profile")
async def endpoint_customer_profile(
    customer_id: uuid.UUID,
    cust: Customer = Depends(require_customer_ownership),
):
    return {"customer_id": str(cust.id), "user_id": str(cust.user_id)}


@foundation_test_router.post("/idempotency-check")
async def endpoint_idempotency_check(
    key: Optional[str] = Depends(get_idempotency_key),
):
    return {"idempotency_key": key}


@foundation_test_router.post("/validate-body")
async def endpoint_validate_body(payload: SamplePayload):
    return {"received": payload.model_dump()}


@foundation_test_router.get("/throw/{error_type}")
async def endpoint_throw_error(error_type: str):
    if error_type == "not-found":
        raise NotFoundError("Resource requested was not found", {"resource_id": "res-999"})
    elif error_type == "authentication":
        raise AuthenticationError("Authentication credentials invalid")
    elif error_type == "token-expired":
        raise TokenExpiredError("Access token expired")
    elif error_type == "invalid-token":
        raise InvalidTokenError("Access token signature is invalid")
    elif error_type == "forbidden":
        raise ForbiddenError("You lack permission to access this resource")
    elif error_type == "conflict":
        raise ConflictError("State conflict encountered")
    elif error_type == "insufficient-stock":
        raise InsufficientStockError("Insufficient available inventory", {"requested": 5, "available": 2})
    elif error_type == "idempotency-conflict":
        raise IdempotencyConflictError("Idempotency key payload mismatch")
    elif error_type == "duplicate-resource":
        raise DuplicateResourceError("Resource with given identifier already exists")
    elif error_type == "validation":
        raise ValidationError("Business rule validation failed", {"field": "email"})
    elif error_type == "bad-request":
        raise BadRequestError("Bad client request parameters")
    elif error_type == "invalid-state":
        raise InvalidStateTransitionError("Order state cannot transition from DELIVERED to CANCELLED")
    elif error_type == "generic-domain":
        raise SmartCartError("Generic domain rule failure")
    elif error_type == "unhandled":
        raise RuntimeError("Unexpected internal crash with database_password=SecretPass123")
    return {"status": "ok"}


# Register foundation test router for testing
app.include_router(foundation_test_router)


# ============================================================================
# 1. Router Registration & Health Endpoints
# ============================================================================

@pytest.mark.asyncio
async def test_api_v1_router_registration(async_client: AsyncClient):
    """Verify API v1 prefix and root info endpoint."""
    response = await async_client.get("/api/v1/")
    assert response.status_code == 200
    data = response.json()
    assert data["project"] == "SmartCart 2.0"
    assert data["api_version"] == "v1"
    assert data["status"] == "online"


@pytest.mark.asyncio
async def test_health_endpoints_compatibility(async_client: AsyncClient):
    """Verify health endpoints across legacy and /api/v1 paths."""
    for path in ["/health", "/api/health", "/api/v1/health"]:
        resp = await async_client.get(path)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "services" in data
        assert "environment" in data

    for db_path in ["/health/db", "/api/health/db", "/api/v1/health/db"]:
        db_resp = await async_client.get(db_path)
        assert db_resp.status_code == 200
        db_data = db_resp.json()
        assert db_data["status"] == "healthy"
        assert db_data["database_connected"] is True


# ============================================================================
# 2. Centralized Exception-to-HTTP Mapping & Uniform Error Format
# ============================================================================

@pytest.mark.asyncio
async def test_centralized_domain_exception_mapping(async_client: AsyncClient):
    """
    Verify all domain exceptions map to exact HTTP status codes and uniform error envelope:
    { "error": { "code": "...", "message": "...", "details": {...} } }
    """
    cases = [
        ("not-found", 404, "NOT_FOUND"),
        ("authentication", 401, "AUTHENTICATION_FAILED"),
        ("token-expired", 401, "TOKEN_EXPIRED"),
        ("invalid-token", 401, "INVALID_TOKEN"),
        ("forbidden", 403, "FORBIDDEN"),
        ("conflict", 409, "CONFLICT"),
        ("insufficient-stock", 409, "INSUFFICIENT_STOCK"),
        ("idempotency-conflict", 409, "IDEMPOTENCY_CONFLICT"),
        ("duplicate-resource", 409, "DUPLICATE_RESOURCE"),
        ("validation", 422, "VALIDATION_ERROR"),
        ("bad-request", 400, "BAD_REQUEST"),
        ("invalid-state", 400, "INVALID_STATE_TRANSITION"),
        ("generic-domain", 400, "DOMAIN_ERROR"),
    ]

    for error_type, expected_status, expected_code in cases:
        resp = await async_client.get(f"/api/v1/test-foundation/throw/{error_type}")
        assert resp.status_code == expected_status, f"Failed for {error_type}: got {resp.status_code}"
        data = resp.json()
        assert "error" in data, f"Envelope missing 'error' key for {error_type}"
        assert data["error"]["code"] == expected_code
        assert isinstance(data["error"]["message"], str)
        assert isinstance(data["error"]["details"], dict)

        if expected_status == 401:
            assert "WWW-Authenticate" in resp.headers


@pytest.mark.asyncio
async def test_request_validation_error_format(async_client: AsyncClient):
    """Verify Pydantic validation failure returns HTTP 422 with structured field errors."""
    # Malformed payload violating min_length and gt constraints
    resp = await async_client.post(
        "/api/v1/test-foundation/validate-body",
        json={"name": "x", "qty": -5},
    )
    assert resp.status_code == 422
    data = resp.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert data["error"]["message"] == "Request payload validation failed"
    assert "errors" in data["error"]["details"]
    errors = data["error"]["details"]["errors"]
    assert len(errors) >= 1
    locs = [tuple(e["loc"]) for e in errors]
    assert ("body", "name") in locs or ("body", "qty") in locs


@pytest.mark.asyncio
async def test_unhandled_exception_sanitization():
    """Verify unhandled 500 errors are sanitized and never leak secrets or tracebacks."""
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/test-foundation/throw/unhandled")
        assert resp.status_code == 500
        data = resp.json()
        assert data["error"]["code"] == "INTERNAL_SERVER_ERROR"
        assert "SecretPass123" not in resp.text
        assert "RuntimeError" not in resp.text


# ============================================================================
# 3. JWT Authentication & Token Dependencies
# ============================================================================

@pytest.mark.asyncio
async def test_jwt_authentication_valid_token(async_client: AsyncClient):
    """Verify valid token resolves the user entity from PostgreSQL."""
    assert AsyncSessionLocal is not None
    async with AsyncSessionLocal() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_email("demo@smartcart.in")
        assert user is not None

    token = create_access_token(data={"sub": str(user.id), "role": user.role.value})
    resp = await async_client.get(
        "/api/v1/test-foundation/user-me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == str(user.id)
    assert data["email"] == "demo@smartcart.in"
    assert data["role"] == "CUSTOMER"


@pytest.mark.asyncio
async def test_jwt_authentication_missing_token(async_client: AsyncClient):
    """Verify request without Authorization header returns HTTP 401."""
    resp = await async_client.get("/api/v1/test-foundation/user-me")
    assert resp.status_code == 401
    data = resp.json()
    assert data["error"]["code"] == "AUTHENTICATION_FAILED"
    assert "token is required" in data["error"]["message"].lower()


@pytest.mark.asyncio
async def test_jwt_authentication_invalid_or_tampered_token(async_client: AsyncClient):
    """Verify invalid signature, malformed string, or wrong secret returns HTTP 401."""
    # 1. Malformed token string
    resp1 = await async_client.get(
        "/api/v1/test-foundation/user-me",
        headers={"Authorization": "Bearer not-a-valid-jwt-token"},
    )
    assert resp1.status_code == 401
    assert resp1.json()["error"]["code"] == "INVALID_TOKEN"

    # 2. Token signed with different secret key
    forged_token = create_access_token(
        data={"sub": str(uuid.uuid4())},
        secret_key="completely-different-signing-key-32-chars-long",
    )
    resp2 = await async_client.get(
        "/api/v1/test-foundation/user-me",
        headers={"Authorization": f"Bearer {forged_token}"},
    )
    assert resp2.status_code == 401
    assert resp2.json()["error"]["code"] == "INVALID_TOKEN"

    # 3. Token with non-UUID subject
    bad_sub_token = create_access_token(data={"sub": "not-a-uuid"})
    resp3 = await async_client.get(
        "/api/v1/test-foundation/user-me",
        headers={"Authorization": f"Bearer {bad_sub_token}"},
    )
    assert resp3.status_code == 401
    assert resp3.json()["error"]["code"] == "INVALID_TOKEN"


@pytest.mark.asyncio
async def test_jwt_authentication_expired_token(async_client: AsyncClient):
    """Verify expired token returns HTTP 401 with TOKEN_EXPIRED code."""
    expired_token = create_access_token(
        data={"sub": str(uuid.uuid4())},
        expires_delta=timedelta(seconds=-30),
    )
    resp = await async_client.get(
        "/api/v1/test-foundation/user-me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert resp.status_code == 401
    data = resp.json()
    assert data["error"]["code"] == "TOKEN_EXPIRED"


@pytest.mark.asyncio
async def test_jwt_authentication_nonexistent_user(async_client: AsyncClient):
    """Verify token for user deleted from database returns HTTP 401."""
    ghost_user_id = uuid.uuid4()
    ghost_token = create_access_token(data={"sub": str(ghost_user_id)})
    resp = await async_client.get(
        "/api/v1/test-foundation/user-me",
        headers={"Authorization": f"Bearer {ghost_token}"},
    )
    assert resp.status_code == 401
    data = resp.json()
    assert data["error"]["code"] == "AUTHENTICATION_FAILED"
    assert "does not exist" in data["error"]["message"].lower()


@pytest.mark.asyncio
async def test_inactive_user_rejection(async_client: AsyncClient):
    """
    Verify inactive user is rejected with HTTP 403 Forbidden even with a valid token.
    Uses an isolated test user cleanly rolled back or deleted.
    """
    assert AsyncSessionLocal is not None
    inactive_user_id = uuid.uuid4()
    run_suffix = uuid.uuid4().hex[:8]

    async with AsyncSessionLocal() as session:
        inactive_user = User(
            id=inactive_user_id,
            email=f"inactive_{run_suffix}@smartcart.in",
            full_name="Inactive User",
            password_hash="mock_hash",
            role=UserRole.CUSTOMER,
            is_active=False,
        )
        session.add(inactive_user)
        await session.commit()

    try:
        token = create_access_token(data={"sub": str(inactive_user_id)})
        resp = await async_client.get(
            "/api/v1/test-foundation/user-me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403
        data = resp.json()
        assert data["error"]["code"] == "FORBIDDEN"
        assert "inactive" in data["error"]["message"].lower()
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(
                text("DELETE FROM users WHERE id = :u"),
                {"u": inactive_user_id},
            )
            await session.commit()


# ============================================================================
# 4. Role-Based Authorization Dependencies
# ============================================================================

@pytest.mark.asyncio
async def test_role_authorization_enforcement(async_client: AsyncClient):
    """
    Verify role-based authorization:
    - CUSTOMER authorized for customer routes, rejected for admin/manager.
    - STORE_MANAGER authorized for manager routes, rejected for customer/admin.
    - ADMIN authorized for admin and super-admin routes.
    """
    assert AsyncSessionLocal is not None
    async with AsyncSessionLocal() as session:
        user_repo = UserRepository(session)
        cust_user = await user_repo.get_by_email("demo@smartcart.in")
        mgr_user = await user_repo.get_by_email("manager.bengaluru@smartcart.in")
        admin_user = await user_repo.get_by_email("admin@smartcart.in")
        super_user = await user_repo.get_by_email("superadmin@smartcart.in")

    token_cust = create_access_token(data={"sub": str(cust_user.id)})
    token_mgr = create_access_token(data={"sub": str(mgr_user.id)})
    token_admin = create_access_token(data={"sub": str(admin_user.id)})
    token_super = create_access_token(data={"sub": str(super_user.id)})

    # 1. Customer endpoint
    resp1 = await async_client.get(
        "/api/v1/test-foundation/role-customer",
        headers={"Authorization": f"Bearer {token_cust}"},
    )
    assert resp1.status_code == 200

    resp2 = await async_client.get(
        "/api/v1/test-foundation/role-customer",
        headers={"Authorization": f"Bearer {token_mgr}"},
    )
    assert resp2.status_code == 403
    assert resp2.json()["error"]["code"] == "FORBIDDEN"

    # 2. Store Manager endpoint
    resp3 = await async_client.get(
        "/api/v1/test-foundation/role-store-manager",
        headers={"Authorization": f"Bearer {token_mgr}"},
    )
    assert resp3.status_code == 200

    resp4 = await async_client.get(
        "/api/v1/test-foundation/role-store-manager",
        headers={"Authorization": f"Bearer {token_cust}"},
    )
    assert resp4.status_code == 403

    # 3. Admin endpoint
    resp5 = await async_client.get(
        "/api/v1/test-foundation/role-admin",
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert resp5.status_code == 200

    resp6 = await async_client.get(
        "/api/v1/test-foundation/role-admin",
        headers={"Authorization": f"Bearer {token_super}"},
    )
    assert resp6.status_code == 200

    resp7 = await async_client.get(
        "/api/v1/test-foundation/role-admin",
        headers={"Authorization": f"Bearer {token_cust}"},
    )
    assert resp7.status_code == 403

    # 4. Super Admin endpoint
    resp8 = await async_client.get(
        "/api/v1/test-foundation/role-super-admin",
        headers={"Authorization": f"Bearer {token_super}"},
    )
    assert resp8.status_code == 200

    resp9 = await async_client.get(
        "/api/v1/test-foundation/role-super-admin",
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert resp9.status_code == 403


# ============================================================================
# 5. Store Manager & Customer Ownership Authorization
# ============================================================================

@pytest.mark.asyncio
async def test_store_manager_isolation(async_client: AsyncClient):
    """
    Verify store manager is strictly isolated to their assigned store:
    - Manager of STORE-001 can manage STORE-001.
    - Manager of STORE-001 is forbidden from managing STORE-002.
    - ADMIN can manage both STORE-001 and STORE-002.
    """
    assert AsyncSessionLocal is not None
    async with AsyncSessionLocal() as session:
        user_repo = UserRepository(session)
        store_repo = StoreRepository(session)
        mgr_user = await user_repo.get_by_email("manager.bengaluru@smartcart.in")
        admin_user = await user_repo.get_by_email("admin@smartcart.in")
        store_1 = await store_repo.get_by_code("STORE-001")
        store_2 = await store_repo.get_by_code("STORE-002")

    token_mgr = create_access_token(data={"sub": str(mgr_user.id)})
    token_admin = create_access_token(data={"sub": str(admin_user.id)})

    # Manager accessing assigned STORE-001 -> Success
    resp1 = await async_client.get(
        f"/api/v1/test-foundation/stores/{store_1.id}/manage",
        headers={"Authorization": f"Bearer {token_mgr}"},
    )
    assert resp1.status_code == 200
    assert resp1.json()["store_id"] == str(store_1.id)

    # Manager accessing unassigned STORE-002 -> 403 Forbidden
    resp2 = await async_client.get(
        f"/api/v1/test-foundation/stores/{store_2.id}/manage",
        headers={"Authorization": f"Bearer {token_mgr}"},
    )
    assert resp2.status_code == 403
    assert resp2.json()["error"]["code"] == "FORBIDDEN"
    assert "not authorized to manage store" in resp2.json()["error"]["message"]

    # Admin accessing STORE-001 and STORE-002 -> Both Success
    resp3 = await async_client.get(
        f"/api/v1/test-foundation/stores/{store_1.id}/manage",
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert resp3.status_code == 200

    resp4 = await async_client.get(
        f"/api/v1/test-foundation/stores/{store_2.id}/manage",
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert resp4.status_code == 200


@pytest.mark.asyncio
async def test_customer_ownership_dependency(async_client: AsyncClient):
    """
    Verify customer resource ownership:
    - Customer accessing own profile -> 200.
    - Customer accessing another customer's profile -> 403 Forbidden.
    - Admin accessing customer profile -> 200.
    """
    assert AsyncSessionLocal is not None
    async with AsyncSessionLocal() as session:
        user_repo = UserRepository(session)
        cust_repo = CustomerRepository(session)
        demo_user = await user_repo.get_by_email("demo@smartcart.in")
        demo_cust = await cust_repo.get_by_user_id(demo_user.id)
        admin_user = await user_repo.get_by_email("admin@smartcart.in")

    token_cust = create_access_token(data={"sub": str(demo_user.id)})
    token_admin = create_access_token(data={"sub": str(admin_user.id)})

    # 1. Customer accesses own profile
    resp1 = await async_client.get(
        f"/api/v1/test-foundation/customers/{demo_cust.id}/profile",
        headers={"Authorization": f"Bearer {token_cust}"},
    )
    assert resp1.status_code == 200
    assert resp1.json()["customer_id"] == str(demo_cust.id)

    # 2. Customer accesses another random customer profile -> 403
    other_cust_id = uuid.uuid4()
    resp2 = await async_client.get(
        f"/api/v1/test-foundation/customers/{other_cust_id}/profile",
        headers={"Authorization": f"Bearer {token_cust}"},
    )
    assert resp2.status_code == 403
    assert resp2.json()["error"]["code"] == "FORBIDDEN"

    # 3. Admin accesses demo customer profile -> 200
    resp3 = await async_client.get(
        f"/api/v1/test-foundation/customers/{demo_cust.id}/profile",
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert resp3.status_code == 200


# ============================================================================
# 6. Idempotency Header Dependency
# ============================================================================

@pytest.mark.asyncio
async def test_idempotency_header_validation(async_client: AsyncClient):
    """Verify Idempotency-Key header extraction and regex validation."""
    # 1. Valid header
    resp1 = await async_client.post(
        "/api/v1/test-foundation/idempotency-check",
        headers={"Idempotency-Key": "order-chk-12345_abc"},
    )
    assert resp1.status_code == 200
    assert resp1.json()["idempotency_key"] == "order-chk-12345_abc"

    # 2. Missing header (optional)
    resp2 = await async_client.post("/api/v1/test-foundation/idempotency-check")
    assert resp2.status_code == 200
    assert resp2.json()["idempotency_key"] is None

    # 3. Invalid header (contains illegal characters)
    resp3 = await async_client.post(
        "/api/v1/test-foundation/idempotency-check",
        headers={"Idempotency-Key": "invalid key with spaces!"},
    )
    assert resp3.status_code == 422
    assert resp3.json()["error"]["code"] == "VALIDATION_ERROR"


# ============================================================================
# 7. Service & Repository Dependency Factories
# ============================================================================

@pytest.mark.asyncio
async def test_service_dependency_factories():
    """Verify all 10 service factory dependencies instantiate correctly with session."""
    assert AsyncSessionLocal is not None
    async with AsyncSessionLocal() as session:
        auth_service = get_auth_service(session)
        assert isinstance(auth_service, AuthService)

        user_service = get_user_service(session)
        assert isinstance(user_service, UserService)

        store_service = get_store_service(session)
        assert isinstance(store_service, StoreService)

        prod_service = get_product_service(session)
        assert isinstance(prod_service, ProductService)

        inv_service = get_inventory_service(session)
        assert isinstance(inv_service, InventoryService)

        cart_service = get_cart_service(session)
        assert isinstance(cart_service, CartService)

        order_service = get_order_service(session)
        assert isinstance(order_service, OrderService)

        idemp_service = get_idempotency_service(session)
        assert isinstance(idemp_service, IdempotencyService)

        outbox_service = get_outbox_service(session)
        assert isinstance(outbox_service, OutboxService)

        checkout_service = get_checkout_service(session)
        assert isinstance(checkout_service, CheckoutService)


@pytest.mark.asyncio
async def test_repository_dependency_factories():
    """Verify all repository dependency factories instantiate correctly with session."""
    assert AsyncSessionLocal is not None
    async with AsyncSessionLocal() as session:
        assert get_user_repository(session) is not None
        assert get_customer_repository(session) is not None
        assert get_store_repository(session) is not None
        assert get_product_repository(session) is not None
        assert get_inventory_repository(session) is not None
        assert get_reservation_repository(session) is not None
        assert get_order_repository(session) is not None
        assert get_idempotency_repository(session) is not None
        assert get_outbox_repository(session) is not None
        assert get_processed_event_repository(session) is not None
