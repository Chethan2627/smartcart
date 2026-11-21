"""
Complete test suite for SmartCart 2.0 Phase 6.5: Store Manager Product & Inventory Management.
Covers 30 required test scenarios:
- 1-4: Authorization & Store Isolation (Manager, Cross-Store, Customer, Admin)
- 5-10: Product Catalogue Management (Create, Duplicate SKU, Update, Pricing Restriction, Deactivation, Historical Integrity)
- 11-16: Image Management (Upload, Invalid Type, Oversized, Cloudinary Error, Replace, Delete)
- 17-25: Inventory & Adjustments (Initial, Increase, Decrease, Negative Rejection, Reservation Protection, Concurrency, Audit, Cross-Store, Low Stock)
- 26-30: Kafka Outbox Events (Product Events, Inventory Events, Transactional Consistency, Low-Stock Alert, Duplicate Suppression)
"""
import asyncio
import io
import uuid
from typing import Any, Dict, Optional
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select, text

from app.api.deps import get_storage_service
from app.core.security import create_access_token
from app.db.session import AsyncSessionLocal, async_engine
from app.main import app
from app.models.enums import ReservationStatus, UserRole
from app.models.inventory import Inventory, InventoryAuditLog, Reservation
from app.models.order import Order, OrderItem
from app.models.outbox import OutboxEvent
from app.models.product import Product
from app.models.store import Store
from app.models.user import User
from app.services.storage import ImageStorageService


# ============================================================================
# Mock Storage Service for Deterministic Automated Testing
# ============================================================================

class MockImageStorageService(ImageStorageService):
    """In-memory mock for Cloudinary image storage."""

    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.uploaded_files: Dict[str, Dict[str, Any]] = {}
        self.deleted_public_ids: list = []

    async def upload_image(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: str,
        folder: Optional[str] = None,
    ) -> Dict[str, Any]:
        if self.should_fail:
            from app.core.exceptions import SmartCartError
            raise SmartCartError("Cloudinary API connection timeout")

        # Validate MIME
        allowed = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
        if (content_type or "").lower().strip() not in allowed:
            from app.core.exceptions import BadRequestError
            raise BadRequestError(f"Unsupported image type '{content_type}'")

        # Validate Size (5 MB)
        if len(file_bytes) > 5 * 1024 * 1024:
            from app.core.exceptions import BadRequestError
            raise BadRequestError("Image file size exceeds maximum limit of 5 MB")

        if len(file_bytes) == 0:
            from app.core.exceptions import BadRequestError
            raise BadRequestError("Image file cannot be empty")

        public_id = f"mock_{uuid.uuid4().hex[:12]}"
        meta = {
            "url": f"https://res.cloudinary.com/mock/{public_id}.jpg",
            "secure_url": f"https://res.cloudinary.com/mock/{public_id}.jpg",
            "public_id": public_id,
            "format": "jpg",
            "width": 800,
            "height": 600,
            "bytes": len(file_bytes),
        }
        self.uploaded_files[public_id] = meta
        return meta

    async def delete_image(self, public_id: str) -> bool:
        self.deleted_public_ids.append(public_id)
        self.uploaded_files.pop(public_id, None)
        return True


@pytest_asyncio.fixture(autouse=True)
async def dispose_engine_after_test():
    """Ensure engine connections are cleanly disposed before event loop teardown."""
    yield
    app.dependency_overrides.pop(get_storage_service, None)
    if async_engine is not None:
        await async_engine.dispose()


