# backend/tests/conftest.py
import pytest
import asyncio
from httpx import AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone
from typing import AsyncGenerator, Any
import os
from config import settings
from main import app
from database import get_database, connect_to_mongo, close_mongo_connection

# Test veritabanı ayarları
TEST_MONGO_URI = os.getenv("TEST_MONGO_URI", "mongodb://localhost:27017")
TEST_DB_NAME = os.getenv("TEST_DB_NAME", "dovl_test_db")

@pytest.fixture(scope="session")
def event_loop():
    """Test oturumu için event loop oluşturur."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()

@pytest.fixture(scope="session")
async def test_db():
    """Test veritabanı bağlantısını sağlar."""
    # Test veritabanı ayarlarını geçici olarak değiştir
    original_uri = settings.MONGO_URI
    original_db = settings.DB_NAME
    
    settings.MONGO_URI = TEST_MONGO_URI
    settings.DB_NAME = TEST_DB_NAME
    
    await connect_to_mongo()
    yield get_database()
    
    await close_mongo_connection()
    # Orijinal ayarları geri yükle
    settings.MONGO_URI = original_uri
    settings.DB_NAME = original_db

@pytest.fixture(autouse=True)
async def clean_db(test_db):
    """Her testten önce veritabanını temizler."""
    collections = await test_db.list_collection_names()
    for collection in collections:
        if not collection.startswith("system."):
            await test_db[collection].delete_many({})

@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, Any]:
    """Test istemcisi sağlar."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

@pytest.fixture
def test_user_data():
    """Test kullanıcı verilerini sağlar."""
    return {
        "name": "Test",
        "surname": "User",
        "email": f"test_{int(datetime.now().timestamp() * 1000)}@example.com",
        "password": "testpassword123"
    }

@pytest.fixture
async def auth_headers(client: AsyncClient, test_user_data: dict) -> dict:
    """Test kullanıcısı için auth token sağlar."""
    # Kullanıcı kaydı
    await client.post("/auth/register", json=test_user_data)
    
    # Giriş yap
    login_data = {
        "username": test_user_data["email"],
        "password": test_user_data["password"]
    }
    response = await client.post("/auth/login", data=login_data)
    token = response.json()["access_token"]
    
    return {"Authorization": f"Bearer {token}"}