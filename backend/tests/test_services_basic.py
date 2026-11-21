"""
Basic unit tests for SmartCart 2.0 Phase 4 Stage 3 domain services:
StoreService, ProductService, AuthService, and UserService.
Runs entirely offline using mock sessions and repositories.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import uuid
import pytest

from app.core.exceptions import (
    AuthenticationError,
    BadRequestError,
    DuplicateResourceError,
    ForbiddenError,
    NotFoundError,
)
from app.core.security import decode_access_token, get_password_hash, verify_password
from app.models.customer import Customer
from app.models.enums import UserRole
from app.models.product import Product
from app.models.store import Store
from app.models.user import User
from app.services.auth import AuthService
from app.services.product import ProductService
from app.services.store import StoreService
from app.services.user import UserService


# ============================================================================
# 1. StoreService Tests
# ============================================================================

@pytest.mark.asyncio
async def test_store_service_get_by_id_success():
    """Verify StoreService returns store when it exists."""
    store_id = uuid.uuid4()
    mock_store = Store(
        id=store_id,
        code="STORE-001",
        name="Indiranagar Flagship",
        city="Bengaluru",
        state="Karnataka",
        is_active=True,
    )
    store_repo = AsyncMock()
    store_repo.get_by_id.return_value = mock_store

    service = StoreService(store_repo=store_repo)
    result = await service.get_store_by_id(store_id)

    assert result == mock_store
    assert result.code == "STORE-001"
    store_repo.get_by_id.assert_awaited_once_with(store_id)


@pytest.mark.asyncio
async def test_store_service_get_by_id_not_found():
    """Verify StoreService raises NotFoundError for non-existent store."""
    store_id = uuid.uuid4()
    store_repo = AsyncMock()
    store_repo.get_by_id.return_value = None

    service = StoreService(store_repo=store_repo)
    with pytest.raises(NotFoundError) as exc_info:
        await service.get_store_by_id(store_id)

    assert f"Store with id '{store_id}' not found" in str(exc_info.value)


@pytest.mark.asyncio
async def test_store_service_get_by_id_inactive_rejected():
    """Verify StoreService raises BadRequestError when require_active=True and store is inactive."""
    store_id = uuid.uuid4()
    mock_store = Store(
        id=store_id,
        code="STORE-INACTIVE",
        name="Closed Store",
        city="Bengaluru",
        state="Karnataka",
        is_active=False,
    )
    store_repo = AsyncMock()
    store_repo.get_by_id.return_value = mock_store

    service = StoreService(store_repo=store_repo)
    with pytest.raises(BadRequestError) as exc_info:
        await service.get_store_by_id(store_id, require_active=True)

    assert "is inactive" in str(exc_info.value)


@pytest.mark.asyncio
async def test_store_service_get_by_code_and_filtering():
    """Verify StoreService get_by_code and location-based filtering."""
    store_repo = AsyncMock()
    s1 = Store(id=uuid.uuid4(), code="STORE-001", name="S1", city="Bengaluru", state="Karnataka", is_active=True)
    s2 = Store(id=uuid.uuid4(), code="STORE-002", name="S2", city="Mysuru", state="Karnataka", is_active=False)

    store_repo.get_by_code.return_value = s1
    store_repo.list_active.return_value = [s1]
    store_repo.list_by_state_and_city.return_value = [s1, s2]

    service = StoreService(store_repo=store_repo)

    # get_by_code success
    store = await service.get_store_by_code("STORE-001")
    assert store.code == "STORE-001"

    # list_active
    active_stores = await service.list_active_stores(skip=0, limit=10)
    assert len(active_stores) == 1
    assert active_stores[0].code == "STORE-001"

    # list_by_location filtering inactive
    filtered = await service.list_stores_by_location(state="Karnataka", require_active=True)
    assert len(filtered) == 1
    assert filtered[0].code == "STORE-001"

    # list_by_location including inactive
    all_loc = await service.list_stores_by_location(state="Karnataka", require_active=False)
    assert len(all_loc) == 2


@pytest.mark.asyncio
async def test_store_service_get_store_managers():
    """Verify StoreService retrieves assigned managers for existing stores."""
    store_id = uuid.uuid4()
    mock_store = Store(id=store_id, code="STORE-001", name="S1", city="Bengaluru", state="KA", is_active=True)
    mock_manager = User(
        id=uuid.uuid4(),
        email="mgr@smartcart.in",
        full_name="Manager 1",
        password_hash="hash",
        role=UserRole.STORE_MANAGER,
        assigned_store_id=store_id,
        is_active=True,
    )

    store_repo = AsyncMock()
    store_repo.get_by_id.return_value = mock_store

    user_repo = AsyncMock()
    user_repo.get_manager_for_store.return_value = mock_manager

    service = StoreService(store_repo=store_repo, user_repo=user_repo)
    managers = await service.get_store_managers(store_id)

    assert len(managers) == 1
    assert managers[0].email == "mgr@smartcart.in"


# ============================================================================
# 2. ProductService Tests
# ============================================================================

@pytest.mark.asyncio
async def test_product_service_get_by_id_and_sku():
    """Verify ProductService retrieves products by ID and SKU, raising NotFoundError on miss."""
    prod_id = uuid.uuid4()
    mock_prod = Product(
        id=prod_id,
        sku="SKU-MOBILE-01",
        name="Smart 5G Phone",
        price_paise=1999900,
        is_active=True,
    )
    product_repo = AsyncMock()
    product_repo.get_by_id.return_value = mock_prod
    product_repo.get_by_sku.return_value = mock_prod

    service = ProductService(product_repo=product_repo)

    by_id = await service.get_product_by_id(prod_id)
    assert by_id.sku == "SKU-MOBILE-01"

    by_sku = await service.get_product_by_sku("SKU-MOBILE-01")
    assert by_sku.id == prod_id

    # Not found ID
    product_repo.get_by_id.return_value = None
    with pytest.raises(NotFoundError):
        await service.get_product_by_id(uuid.uuid4())

    # Not found SKU
    product_repo.get_by_sku.return_value = None
    with pytest.raises(NotFoundError):
        await service.get_product_by_sku("UNKNOWN-SKU")


@pytest.mark.asyncio
async def test_product_service_inactive_handling_and_price_verification():
    """Verify ProductService rejects inactive products and enforces authoritative DB prices."""
    prod_id = uuid.uuid4()
    inactive_prod = Product(
        id=prod_id,
        sku="SKU-DISCONTINUED",
        name="Old Model",
        price_paise=99900,
        is_active=False,
    )
    product_repo = AsyncMock()
    product_repo.get_by_id.return_value = inactive_prod

    service = ProductService(product_repo=product_repo)

    # Inactive product lookup with require_active=True raises BadRequestError
    with pytest.raises(BadRequestError) as exc_info:
        await service.get_product_by_id(prod_id, require_active=True)
    assert "currently inactive" in str(exc_info.value)

    # get_verified_price on inactive product is rejected
    with pytest.raises(BadRequestError):
        await service.get_verified_price(prod_id)

    # Active product returns authoritative database price
    active_prod = Product(
        id=prod_id,
        sku="SKU-ACTIVE",
        name="Active Product",
        price_paise=249900,
        is_active=True,
    )
    product_repo.get_by_id.return_value = active_prod
    price = await service.get_verified_price(prod_id)
    assert price == 249900


@pytest.mark.asyncio
async def test_product_service_listing_and_filtering():
    """Verify product listing and category filtering."""
    product_repo = AsyncMock()
    p1 = Product(id=uuid.uuid4(), sku="P1", name="P1", category="Electronics", is_active=True, price_paise=100)
    product_repo.list_active.return_value = [p1]
    product_repo.list_by_category.return_value = [p1]

    service = ProductService(product_repo=product_repo)
    active = await service.list_active_products(skip=0, limit=20)
    assert len(active) == 1
    assert active[0].sku == "P1"

    by_cat = await service.list_products_by_category("Electronics")
    assert len(by_cat) == 1


# ============================================================================
# 3. AuthService Tests
# ============================================================================

@pytest.mark.asyncio
async def test_auth_service_successful_customer_login():
    """Verify AuthService authenticates customer, resolves customer_id, and produces valid JWT claims."""
    raw_password = "SuperSecretPassword123"
    hashed = get_password_hash(raw_password)
    user_id = uuid.uuid4()
    customer_id = uuid.uuid4()

    mock_user = User(
        id=user_id,
        email="customer@smartcart.in",
        full_name="Priya Customer",
        password_hash=hashed,
        role=UserRole.CUSTOMER,
        assigned_store_id=None,
        is_active=True,
    )
    mock_customer = Customer(
        id=customer_id,
        user_id=user_id,
        phone="+91-9876543210",
        address="Bengaluru",
    )

    user_repo = AsyncMock()
    user_repo.get_by_email.return_value = mock_user

    customer_repo = AsyncMock()
    customer_repo.get_by_user_id.return_value = mock_customer

    auth_service = AuthService(user_repo=user_repo, customer_repo=customer_repo)
    token_resp = await auth_service.login(email="customer@smartcart.in", password=raw_password)

    assert token_resp.token_type == "bearer"
    assert token_resp.access_token is not None

    # Decode and verify token claims
    claims = decode_access_token(token_resp.access_token)
    assert claims["sub"] == str(user_id)
    assert claims["email"] == "customer@smartcart.in"
    assert claims["role"] == "CUSTOMER"
    assert claims["customer_id"] == str(customer_id)
    assert "store_id" not in claims


@pytest.mark.asyncio
async def test_auth_service_successful_store_manager_login():
    """Verify AuthService embeds store_id in JWT claims for STORE_MANAGER role."""
    raw_password = "ManagerPassword123"
    hashed = get_password_hash(raw_password)
    user_id = uuid.uuid4()
    store_id = uuid.uuid4()

    mock_manager = User(
        id=user_id,
        email="manager@smartcart.in",
        full_name="Indiranagar Manager",
        password_hash=hashed,
        role=UserRole.STORE_MANAGER,
        assigned_store_id=store_id,
        is_active=True,
    )

    user_repo = AsyncMock()
    user_repo.get_by_email.return_value = mock_manager

    auth_service = AuthService(user_repo=user_repo)
    token_resp = await auth_service.login(email="manager@smartcart.in", password=raw_password)

    claims = decode_access_token(token_resp.access_token)
    assert claims["sub"] == str(user_id)
    assert claims["role"] == "STORE_MANAGER"
    assert claims["store_id"] == str(store_id)


@pytest.mark.asyncio
async def test_auth_service_failed_login_and_enumeration_prevention():
    """Verify AuthService gives identical error on wrong password or missing user (no user enumeration)."""
    raw_password = "ValidPassword123"
    hashed = get_password_hash(raw_password)
    user_id = uuid.uuid4()

    mock_user = User(
        id=user_id,
        email="user@smartcart.in",
        full_name="User",
        password_hash=hashed,
        role=UserRole.CUSTOMER,
        is_active=True,
    )

    user_repo = AsyncMock()
    auth_service = AuthService(user_repo=user_repo)

    # 1. Missing user
    user_repo.get_by_email.return_value = None
    with pytest.raises(AuthenticationError) as exc_info:
        await auth_service.login("nonexistent@smartcart.in", raw_password)
    assert str(exc_info.value) == "Invalid email or password"

    # 2. Wrong password
    user_repo.get_by_email.return_value = mock_user
    with pytest.raises(AuthenticationError) as exc_info:
        await auth_service.login("user@smartcart.in", "WrongPassword!")
    assert str(exc_info.value) == "Invalid email or password"


@pytest.mark.asyncio
async def test_auth_service_inactive_user_rejection():
    """Verify AuthService rejects inactive user accounts even with correct credentials."""
    raw_password = "ValidPassword123"
    hashed = get_password_hash(raw_password)

    inactive_user = User(
        id=uuid.uuid4(),
        email="inactive@smartcart.in",
        full_name="Deactivated User",
        password_hash=hashed,
        role=UserRole.CUSTOMER,
        is_active=False,
    )

    user_repo = AsyncMock()
    user_repo.get_by_email.return_value = inactive_user

    auth_service = AuthService(user_repo=user_repo)
    with pytest.raises(AuthenticationError) as exc_info:
        await auth_service.login("inactive@smartcart.in", raw_password)

    assert "Account is inactive" in str(exc_info.value)


# ============================================================================
# 4. UserService Tests
# ============================================================================

class MockAsyncContextManager:
    """Mock for SQLAlchemy async context managers (begin, begin_nested)."""

    def __init__(self):
        self.entered = False
        self.exited = False

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.exited = True
        return False


@pytest.mark.asyncio
async def test_user_service_customer_registration_and_password_hashing():
    """Verify UserService registers customer, hashes password with Argon2id, and sets role=CUSTOMER."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.in_transaction = MagicMock(return_value=True)
    mock_session.begin_nested = MagicMock(return_value=MockAsyncContextManager())

    user_repo = AsyncMock()
    user_repo.session = mock_session
    user_repo.get_by_email.return_value = None  # Email not taken

    customer_repo = AsyncMock()
    customer_repo.session = mock_session

    user_service = UserService(user_repo=user_repo, customer_repo=customer_repo)

    raw_password = "SecurePassword@123"
    user, customer = await user_service.register_customer(
        email="new.customer@example.in",
        password=raw_password,
        full_name="Ramesh Kumar",
        phone="+91-9988776655",
        address="Koramangala, Bengaluru",
    )

    # Assert user properties
    assert user.email == "new.customer@example.in"
    assert user.full_name == "Ramesh Kumar"
    assert user.role == UserRole.CUSTOMER
    assert user.assigned_store_id is None
    assert user.is_active is True

    # Assert password hash is valid Argon2id and verified
    assert user.password_hash != raw_password
    assert user.password_hash.startswith("$argon2id$")
    assert verify_password(raw_password, user.password_hash) is True

    # Assert customer profile
    assert customer.user_id == user.id
    assert customer.phone == "+91-9988776655"
    assert customer.address == "Koramangala, Bengaluru"

    # Assert session.add called for both entities
    assert mock_session.add.call_count == 2
    mock_session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_user_service_duplicate_email_rejection():
    """Verify UserService raises DuplicateResourceError when email is already registered."""
    existing_user = User(
        id=uuid.uuid4(),
        email="existing@example.in",
        full_name="Existing User",
        password_hash="hash",
        role=UserRole.CUSTOMER,
        is_active=True,
    )
    user_repo = AsyncMock()
    user_repo.get_by_email.return_value = existing_user

    customer_repo = AsyncMock()
    user_service = UserService(user_repo=user_repo, customer_repo=customer_repo)

    with pytest.raises(DuplicateResourceError) as exc_info:
        await user_service.register_customer(
            email="existing@example.in",
            password="Password123",
            full_name="Another Name",
        )

    assert "already registered" in str(exc_info.value)