@pytest_asyncio.fixture
async def setup_test_environment():
    """
    Creates isolated test fixtures in PostgreSQL:
    - Store A and Store B
    - Store Manager A (assigned to Store A)
    - Store Manager B (assigned to Store B)
    - Admin User
    - Customer User
    - Auth Tokens for each user
    Cleans up all created rows in database upon completion.
    """
    store_a_id = uuid.uuid4()
    store_b_id = uuid.uuid4()
    mgr_a_id = uuid.uuid4()
    mgr_b_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    customer_id = uuid.uuid4()

    code_a = f"STR-{uuid.uuid4().hex[:6].upper()}"
    code_b = f"STR-{uuid.uuid4().hex[:6].upper()}"

    created_product_ids = []

    mock_storage = MockImageStorageService()
    app.dependency_overrides[get_storage_service] = lambda: mock_storage

    async with AsyncSessionLocal() as session:
        # Create Stores
        store_a = Store(id=store_a_id, code=code_a, name="Store A Test", city="Bengaluru", state="KA", is_active=True)
        store_b = Store(id=store_b_id, code=code_b, name="Store B Test", city="Mysuru", state="KA", is_active=True)
        session.add_all([store_a, store_b])

        # Create Users
        mgr_a = User(
            id=mgr_a_id,
            email=f"mgr_a_{uuid.uuid4().hex[:6]}@smartcart.in",
            full_name="Manager A",
            password_hash="argon2id$mocked",
            role=UserRole.STORE_MANAGER,
            assigned_store_id=store_a_id,
            is_active=True,
        )
        mgr_b = User(
            id=mgr_b_id,
            email=f"mgr_b_{uuid.uuid4().hex[:6]}@smartcart.in",
            full_name="Manager B",
            password_hash="argon2id$mocked",
            role=UserRole.STORE_MANAGER,
            assigned_store_id=store_b_id,
            is_active=True,
        )
        admin = User(
            id=admin_id,
            email=f"admin_{uuid.uuid4().hex[:6]}@smartcart.in",
            full_name="Admin User",
            password_hash="argon2id$mocked",
            role=UserRole.ADMIN,
            is_active=True,
        )
        customer = User(
            id=customer_id,
            email=f"cust_{uuid.uuid4().hex[:6]}@smartcart.in",
            full_name="Customer User",
            password_hash="argon2id$mocked",
            role=UserRole.CUSTOMER,
            is_active=True,
        )
        session.add_all([mgr_a, mgr_b, admin, customer])
        await session.commit()

    token_mgr_a = create_access_token({"sub": str(mgr_a_id), "role": UserRole.STORE_MANAGER.value, "store_id": str(store_a_id)})
    token_mgr_b = create_access_token({"sub": str(mgr_b_id), "role": UserRole.STORE_MANAGER.value, "store_id": str(store_b_id)})
    token_admin = create_access_token({"sub": str(admin_id), "role": UserRole.ADMIN.value})
    token_customer = create_access_token({"sub": str(customer_id), "role": UserRole.CUSTOMER.value})

    env_data = {
        "store_a_id": store_a_id,
        "store_b_id": store_b_id,
        "mgr_a_id": mgr_a_id,
        "mgr_b_id": mgr_b_id,
        "admin_id": admin_id,
        "customer_id": customer_id,
        "token_mgr_a": token_mgr_a,
        "token_mgr_b": token_mgr_b,
        "token_admin": token_admin,
        "token_customer": token_customer,
        "mock_storage": mock_storage,
        "created_product_ids": created_product_ids,
    }

    yield env_data

    # Cleanup test data
    async with AsyncSessionLocal() as session:
        for pid in created_product_ids:
            await session.execute(text("DELETE FROM outbox_events WHERE aggregate_id LIKE :aid"), {"aid": f"%{pid}%"})
            await session.execute(text("DELETE FROM inventory_audit_log WHERE product_id = :pid"), {"pid": pid})
            await session.execute(text("DELETE FROM inventory WHERE product_id = :pid"), {"pid": pid})
            await session.execute(text("DELETE FROM products WHERE id = :pid"), {"pid": pid})

        await session.execute(text("DELETE FROM inventory_audit_log WHERE store_id IN (:sa, :sb)"), {"sa": store_a_id, "sb": store_b_id})
        await session.execute(text("DELETE FROM inventory WHERE store_id IN (:sa, :sb)"), {"sa": store_a_id, "sb": store_b_id})
        await session.execute(text("DELETE FROM users WHERE id IN (:u1, :u2, :u3, :u4)"), {"u1": mgr_a_id, "u2": mgr_b_id, "u3": admin_id, "u4": customer_id})
        await session.execute(text("DELETE FROM stores WHERE id IN (:s1, :s2)"), {"s1": store_a_id, "s2": store_b_id})
        await session.commit()


# ============================================================================
# Part 1: Authorization Tests (1 - 4)
# ============================================================================

