import pytest


@pytest.mark.asyncio
async def test_root_endpoint(async_client):
    response = await async_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["project"] == "SmartCart 2.0"
    assert data["team"] == "Hack Hive"
    assert data["status"] == "online"

    # Also test /api alias for frontend proxy
    api_response = await async_client.get("/api")
    assert api_response.status_code == 200
    api_data = api_response.json()
    assert api_data["project"] == "SmartCart 2.0"


@pytest.mark.asyncio
async def test_health_check_endpoint(async_client):
    response = await async_client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "services" in data
    assert "version" in data


@pytest.mark.asyncio
async def test_swagger_openapi_docs(async_client):
    response = await async_client.get("/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert data["info"]["title"] == "SmartCart 2.0"
