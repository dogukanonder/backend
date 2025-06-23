# backend/models/user_models.py
from pydantic import BaseModel, EmailStr, Field, ConfigDict, validator
from typing import Optional, List
from datetime import datetime

# Adresler için alt model
class AddressBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=100, description="Adres Başlığı (Ev, İş vb.)")
    fullName: str = Field(..., min_length=2, max_length=100, description="Ad Soyad")
    address: str = Field(..., min_length=5, max_length=255, description="Adres Satırı")
    street: Optional[str] = Field(None, min_length=2, max_length=100, description="Sokak Bilgisi")
    city: str = Field(..., min_length=2, max_length=50, description="Şehir")
    district: Optional[str] = Field(None, min_length=2, max_length=50, description="İlçe")
    postalCode: Optional[str] = Field(None, max_length=10, description="Posta Kodu")
    country: str = Field("Türkiye", max_length=50, description="Ülke")
    phone: str = Field(..., min_length=10, max_length=20, description="Telefon Numarası")

class AddressCreate(AddressBase):
    isDefaultShipping: bool = False
    isDefaultBilling: bool = False

class Address(AddressBase):
    # Pydantic v2'de model_config kullanılır
    model_config = ConfigDict(
        from_attributes=True, # ORM modellerinden veri okumak için
        populate_by_name=True, # Alan adlarını kullan
        json_schema_extra={
            "example": {
                "title": "Ev Adresim",
                "fullName": "Ayşe Yılmaz",
                "address": "Örnek Mah. Test Cad. No:1 D:2",
                "city": "İstanbul",
                "district": "Kadıköy",
                "postalCode": "34700",
                "country": "Türkiye",
                "phone": "5551234567",
                "isDefaultShipping": True,
                "isDefaultBilling": True
            }
        }
    )
    id: str = Field(..., alias='_id', description="MongoDB Adres ID") # Veritabanından gelen _id'yi id olarak mapleriz
    isDefaultShipping: bool = False
    isDefaultBilling: bool = False
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None


# Kullanıcı Oluşturma Modeli (Request Body)
class UserCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=50)
    surname: str = Field(..., min_length=2, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6)
    phone: Optional[str] = Field(None, min_length=10, max_length=20)

    # Pydantic v2'de model_config kullanılır
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Test",
                "surname": "Kullanıcı",
                "email": "test@example.com",
                "password": "password123",
                "phone": "5551112233"
            }
        }
    )


# Kullanıcı Giriş Modeli (Request Body)
class UserLogin(BaseModel):
    email: EmailStr
    password: str

    # Pydantic v2'de model_config kullanılır
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "test@example.com",
                "password": "password123"
            }
        }
    )


# Genel Kullanıcı Bilgisi Modeli (Response Body - Şifresiz)
class UserPublic(BaseModel):
    id: str = Field(..., alias='_id') # MongoDB ID
    name: str
    surname: str
    email: EmailStr
    phone: Optional[str] = None
    role: str
    isActive: bool
    createdAt: datetime
    updatedAt: datetime
    lastLogin: Optional[datetime] = None
    addresses: List[Address] = [] # Adres listesi

    # Pydantic v2'de model_config kullanılır
    model_config = ConfigDict(
        from_attributes=True, # ORM modellerinden veri okumak için
        populate_by_name=True, # _id gibi alanları id olarak almak için
         json_schema_extra={
            "example": {
                "id": "605c72aadd70e9a3e4e1f1ab",
                "name": "Test",
                "surname": "Kullanıcı",
                "email": "test@example.com",
                "phone": "5551112233",
                "role": "user",
                "isActive": True,
                "createdAt": "2023-01-01T10:00:00Z",
                "updatedAt": "2023-01-02T12:30:00Z",
                "lastLogin": "2023-01-05T09:15:00Z",
                "addresses": []
            }
        }
    )