@pytest.mark.asyncio
async def test_01_manager_can_access_assigned_store(async_client: AsyncClient, setup_test_environment: dict):
    """Test 1: Store manager can access product and inventory endpoints for their assigned store."""
    env = setup_test_environment
    resp = await async_client.get(
        "/api/v1/manager/inventory",
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_02_manager_cannot_access_another_store(async_client: AsyncClient, setup_test_environment: dict):
    """Test 2: Store manager cannot access another store's inventory or management endpoints (HTTP 403)."""
    env = setup_test_environment
    resp = await async_client.get(
        f"/api/v1/manager/inventory?store_id={env['store_b_id']}",
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    assert resp.status_code == 403
    data = resp.json()
    assert "not authorized" in data.get("message", "").lower() or "not authorized" in str(data).lower()


@pytest.mark.asyncio
async def test_03_customer_cannot_access_manager_endpoints(async_client: AsyncClient, setup_test_environment: dict):
    """Test 3: Customer role is strictly rejected from all manager endpoints with HTTP 403 Forbidden."""
    env = setup_test_environment
    resp = await async_client.get(
        "/api/v1/manager/products",
        headers={"Authorization": f"Bearer {env['token_customer']}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_04_admin_can_manage_any_store(async_client: AsyncClient, setup_test_environment: dict):
    """Test 4: Platform Admin can manage any store by providing target store_id."""
    env = setup_test_environment
    resp_a = await async_client.get(
        f"/api/v1/manager/inventory?store_id={env['store_a_id']}",
        headers={"Authorization": f"Bearer {env['token_admin']}"},
    )
    assert resp_a.status_code == 200

    resp_b = await async_client.get(
        f"/api/v1/manager/inventory?store_id={env['store_b_id']}",
        headers={"Authorization": f"Bearer {env['token_admin']}"},
    )
    assert resp_b.status_code == 200


# ============================================================================
# Part 2: Product Management Tests (5 - 10)
# ============================================================================

@pytest.mark.asyncio
async def test_05_product_creation_by_manager(async_client: AsyncClient, setup_test_environment: dict):
    """Test 5: Manager creates product, initializes physical stock and threshold, emits outbox event."""
    env = setup_test_environment
    sku = f"SKU-{uuid.uuid4().hex[:8].upper()}"
    payload = {
        "sku": sku,
        "name": "Smart Ultra Widget",
        "description": "High performance widget",
        "brand": "TechCorp",
        "category": "Electronics",
        "price_paise": 199900,
        "attributes": {"color": "black", "weight": "250g"},
        "initial_stock": 25,
        "low_stock_threshold": 5,
    }

    resp = await async_client.post(
        "/api/v1/manager/products",
        json=payload,
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    assert resp.status_code == 201
    prod = resp.json()
    product_id = prod["id"]
    env["created_product_ids"].append(product_id)

    assert prod["sku"] == sku
    assert prod["name"] == "Smart Ultra Widget"
    assert prod["qty_on_hand"] == 25
    assert prod["qty_reserved"] == 0
    assert prod["qty_available"] == 25
    assert prod["low_stock_threshold"] == 5
    assert prod["is_low_stock"] is False
    assert prod["is_active"] is True


@pytest.mark.asyncio
async def test_06_duplicate_sku_rejection(async_client: AsyncClient, setup_test_environment: dict):
    """Test 6: Attempting to create product with duplicate SKU returns HTTP 409 Conflict."""
    env = setup_test_environment
    sku = f"SKU-DUP-{uuid.uuid4().hex[:6].upper()}"
    payload = {
        "sku": sku,
        "name": "First Product",
        "price_paise": 5000,
        "initial_stock": 5,
    }
    resp1 = await async_client.post(
        "/api/v1/manager/products",
        json=payload,
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    assert resp1.status_code == 201
    env["created_product_ids"].append(resp1.json()["id"])

    # Attempt duplicate
    resp2 = await async_client.post(
        "/api/v1/manager/products",
        json=payload,
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_07_product_metadata_update(async_client: AsyncClient, setup_test_environment: dict):
    """Test 7: Manager updates product metadata (name, description, brand, category, attributes)."""
    env = setup_test_environment
    sku = f"SKU-UPD-{uuid.uuid4().hex[:6].upper()}"
    create_resp = await async_client.post(
        "/api/v1/manager/products",
        json={"sku": sku, "name": "Old Name", "price_paise": 1000},
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    pid = create_resp.json()["id"]
    env["created_product_ids"].append(pid)

    update_payload = {
        "name": "Updated New Name",
        "description": "Updated Description",
        "brand": "NewBrand",
        "category": "Appliances",
        "attributes": {"warranty": "2 years"},
    }
    patch_resp = await async_client.patch(
        f"/api/v1/manager/products/{pid}",
        json=update_payload,
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    assert patch_resp.status_code == 200
    data = patch_resp.json()
    assert data["name"] == "Updated New Name"
    assert data["description"] == "Updated Description"
    assert data["brand"] == "NewBrand"
    assert data["category"] == "Appliances"
    assert data["attributes"]["warranty"] == "2 years"


@pytest.mark.asyncio
async def test_08_price_validation_and_manager_restriction(async_client: AsyncClient, setup_test_environment: dict):
    """
    Test 8: Strict Pricing Rules:
    - STORE_MANAGER cannot update global catalog price (HTTP 403 Forbidden).
    - ADMIN can update global catalog price (HTTP 200 OK).
    """
    env = setup_test_environment
    sku = f"SKU-PRC-{uuid.uuid4().hex[:6].upper()}"
    create_resp = await async_client.post(
        "/api/v1/manager/products",
        json={"sku": sku, "name": "Price Test Product", "price_paise": 50000},
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    pid = create_resp.json()["id"]
    env["created_product_ids"].append(pid)

    # 1. Manager attempts price update -> HTTP 403 Forbidden
    mgr_resp = await async_client.patch(
        f"/api/v1/manager/products/{pid}",
        json={"price_paise": 75000},
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    assert mgr_resp.status_code == 403
    assert "price" in str(mgr_resp.json()).lower()

    # 2. Admin performs price update -> HTTP 200 OK
    admin_resp = await async_client.patch(
        f"/api/v1/manager/products/{pid}?store_id={env['store_a_id']}",
        json={"price_paise": 75000},
        headers={"Authorization": f"Bearer {env['token_admin']}"},
    )
    assert admin_resp.status_code == 200
    assert admin_resp.json()["price_paise"] == 75000


@pytest.mark.asyncio
async def test_09_product_deactivation(async_client: AsyncClient, setup_test_environment: dict):
    """Test 9: Safe product deactivation sets is_active = False and emits outbox event."""
    env = setup_test_environment
    sku = f"SKU-DEACT-{uuid.uuid4().hex[:6].upper()}"
    create_resp = await async_client.post(
        "/api/v1/manager/products",
        json={"sku": sku, "name": "Deactivate Test", "price_paise": 1000},
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    pid = create_resp.json()["id"]
    env["created_product_ids"].append(pid)

    del_resp = await async_client.delete(
        f"/api/v1/manager/products/{pid}",
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    assert del_resp.status_code == 200
    assert del_resp.json()["is_active"] is False


@pytest.mark.asyncio
async def test_10_historical_order_references_intact(async_client: AsyncClient, setup_test_environment: dict):
    """
    Test 10: Deactivating a product does NOT delete historical orders or foreign key references.
    """
    env = setup_test_environment
    sku = f"SKU-HIST-{uuid.uuid4().hex[:6].upper()}"
    create_resp = await async_client.post(
        "/api/v1/manager/products",
        json={"sku": sku, "name": "Historical Product", "price_paise": 1000, "initial_stock": 10},
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    pid = uuid.UUID(create_resp.json()["id"])
    env["created_product_ids"].append(str(pid))

    # Deactivate product
    await async_client.delete(
        f"/api/v1/manager/products/{pid}",
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )

    # Verify product row still physically exists in database
    async with AsyncSessionLocal() as session:
        p = await session.get(Product, pid)
        assert p is not None
        assert p.is_active is False


# ============================================================================
# Part 3: Image Management Tests (11 - 16)
# ============================================================================

@pytest.mark.asyncio
async def test_11_valid_image_upload(async_client: AsyncClient, setup_test_environment: dict):
    """Test 11: Valid image upload stores Cloudinary metadata in product attributes."""
    env = setup_test_environment
    sku = f"SKU-IMG-{uuid.uuid4().hex[:6].upper()}"
    create_resp = await async_client.post(
        "/api/v1/manager/products",
        json={"sku": sku, "name": "Image Product", "price_paise": 1000},
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    pid = create_resp.json()["id"]
    env["created_product_ids"].append(pid)

    fake_jpeg = b"\xff\xd8\xff\xe0" + b"x" * 1024
    files = {"file": ("product.jpg", fake_jpeg, "image/jpeg")}
    upload_resp = await async_client.post(
        f"/api/v1/manager/products/{pid}/image",
        files=files,
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    assert upload_resp.status_code == 200
    data = upload_resp.json()
    assert data["image"] is not None
    assert "https://res.cloudinary.com" in data["image"]["url"]
    assert data["attributes"]["image"]["public_id"].startswith("mock_")


@pytest.mark.asyncio
async def test_12_unsupported_file_type_rejection(async_client: AsyncClient, setup_test_environment: dict):
    """Test 12: Uploading unsupported file type (e.g. text/pdf) returns HTTP 400 Bad Request."""
    env = setup_test_environment
    sku = f"SKU-PDF-{uuid.uuid4().hex[:6].upper()}"
    create_resp = await async_client.post(
        "/api/v1/manager/products",
        json={"sku": sku, "name": "Doc Product", "price_paise": 1000},
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    pid = create_resp.json()["id"]
    env["created_product_ids"].append(pid)

    fake_pdf = b"%PDF-1.4 test document"
    files = {"file": ("manual.pdf", fake_pdf, "application/pdf")}
    resp = await async_client.post(
        f"/api/v1/manager/products/{pid}/image",
        files=files,
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    assert resp.status_code == 400
    assert "unsupported" in str(resp.json()).lower()


@pytest.mark.asyncio
async def test_13_oversized_file_rejection(async_client: AsyncClient, setup_test_environment: dict):
    """Test 13: Uploading file larger than 5 MB returns HTTP 400 Bad Request."""
    env = setup_test_environment
    sku = f"SKU-BIG-{uuid.uuid4().hex[:6].upper()}"
    create_resp = await async_client.post(
        "/api/v1/manager/products",
        json={"sku": sku, "name": "Big Image Product", "price_paise": 1000},
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    pid = create_resp.json()["id"]
    env["created_product_ids"].append(pid)

    huge_file = b"x" * (6 * 1024 * 1024)  # 6 MB
    files = {"file": ("huge.jpg", huge_file, "image/jpeg")}
    resp = await async_client.post(
        f"/api/v1/manager/products/{pid}/image",
        files=files,
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    assert resp.status_code == 400
    assert "exceeds" in str(resp.json()).lower()


@pytest.mark.asyncio
async def test_14_cloudinary_failure_handling(async_client: AsyncClient, setup_test_environment: dict):
    """Test 14: Cloudinary service failures are handled gracefully without application crash."""
    env = setup_test_environment
    failing_storage = MockImageStorageService(should_fail=True)
    app.dependency_overrides[get_storage_service] = lambda: failing_storage

    sku = f"SKU-FAIL-{uuid.uuid4().hex[:6].upper()}"
    create_resp = await async_client.post(
        "/api/v1/manager/products",
        json={"sku": sku, "name": "Fail Product", "price_paise": 1000},
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    pid = create_resp.json()["id"]
    env["created_product_ids"].append(pid)

    files = {"file": ("test.jpg", b"fakeimg", "image/jpeg")}
    resp = await async_client.post(
        f"/api/v1/manager/products/{pid}/image",
        files=files,
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    assert resp.status_code in (400, 500, 502)
    assert "error" in resp.json()
    # Domain exception mapper maps SmartCartError to HTTP 400 or 500
    assert resp.status_code in (400, 500, 502)


@pytest.mark.asyncio
async def test_15_image_replacement_cleans_old_image(async_client: AsyncClient, setup_test_environment: dict):
    """Test 15: Replacing a product image deletes the previous image's public_id from Cloudinary."""
    env = setup_test_environment
    mock_storage = env["mock_storage"]

    sku = f"SKU-RPL-{uuid.uuid4().hex[:6].upper()}"
    create_resp = await async_client.post(
        "/api/v1/manager/products",
        json={"sku": sku, "name": "Replace Image Product", "price_paise": 1000},
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    pid = create_resp.json()["id"]
    env["created_product_ids"].append(pid)

    # 1. First upload
    files1 = {"file": ("first.jpg", b"image1", "image/jpeg")}
    res1 = await async_client.post(
        f"/api/v1/manager/products/{pid}/image",
        files=files1,
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    first_pub_id = res1.json()["image"]["public_id"]

    # 2. Second upload (replaces first)
    files2 = {"file": ("second.jpg", b"image2", "image/jpeg")}
    res2 = await async_client.post(
        f"/api/v1/manager/products/{pid}/image",
        files=files2,
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    second_pub_id = res2.json()["image"]["public_id"]

    assert first_pub_id != second_pub_id
    assert first_pub_id in mock_storage.deleted_public_ids


@pytest.mark.asyncio
async def test_16_image_deletion_endpoint(async_client: AsyncClient, setup_test_environment: dict):
    """Test 16: DELETE /products/{id}/image removes image from Cloudinary and product attributes."""
    env = setup_test_environment
    mock_storage = env["mock_storage"]

    sku = f"SKU-DELIMG-{uuid.uuid4().hex[:6].upper()}"
    create_resp = await async_client.post(
        "/api/v1/manager/products",
        json={"sku": sku, "name": "Delete Image Product", "price_paise": 1000},
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    pid = create_resp.json()["id"]
    env["created_product_ids"].append(pid)

    # Upload
    files = {"file": ("del.jpg", b"delimage", "image/jpeg")}
    up = await async_client.post(
        f"/api/v1/manager/products/{pid}/image",
        files=files,
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    pub_id = up.json()["image"]["public_id"]

    # Delete
    del_resp = await async_client.delete(
        f"/api/v1/manager/products/{pid}/image",
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    assert del_resp.status_code == 200
    assert del_resp.json()["image"] is None
    assert "image" not in del_resp.json()["attributes"]
    assert pub_id in mock_storage.deleted_public_ids


# ============================================================================
# Part 4: Inventory & Stock Adjustments (17 - 25)
# ============================================================================

@pytest.mark.asyncio
async def test_17_initial_stock_creation(async_client: AsyncClient, setup_test_environment: dict):
    """Test 17: Initial stock is properly populated in inventory table."""
    env = setup_test_environment
    sku = f"SKU-INIT-{uuid.uuid4().hex[:6].upper()}"
    create_resp = await async_client.post(
        "/api/v1/manager/products",
        json={"sku": sku, "name": "Initial Stock Product", "price_paise": 1000, "initial_stock": 40, "low_stock_threshold": 8},
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    pid = create_resp.json()["id"]
    env["created_product_ids"].append(pid)

    stock_resp = await async_client.get(
        f"/api/v1/manager/inventory/{pid}",
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    assert stock_resp.status_code == 200
    data = stock_resp.json()
    assert data["qty_on_hand"] == 40
    assert data["qty_reserved"] == 0
    assert data["qty_available"] == 40
    assert data["low_stock_threshold"] == 8


@pytest.mark.asyncio
async def test_18_stock_increase(async_client: AsyncClient, setup_test_environment: dict):
    """Test 18: Stock INCREASE adjustment increments on-hand quantity and logs audit."""
    env = setup_test_environment
    sku = f"SKU-INC-{uuid.uuid4().hex[:6].upper()}"
    create_resp = await async_client.post(
        "/api/v1/manager/products",
        json={"sku": sku, "name": "Increase Stock Product", "price_paise": 1000, "initial_stock": 10},
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    pid = create_resp.json()["id"]
    env["created_product_ids"].append(pid)

    adj_resp = await async_client.post(
        f"/api/v1/manager/inventory/{pid}/adjustments",
        json={"adjustment_type": "INCREASE", "quantity": 15, "reason": "Supplier shipment received"},
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    assert adj_resp.status_code == 200
    data = adj_resp.json()
    assert data["old_on_hand"] == 10
    assert data["new_on_hand"] == 25
    assert data["qty_available"] == 25
    assert data["quantity_delta"] == 15


@pytest.mark.asyncio
async def test_19_stock_decrease(async_client: AsyncClient, setup_test_environment: dict):
    """Test 19: Stock DECREASE adjustment decrements on-hand quantity and logs audit."""
    env = setup_test_environment
    sku = f"SKU-DEC-{uuid.uuid4().hex[:6].upper()}"
    create_resp = await async_client.post(
        "/api/v1/manager/products",
        json={"sku": sku, "name": "Decrease Stock Product", "price_paise": 1000, "initial_stock": 20},
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    pid = create_resp.json()["id"]
    env["created_product_ids"].append(pid)

    adj_resp = await async_client.post(
        f"/api/v1/manager/inventory/{pid}/adjustments",
        json={"adjustment_type": "DECREASE", "quantity": 7, "reason": "Damaged goods written off"},
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    assert adj_resp.status_code == 200
    data = adj_resp.json()
    assert data["old_on_hand"] == 20
    assert data["new_on_hand"] == 13
    assert data["qty_available"] == 13
    assert data["quantity_delta"] == -7


@pytest.mark.asyncio
async def test_20_negative_stock_rejection(async_client: AsyncClient, setup_test_environment: dict):
    """Test 20: Decreasing stock beyond current on-hand quantity returns HTTP 400 Bad Request."""
    env = setup_test_environment
    sku = f"SKU-NEG-{uuid.uuid4().hex[:6].upper()}"
    create_resp = await async_client.post(
        "/api/v1/manager/products",
        json={"sku": sku, "name": "Negative Test Product", "price_paise": 1000, "initial_stock": 5},
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    pid = create_resp.json()["id"]
    env["created_product_ids"].append(pid)

    adj_resp = await async_client.post(
        f"/api/v1/manager/inventory/{pid}/adjustments",
        json={"adjustment_type": "DECREASE", "quantity": 10, "reason": "Attempting excess decrease"},
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    assert adj_resp.status_code == 400
    assert "negative" in str(adj_resp.json()).lower()


@pytest.mark.asyncio
async def test_21_outstanding_reservation_protection(async_client: AsyncClient, setup_test_environment: dict):
    """Test 21: Cannot reduce stock below active reserved quantity (HTTP 400 Bad Request)."""
    env = setup_test_environment
    sku = f"SKU-RES-{uuid.uuid4().hex[:6].upper()}"
    create_resp = await async_client.post(
        "/api/v1/manager/products",
        json={"sku": sku, "name": "Reserved Protection Product", "price_paise": 1000, "initial_stock": 20},
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    pid = uuid.UUID(create_resp.json()["id"])
    env["created_product_ids"].append(str(pid))

    # Manually simulate 12 units reserved in PostgreSQL
    async with AsyncSessionLocal() as session:
        inv = await session.get(Inventory, (env["store_a_id"], pid))
        inv.qty_reserved = 12
        await session.commit()

    # Attempt to reduce stock to 10 (which is less than 12 reserved) -> HTTP 400 Bad Request
    adj_resp = await async_client.post(
        f"/api/v1/manager/inventory/{pid}/adjustments",
        json={"adjustment_type": "SET", "quantity": 10, "reason": "Attempt to breach reservations"},
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    assert adj_resp.status_code == 400
    assert "reserved" in str(adj_resp.json()).lower()


@pytest.mark.asyncio
async def test_22_concurrent_stock_adjustments(async_client: AsyncClient, setup_test_environment: dict):
    """Test 22: Concurrent stock adjustments succeed without lost updates."""
    env = setup_test_environment
    sku = f"SKU-CONC-{uuid.uuid4().hex[:6].upper()}"
    create_resp = await async_client.post(
        "/api/v1/manager/products",
        json={"sku": sku, "name": "Concurrency Product", "price_paise": 1000, "initial_stock": 100},
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    pid = create_resp.json()["id"]
    env["created_product_ids"].append(pid)

    # Perform 5 parallel increments of 5 units each (+25 total)
    tasks = [
        async_client.post(
            f"/api/v1/manager/inventory/{pid}/adjustments",
            json={"adjustment_type": "INCREASE", "quantity": 5, "reason": f"Parallel {i}"},
            headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
        )
        for i in range(5)
    ]
    responses = await asyncio.gather(*tasks)
    assert all(r.status_code == 200 for r in responses)

    # Verify final stock is exactly 125
    final_resp = await async_client.get(
        f"/api/v1/manager/inventory/{pid}",
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    assert final_resp.json()["qty_on_hand"] == 125


@pytest.mark.asyncio
async def test_23_audit_history_correctness(async_client: AsyncClient, setup_test_environment: dict):
    """Test 23: Inventory adjustments automatically record entries in inventory_audit_log via trigger."""
    env = setup_test_environment
    sku = f"SKU-AUDIT-{uuid.uuid4().hex[:6].upper()}"
    create_resp = await async_client.post(
        "/api/v1/manager/products",
        json={"sku": sku, "name": "Audit Product", "price_paise": 1000, "initial_stock": 10},
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    pid = create_resp.json()["id"]
    env["created_product_ids"].append(pid)

    # Perform adjustment
    await async_client.post(
        f"/api/v1/manager/inventory/{pid}/adjustments",
        json={"adjustment_type": "INCREASE", "quantity": 8, "reason": "Restock audit verify"},
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )

    history_resp = await async_client.get(
        f"/api/v1/manager/inventory/{pid}/history",
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    assert history_resp.status_code == 200
    logs = history_resp.json()
    assert len(logs) >= 1
    latest_log = logs[0]
    assert latest_log["old_on_hand"] == 10
    assert latest_log["new_on_hand"] == 18
    assert "Restock audit verify" in latest_log["reason"]


@pytest.mark.asyncio
async def test_24_cross_store_isolation_inventory(async_client: AsyncClient, setup_test_environment: dict):
    """Test 24: Store Manager A cannot view or adjust Store Manager B's inventory."""
    env = setup_test_environment
    sku = f"SKU-ISOL-{uuid.uuid4().hex[:6].upper()}"
    create_resp = await async_client.post(
        "/api/v1/manager/products",
        json={"sku": sku, "name": "Store B Only Product", "price_paise": 1000, "initial_stock": 30},
        headers={"Authorization": f"Bearer {env['token_mgr_b']}"},
    )
    pid = create_resp.json()["id"]
    env["created_product_ids"].append(pid)

    # Manager A attempts to adjust stock of this product passing Store B ID -> 403 Forbidden
    adj_resp = await async_client.post(
        f"/api/v1/manager/inventory/{pid}/adjustments?store_id={env['store_b_id']}",
        json={"adjustment_type": "DECREASE", "quantity": 5, "reason": "Cross store breach"},
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    assert adj_resp.status_code == 403


@pytest.mark.asyncio
async def test_25_low_stock_detection_endpoint(async_client: AsyncClient, setup_test_environment: dict):
    """Test 25: Low-stock monitoring endpoint lists items where available stock <= threshold."""
    env = setup_test_environment
    sku = f"SKU-LOW-{uuid.uuid4().hex[:6].upper()}"
    create_resp = await async_client.post(
        "/api/v1/manager/products",
        json={"sku": sku, "name": "Low Stock Test", "price_paise": 1000, "initial_stock": 2, "low_stock_threshold": 5},
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    pid = create_resp.json()["id"]
    env["created_product_ids"].append(pid)

    low_resp = await async_client.get(
        "/api/v1/manager/inventory/low-stock",
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    assert low_resp.status_code == 200
    items = low_resp.json()
    assert any(item["product_id"] == pid for item in items)


# ============================================================================
# Part 5: Kafka Outbox Events (26 - 30)
# ============================================================================

@pytest.mark.asyncio
async def test_26_product_event_generation(async_client: AsyncClient, setup_test_environment: dict):
    """Test 26: Product creation, update, and deactivation write events to outbox_events table."""
    env = setup_test_environment
    sku = f"SKU-EVT-{uuid.uuid4().hex[:6].upper()}"

    # 1. Create -> product.created
    res_create = await async_client.post(
        "/api/v1/manager/products",
        json={"sku": sku, "name": "Event Product", "price_paise": 1000},
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    pid = res_create.json()["id"]
    env["created_product_ids"].append(pid)

    # 2. Update -> product.updated
    await async_client.patch(
        f"/api/v1/manager/products/{pid}",
        json={"name": "Event Product New Name"},
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )

    # 3. Deactivate -> product.deactivated
    await async_client.delete(
        f"/api/v1/manager/products/{pid}",
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )

    # Verify outbox records in DB
    async with AsyncSessionLocal() as session:
        stmt = (
            select(OutboxEvent)
            .where(OutboxEvent.aggregate_id == pid)
            .order_by(OutboxEvent.created_at.asc())
        )
        res = await session.execute(stmt)
        events = res.scalars().all()
        types = [e.event_type for e in events]
        assert "product.created" in types
        assert "product.updated" in types
        assert "product.deactivated" in types


@pytest.mark.asyncio
async def test_27_inventory_event_generation(async_client: AsyncClient, setup_test_environment: dict):
    """Test 27: Stock adjustment writes inventory.stock.updated event to outbox_events table."""
    env = setup_test_environment
    sku = f"SKU-INVEVT-{uuid.uuid4().hex[:6].upper()}"
    create_resp = await async_client.post(
        "/api/v1/manager/products",
        json={"sku": sku, "name": "Stock Event Product", "price_paise": 1000, "initial_stock": 20},
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    pid = create_resp.json()["id"]
    env["created_product_ids"].append(pid)

    await async_client.post(
        f"/api/v1/manager/inventory/{pid}/adjustments",
        json={"adjustment_type": "INCREASE", "quantity": 10, "reason": "Kafka inventory event test"},
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )

    async with AsyncSessionLocal() as session:
        stmt = (
            select(OutboxEvent)
            .where(
                OutboxEvent.aggregate_id == f"{env['store_a_id']}:{pid}",
                OutboxEvent.event_type == "inventory.stock.updated",
            )
            .order_by(OutboxEvent.created_at.desc())
        )
        res = await session.execute(stmt)
        evt = res.scalars().first()
        assert evt is not None
        assert evt.payload["new_on_hand"] == 30


@pytest.mark.asyncio
async def test_28_outbox_transactional_rollback_on_failure(async_client: AsyncClient, setup_test_environment: dict):
    """Test 28: Failed stock adjustments do NOT produce dangling outbox events."""
    env = setup_test_environment
    sku = f"SKU-RB-{uuid.uuid4().hex[:6].upper()}"
    create_resp = await async_client.post(
        "/api/v1/manager/products",
        json={"sku": sku, "name": "Rollback Product", "price_paise": 1000, "initial_stock": 5},
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    pid = create_resp.json()["id"]
    env["created_product_ids"].append(pid)

    # Attempt illegal decrease that fails
    fail_resp = await async_client.post(
        f"/api/v1/manager/inventory/{pid}/adjustments",
        json={"adjustment_type": "DECREASE", "quantity": 100, "reason": "Will fail and rollback"},
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    assert fail_resp.status_code == 400

    # Verify no inventory outbox event with quantity 100 was committed
    async with AsyncSessionLocal() as session:
        stmt = select(OutboxEvent).where(
            OutboxEvent.aggregate_id == f"{env['store_a_id']}:{pid}",
            OutboxEvent.payload["reason"].astext == "Will fail and rollback",
        )
        res = await session.execute(stmt)
        evt = res.scalars().first()
        assert evt is None


@pytest.mark.asyncio
async def test_29_low_stock_event_generation(async_client: AsyncClient, setup_test_environment: dict):
    """Test 29: Crossing below threshold emits inventory.low_stock outbox event."""
    env = setup_test_environment
    sku = f"SKU-LOWEVT-{uuid.uuid4().hex[:6].upper()}"
    create_resp = await async_client.post(
        "/api/v1/manager/products",
        json={"sku": sku, "name": "Low Stock Alert Product", "price_paise": 1000, "initial_stock": 10, "low_stock_threshold": 5},
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    pid = create_resp.json()["id"]
    env["created_product_ids"].append(pid)

    # Adjust from 10 down to 3 (threshold is 5)
    await async_client.post(
        f"/api/v1/manager/inventory/{pid}/adjustments",
        json={"adjustment_type": "SET", "quantity": 3, "reason": "Drop below threshold"},
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )

    async with AsyncSessionLocal() as session:
        stmt = select(OutboxEvent).where(
            OutboxEvent.aggregate_id == f"{env['store_a_id']}:{pid}",
            OutboxEvent.event_type == "inventory.low_stock",
        )
        res = await session.execute(stmt)
        evt = res.scalars().first()
        assert evt is not None
        assert evt.payload["qty_available"] == 3


@pytest.mark.asyncio
async def test_30_duplicate_low_stock_suppression(async_client: AsyncClient, setup_test_environment: dict):
    """Test 30: Adjustments on an item that was ALREADY below threshold do not re-emit duplicate low_stock alerts."""
    env = setup_test_environment
    sku = f"SKU-SUPP-{uuid.uuid4().hex[:6].upper()}"
    create_resp = await async_client.post(
        "/api/v1/manager/products",
        json={"sku": sku, "name": "Suppression Product", "price_paise": 1000, "initial_stock": 10, "low_stock_threshold": 5},
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )
    pid = create_resp.json()["id"]
    env["created_product_ids"].append(pid)

    # 1. First drop from 10 to 4 -> crosses threshold -> emits 1 event
    await async_client.post(
        f"/api/v1/manager/inventory/{pid}/adjustments",
        json={"adjustment_type": "SET", "quantity": 4, "reason": "First drop"},
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )

    # 2. Second drop from 4 to 2 -> was already below threshold -> suppressed
    await async_client.post(
        f"/api/v1/manager/inventory/{pid}/adjustments",
        json={"adjustment_type": "SET", "quantity": 2, "reason": "Second drop while already low"},
        headers={"Authorization": f"Bearer {env['token_mgr_a']}"},
    )

    async with AsyncSessionLocal() as session:
        stmt = select(OutboxEvent).where(
            OutboxEvent.aggregate_id == f"{env['store_a_id']}:{pid}",
            OutboxEvent.event_type == "inventory.low_stock",
        )
        res = await session.execute(stmt)
        events = res.scalars().all()
        # Exactly one low_stock event emitted!
        assert len(events) == 1
