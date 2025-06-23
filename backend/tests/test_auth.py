# backend/tests/test_auth.py
import pytest
from httpx import AsyncClient
from fastapi import status
from motor.motor_asyncio import AsyncIOMotorDatabase # DB tipi için
from utils.security import verify_password # Şifre doğrulaması için

pytestmark = pytest.mark.asyncio

@pytest.mark.asyncio
async def test_register_user_success(client: AsyncClient, test_user_data: dict):
    """Başarılı kullanıcı kaydı testi"""
    response = await client.post("/auth/register", json=test_user_data)
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == test_user_data["email"]
    assert "id" in data

@pytest.mark.asyncio
async def test_register_user_duplicate_email(client: AsyncClient, test_user_data: dict):
    """Aynı email ile tekrar kayıt testi"""
    # İlk kayıt
    await client.post("/auth/register", json=test_user_data)
    # Aynı email ile tekrar kayıt
    response = await client.post("/auth/register", json=test_user_data)
    assert response.status_code == 400
    assert "email already registered" in response.json()["detail"].lower()

@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, test_user_data: dict):
    """Başarılı giriş testi"""
    # Önce kayıt ol
    await client.post("/auth/register", json=test_user_data)
    # Giriş yap
    login_data = {
        "username": test_user_data["email"],
        "password": test_user_data["password"]
    }
    response = await client.post("/auth/login", data=login_data)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, test_user_data: dict):
    """Yanlış şifre ile giriş testi"""
    # Önce kayıt ol
    await client.post("/auth/register", json=test_user_data)
    # Yanlış şifre ile giriş yap
    login_data = {
        "username": test_user_data["email"],
        "password": "wrongpassword"
    }
    response = await client.post("/auth/login", data=login_data)
    assert response.status_code == 401
    assert "incorrect password" in response.json()["detail"].lower()

@pytest.mark.asyncio
async def test_login_nonexistent_user(client: AsyncClient):
    """Var olmayan kullanıcı ile giriş testi"""
    login_data = {
        "username": "nonexistent@example.com",
        "password": "anypassword"
    }
    response = await client.post("/auth/login", data=login_data)
    assert response.status_code == 401
    assert "user not found" in response.json()["detail"].lower()

@pytest.mark.parametrize("field_to_remove, error_message", [
    ("name", "Field required"),
    ("surname", "Field required"),
    ("email", "Field required"),
    ("password", "Field required"),
])
async def test_register_user_missing_fields(client: AsyncClient, test_user_data: dict, field_to_remove: str, error_message: str):
    """ Zorunlu alanlar eksik olduğunda kayıt hatasını test eder."""
    invalid_data = test_user_data.copy()
    del invalid_data[field_to_remove]
    response = await client.post("/auth/register", json=invalid_data)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY # FastAPI validation error
    assert error_message in str(response.json()) # Pydantic hatasını kontrol et

async def test_register_user_invalid_email(client: AsyncClient, test_user_data: dict):
    """ Geçersiz e-posta ile kayıt hatasını test eder."""
    invalid_data = test_user_data.copy()
    invalid_data["email"] = "invalid-email"
    response = await client.post("/auth/register", json=invalid_data)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "value is not a valid email address" in str(response.json())

async def test_register_user_short_password(client: AsyncClient, test_user_data: dict):
    """ Kısa şifre ile kayıt hatasını test eder."""
    invalid_data = test_user_data.copy()
    invalid_data["password"] = "12345" # 6'dan kısa
    response = await client.post("/auth/register", json=invalid_data)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "String should have at least 6 characters" in str(response.json())

async def test_login_inactive_user(client: AsyncClient, db: AsyncIOMotorDatabase, test_user_data: dict):
    """ Aktif olmayan kullanıcı ile girişi test eder."""
    # Kullanıcıyı kaydet ve pasif yap
    register_response = await client.post("/auth/register", json=test_user_data)
    user_id = register_response.json()["id"]
    await db["users"].update_one({"_id": ObjectId(user_id)}, {"$set": {"isActive": False}})

    login_data = {"username": test_user_data["email"], "password": test_user_data["password"]}
    response = await client.post("/auth/login", data=login_data)
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "askıya alınmış" in response.json()["detail"]