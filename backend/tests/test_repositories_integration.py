import uuid
import pytest
import pytest_asyncio
from app.db.session import AsyncSessionLocal, async_engine
from app.models.enums import UserRole
from app.repositories import (
    CustomerRepository,
    IdempotencyKeyRepository,
    InventoryAuditLogRepository,
    InventoryRepository,
    OrderRepository,
    OutboxEventRepository,
    ProcessedEventRepository,
    ProductRepository,
    ReservationRepository,
    StoreRepository,
    UserRepository,
)


@pytest_asyncio.fixture(autouse=True)
async def dispose_engine_after_test():
    """
    Ensures connection pool cleanly disposes connections before event loop teardown,
    preventing Windows cross-loop reuse issues.
    """
    yield
    if async_engine is not None:
        await async_engine.dispose()


@pytest_asyncio.fixture
async def session():
    """Provides a transactional async session strictly for read-only repository tests."""
    assert AsyncSessionLocal is not None, "AsyncSessionLocal must be configured"
    async with AsyncSessionLocal() as sess:
        yield sess


@pytest.mark.asyncio
async def test_store_repository_read(session):
    """Verify StoreRepository reads seeded stores and handles non-existent lookups."""
    repo = StoreRepository(session)

    # 1. Look up existing store by unique code
    store_blr = await repo.get_by_code("STORE-001")
    assert store_blr is not None
    assert store_blr.code == "STORE-001"
    assert store_blr.city == "Bengaluru"
    assert store_blr.state == "Karnataka"

    store_mum = await repo.get_by_code("STORE-005")
    assert store_mum is not None
    assert store_mum.city == "Mumbai"
    assert store_mum.state == "Maharashtra"

    # 2. List active stores
    active_stores = await repo.list_active()
    assert len(active_stores) >= 5

    # 3. List by state and city
    karnataka_stores = await repo.list_by_state_and_city("Karnataka", "Bengaluru")
    assert len(karnataka_stores) >= 1

    # 4. Missing record behavior
    missing = await repo.get_by_code("NON-EXISTENT-STORE")
    assert missing is None

    missing_id = await repo.get_by_id(uuid.uuid4())
    assert missing_id is None


@pytest.mark.asyncio
async def test_user_repository_read(session):
    """Verify UserRepository reads seeded users, managers, and roles."""
    repo = UserRepository(session)

    # 1. Customer user
    customer_user = await repo.get_by_email("demo@smartcart.in")
    assert customer_user is not None
    assert customer_user.email == "demo@smartcart.in"
    assert customer_user.role == UserRole.CUSTOMER
    assert customer_user.full_name == "Demo Customer"

    # 2. Store Manager user and assigned store
    manager_blr = await repo.get_by_email("manager.bengaluru@smartcart.in")
    assert manager_blr is not None
    assert manager_blr.role == UserRole.STORE_MANAGER
    assert manager_blr.assigned_store_id is not None

    # 3. Manager lookup by store ID
    found_mgr = await repo.get_manager_for_store(manager_blr.assigned_store_id)
    assert found_mgr is not None
    assert found_mgr.id == manager_blr.id

    # 4. List by role
    managers = await repo.list_by_role(UserRole.STORE_MANAGER)
    assert len(managers) >= 1

    # 5. Missing user lookup
    missing = await repo.get_by_email("unknown@smartcart.in")
    assert missing is None


@pytest.mark.asyncio
async def test_customer_repository_read(session):
    """Verify CustomerRepository reads customer profile and eager-loads user relationship."""
    user_repo = UserRepository(session)
    cust_repo = CustomerRepository(session)

    # Get customer user
    user = await user_repo.get_by_email("demo@smartcart.in")
    assert user is not None

    # 1. Lookup customer profile by user_id
    customer = await cust_repo.get_by_user_id(user.id)
    assert customer is not None
    assert customer.user_id == user.id

    # 2. Lookup customer with eager-loaded user relationship
    cust_with_user = await cust_repo.get_with_user(customer.id)
    assert cust_with_user is not None
    assert cust_with_user.user is not None
    assert cust_with_user.user.email == "demo@smartcart.in"

    # 3. Missing customer lookup
    missing = await cust_repo.get_by_user_id(uuid.uuid4())
    assert missing is None


@pytest.mark.asyncio
async def test_product_repository_read(session):
    """Verify ProductRepository reads seeded products, categories, and attributes."""
    repo = ProductRepository(session)

    # 1. Look up existing product by SKU
    phone = await repo.get_by_sku("PHONE-001")
    assert phone is not None
    assert phone.sku == "PHONE-001"
    assert phone.name == "Galaxy 5G Smartphone"
    assert phone.price_paise == 1799900
    assert isinstance(phone.attributes, dict)

    # 2. List active products
    active_prods = await repo.list_active()
    assert len(active_prods) >= 5

    # 3. List by category
    grocery = await repo.list_by_category("Grocery")
    assert len(grocery) >= 3

    # 4. Missing SKU lookup
    missing = await repo.get_by_sku("DOES-NOT-EXIST")
    assert missing is None


