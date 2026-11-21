"""
Integration and API tests for SmartCart 2.0 Product Catalogue Routes:
- GET /api/v1/products (catalogue listing, pagination, category and brand filters)
- GET /api/v1/products/sku/{sku} (authoritative product lookup by SKU)
- GET /api/v1/products/{product_id} (product details by UUID)
- Inactive product access restrictions and administrator bypass
- Authoritative database pricing verification and tamper-resistance
- Error response standardization and input validation
"""
import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text

from app.db.session import AsyncSessionLocal, async_engine
from app.models.product import Product


@pytest_asyncio.fixture(autouse=True)
async def dispose_engine_after_test():
    """Ensure engine connections are cleanly disposed before event loop teardown."""
    yield
    if async_engine is not None:
        await async_engine.dispose()


@pytest.mark.asyncio
async def test_list_active_products_unauthenticated(async_client: AsyncClient):
    """
    Verify public visitors can browse the active product catalogue.
    Checks:
    - HTTP 200 OK
    - All returned items have is_active is True
    - Authoritative fields present (id, sku, name, brand, category, price_paise, attributes)
    - price_paise is a positive integer
    - No password hashes or internal secrets in response
    """
    resp = await async_client.get("/api/v1/products")
    assert resp.status_code == 200
    products = resp.json()
    assert isinstance(products, list)
    assert len(products) >= 5

    for prod in products:
        assert "id" in prod
        assert "sku" in prod
        assert "name" in prod
        assert "brand" in prod
        assert "category" in prod
        assert isinstance(prod["price_paise"], int)
        assert prod["price_paise"] > 0
        assert prod["is_active"] is True
        assert "attributes" in prod
        assert isinstance(prod["attributes"], dict)
        assert "created_at" in prod
        assert "updated_at" in prod
        # Verify no sensitive leakage
        assert "password" not in prod
        assert "hash" not in prod


@pytest.mark.asyncio
async def test_list_products_category_and_brand_filtering(async_client: AsyncClient):
    """
    Verify product filtering by exact category and brand.
    """
    # Filter by category
    resp_cat = await async_client.get("/api/v1/products?category=Grocery")
    assert resp_cat.status_code == 200
    grocery_prods = resp_cat.json()
    assert len(grocery_prods) >= 3
    for p in grocery_prods:
        assert p["category"] == "Grocery"

    # Filter by brand
    resp_brand = await async_client.get("/api/v1/products?brand=Samsung")
    assert resp_brand.status_code == 200
    samsung_prods = resp_brand.json()
    assert len(samsung_prods) == 1
    assert samsung_prods[0]["sku"] == "PHONE-001"
    assert samsung_prods[0]["brand"] == "Samsung"

    # Filter by both category and brand
    resp_both = await async_client.get("/api/v1/products?category=Grocery&brand=Nandini")
    assert resp_both.status_code == 200
    nandini_prods = resp_both.json()
    assert len(nandini_prods) == 1
    assert nandini_prods[0]["sku"] == "MILK-1L"

    # Nonexistent category
    resp_empty = await async_client.get("/api/v1/products?category=NonExistentCategory")
    assert resp_empty.status_code == 200
    assert resp_empty.json() == []


@pytest.mark.asyncio
async def test_list_products_pagination(async_client: AsyncClient):
    """
    Verify catalogue pagination (skip and limit) offsets.
    """
    resp_all = await async_client.get("/api/v1/products?skip=0&limit=5")
    assert resp_all.status_code == 200
    all_prods = resp_all.json()
    assert len(all_prods) >= 3

    resp_paged = await async_client.get("/api/v1/products?skip=1&limit=2")
    assert resp_paged.status_code == 200
    paged_prods = resp_paged.json()
    assert len(paged_prods) == 2
    assert paged_prods[0]["id"] == all_prods[1]["id"]
    assert paged_prods[1]["id"] == all_prods[2]["id"]


