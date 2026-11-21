import uuid
from datetime import datetime, timezone
import pytest
from pydantic import TypeAdapter, ValidationError

from app.models.enums import OrderStatus, OutboxStatus, ReservationStatus, UserRole
from app.schemas import (
    CartItemAddRequest,
    CartItemResponse,
    CartItemUpdateRequest,
    CartResponse,
    CheckoutRequest,
    CustomerProfileResponse,
    CustomerRegisterRequest,
    EmailStr,
    IdempotencyKeyHeader,
    IdempotencyRecordResponse,
    InventoryAuditLogResponse,
    LoginRequest,
    OrderCancelRequest,
    OrderFilterParams,
    OrderItemResponse,
    OrderResponse,
    OrderStatusHistoryResponse,
    OrderStatusUpdateRequest,
    OutboxEventDetailResponse,
    OutboxEventResponse,
    OutboxEventSummaryResponse,
    PaginationParams,
    ProductFilterParams,
    ProductResponse,
    ReservationCreateRequest,
    ReservationResponse,
    StockResponse,
    StoreFilterParams,
    StoreManagerAssignRequest,
    StoreResponse,
    TokenPayload,
    TokenResponse,
    UserResponse,
)


def test_login_request_validation():
    """Verify LoginRequest email format and non-empty password."""
    # Valid
    req = LoginRequest(email="valid.user@example.com", password="SecretPassword123")
    assert req.email == "valid.user@example.com"
    assert req.password == "SecretPassword123"

    # Invalid email
    with pytest.raises(ValidationError):
        LoginRequest(email="not-an-email", password="ValidPassword123")

    # Empty password
    with pytest.raises(ValidationError):
        LoginRequest(email="valid.user@example.com", password="")


def test_token_response_and_payload_schemas():
    """Verify TokenResponse and TokenPayload claim validation."""
    token_resp = TokenResponse(access_token="sample.jwt.token", expires_in=3600)
    assert token_resp.token_type == "bearer"
    assert token_resp.expires_in == 3600

    user_id = uuid.uuid4()
    payload = TokenPayload(
        sub=str(user_id),
        email="customer@smartcart.in",
        role=UserRole.CUSTOMER,
        customer_id=uuid.uuid4(),
    )
    assert payload.sub == str(user_id)
    assert payload.role == UserRole.CUSTOMER


def test_customer_register_request_validation():
    """Verify CustomerRegisterRequest validation rules and field safety."""
    # Valid registration
    valid_data = {
        "email": "priya.sharma@example.in",
        "password": "StrongPassword@123",
        "full_name": "Priya Sharma",
        "phone": "+91-9876543210",
        "address": "123 MG Road, Bengaluru",
    }
    req = CustomerRegisterRequest(**valid_data)
    assert req.email == "priya.sharma@example.in"
    assert req.full_name == "Priya Sharma"

    # Password too short (< 8 characters)
    with pytest.raises(ValidationError):
        CustomerRegisterRequest(
            email="test@example.in",
            password="short",
            full_name="Test User",
        )

    # Empty name
    with pytest.raises(ValidationError):
        CustomerRegisterRequest(
            email="test@example.in",
            password="StrongPassword@123",
            full_name="",
        )


def test_store_schemas_and_pagination_limits():
    """Verify StoreResponse serialization and StoreFilterParams boundaries."""
    store_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    store_data = {
        "id": store_id,
        "code": "STORE-001",
        "name": "SmartCart Flagship Indiranagar",
        "city": "Bengaluru",
        "state": "Karnataka",
        "address": "100ft Road, Indiranagar",
        "is_active": True,
        "created_at": now,
    }
    store_resp = StoreResponse(**store_data)
    assert store_resp.id == store_id
    assert store_resp.code == "STORE-001"

    # Pagination bounds
    valid_filter = StoreFilterParams(state="Karnataka", skip=0, limit=25)
    assert valid_filter.limit == 25

    # Negative skip rejected
    with pytest.raises(ValidationError):
        StoreFilterParams(skip=-1)

    # Limit = 0 rejected
    with pytest.raises(ValidationError):
        StoreFilterParams(limit=0)

    # Limit > 100 rejected
    with pytest.raises(ValidationError):
        StoreFilterParams(limit=101)


