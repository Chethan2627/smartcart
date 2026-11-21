"""
Unit tests for SmartCart 2.0 Phase 4 Stage 6:
OrderService and CheckoutService.
Runs completely offline using mock repositories and async sessions.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
import uuid
import pytest
from sqlalchemy.exc import DBAPIError

from app.core.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    IdempotencyConflictError,
    InvalidStateTransitionError,
    NotFoundError,
    SmartCartError,
    ValidationError,
)
from app.models.enums import OrderStatus
from app.models.order import Order, OrderItem, OrderStatusHistory
from app.models.outbox import IdempotencyKey
from app.models.product import Product
from app.models.store import Store
from app.schemas.cart import CartItemResponse, CartResponse
from app.schemas.order import CheckoutRequest, OrderResponse
from app.services.checkout import CheckoutService
from app.services.order import OrderService


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


def make_mock_session():
    """Create a fully configured mock AsyncSession with transaction context managers."""
    session = AsyncMock()
    session.add = MagicMock()
    session.add_all = MagicMock()
    session.in_transaction = MagicMock(return_value=False)
    session.begin = MagicMock(return_value=MockAsyncContextManager())
    session.begin_nested = MagicMock(return_value=MockAsyncContextManager())
    return session


# ============================================================================
# 1. OrderService Tests
# ============================================================================

@pytest.mark.asyncio
async def test_order_service_get_order_success():
    """Verify OrderService retrieves an order with eager-loaded items and status history."""
    order_id = uuid.uuid4()
    cust_id = uuid.uuid4()
    mock_order = Order(
        id=order_id,
        order_number="SC-2026-000001",
        customer_id=cust_id,
        store_id=uuid.uuid4(),
        status=OrderStatus.CONFIRMED,
        total_paise=50000,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    mock_order.items = []
    mock_order.status_history = []

    repo = AsyncMock()
    repo.get_with_items_and_history.return_value = mock_order

    service = OrderService(order_repo=repo)
    result = await service.get_order(order_id, customer_id=cust_id)

    assert result.id == order_id
    assert result.order_number == "SC-2026-000001"
    repo.get_with_items_and_history.assert_awaited_once_with(order_id)


@pytest.mark.asyncio
async def test_order_service_get_order_not_found():
    """Verify OrderService raises NotFoundError when an order does not exist."""
    order_id = uuid.uuid4()
    repo = AsyncMock()
    repo.get_with_items_and_history.return_value = None

    service = OrderService(order_repo=repo)
    with pytest.raises(NotFoundError) as exc_info:
        await service.get_order(order_id)

    assert f"Order '{order_id}' not found" in str(exc_info.value)


@pytest.mark.asyncio
async def test_order_service_get_order_ownership_forbidden():
    """Verify OrderService prevents a customer from accessing another customer's order."""
    order_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    attacker_id = uuid.uuid4()

    mock_order = Order(
        id=order_id,
        order_number="SC-2026-000002",
        customer_id=owner_id,
        store_id=uuid.uuid4(),
        status=OrderStatus.CONFIRMED,
        total_paise=10000,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    repo = AsyncMock()
    repo.get_with_items_and_history.return_value = mock_order

    service = OrderService(order_repo=repo)
    with pytest.raises(ForbiddenError) as exc_info:
        await service.get_order(order_id, customer_id=attacker_id)

    assert "Cannot access order belonging to another customer" in str(exc_info.value)


@pytest.mark.asyncio
async def test_order_service_get_order_by_number_success_and_forbidden():
    """Verify OrderService retrieves order by order_number and enforces ownership."""
    cust_id = uuid.uuid4()
    other_cust_id = uuid.uuid4()
    order_number = "SC-2026-000042"

    mock_order = Order(
        id=uuid.uuid4(),
        order_number=order_number,
        customer_id=cust_id,
        store_id=uuid.uuid4(),
        status=OrderStatus.CONFIRMED,
        total_paise=15000,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    repo = AsyncMock()
    repo.get_by_order_number.return_value = mock_order

    service = OrderService(order_repo=repo)

    # 1. Successful lookup with matching customer
    res = await service.get_order_by_number(order_number, customer_id=cust_id)
    assert res.order_number == order_number

    # 2. Forbidden lookup with mismatched customer
    with pytest.raises(ForbiddenError):
        await service.get_order_by_number(order_number, customer_id=other_cust_id)

    # 3. NotFound when number doesn't exist
    repo.get_by_order_number.return_value = None
    with pytest.raises(NotFoundError):
        await service.get_order_by_number("SC-2026-999999")


@pytest.mark.asyncio
async def test_order_service_list_customer_and_store_orders():
    """Verify OrderService paginates customer and store order listings."""
    cust_id = uuid.uuid4()
    store_id = uuid.uuid4()
    repo = AsyncMock()
    repo.list_by_customer.return_value = []
    repo.list_by_store_and_status.return_value = []

    service = OrderService(order_repo=repo)

    await service.list_customer_orders(cust_id, skip=10, limit=20)
    repo.list_by_customer.assert_awaited_once_with(cust_id, skip=10, limit=20)

    await service.list_store_orders(store_id, status=OrderStatus.PENDING, skip=0, limit=50)
    repo.list_by_store_and_status.assert_awaited_once_with(store_id, status=OrderStatus.PENDING, skip=0, limit=50)

    # Pagination validation
    with pytest.raises(ValidationError):
        await service.list_customer_orders(cust_id, skip=-1, limit=10)

    with pytest.raises(ValidationError):
        await service.list_customer_orders(cust_id, skip=0, limit=101)


@pytest.mark.asyncio
async def test_order_service_cancel_order_delegation_success():
    """Verify OrderService delegates cancellation to PostgreSQL cancel_order() and returns True."""
    order_id = uuid.uuid4()
    cust_id = uuid.uuid4()

    mock_session = make_mock_session()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = True
    mock_session.execute.return_value = mock_result

    repo = AsyncMock()
    service = OrderService(order_repo=repo, session=mock_session)

    success = await service.cancel_order(order_id, customer_id=cust_id, reason="Customer changed mind")
    assert success is True
    mock_session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_order_service_cancel_order_idempotent_already_cancelled():
    """Verify OrderService returns False when order was already cancelled."""
    order_id = uuid.uuid4()
    mock_session = make_mock_session()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = False
    mock_session.execute.return_value = mock_result

    repo = AsyncMock()
    service = OrderService(order_repo=repo, session=mock_session)

    success = await service.cancel_order(order_id, reason="Double cancel attempt")
    assert success is False


@pytest.mark.asyncio
async def test_order_service_cancel_order_error_mappings():
    """Verify OrderService translates PostgreSQL error codes (P0002, 42501, 23514) into domain exceptions."""
    order_id = uuid.uuid4()
    cust_id = uuid.uuid4()
    mock_session = make_mock_session()
    repo = AsyncMock()
    service = OrderService(order_repo=repo, session=mock_session)

    # 1. Empty reason validation
    with pytest.raises(ValidationError):
        await service.cancel_order(order_id, reason="   ")

    # 2. P0002 -> NotFoundError
    orig_p0002 = Exception("P0002: Order not found")
    mock_session.execute.side_effect = DBAPIError("SELECT cancel_order", {}, orig_p0002)
    with pytest.raises(NotFoundError):
        await service.cancel_order(order_id, customer_id=cust_id)

    # 3. 42501 -> ForbiddenError
    orig_42501 = Exception("42501: Unauthorized: order does not belong to specified customer")
    mock_session.execute.side_effect = DBAPIError("SELECT cancel_order", {}, orig_42501)
    with pytest.raises(ForbiddenError):
        await service.cancel_order(order_id, customer_id=cust_id)

    # 4. 23514 -> InvalidStateTransitionError
    orig_23514 = Exception("23514: Cannot cancel order in DELIVERED state")
    mock_session.execute.side_effect = DBAPIError("SELECT cancel_order", {}, orig_23514)
    with pytest.raises(InvalidStateTransitionError):
        await service.cancel_order(order_id, customer_id=cust_id)


@pytest.mark.asyncio
async def test_order_service_confirm_order():
    """Verify OrderService delegates confirmation to PostgreSQL confirm_order()."""
    order_id = uuid.uuid4()
    mock_session = make_mock_session()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = True
    mock_session.execute.return_value = mock_result

    repo = AsyncMock()
    service = OrderService(order_repo=repo, session=mock_session)

    res = await service.confirm_order(order_id)
    assert res is True

    # Error handling
    orig_23514 = Exception("23514: Order confirmation failed: reservation coverage mismatch")
    mock_session.execute.side_effect = DBAPIError("SELECT confirm_order", {}, orig_23514)
    with pytest.raises(BadRequestError):
        await service.confirm_order(order_id)


# ============================================================================
# 2. CheckoutService Tests
# ============================================================================

def make_test_cart(store_id: uuid.UUID, prod_id: uuid.UUID, qty: int = 2, unit_price_paise: int = 25000):
    """Helper to build a valid active CartResponse."""
    subtotal = qty * unit_price_paise
    return CartResponse(
        store_id=store_id,
        items=[
            CartItemResponse(
                reservation_id=uuid.uuid4(),
                product_id=prod_id,
                product_name="Aashirvaad Atta 5kg",
                product_sku="AT-001",
                unit_price_paise=unit_price_paise,
                qty=qty,
                item_subtotal_paise=subtotal,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            )
        ],
        total_items=qty,
        total_paise=subtotal,
        earliest_expiration=datetime.now(timezone.utc) + timedelta(minutes=10),
    )


@pytest.mark.asyncio
async def test_checkout_successful_orchestration():
    """Verify CheckoutService coordinates atomic checkout successfully."""
    cust_id = uuid.uuid4()
    store_id = uuid.uuid4()
    prod_id = uuid.uuid4()
    unit_price = 25000
    qty = 2
    expected_total = qty * unit_price

    mock_session = make_mock_session()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = True
    mock_session.execute.return_value = mock_result

    mock_store = Store(id=store_id, code="BLR-IND-01", name="Indiranagar Hub", city="Bangalore", state="Karnataka", is_active=True)
    mock_product = Product(id=prod_id, sku="AT-001", name="Aashirvaad Atta 5kg", price_paise=unit_price, is_active=True)
    cart = make_test_cart(store_id, prod_id, qty=qty, unit_price_paise=unit_price)

    store_svc = AsyncMock()
    store_svc.get_store_by_id.return_value = mock_store

    prod_svc = AsyncMock()
    prod_svc.get_product_by_id.return_value = mock_product

    cart_svc = AsyncMock()
    cart_svc.get_cart.return_value = cart

    order_repo = AsyncMock()
    order_repo.session = mock_session

    checkout_svc = CheckoutService(
        order_repo=order_repo,
        cart_service=cart_svc,
        product_service=prod_svc,
        store_service=store_svc,
        session=mock_session,
    )

    resp = await checkout_svc.checkout(customer_id=cust_id, store_id=store_id)

    assert isinstance(resp, OrderResponse)
    assert resp.customer_id == cust_id
    assert resp.store_id == store_id
    assert resp.status == OrderStatus.CONFIRMED
    assert resp.total_paise == expected_total
    assert len(resp.items) == 1
    assert resp.items[0].product_id == prod_id
    assert resp.items[0].qty == qty
    assert resp.items[0].unit_price_paise == unit_price

    # Verify session additions and flushes
    mock_session.add.assert_called_once()
    mock_session.add_all.assert_called_once()
    assert mock_session.flush.await_count >= 1

    # Verify link_reservation_to_order and confirm_order SQL executions occurred
    assert mock_session.execute.await_count == 2


@pytest.mark.asyncio
async def test_checkout_empty_cart_fails():
    """Verify CheckoutService rejects checkout when customer cart is empty."""
    cust_id = uuid.uuid4()
    store_id = uuid.uuid4()

    mock_store = Store(id=store_id, code="BLR-01", name="Hub", city="Bangalore", state="Karnataka", is_active=True)
    store_svc = AsyncMock()
    store_svc.get_store_by_id.return_value = mock_store

    cart_svc = AsyncMock()
    cart_svc.get_cart.return_value = CartResponse(store_id=None, items=[], total_items=0, total_paise=0)

    checkout_svc = CheckoutService(
        order_repo=AsyncMock(),
        cart_service=cart_svc,
        product_service=AsyncMock(),
        store_service=store_svc,
        session=make_mock_session(),
    )

    with pytest.raises(BadRequestError) as exc_info:
        await checkout_svc.checkout(customer_id=cust_id, store_id=store_id)

    assert "empty shopping cart" in str(exc_info.value)


@pytest.mark.asyncio
async def test_checkout_store_mismatch_fails():
    """Verify CheckoutService rejects checkout if cart items belong to a different store."""
    cust_id = uuid.uuid4()
    store_cart = uuid.uuid4()
    store_checkout = uuid.uuid4()
    prod_id = uuid.uuid4()

    mock_store = Store(id=store_checkout, code="BLR-02", name="Hub 2", city="Bangalore", state="Karnataka", is_active=True)
    store_svc = AsyncMock()
    store_svc.get_store_by_id.return_value = mock_store

    cart = make_test_cart(store_cart, prod_id)
    cart_svc = AsyncMock()
    cart_svc.get_cart.return_value = cart

    checkout_svc = CheckoutService(
        order_repo=AsyncMock(),
        cart_service=cart_svc,
        product_service=AsyncMock(),
        store_service=store_svc,
        session=make_mock_session(),
    )

    with pytest.raises(BadRequestError) as exc_info:
        await checkout_svc.checkout(customer_id=cust_id, store_id=store_checkout)

    assert "reserved at store" in str(exc_info.value)


@pytest.mark.asyncio
async def test_checkout_authoritative_database_pricing():
    """Verify CheckoutService strictly computes order total from DB product prices."""
    cust_id = uuid.uuid4()
    store_id = uuid.uuid4()
    prod_id = uuid.uuid4()
    db_unit_price = 30000  # Database price: Rs 300.00
    qty = 3
    expected_total = 90000

    mock_session = make_mock_session()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = True
    mock_session.execute.return_value = mock_result

    mock_product = Product(id=prod_id, sku="AT-002", name="Atta", price_paise=db_unit_price, is_active=True)
    cart = make_test_cart(store_id, prod_id, qty=qty, unit_price_paise=db_unit_price)

    store_svc = AsyncMock()
    store_svc.get_store_by_id.return_value = Store(id=store_id, is_active=True)

    prod_svc = AsyncMock()
    prod_svc.get_product_by_id.return_value = mock_product

    cart_svc = AsyncMock()
    cart_svc.get_cart.return_value = cart

    checkout_svc = CheckoutService(
        order_repo=AsyncMock(session=mock_session),
        cart_service=cart_svc,
        product_service=prod_svc,
        store_service=store_svc,
        session=mock_session,
    )

    resp = await checkout_svc.checkout(customer_id=cust_id, store_id=store_id)
    assert resp.total_paise == expected_total


@pytest.mark.asyncio
async def test_checkout_reservation_linking_failure_raises_bad_request():
    """Verify CheckoutService rolls back and raises BadRequestError if linking reservation fails."""
    cust_id = uuid.uuid4()
    store_id = uuid.uuid4()
    prod_id = uuid.uuid4()

    mock_session = make_mock_session()
    # Mock link_reservation_to_order returning False (e.g. hold expired)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = False
    mock_session.execute.return_value = mock_result

    cart = make_test_cart(store_id, prod_id)
    cart_svc = AsyncMock()
    cart_svc.get_cart.return_value = cart

    store_svc = AsyncMock()
    store_svc.get_store_by_id.return_value = Store(id=store_id, is_active=True)

    prod_svc = AsyncMock()
    prod_svc.get_product_by_id.return_value = Product(id=prod_id, price_paise=25000, is_active=True)

    checkout_svc = CheckoutService(
        order_repo=AsyncMock(session=mock_session),
        cart_service=cart_svc,
        product_service=prod_svc,
        store_service=store_svc,
        session=mock_session,
    )

    with pytest.raises(BadRequestError) as exc_info:
        await checkout_svc.checkout(customer_id=cust_id, store_id=store_id)

    assert "Failed to link reservation" in str(exc_info.value)


@pytest.mark.asyncio
async def test_checkout_order_confirmation_failure_raises_bad_request():
    """Verify CheckoutService raises BadRequestError if PostgreSQL confirm_order() fails."""
    cust_id = uuid.uuid4()
    store_id = uuid.uuid4()
    prod_id = uuid.uuid4()

    mock_session = make_mock_session()

    # Link succeeds (True), but confirm_order raises DBAPIError (23514)
    link_res = MagicMock()
    link_res.scalar_one_or_none.return_value = True

    confirm_exc = DBAPIError("SELECT confirm_order", {}, Exception("23514: Order confirmation failed"))
    mock_session.execute.side_effect = [link_res, confirm_exc]

    cart = make_test_cart(store_id, prod_id)
    cart_svc = AsyncMock()
    cart_svc.get_cart.return_value = cart

    store_svc = AsyncMock()
    store_svc.get_store_by_id.return_value = Store(id=store_id, is_active=True)

    prod_svc = AsyncMock()
    prod_svc.get_product_by_id.return_value = Product(id=prod_id, price_paise=25000, is_active=True)

    checkout_svc = CheckoutService(
        order_repo=AsyncMock(session=mock_session),
        cart_service=cart_svc,
        product_service=prod_svc,
        store_service=store_svc,
        session=mock_session,
    )

    with pytest.raises(BadRequestError) as exc_info:
        await checkout_svc.checkout(customer_id=cust_id, store_id=store_id)

    assert "Order confirmation failed" in str(exc_info.value)


@pytest.mark.asyncio
async def test_checkout_idempotent_replay():
    """Verify CheckoutService returns cached response when matching completed idempotency key is replayed."""
    cust_id = uuid.uuid4()
    store_id = uuid.uuid4()
    key = "order-idemp-key-123"

    order_id = uuid.uuid4()
    cached_response_payload = {
        "id": str(order_id),
        "order_number": "SC-2026-000001",
        "customer_id": str(cust_id),
        "store_id": str(store_id),
        "status": "CONFIRMED",
        "total_paise": 50000,
        "items": [],
        "status_history": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    cached_record = IdempotencyKey(
        customer_id=cust_id,
        key=key,
        request_hash="mock-hash",
        order_id=order_id,
        response=cached_response_payload,
    )

    idemp_svc = AsyncMock()
    idemp_svc.start_idempotent_operation.return_value = (cached_record, True)

    cart_svc = AsyncMock()
    store_svc = AsyncMock()

    checkout_svc = CheckoutService(
        order_repo=AsyncMock(),
        cart_service=cart_svc,
        product_service=AsyncMock(),
        store_service=store_svc,
        idempotency_service=idemp_svc,
        session=make_mock_session(),
    )

    resp = await checkout_svc.checkout(
        customer_id=cust_id,
        store_id=store_id,
        idempotency_key=key,
    )

    assert isinstance(resp, OrderResponse)
    assert resp.id == order_id
    assert resp.status == OrderStatus.CONFIRMED

    # Verification: Cart service and store service were NOT queried because response was replayed
    cart_svc.get_cart.assert_not_awaited()
    store_svc.get_store_by_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_checkout_idempotency_conflict_different_payload():
    """Verify CheckoutService propagates IdempotencyConflictError when key is reused with different payload."""
    cust_id = uuid.uuid4()
    store_id = uuid.uuid4()
    key = "order-idemp-conflict"

    idemp_svc = AsyncMock()
    idemp_svc.start_idempotent_operation.side_effect = IdempotencyConflictError("Key reused with different body")

    checkout_svc = CheckoutService(
        order_repo=AsyncMock(),
        cart_service=AsyncMock(),
        product_service=AsyncMock(),
        store_service=AsyncMock(),
        idempotency_service=idemp_svc,
        session=make_mock_session(),
    )

    with pytest.raises(IdempotencyConflictError):
        await checkout_svc.checkout(customer_id=cust_id, store_id=store_id, idempotency_key=key)


@pytest.mark.asyncio
async def test_checkout_failure_cleans_up_pending_idempotency_key():
    """Verify CheckoutService invokes fail_idempotent_operation when checkout fails, allowing customer retry."""
    cust_id = uuid.uuid4()
    store_id = uuid.uuid4()
    key = "order-idemp-fail-key"

    pending_record = IdempotencyKey(
        customer_id=cust_id,
        key=key,
        request_hash="hash",
        order_id=None,
        response=None,
    )

    idemp_svc = AsyncMock()
    idemp_svc.start_idempotent_operation.return_value = (pending_record, False)

    # Empty cart triggers failure after pending key created
    cart_svc = AsyncMock()
    cart_svc.get_cart.return_value = CartResponse(store_id=None, items=[], total_items=0, total_paise=0)

    store_svc = AsyncMock()
    store_svc.get_store_by_id.return_value = Store(id=store_id, is_active=True)

    checkout_svc = CheckoutService(
        order_repo=AsyncMock(),
        cart_service=cart_svc,
        product_service=AsyncMock(),
        store_service=store_svc,
        idempotency_service=idemp_svc,
        session=make_mock_session(),
    )

    with pytest.raises(BadRequestError):
        await checkout_svc.checkout(customer_id=cust_id, store_id=store_id, idempotency_key=key)

    # Clean up called so client is not locked out
    idemp_svc.fail_idempotent_operation.assert_awaited_once_with(
        customer_id=cust_id,
        key=key,
    )


@pytest.mark.asyncio
async def test_order_service_update_order_status_success_and_same_status():
    """Verify OrderService transitions order status and skips flush on no-op."""
    order_id = uuid.uuid4()
    mock_order = Order(
        id=order_id,
        order_number="SC-2026-000001",
        customer_id=uuid.uuid4(),
        store_id=uuid.uuid4(),
        status=OrderStatus.CONFIRMED,
        total_paise=50000,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    mock_session = make_mock_session()
    repo = AsyncMock()
    repo.get_with_items_and_history.return_value = mock_order

    service = OrderService(order_repo=repo, session=mock_session)

    # 1. No-op update to same status (CONFIRMED -> CONFIRMED)
    res = await service.update_order_status(order_id, OrderStatus.CONFIRMED)
    assert res.status == OrderStatus.CONFIRMED
    mock_session.flush.assert_not_awaited()

    # 2. Valid transition (CONFIRMED -> PACKED)
    res2 = await service.update_order_status(order_id, OrderStatus.PACKED)
    assert res2.status == OrderStatus.PACKED
    mock_session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_order_service_update_order_status_trigger_violation():
    """Verify OrderService translates database trigger violation (23514) into InvalidStateTransitionError."""
    order_id = uuid.uuid4()
    mock_order = Order(
        id=order_id,
        order_number="SC-2026-000001",
        customer_id=uuid.uuid4(),
        store_id=uuid.uuid4(),
        status=OrderStatus.PENDING,
        total_paise=50000,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    mock_session = make_mock_session()
    mock_session.flush.side_effect = DBAPIError(
        "UPDATE orders", {}, Exception("23514: Invalid order transition PENDING -> SHIPPED")
    )
    repo = AsyncMock()
    repo.get_with_items_and_history.return_value = mock_order

    service = OrderService(order_repo=repo, session=mock_session)

    with pytest.raises(InvalidStateTransitionError) as exc_info:
        await service.update_order_status(order_id, OrderStatus.SHIPPED)

    assert "Invalid order transition" in str(exc_info.value)


@pytest.mark.asyncio
async def test_checkout_with_checkout_request_dto():
    """Verify CheckoutService supports passing CheckoutRequest DTO object directly."""
    cust_id = uuid.uuid4()
    store_id = uuid.uuid4()
    prod_id = uuid.uuid4()

    mock_session = make_mock_session()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = True
    mock_session.execute.return_value = mock_result

    mock_store = Store(id=store_id, code="BLR-IND-01", name="Indiranagar Hub", city="Bangalore", state="Karnataka", is_active=True)
    mock_product = Product(id=prod_id, sku="AT-001", name="Atta", price_paise=25000, is_active=True)
    cart = make_test_cart(store_id, prod_id, qty=1, unit_price_paise=25000)

    store_svc = AsyncMock()
    store_svc.get_store_by_id.return_value = mock_store

    prod_svc = AsyncMock()
    prod_svc.get_product_by_id.return_value = mock_product

    cart_svc = AsyncMock()
    cart_svc.get_cart.return_value = cart

    checkout_svc = CheckoutService(
        order_repo=AsyncMock(session=mock_session),
        cart_service=cart_svc,
        product_service=prod_svc,
        store_service=store_svc,
        session=mock_session,
    )

    req_dto = CheckoutRequest(store_id=store_id, delivery_address="Flat 402, Indiranagar, Bangalore")
    resp = await checkout_svc.checkout(customer_id=cust_id, request=req_dto)

    assert resp.customer_id == cust_id
    assert resp.store_id == store_id
    assert resp.status == OrderStatus.CONFIRMED


@pytest.mark.asyncio
async def test_checkout_inactive_product_raises_bad_request():
    """Verify CheckoutService rejects checkout if a cart product becomes inactive before purchase."""
    cust_id = uuid.uuid4()
    store_id = uuid.uuid4()
    prod_id = uuid.uuid4()

    mock_store = Store(id=store_id, code="BLR-01", name="Hub", city="Bangalore", state="Karnataka", is_active=True)
    store_svc = AsyncMock()
    store_svc.get_store_by_id.return_value = mock_store

    prod_svc = AsyncMock()
    prod_svc.get_product_by_id.side_effect = BadRequestError("Product 'AT-001' is inactive")

    cart = make_test_cart(store_id, prod_id)
    cart_svc = AsyncMock()
    cart_svc.get_cart.return_value = cart

    checkout_svc = CheckoutService(
        order_repo=AsyncMock(),
        cart_service=cart_svc,
        product_service=prod_svc,
        store_service=store_svc,
        session=make_mock_session(),
    )

    with pytest.raises(BadRequestError) as exc_info:
        await checkout_svc.checkout(customer_id=cust_id, store_id=store_id)

    assert "inactive" in str(exc_info.value)