@pytest.mark.asyncio
async def test_list_products_invalid_query_parameters(async_client: AsyncClient):
    """
    Verify validation rejection for invalid query parameters:
    - Negative skip (skip < 0)
    - Zero or negative limit (limit < 1)
    - Exceeded limit (limit > 100)
    - Non-integer skip
    """
    # Negative skip
    r1 = await async_client.get("/api/v1/products?skip=-1")
    assert r1.status_code == 422
    assert r1.json()["error"]["code"] == "VALIDATION_ERROR"

    # Zero limit
    r2 = await async_client.get("/api/v1/products?limit=0")
    assert r2.status_code == 422
    assert r2.json()["error"]["code"] == "VALIDATION_ERROR"

    # Excess limit (> 100)
    r3 = await async_client.get("/api/v1/products?limit=101")
    assert r3.status_code == 422
    assert r3.json()["error"]["code"] == "VALIDATION_ERROR"

    # Non-integer skip
    r4 = await async_client.get("/api/v1/products?skip=invalid")
    assert r4.status_code == 422
    assert r4.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_get_product_by_id_success(async_client: AsyncClient):
    """
    Verify retrieving product details by primary key UUID.
    """
    list_resp = await async_client.get("/api/v1/products")
    first_prod = list_resp.json()[0]
    product_id = first_prod["id"]

    resp = await async_client.get(f"/api/v1/products/{product_id}")
    assert resp.status_code == 200
    product = resp.json()
    assert product["id"] == product_id
    assert product["sku"] == first_prod["sku"]
    assert product["name"] == first_prod["name"]
    assert product["price_paise"] == first_prod["price_paise"]
    assert product["is_active"] is True


@pytest.mark.asyncio
async def test_get_product_by_id_not_found(async_client: AsyncClient):
    """
    Verify requesting a nonexistent product UUID returns HTTP 404 NOT_FOUND.
    """
    missing_id = str(uuid.uuid4())
    resp = await async_client.get(f"/api/v1/products/{missing_id}")
    assert resp.status_code == 404
    data = resp.json()
    assert data["error"]["code"] == "NOT_FOUND"
    assert "not found" in data["error"]["message"].lower()


@pytest.mark.asyncio
async def test_get_product_invalid_uuid(async_client: AsyncClient):
    """
    Verify passing a malformed UUID in the path returns HTTP 422 VALIDATION_ERROR.
    """
    resp = await async_client.get("/api/v1/products/invalid-uuid-format")
    assert resp.status_code == 422
    data = resp.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_get_product_by_sku_success(async_client: AsyncClient):
    """
    Verify lookup by unique SKU returns authoritative product data and price.
    """
    resp = await async_client.get("/api/v1/products/sku/BT-HEAD-001")
    assert resp.status_code == 200
    product = resp.json()
    assert product["sku"] == "BT-HEAD-001"
    assert product["name"] == "Bluetooth Headphones"
    assert product["brand"] == "boAt"
    assert product["category"] == "Electronics"
    assert product["price_paise"] == 149900  # ₹1,499.00
    assert product["is_active"] is True


@pytest.mark.asyncio
async def test_get_product_by_sku_not_found(async_client: AsyncClient):
    """
    Verify lookup with nonexistent SKU returns HTTP 404 NOT_FOUND.
    """
    resp = await async_client.get("/api/v1/products/sku/UNKNOWN-SKU-999")
    assert resp.status_code == 404
    data = resp.json()
    assert data["error"]["code"] == "NOT_FOUND"
    assert "not found" in data["error"]["message"].lower()