@pytest.mark.asyncio
async def test_inventory_repository_composite_pk_read(session):
    """Verify InventoryRepository reads stock using composite primary key (store_id, product_id)."""
    store_repo = StoreRepository(session)
    prod_repo = ProductRepository(session)
    inv_repo = InventoryRepository(session)

    store_mum = await store_repo.get_by_code("STORE-005")
    phone = await prod_repo.get_by_sku("PHONE-001")
    assert store_mum is not None
    assert phone is not None

    # 1. Fetch stock using composite primary key
    stock = await inv_repo.get_stock(store_mum.id, phone.id)
    assert stock is not None
    assert stock.store_id == store_mum.id
    assert stock.product_id == phone.id
    assert stock.qty_on_hand == 1
    assert stock.qty_reserved == 0

    # 2. Test get_by_pk directly with composite keys
    stock_via_pk = await inv_repo.get_by_pk(store_mum.id, phone.id)
    assert stock_via_pk is not None
    assert stock_via_pk.product_id == phone.id

    # 3. List inventory for store
    store_inventory = await inv_repo.list_by_store(store_mum.id)
    assert len(store_inventory) >= 2


    # 4. Missing composite primary key lookup
    random_prod_id = uuid.uuid4()
    missing_stock = await inv_repo.get_stock(store_mum.id, random_prod_id)
    assert missing_stock is None


@pytest.mark.asyncio
async def test_reservation_repository_read(session):
    """Verify ReservationRepository queries execute cleanly without mutation."""
    cust_repo = CustomerRepository(session)
    res_repo = ReservationRepository(session)

    user_repo = UserRepository(session)
    user = await user_repo.get_by_email("demo@smartcart.in")
    customer = await cust_repo.get_by_user_id(user.id)
    assert customer is not None

    # Read queries
    active_res = await res_repo.list_active_by_customer(customer.id)
    assert isinstance(active_res, list)

    expired_res = await res_repo.list_expired()
    assert isinstance(expired_res, list)

    # Missing reservation
    missing = await res_repo.get_by_id(uuid.uuid4())
    assert missing is None


@pytest.mark.asyncio
async def test_order_repository_read(session):
    """Verify OrderRepository queries execute cleanly and handle missing orders."""
    order_repo = OrderRepository(session)
    store_repo = StoreRepository(session)
    store = await store_repo.get_by_code("STORE-001")

    # Read orders by store and status
    store_orders = await order_repo.list_by_store_and_status(store.id)
    assert isinstance(store_orders, list)

    # Missing order lookups
    missing_order = await order_repo.get_by_order_number("SC-2099-999999")
    assert missing_order is None

    missing_detail = await order_repo.get_with_items_and_history(uuid.uuid4())
    assert missing_detail is None


@pytest.mark.asyncio
async def test_idempotency_key_repository_composite_pk_read(session):
    """Verify IdempotencyKeyRepository handles composite primary key (customer_id, key)."""
    cust_repo = CustomerRepository(session)
    user_repo = UserRepository(session)
    user = await user_repo.get_by_email("demo@smartcart.in")
    customer = await cust_repo.get_by_user_id(user.id)
    assert customer is not None

    idem_repo = IdempotencyKeyRepository(session)

    # Missing record lookup with composite PK
    record = await idem_repo.get_by_customer_and_key(customer.id, "test-nonexistent-key")
    assert record is None

    # Generic exists with composite PK
    exists = await idem_repo.exists(customer.id, "test-nonexistent-key")
    assert exists is False


@pytest.mark.asyncio
async def test_processed_event_repository_composite_pk_read(session):
    """Verify ProcessedEventRepository handles composite primary key (event_id, consumer_group)."""
    repo = ProcessedEventRepository(session)

    # Missing record lookup with composite PK
    evt = await repo.get_event("non-existent-evt-id", "test-consumer-group")
    assert evt is None

    # is_processed check
    processed = await repo.is_processed("non-existent-evt-id", "test-consumer-group")
    assert processed is False


@pytest.mark.asyncio
async def test_outbox_event_repository_read(session):
    """Verify OutboxEventRepository queries execute cleanly without mutation."""
    repo = OutboxEventRepository(session)

    pending = await repo.list_pending(limit=10)
    assert isinstance(pending, list)

    by_aggregate = await repo.list_by_aggregate("order", str(uuid.uuid4()))
    assert isinstance(by_aggregate, list)


@pytest.mark.asyncio
async def test_inventory_audit_log_repository_read_only(session):
    """Verify InventoryAuditLogRepository is strictly read-only and queries history cleanly."""
    audit_repo = InventoryAuditLogRepository(session)

    # 1. Verify read methods execute
    recent_logs = await audit_repo.list_recent(limit=10)
    assert isinstance(recent_logs, list)

    logs_by_item = await audit_repo.list_by_store_and_product(uuid.uuid4(), uuid.uuid4())
    assert isinstance(logs_by_item, list)

    # 2. Verify repository exposes no mutation methods
    assert not hasattr(audit_repo, "create")
    assert not hasattr(audit_repo, "update")
    assert not hasattr(audit_repo, "delete")
    assert not hasattr(audit_repo, "insert")


@pytest.mark.asyncio
async def test_base_repository_generic_methods(session):
    """Verify BaseRepository generic methods (count, get_all, exists)."""
    store_repo = StoreRepository(session)

    # count()
    total_stores = await store_repo.count()
    assert total_stores >= 5

    # get_all() with pagination
    stores_page = await store_repo.get_all(skip=0, limit=2)
    assert len(stores_page) == 2

    # exists() for single PK
    first_store = stores_page[0]
    assert await store_repo.exists(first_store.id) is True
    assert await store_repo.exists(uuid.uuid4()) is False
