from unittest.mock import AsyncMock, MagicMock, patch
import pytest


@pytest.mark.asyncio
async def test_root_endpoint(async_client):
    response = await async_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["project"] == "SmartCart 2.0"
    assert data["team"] == "Hack Hive"
    assert data["status"] == "online"

    # Also test /api alias
    api_response = await async_client.get("/api")
    assert api_response.status_code == 200
    api_data = api_response.json()
    assert api_data["project"] == "SmartCart 2.0"


@pytest.mark.asyncio
async def test_health_check_endpoints(async_client):
    for path in ["/health", "/api/health"]:
        response = await async_client.get(path)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "services" in data
        assert "version" in data
        assert "environment" in data


@pytest.mark.asyncio
async def test_database_health_success_mocked(async_client):
    """
    Unit test: Verifies /health/db returns 200 without requiring a real database connection.
    """
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = 1
    mock_session.execute.return_value = mock_result

    class MockSessionContext:
        async def __aenter__(self):
            return mock_session
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    with patch("app.main.AsyncSessionLocal", return_value=MockSessionContext()):
        for path in ["/health/db", "/api/health/db"]:
            response = await async_client.get(path)
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["database_connected"] is True
            assert "latency_ms" in data


@pytest.mark.asyncio
async def test_database_health_failure_returns_503(async_client):
    """
    Unit test: Verifies /health/db returns 503 and a sanitized error message when database fails.
    Ensures raw exceptions and credentials are never leaked.
    """
    class MockFailingSessionContext:
        async def __aenter__(self):
            raise ConnectionRefusedError("Connection refused to internal-db.internal:5432 with password=secret")
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    with patch("app.main.AsyncSessionLocal", return_value=MockFailingSessionContext()):
        for path in ["/health/db", "/api/health/db"]:
            response = await async_client.get(path)
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "unhealthy"
            assert data["database_connected"] is False
            # Ensure error is sanitized and leaks no passwords, IPs, or connection strings
            assert data["error"] == "Database connectivity check failed"
            assert "secret" not in response.text
            assert "internal-db" not in response.text


@pytest.mark.asyncio
async def test_app_starts_without_database_url(async_client):
    """
    Unit test: Verifies FastAPI starts and root/health endpoints function even when DATABASE_URL is None.
    Only /health/db returns HTTP 503.
    """
    with patch("app.main.settings.DATABASE_URL", None), patch("app.main.AsyncSessionLocal", None):
        root_resp = await async_client.get("/")
        assert root_resp.status_code == 200

        health_resp = await async_client.get("/health")
        assert health_resp.status_code == 200
        health_data = health_resp.json()
        assert health_data["services"]["postgresql_configured"] is False

        db_resp = await async_client.get("/health/db")
        assert db_resp.status_code == 503
        db_data = db_resp.json()
        assert db_data["status"] == "unhealthy"
        assert db_data["database_connected"] is False
        assert db_data["error"] == "Database service is not configured"


@pytest.mark.asyncio
async def test_swagger_openapi_docs(async_client):
    response = await async_client.get("/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert data["info"]["title"] == "SmartCart 2.0"