@pytest.mark.asyncio
async def test_inactive_product_restrictions_and_admin_access(async_client: AsyncClient):
    """
    Verify inactive product access boundaries:
    - Public visitors cannot browse or lookup inactive products (returns HTTP 400 Bad Request).
    - Inactive products do not appear in public listings.
    - Administrators CAN inspect inactive products by UUID, SKU, and listing filter.
    """
    inactive_id = uuid.uuid4()
    inactive_sku = f"INACT-{uuid.uuid4().hex[:6].upper()}"

    # Insert an inactive product into PostgreSQL
    async with AsyncSessionLocal() as session:
        inactive_prod = Product(
            id=inactive_id,
            sku=inactive_sku,
            name="Discontinued Item",
            brand="OldBrand",
            category="Discontinued",
            price_paise=99900,
            is_active=False,
        )
        session.add(inactive_prod)
        await session.commit()

    try:
        # 1. Public listing must NOT include inactive product
        list_resp = await async_client.get("/api/v1/products?category=Discontinued")
        assert list_resp.status_code == 200
        assert not any(p["sku"] == inactive_sku for p in list_resp.json())

        # 2. Public lookup by ID must return HTTP 400 Bad Request
        direct_resp = await async_client.get(f"/api/v1/products/{inactive_id}")
        assert direct_resp.status_code == 400
        assert direct_resp.json()["error"]["code"] == "BAD_REQUEST"
        assert "inactive" in direct_resp.json()["error"]["message"]

        # 3. Public lookup by SKU must return HTTP 400 Bad Request
        sku_resp = await async_client.get(f"/api/v1/products/sku/{inactive_sku}")
        assert sku_resp.status_code == 400
        assert sku_resp.json()["error"]["code"] == "BAD_REQUEST"
        assert "inactive" in sku_resp.json()["error"]["message"]

        # 4. Customer lookup by ID must also return HTTP 400 Bad Request
        login_cust = await async_client.post(
            "/api/v1/auth/login",
            json={"email": "demo@smartcart.in", "password": "Demo@123"},
        )
        cust_token = login_cust.json()["access_token"]
        cust_resp = await async_client.get(
            f"/api/v1/products/{inactive_id}",
            headers={"Authorization": f"Bearer {cust_token}"},
        )
        assert cust_resp.status_code == 400
        assert cust_resp.json()["error"]["code"] == "BAD_REQUEST"

        # 5. Administrator CAN view inactive product by ID
        login_admin = await async_client.post(
            "/api/v1/auth/login",
            json={"email": "admin@smartcart.in", "password": "Demo@123"},
        )
        admin_token = login_admin.json()["access_token"]
        admin_id_resp = await async_client.get(
            f"/api/v1/products/{inactive_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert admin_id_resp.status_code == 200
        assert admin_id_resp.json()["id"] == str(inactive_id)
        assert admin_id_resp.json()["is_active"] is False

        # 6. Administrator CAN view inactive product by SKU
        admin_sku_resp = await async_client.get(
            f"/api/v1/products/sku/{inactive_sku}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert admin_sku_resp.status_code == 200
        assert admin_sku_resp.json()["sku"] == inactive_sku
        assert admin_sku_resp.json()["is_active"] is False

        # 7. Administrator can list inactive products with is_active=false
        admin_list_resp = await async_client.get(
            "/api/v1/products?category=Discontinued&is_active=false",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert admin_list_resp.status_code == 200
        assert any(p["sku"] == inactive_sku for p in admin_list_resp.json())

    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(text("DELETE FROM products WHERE id = :id"), {"id": inactive_id})
            await session.commit()


@pytest.mark.asyncio
async def test_authoritative_pricing_tamper_resistance(async_client: AsyncClient):
    """
    Verify clients cannot tamper with authoritative database prices:
    - Injected query parameters (e.g. ?price_paise=1) have no effect on output.
    - Product mutations (POST, PUT, DELETE) are rejected as 405 Method Not Allowed.
    """
    resp = await async_client.get("/api/v1/products/sku/BT-HEAD-001?price_paise=100")
    assert resp.status_code == 200
    # Price remains canonical database price 149900 paise
    assert resp.json()["price_paise"] == 149900

    # Creation attempt rejected (catalogue routes are read-only)
    post_resp = await async_client.post(
        "/api/v1/products",
        json={"sku": "FAKE-001", "name": "Fake", "price_paise": 10},
    )
    assert post_resp.status_code == 405  # Method Not Allowed


@pytest.mark.asyncio
async def test_standard_error_response_structure(async_client: AsyncClient):
    """
    Verify error responses strictly follow the SmartCart 2.0 standardized envelope:
    { "error": { "code": "...", "message": "...", "details": { ... } } }
    """
    # 404 Not Found error envelope
    r404 = await async_client.get(f"/api/v1/products/{uuid.uuid4()}")
    assert r404.status_code == 404
    data404 = r404.json()
    assert "error" in data404
    assert data404["error"]["code"] == "NOT_FOUND"
    assert isinstance(data404["error"]["message"], str)
    assert isinstance(data404["error"]["details"], dict)

    # 422 Validation Error envelope
    r422 = await async_client.get("/api/v1/products?limit=-5")
    assert r422.status_code == 422
    data422 = r422.json()
    assert "error" in data422
    assert data422["error"]["code"] == "VALIDATION_ERROR"
    assert isinstance(data422["error"]["message"], str)
    assert "errors" in data422["error"]["details"]
