import httpx
import pytest

from app.main import create_app


@pytest.mark.asyncio
async def test_health_endpoint_returns_status_even_without_live_services() -> None:
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"healthy", "degraded"}
    assert body["symbol"] == "XAUUSD"
    assert body["database"] in {"connected", "disconnected"}
    assert body["redis"] in {"connected", "disconnected"}


@pytest.mark.asyncio
async def test_health_database_endpoint() -> None:
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/database")

    assert response.status_code == 200
    assert response.json()["status"] in {"connected", "disconnected"}


@pytest.mark.asyncio
async def test_health_redis_endpoint() -> None:
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/redis")

    assert response.status_code == 200
    assert response.json()["status"] in {"connected", "disconnected"}
