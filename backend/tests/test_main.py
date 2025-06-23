# backend/tests/test_main.py
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_read_root(client: AsyncClient):
    """Ana sayfa endpoint testi"""
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "DOVL E-Commerce API" in data["message"]

@pytest.mark.asyncio
async def test_docs_accessible(client: AsyncClient):
    """API dokümantasyonu erişilebilirlik testi"""
    response = await client.get("/docs")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

@pytest.mark.asyncio
async def test_openapi_json_accessible(client: AsyncClient):
    """OpenAPI JSON şeması erişilebilirlik testi"""
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    assert "application/json" in response.headers["content-type"]
    data = response.json()
    assert "openapi" in data
    assert "info" in data
    assert "paths" in data