@pytest.mark.asyncio
async def test_user_service_role_escalation_rejection():
    """Verify UserService.register_customer rejects role escalation parameters and hardcodes CUSTOMER."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.in_transaction = MagicMock(return_value=True)
    mock_session.begin_nested = MagicMock(return_value=MockAsyncContextManager())

    user_repo = AsyncMock()
    user_repo.session = mock_session
    user_repo.get_by_email.return_value = None

    customer_repo = AsyncMock()
    user_service = UserService(user_repo=user_repo, customer_repo=customer_repo)

    # Attempting to supply role keyword argument fails with TypeError
    with pytest.raises(TypeError):
        await user_service.register_customer(
            email="hacker@example.in",
            password="Password123",
            full_name="Hacker",
            role=UserRole.ADMIN,  # Unexpected argument
        )

    # Standard registration strictly creates CUSTOMER role
    user, _ = await user_service.register_customer(
        email="regular@example.in",
        password="Password123",
        full_name="Regular",
    )
    assert user.role == UserRole.CUSTOMER


@pytest.mark.asyncio
async def test_user_service_transaction_rollback_on_failure():
    """Verify transaction rolls back when an error occurs during customer creation/persistence."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.in_transaction = MagicMock(return_value=False)

    cm = MockAsyncContextManager()
    mock_session.begin = MagicMock(return_value=cm)
    mock_session.flush.side_effect = RuntimeError("Database constraint or disk error")

    user_repo = AsyncMock()
    user_repo.session = mock_session
    user_repo.get_by_email.return_value = None

    customer_repo = AsyncMock()
    user_service = UserService(user_repo=user_repo, customer_repo=customer_repo)

    with pytest.raises(RuntimeError) as exc_info:
        await user_service.register_customer(
            email="fail@example.in",
            password="Password123",
            full_name="Fail Case",
        )

    assert "Database constraint or disk error" in str(exc_info.value)
    # Ensure context manager was exited on exception
    assert cm.exited is True


