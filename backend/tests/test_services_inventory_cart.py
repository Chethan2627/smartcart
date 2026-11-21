"""
Unit tests for SmartCart 2.0 Phase 4 Stage 4: InventoryService and CartService.
Runs completely offline using mock repositories and async sessions.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
import uuid
import pytest
from sqlalchemy.exc import DBAPIError

from app.core.exceptions import (
    BadRequestError,
    ForbiddenError,
    InsufficientStockError,
    NotFoundError,
    SmartCartError,
    ValidationError,
)
from app.models.enums import ReservationStatus
from app.models.inventory import Inventory, Reservation
from app.models.product import Product
from app.models.store import Store
from app.services.cart import CartService
from app.services.inventory import InventoryService
from app.services.product import ProductService
from app.services.store import StoreService


class MockAsyncContextManager:
    """Mock for SQLAlchemy async context managers (begin, begin_nested)."""

    def __init__(self, raises_on_exit=None):
        self.entered = False
        self.exited = False
        self.raises_on_exit = raises_on_exit

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.exited = True
        if self.raises_on_exit:
            raise self.raises_on_exit
        return False


# ============================================================================
# 1. InventoryService Tests
# ============================================================================

@pytest.mark.asyncio
async def test_inventory_service_get_stock_and_available():
    """Verify InventoryService retrieves stock balance and available stock correctly."""
    store_id = uuid.uuid4()
    prod_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    mock_inv = Inventory(
        store_id=store_id,
        product_id=prod_id,
        qty_on_hand=50,
        qty_reserved=10,
        low_stock_threshold=5,
        updated_at=now,
    )

    inv_repo = AsyncMock()
    inv_repo.get_stock.return_value = mock_inv

    res_repo = AsyncMock()
    session = AsyncMock()

    # Mock view query for get_available_stock
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = 40
    session.execute.return_value = mock_result

    service = InventoryService(
        inventory_repo=inv_repo,
        reservation_repo=res_repo,
        session=session,
    )

    # 1. get_stock
    stock_resp = await service.get_stock(store_id, prod_id)
    assert stock_resp.qty_on_hand == 50
    assert stock_resp.qty_reserved == 10
    assert stock_resp.qty_available == 40
    assert stock_resp.is_low_stock is False

    # 2. get_available_stock
    available = await service.get_available_stock(store_id, prod_id)
    assert available == 40


@pytest.mark.asyncio
async def test_inventory_service_get_stock_not_found():
    """Verify InventoryService raises NotFoundError for non-existent inventory records."""
    store_id = uuid.uuid4()
    prod_id = uuid.uuid4()

    inv_repo = AsyncMock()
    inv_repo.get_stock.return_value = None

    service = InventoryService(
        inventory_repo=inv_repo,
        reservation_repo=AsyncMock(),
        session=AsyncMock(),
    )

    with pytest.raises(NotFoundError) as exc_info:
        await service.get_stock(store_id, prod_id)
    assert "Inventory record for product" in str(exc_info.value)


@pytest.mark.asyncio
async def test_inventory_service_reserve_stock_success():
    """Verify InventoryService calls reserve_stock and returns reservation UUID."""
    cust_id = uuid.uuid4()
    store_id = uuid.uuid4()
    prod_id = uuid.uuid4()
    res_id = uuid.uuid4()

    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = res_id
    session.execute.return_value = mock_result

    service = InventoryService(
        inventory_repo=AsyncMock(),
        reservation_repo=AsyncMock(),
        session=session,
    )

    result = await service.reserve_stock(cust_id, store_id, prod_id, qty=3, ttl_seconds=600)
    assert result == res_id
    session.execute.assert_awaited()


@pytest.mark.asyncio
async def test_inventory_service_reserve_stock_insufficient_stock():
    """Verify reserve_stock raises InsufficientStockError when DB returns NULL."""
    cust_id = uuid.uuid4()
    store_id = uuid.uuid4()
    prod_id = uuid.uuid4()

    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None  # DB returned NULL
    session.execute.return_value = mock_result

    service = InventoryService(
        inventory_repo=AsyncMock(),
        reservation_repo=AsyncMock(),
        session=session,
    )

    with pytest.raises(InsufficientStockError) as exc_info:
        await service.reserve_stock(cust_id, store_id, prod_id, qty=100)

    assert "Insufficient available stock" in str(exc_info.value)


@pytest.mark.asyncio
async def test_inventory_service_reserve_stock_invalid_inputs():
    """Verify reserve_stock validates quantity and TTL ranges before DB call."""
    service = InventoryService(
        inventory_repo=AsyncMock(),
        reservation_repo=AsyncMock(),
        session=AsyncMock(),
    )
    uid = uuid.uuid4()

    # Non-positive quantity
    with pytest.raises(ValidationError):
        await service.reserve_stock(uid, uid, uid, qty=0)

    with pytest.raises(ValidationError):
        await service.reserve_stock(uid, uid, uid, qty=-5)

    # Invalid TTL
    with pytest.raises(ValidationError):
        await service.reserve_stock(uid, uid, uid, qty=1, ttl_seconds=0)

    with pytest.raises(ValidationError):
        await service.reserve_stock(uid, uid, uid, qty=1, ttl_seconds=7200)


@pytest.mark.asyncio
async def test_inventory_service_release_reservation_and_ownership():
    """Verify release_reservation validates customer ownership and ACTIVE status."""
    cust_id = uuid.uuid4()
    other_cust_id = uuid.uuid4()
    res_id = uuid.uuid4()

    mock_res = Reservation(
        id=res_id,
        customer_id=cust_id,
        store_id=uuid.uuid4(),
        product_id=uuid.uuid4(),
        qty=2,
        status=ReservationStatus.ACTIVE,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )

    res_repo = AsyncMock()
    res_repo.get_by_id.return_value = mock_res

    session = AsyncMock()
    mock_exec = MagicMock()
    mock_exec.scalar_one_or_none.return_value = True
    session.execute.return_value = mock_exec

    service = InventoryService(
        inventory_repo=AsyncMock(),
        reservation_repo=res_repo,
        session=session,
    )

    # 1. Unauthorized release rejected with ForbiddenError
    with pytest.raises(ForbiddenError):
        await service.release_reservation(res_id, customer_id=other_cust_id)

    # 2. Non-active reservation release rejected with BadRequestError
    mock_res.status = ReservationStatus.RELEASED
    with pytest.raises(BadRequestError):
        await service.release_reservation(res_id, customer_id=cust_id)
    mock_res.status = ReservationStatus.ACTIVE

    # 3. Authorized release succeeds
    released = await service.release_reservation(res_id, customer_id=cust_id)
    assert released is True


@pytest.mark.asyncio
async def test_inventory_service_expire_reservations():
    """Verify expire_reservations invokes DB function and returns expired count."""
    session = AsyncMock()
    mock_exec = MagicMock()
    mock_exec.scalar_one_or_none.return_value = 5
    session.execute.return_value = mock_exec

    service = InventoryService(
        inventory_repo=AsyncMock(),
        reservation_repo=AsyncMock(),
        session=session,
    )

    count = await service.expire_reservations(batch_size=100)
    assert count == 5

    # Invalid batch size
    with pytest.raises(ValidationError):
        await service.expire_reservations(batch_size=0)


@pytest.mark.asyncio
async def test_inventory_service_db_exception_translation():
    """Verify PostgreSQL function errors are mapped to clean domain exceptions."""
    session = AsyncMock()
    db_err = DBAPIError("SELECT reserve_stock(...)", {}, Exception("Store is inactive"))
    session.execute.side_effect = db_err

    service = InventoryService(
        inventory_repo=AsyncMock(),
        reservation_repo=AsyncMock(),
        session=session,
    )

    with pytest.raises(BadRequestError) as exc_info:
        await service.reserve_stock(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), qty=1)
    assert "is inactive" in str(exc_info.value)

    # Product does not exist
    session.execute.side_effect = DBAPIError("SELECT reserve_stock(...)", {}, Exception("Product does not exist"))
    with pytest.raises(NotFoundError) as exc_info:
        await service.reserve_stock(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), qty=1)
    assert "does not exist" in str(exc_info.value)


# ============================================================================
# 2. CartService Tests
# ============================================================================

@pytest.mark.asyncio
async def test_cart_service_add_and_get_cart():
    """Verify CartService adds items, retrieves active cart, and calculates paise totals accurately."""
    cust_id = uuid.uuid4()
    store_id = uuid.uuid4()
    prod_id = uuid.uuid4()
    res_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    # 1. Mock store and product
    mock_store = Store(id=store_id, code="STORE-001", name="Bangalore Flagship", city="BLR", state="KA", is_active=True)
    mock_prod = Product(id=prod_id, sku="BT-01", name="Wireless Headphone", price_paise=150000, is_active=True)

    mock_res = Reservation(
        id=res_id,
        customer_id=cust_id,
        store_id=store_id,
        product_id=prod_id,
        qty=2,
        status=ReservationStatus.ACTIVE,
        expires_at=now + timedelta(minutes=10),
        order_id=None,
    )

    store_service = AsyncMock()
    store_service.get_store_by_id.return_value = mock_store

    product_service = AsyncMock()
    product_service.get_product_by_id.return_value = mock_prod

    inventory_service = AsyncMock()
    inventory_service.reserve_stock.return_value = res_id

    res_repo = AsyncMock()
    # First get_cart during add is empty, second has the reservation
    res_repo.list_active_by_customer.side_effect = [[], [mock_res], [mock_res]]

    cart_service = CartService(
        inventory_service=inventory_service,
        product_service=product_service,
        store_service=store_service,
        reservation_repo=res_repo,
    )

    cart = await cart_service.add_to_cart(
        customer_id=cust_id,
        store_id=store_id,
        product_id=prod_id,
        qty=2,
    )

    assert cart.store_id == store_id
    assert cart.total_items == 2
    assert cart.total_paise == 300000  # 2 * 150000 paise
    assert len(cart.items) == 1
    assert cart.items[0].product_sku == "BT-01"
    assert cart.items[0].unit_price_paise == 150000
    assert cart.items[0].item_subtotal_paise == 300000


@pytest.mark.asyncio
async def test_cart_service_reject_different_store_items():
    """Verify CartService prevents adding items from another store in a single cart."""
    cust_id = uuid.uuid4()
    store1 = uuid.uuid4()
    store2 = uuid.uuid4()
    prod_id = uuid.uuid4()

    mock_res = Reservation(
        id=uuid.uuid4(),
        customer_id=cust_id,
        store_id=store1,
        product_id=prod_id,
        qty=1,
        status=ReservationStatus.ACTIVE,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        order_id=None,
    )

    store_service = AsyncMock()
    store_service.get_store_by_id.return_value = Store(id=store2, is_active=True, code="S2", name="S2", city="MUM", state="MH")
    product_service = AsyncMock()
    product_service.get_product_by_id.return_value = Product(id=prod_id, sku="P1", name="Product 1", is_active=True, price_paise=100)

    res_repo = AsyncMock()
    res_repo.list_active_by_customer.return_value = [mock_res]

    cart_service = CartService(
        inventory_service=AsyncMock(),
        product_service=product_service,
        store_service=store_service,
        reservation_repo=res_repo,
    )

    with pytest.raises(BadRequestError) as exc_info:
        await cart_service.add_to_cart(cust_id, store_id=store2, product_id=prod_id, qty=1)

    assert "different store" in str(exc_info.value)


@pytest.mark.asyncio
async def test_cart_service_expired_reservations_excluded():
    """Verify CartService excludes expired reservations from active cart items and totals."""
    cust_id = uuid.uuid4()
    store_id = uuid.uuid4()
    prod_id = uuid.uuid4()

    # Expired 5 minutes ago
    expired_res = Reservation(
        id=uuid.uuid4(),
        customer_id=cust_id,
        store_id=store_id,
        product_id=prod_id,
        qty=1,
        status=ReservationStatus.ACTIVE,
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        order_id=None,
    )

    res_repo = AsyncMock()
    res_repo.list_active_by_customer.return_value = [expired_res]

    cart_service = CartService(
        inventory_service=AsyncMock(),
        product_service=AsyncMock(),
        store_service=AsyncMock(),
        reservation_repo=res_repo,
    )

    cart = await cart_service.get_cart(cust_id)
    assert len(cart.items) == 0
    assert cart.total_items == 0
    assert cart.total_paise == 0


@pytest.mark.asyncio
async def test_cart_service_reject_another_customers_cart():
    """Verify customer cannot remove or update another customer's cart reservation."""
    cust1 = uuid.uuid4()
    cust2 = uuid.uuid4()
    res_id = uuid.uuid4()

    inventory_service = AsyncMock()
    inventory_service.release_reservation.side_effect = ForbiddenError(
        "Cannot release a reservation belonging to another customer"
    )
    inventory_service.get_reservation.side_effect = ForbiddenError(
        "Cannot access reservation belonging to another customer"
    )

    cart_service = CartService(
        inventory_service=inventory_service,
        product_service=AsyncMock(),
        store_service=AsyncMock(),
        reservation_repo=AsyncMock(),
    )

    # 1. Removal rejected
    with pytest.raises(ForbiddenError):
        await cart_service.remove_from_cart(customer_id=cust2, reservation_id=res_id)

    # 2. Update rejected
    with pytest.raises(ForbiddenError):
        await cart_service.update_item_quantity(customer_id=cust2, reservation_id=res_id, new_qty=5)


