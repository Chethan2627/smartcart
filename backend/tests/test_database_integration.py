import pytest
import pytest_asyncio
from sqlalchemy import text
from app.db.session import AsyncSessionLocal, get_db, async_engine
from app.config import settings


@pytest_asyncio.fixture(autouse=True)
async def dispose_engine_after_test():
    """
    Ensures SQLAlchemy connection pool disposes connections before the test event loop closes.
    Prevents Event loop is closed / cross-loop connection reuse issues on Windows pytest-asyncio.
    """
    yield
    if async_engine is not None:
        await async_engine.dispose()


@pytest.mark.asyncio
async def test_live_database_connection_select_1():
    """
    Integration test: Verifies live PostgreSQL async connectivity by executing SELECT 1.
    """
    assert AsyncSessionLocal is not None, "AsyncSessionLocal must be initialized"
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT 1 AS alive, current_database() AS db_name;"))
        row = result.mappings().one()
        assert row["alive"] == 1
        assert row["db_name"] == "smartcart_dev"


@pytest.mark.asyncio
async def test_get_db_dependency_lifecycle():
    """
    Integration test: Verifies that get_db yields an active session and closes it cleanly.
    """
    session_gen = get_db()
    session = await anext(session_gen)
    try:
        result = await session.execute(text("SELECT 42 AS answer;"))
        assert result.scalar_one() == 42
        assert session.is_active is True
    finally:
        with pytest.raises(StopAsyncIteration):
            await anext(session_gen)


@pytest.mark.asyncio
async def test_get_db_dependency_rolls_back_on_exception():
    """
    Integration test: Verifies that get_db rolls back the transaction when an exception is raised.
    """
    session_gen = get_db()
    session = await anext(session_gen)
    try:
        # Simulate an application failure during request handling
        raise ValueError("Simulated route error")
    except ValueError:
        with pytest.raises(ValueError, match="Simulated route error"):
            await session_gen.athrow(ValueError("Simulated route error"))


@pytest.mark.asyncio
async def test_readonly_stores_schema_preservation():
    """
    Integration test: Read-only query asserting that all 5 metro stores seeded in Phase 1 exist intact.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT code, name, city FROM stores ORDER BY code;"))
        rows = result.mappings().all()
        assert len(rows) == 5, f"Expected 5 stores from Phase 1, found {len(rows)}"
        codes = [r["code"] for r in rows]
        assert codes == ["STORE-001", "STORE-002", "STORE-003", "STORE-004", "STORE-005"]


@pytest.mark.asyncio
async def test_readonly_products_schema_preservation():
    """
    Integration test: Read-only query asserting that all 5 products seeded in Phase 1 exist intact.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT sku, name, price_paise FROM products ORDER BY sku;"))
        rows = result.mappings().all()
        assert len(rows) == 5, f"Expected 5 products from Phase 1, found {len(rows)}"
        skus = [r["sku"] for r in rows]
        assert "PHONE-001" in skus
        assert "BT-HEAD-001" in skus
        assert "RICE-5KG" in skus


@pytest.mark.asyncio
async def test_readonly_inventory_balances_preservation():
    """
    Integration test: Read-only query asserting that initial inventory quantities match Phase 1 baselines.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT s.code, p.sku, i.qty_on_hand, i.qty_reserved
                  FROM inventory i
                  JOIN stores s ON s.id = i.store_id
                  JOIN products p ON p.id = i.product_id
                 WHERE s.code = 'STORE-005' AND p.sku = 'PHONE-001';
            """)
        )
        row = result.mappings().one()
        # Mumbai phone inventory must be exactly 1 on hand, 0 reserved
        assert row["qty_on_hand"] == 1
        assert row["qty_reserved"] == 0


@pytest.mark.asyncio
async def test_live_database_health_endpoint(async_client):
    """
    Integration test: Verifies the live /health/db endpoint against the real PostgreSQL container.
    """
    response = await async_client.get("/health/db")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "postgresql"
    assert data["database_connected"] is True
    assert isinstance(data["latency_ms"], (int, float))
    assert data["latency_ms"] >= 0