def test_product_schemas_and_paise_validation():
    """Verify ProductResponse enforces non-negative paise and JSONB attributes."""
    prod_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    # Valid product
    prod = ProductResponse(
        id=prod_id,
        sku="PHONE-001",
        name="Galaxy 5G Smartphone",
        price_paise=1799900,
        attributes={"color": "Midnight Black", "storage": "128GB"},
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    assert prod.price_paise == 1799900
    assert prod.attributes["color"] == "Midnight Black"

    # Negative price in paise rejected
    with pytest.raises(ValidationError):
        ProductResponse(
            id=prod_id,
            sku="PHONE-001",
            name="Galaxy 5G Smartphone",
            price_paise=-1,
            is_active=True,
            created_at=now,
            updated_at=now,
        )

    # ProductFilterParams pagination bounds
    with pytest.raises(ValidationError):
        ProductFilterParams(limit=105)


def test_inventory_and_reservation_schemas():
    """Verify Inventory and Reservation schemas enforce positive quantities and hold limits."""
    store_id = uuid.uuid4()
    product_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    # Valid stock response
    stock = StockResponse(
        store_id=store_id,
        product_id=product_id,
        qty_on_hand=50,
        qty_reserved=5,
        qty_available=45,
        low_stock_threshold=10,
        is_low_stock=False,
        updated_at=now,
    )
    assert stock.qty_available == 45
    assert stock.is_low_stock is False

    # Negative stock quantities rejected
    with pytest.raises(ValidationError):
        StockResponse(
            store_id=store_id,
            product_id=product_id,
            qty_on_hand=-5,
            qty_reserved=0,
            qty_available=-5,
            low_stock_threshold=5,
            is_low_stock=True,
            updated_at=now,
        )

    # Reservation request: strictly positive quantity
    res_req = ReservationCreateRequest(store_id=store_id, product_id=product_id, qty=3)
    assert res_req.qty == 3
    assert res_req.ttl_seconds == 600

    # Non-positive reservation quantity rejected
    with pytest.raises(ValidationError):
        ReservationCreateRequest(store_id=store_id, product_id=product_id, qty=0)

    with pytest.raises(ValidationError):
        ReservationCreateRequest(store_id=store_id, product_id=product_id, qty=-2)

    # Excessive TTL (> 3600 seconds) rejected
    with pytest.raises(ValidationError):
        ReservationCreateRequest(store_id=store_id, product_id=product_id, qty=1, ttl_seconds=7200)


def test_shopping_cart_schemas():
    """Verify Cart schemas enforce positive item quantities and non-negative paise."""
    store_id = uuid.uuid4()
    prod_id = uuid.uuid4()
    res_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    # Cart item add request
    add_req = CartItemAddRequest(store_id=store_id, product_id=prod_id, qty=2)
    assert add_req.qty == 2

    with pytest.raises(ValidationError):
        CartItemAddRequest(store_id=store_id, product_id=prod_id, qty=0)

    # Cart item update request
    up_req = CartItemUpdateRequest(qty=5)
    assert up_req.qty == 5

    with pytest.raises(ValidationError):
        CartItemUpdateRequest(qty=-1)

    # Cart item response
    item_resp = CartItemResponse(
        reservation_id=res_id,
        product_id=prod_id,
        product_name="Bluetooth Headphones",
        product_sku="BT-HEAD-001",
        unit_price_paise=149900,
        qty=2,
        item_subtotal_paise=299800,
        expires_at=now,
    )
    assert item_resp.item_subtotal_paise == 299800

    # Cart aggregated response
    cart = CartResponse(
        store_id=store_id,
        items=[item_resp],
        total_items=2,
        total_paise=299800,
        earliest_expiration=now,
    )
    assert cart.total_items == 2
    assert cart.total_paise == 299800


def test_order_and_checkout_schemas():
    """Verify CheckoutRequest, OrderResponse, and lifecycle schemas."""
    store_id = uuid.uuid4()
    cust_id = uuid.uuid4()
    order_id = uuid.uuid4()
    prod_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    # CheckoutRequest only accepts store_id and address; cannot specify prices
    checkout = CheckoutRequest(store_id=store_id, delivery_address="Flat 402, MG Road")
    assert checkout.store_id == store_id
    assert not hasattr(checkout, "total_paise")
    assert not hasattr(checkout, "price_paise")

    # Order item response
    order_item = OrderItemResponse(
        id=1,
        order_id=order_id,
        product_id=prod_id,
        qty=1,
        unit_price_paise=1799900,
        item_subtotal_paise=1799900,
    )
    assert order_item.qty == 1

    # Order status history response
    status_hist = OrderStatusHistoryResponse(
        id=1,
        order_id=order_id,
        from_status=None,
        to_status=OrderStatus.PENDING,
        changed_at=now,
    )
    assert status_hist.to_status == OrderStatus.PENDING

    # Full OrderResponse
    order_resp = OrderResponse(
        id=order_id,
        order_number="SC-2026-000001",
        customer_id=cust_id,
        store_id=store_id,
        status=OrderStatus.CONFIRMED,
        total_paise=1799900,
        items=[order_item],
        status_history=[status_hist],
        created_at=now,
        updated_at=now,
    )
    assert order_resp.order_number == "SC-2026-000001"
    assert len(order_resp.items) == 1
    assert len(order_resp.status_history) == 1

    # Cancellation request
    cancel_req = OrderCancelRequest(reason="Changed mind")
    assert cancel_req.reason == "Changed mind"

    # Status update request
    status_update = OrderStatusUpdateRequest(to_status=OrderStatus.SHIPPED)
    assert status_update.to_status == OrderStatus.SHIPPED


def test_idempotency_and_outbox_schemas():
    """Verify IdempotencyRecordResponse and OutboxEventResponse schemas."""
    cust_id = uuid.uuid4()
    order_id = uuid.uuid4()
    event_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    # Idempotency response
    idem = IdempotencyRecordResponse(
        customer_id=cust_id,
        key="idemp-checkout-key-999",
        request_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        order_id=order_id,
        response={"status": "confirmed", "order_id": str(order_id)},
        created_at=now,
    )
    assert idem.key == "idemp-checkout-key-999"
    assert idem.order_id == order_id

    # Key cannot be empty
    with pytest.raises(ValidationError):
        IdempotencyRecordResponse(
            customer_id=cust_id,
            key="",
            request_hash="hash",
            created_at=now,
        )

    # Outbox event response
    outbox = OutboxEventResponse(
        id=event_id,
        aggregate_type="order",
        aggregate_id=str(order_id),
        event_type="order.placed",
        payload={"order_id": str(order_id), "total_paise": 1799900},
        status=OutboxStatus.PENDING,
        retry_count=0,
        created_at=now,
    )
    assert outbox.status == OutboxStatus.PENDING
    assert outbox.event_type == "order.placed"


def test_orm_from_attributes_deserialization():
    """Verify schemas can deserialize directly from ORM-like Python objects using from_attributes=True."""

    class MockORMStore:
        id = uuid.uuid4()
        code = "STORE-001"
        name = "SmartCart Indiranagar"
        city = "Bengaluru"
        state = "Karnataka"
        address = "100ft Road"
        is_active = True
        created_at = datetime.now(timezone.utc)

    store_orm = MockORMStore()
    schema_obj = StoreResponse.model_validate(store_orm)
    assert schema_obj.id == store_orm.id
    assert schema_obj.code == "STORE-001"
    assert schema_obj.city == "Bengaluru"

    class MockORMProduct:
        id = uuid.uuid4()
        sku = "PHONE-001"
        name = "Galaxy 5G Smartphone"
        description = "High-end smartphone"
        brand = "Samsung"
        category = "Mobiles"
        price_paise = 1799900
        attributes = {"color": "Black"}
        is_active = True
        created_at = datetime.now(timezone.utc)
        updated_at = datetime.now(timezone.utc)

    prod_orm = MockORMProduct()
    prod_schema = ProductResponse.model_validate(prod_orm)
    assert prod_schema.sku == "PHONE-001"
    assert prod_schema.price_paise == 1799900


def test_extra_fields_forbidden():
    """Verify that all client-facing request DTOs reject unexpected fields via extra='forbid'."""
    # 1. CustomerRegisterRequest rejects role, assigned_store_id, password_hash
    with pytest.raises(ValidationError) as exc_info:
        CustomerRegisterRequest(
            email="attacker@example.com",
            password="StrongPassword123",
            full_name="Attacker",
            role="ADMIN",  # Forbidden extra field
        )
    assert "Extra inputs are not permitted" in str(exc_info.value)

    with pytest.raises(ValidationError):
        CustomerRegisterRequest(
            email="attacker@example.com",
            password="StrongPassword123",
            full_name="Attacker",
            role="SUPER_ADMIN",
        )

    with pytest.raises(ValidationError):
        CustomerRegisterRequest(
            email="attacker@example.com",
            password="StrongPassword123",
            full_name="Attacker",
            assigned_store_id=uuid.uuid4(),
        )

    with pytest.raises(ValidationError):
        CustomerRegisterRequest(
            email="attacker@example.com",
            password="StrongPassword123",
            full_name="Attacker",
            password_hash="$argon2id$...",
        )

    # 2. LoginRequest rejects extra fields (e.g. role, password_hash)
    with pytest.raises(ValidationError):
        LoginRequest(email="user@example.com", password="pw", role="ADMIN")

    with pytest.raises(ValidationError):
        LoginRequest(email="user@example.com", password="pw", password_hash="hash")

    # 3. StoreManagerAssignRequest rejects extra fields
    with pytest.raises(ValidationError):
        StoreManagerAssignRequest(assigned_store_id=uuid.uuid4(), role="ADMIN")

    # 4. CartItemAddRequest rejects extra fields (e.g. price_paise)
    with pytest.raises(ValidationError):
        CartItemAddRequest(store_id=uuid.uuid4(), product_id=uuid.uuid4(), qty=1, price_paise=100)

    # 5. CartItemUpdateRequest rejects extra fields
    with pytest.raises(ValidationError):
        CartItemUpdateRequest(qty=2, product_id=uuid.uuid4())

    # 6. ReservationCreateRequest rejects extra fields
    with pytest.raises(ValidationError):
        ReservationCreateRequest(store_id=uuid.uuid4(), product_id=uuid.uuid4(), qty=1, user_id=uuid.uuid4())

    # 7. CheckoutRequest rejects price_paise, total_paise, or arbitrary inputs
    with pytest.raises(ValidationError):
        CheckoutRequest(store_id=uuid.uuid4(), price_paise=100)

    with pytest.raises(ValidationError):
        CheckoutRequest(store_id=uuid.uuid4(), total_paise=50000)

    # 8. OrderCancelRequest rejects extra fields
    with pytest.raises(ValidationError):
        OrderCancelRequest(reason="Changed mind", refund_amount=1000)

    # 9. OrderStatusUpdateRequest rejects extra fields
    with pytest.raises(ValidationError):
        OrderStatusUpdateRequest(to_status=OrderStatus.SHIPPED, force=True)

    # 10. Filter and pagination parameter DTOs reject extra fields
    with pytest.raises(ValidationError):
        StoreFilterParams(extra_filter="unknown")

    with pytest.raises(ValidationError):
        ProductFilterParams(inject_sql="DROP TABLE")

    with pytest.raises(ValidationError):
        OrderFilterParams(order_by="illegal_field")

    with pytest.raises(ValidationError):
        PaginationParams(sort_direction="asc")


def test_strict_integer_validation():
    """Verify that quantity and monetary fields reject booleans and floats using strict=True."""
    store_id = uuid.uuid4()
    prod_id = uuid.uuid4()
    order_id = uuid.uuid4()

    # Booleans are subclasses of int in Python; strict=True must reject them
    with pytest.raises(ValidationError):
        CartItemAddRequest(store_id=store_id, product_id=prod_id, qty=True)

    with pytest.raises(ValidationError):
        CartItemAddRequest(store_id=store_id, product_id=prod_id, qty=False)

    with pytest.raises(ValidationError):
        CartItemUpdateRequest(qty=True)

    with pytest.raises(ValidationError):
        ReservationCreateRequest(store_id=store_id, product_id=prod_id, qty=True)

    with pytest.raises(ValidationError):
        ReservationCreateRequest(store_id=store_id, product_id=prod_id, qty=1, ttl_seconds=True)

    with pytest.raises(ValidationError):
        ProductResponse(
            id=prod_id,
            sku="SKU-1",
            name="Prod 1",
            price_paise=True,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    with pytest.raises(ValidationError):
        OrderItemResponse(
            id=1,
            order_id=order_id,
            product_id=prod_id,
            qty=True,
            unit_price_paise=100,
        )

    with pytest.raises(ValidationError):
        OrderItemResponse(
            id=1,
            order_id=order_id,
            product_id=prod_id,
            qty=1,
            unit_price_paise=True,
        )

    with pytest.raises(ValidationError):
        OrderResponse(
            id=order_id,
            order_number="SC-2026-000001",
            customer_id=uuid.uuid4(),
            store_id=store_id,
            status=OrderStatus.PENDING,
            total_paise=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    # Floats must also be rejected by strict=True
    with pytest.raises(ValidationError):
        CartItemAddRequest(store_id=store_id, product_id=prod_id, qty=1.5)

    with pytest.raises(ValidationError):
        ProductResponse(
            id=prod_id,
            sku="SKU-1",
            name="Prod 1",
            price_paise=199.99,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )


def test_idempotency_header_validation():
    """Verify IdempotencyKeyHeader annotated type validation constraints."""
    adapter = TypeAdapter(IdempotencyKeyHeader)

    # Valid header keys
    assert adapter.validate_python("idemp-checkout-key-999") == "idemp-checkout-key-999"
    assert adapter.validate_python("ABC_123-xyz") == "ABC_123-xyz"
    assert (
        adapter.validate_python("UUID_550e8400-e29b-41d4-a716-446655440000")
        == "UUID_550e8400-e29b-41d4-a716-446655440000"
    )

    # Invalid header keys: empty
    with pytest.raises(ValidationError):
        adapter.validate_python("")

    # Invalid header keys: too long (> 255 chars)
    with pytest.raises(ValidationError):
        adapter.validate_python("k" * 256)

    # Invalid header keys: characters with whitespace or special chars
    with pytest.raises(ValidationError):
        adapter.validate_python("key with spaces")

    with pytest.raises(ValidationError):
        adapter.validate_python("key@#$%")


def test_outbox_summary_excludes_sensitive_fields():
    """Verify that OutboxEventSummaryResponse excludes payload and last_error, while detail includes them."""
    assert "last_error" not in OutboxEventSummaryResponse.model_fields
    assert "payload" not in OutboxEventSummaryResponse.model_fields
    assert "last_error" in OutboxEventDetailResponse.model_fields
    assert "payload" in OutboxEventDetailResponse.model_fields

    event_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    # Summary response can be constructed without payload or last_error
    summary = OutboxEventSummaryResponse(
        id=event_id,
        aggregate_type="order",
        aggregate_id="SC-2026-000001",
        event_type="order.created",
        status=OutboxStatus.PENDING,
        retry_count=0,
        created_at=now,
    )
    assert summary.id == event_id
    assert not hasattr(summary, "payload") or "payload" not in summary.model_dump()
    assert "last_error" not in summary.model_dump()

    # Detail response includes both
    detail = OutboxEventDetailResponse(
        id=event_id,
        aggregate_type="order",
        aggregate_id="SC-2026-000001",
        event_type="order.created",
        payload={"order_id": str(event_id)},
        status=OutboxStatus.FAILED,
        retry_count=3,
        last_error="Connection refused to message bus",
        created_at=now,
    )
    assert detail.last_error == "Connection refused to message bus"
    assert detail.payload == {"order_id": str(event_id)}


def test_native_email_validation():
    """Verify that native EmailStr correctly validates and rejects RFC email addresses."""
    # Valid emails
    valid_req = LoginRequest(email="customer.support@smartcart.co.in", password="ValidPassword123")
    assert valid_req.email == "customer.support@smartcart.co.in"

    reg_req = CustomerRegisterRequest(
        email="john.doe+test@example.com",
        password="ValidPassword123",
        full_name="John Doe",
    )
    assert reg_req.email == "john.doe+test@example.com"

    # Invalid emails
    invalid_emails = [
        "not-an-email",
        "missingatsign.com",
        "@missingusername.com",
        "username@",
        "spaces in@email.com",
    ]
    for bad_email in invalid_emails:
        with pytest.raises(ValidationError):
            LoginRequest(email=bad_email, password="ValidPassword123")