@pytest.mark.asyncio
async def test_cart_service_inactive_product_and_store_rejection():
    """Verify add_to_cart rejects inactive products and stores."""
    store_service = AsyncMock()
    store_service.get_store_by_id.side_effect = BadRequestError("Store is inactive")

    cart_service = CartService(
        inventory_service=AsyncMock(),
        product_service=AsyncMock(),
        store_service=store_service,
        reservation_repo=AsyncMock(),
    )

    with pytest.raises(BadRequestError):
        await cart_service.add_to_cart(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), qty=1)


@pytest.mark.asyncio
async def test_cart_service_safe_quantity_update_preserves_reservation_on_failure():
    """
    Verify that if increasing reservation quantity fails (e.g. InsufficientStockError),
    the transaction savepoint rolls back so the customer's existing reservation is preserved!
    """
    cust_id = uuid.uuid4()
    store_id = uuid.uuid4()
    prod_id = uuid.uuid4()
    res_id = uuid.uuid4()

    mock_res = Reservation(
        id=res_id,
        customer_id=cust_id,
        store_id=store_id,
        product_id=prod_id,
        qty=2,
        status=ReservationStatus.ACTIVE,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )

    inventory_service = AsyncMock()
    inventory_service.get_reservation.return_value = mock_res
    inventory_service.release_reservation.return_value = True
    # Attempting to reserve new quantity fails with InsufficientStockError
    inventory_service.reserve_stock.side_effect = InsufficientStockError("Insufficient stock")

    mock_session = AsyncMock()
    mock_session.in_transaction = MagicMock(return_value=True)
    nested_cm = MockAsyncContextManager()
    mock_session.begin_nested = MagicMock(return_value=nested_cm)

    cart_service = CartService(
        inventory_service=inventory_service,
        product_service=AsyncMock(),
        store_service=AsyncMock(),
        reservation_repo=AsyncMock(),
        session=mock_session,
    )

    # Update quantity from 2 to 5 fails
    with pytest.raises(InsufficientStockError):
        await cart_service.update_item_quantity(
            customer_id=cust_id,
            reservation_id=res_id,
            new_qty=5,
        )

    # Savepoint was entered and exited (handled rollback)
    assert nested_cm.entered is True
    assert nested_cm.exited is True