@pytest.mark.asyncio
async def test_user_service_assign_store_manager_permissions():
    """Verify assign_store_manager requires admin role and active store."""
    admin_user = User(id=uuid.uuid4(), email="admin@smartcart.in", full_name="Admin", role=UserRole.ADMIN, password_hash="h", is_active=True)
    customer_user = User(id=uuid.uuid4(), email="cust@smartcart.in", full_name="Cust", role=UserRole.CUSTOMER, password_hash="h", is_active=True)
    target_user = User(id=uuid.uuid4(), email="target@smartcart.in", full_name="Target", role=UserRole.CUSTOMER, password_hash="h", is_active=True)

    store_id = uuid.uuid4()
    active_store = Store(id=store_id, code="S1", name="Store 1", city="BLR", state="KA", is_active=True)
    inactive_store = Store(id=store_id, code="S2", name="Store 2", city="BLR", state="KA", is_active=False)

    user_repo = AsyncMock()
    user_repo.session = AsyncMock()
    user_repo.get_by_id.return_value = target_user

    store_repo = AsyncMock()
    store_repo.get_by_id.return_value = active_store

    customer_repo = AsyncMock()
    user_service = UserService(user_repo=user_repo, customer_repo=customer_repo, store_repo=store_repo)

    # 1. Non-admin caller raises ForbiddenError
    with pytest.raises(ForbiddenError):
        await user_service.assign_store_manager(
            admin_user=customer_user,
            target_user_id=target_user.id,
            store_id=store_id,
        )

    # 2. Inactive store raises BadRequestError
    store_repo.get_by_id.return_value = inactive_store
    with pytest.raises(BadRequestError):
        await user_service.assign_store_manager(
            admin_user=admin_user,
            target_user_id=target_user.id,
            store_id=store_id,
        )

    # 3. Successful assignment
    store_repo.get_by_id.return_value = active_store
    assigned = await user_service.assign_store_manager(
        admin_user=admin_user,
        target_user_id=target_user.id,
        store_id=store_id,
    )
    assert assigned.role == UserRole.STORE_MANAGER
    assert assigned.assigned_store_id == store_id


@pytest.mark.asyncio
async def test_user_service_update_user_status_rules():
    """Verify update_user_status enforces admin privileges and prevents self-deactivation."""
    admin_id = uuid.uuid4()
    admin_user = User(id=admin_id, email="admin@smartcart.in", full_name="Admin", role=UserRole.ADMIN, password_hash="h", is_active=True)
    other_user = User(id=uuid.uuid4(), email="other@smartcart.in", full_name="Other", role=UserRole.CUSTOMER, password_hash="h", is_active=True)

    user_repo = AsyncMock()
    user_repo.session = AsyncMock()
    user_repo.get_by_id.return_value = other_user

    customer_repo = AsyncMock()
    user_service = UserService(user_repo=user_repo, customer_repo=customer_repo)

    # 1. Admin deactivating self is rejected
    with pytest.raises(BadRequestError) as exc_info:
        await user_service.update_user_status(admin_user=admin_user, target_user_id=admin_id, is_active=False)
    assert "cannot deactivate their own account" in str(exc_info.value)

    # 2. Admin deactivating other user succeeds
    updated = await user_service.update_user_status(admin_user=admin_user, target_user_id=other_user.id, is_active=False)
    assert updated.is_active is False