@pytest.mark.asyncio
async def test_cart_service_successful_quantity_update():
    """Verify successful quantity update releases old reservation and creates new one within savepoint."""
    cust_id = uuid.uuid4()
    store_id = uuid.uuid4()
    prod_id = uuid.uuid4()
    old_res_id = uuid.uuid4()
    new_res_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    old_res = Reservation(
        id=old_res_id,
        customer_id=cust_id,
        store_id=store_id,
        product_id=prod_id,
        qty=1,
        status=ReservationStatus.ACTIVE,
        expires_at=now + timedelta(minutes=10),
    )
    new_res = Reservation(
        id=new_res_id,
        customer_id=cust_id,
        store_id=store_id,
        product_id=prod_id,
        qty=3,
        status=ReservationStatus.ACTIVE,
        expires_at=now + timedelta(minutes=10),
        order_id=None,
    )

    inventory_service = AsyncMock()
    inventory_service.get_reservation.return_value = old_res
    inventory_service.release_reservation.return_value = True
    inventory_service.reserve_stock.return_value = new_res_id

    product_service = AsyncMock()
    product_service.get_product_by_id.return_value = Product(id=prod_id, sku="P1", name="P1", price_paise=10000)

    res_repo = AsyncMock()
    res_repo.list_active_by_customer.return_value = [new_res]

    mock_session = AsyncMock()
    mock_session.in_transaction = MagicMock(return_value=True)
    nested_cm = MockAsyncContextManager()
    mock_session.begin_nested = MagicMock(return_value=nested_cm)

    cart_service = CartService(
        inventory_service=inventory_service,
        product_service=product_service,
        store_service=AsyncMock(),
        reservation_repo=res_repo,
        session=mock_session,
    )

    updated_cart = await cart_service.update_item_quantity(
        customer_id=cust_id,
        reservation_id=old_res_id,
        new_qty=3,
    )

    assert updated_cart.total_items == 3
    assert updated_cart.total_paise == 30000  # 3 * 10000 paise
    assert nested_cm.entered is True
    assert nested_cm.exited is True
