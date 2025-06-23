# backend/routers/users.py
from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import Annotated, List # List import et
from bson import ObjectId

from database import get_db_dependency
from models.user_models import UserPublic, Address, AddressCreate # Gerekli modelleri import et
# Güvenlik ve dependency fonksiyonlarını import et
from utils.security import get_current_active_user, get_current_admin_user
from pydantic import BaseModel


router = APIRouter()

class PasswordChange(BaseModel):
    currentPassword: str
    newPassword: str

# Dependency Injection ile veritabanı ve kullanıcı bilgilerini al
DBDep = Annotated[AsyncIOMotorDatabase, Depends(get_db_dependency)]
CurrentUserDep = Annotated[dict, Depends(get_current_active_user)] # Aktif kullanıcıyı dict olarak alır
AdminUserDep = Annotated[dict, Depends(get_current_admin_user)] # Aktif admin kullanıcıyı dict olarak alır

@router.get("/me", response_model=UserPublic)
async def read_users_me(current_user: CurrentUserDep):
    """
    Mevcut giriş yapmış kullanıcının profil bilgilerini döndürür.
    Token gerektirir.
    """
    # Dependency zaten kullanıcıyı getirdiği için direkt döndürebiliriz
    # Modeli doğrulamak için Pydantic modelini kullan
    return UserPublic.model_validate(current_user)

@router.put("/me/password", status_code=status.HTTP_200_OK)
async def change_my_password(passwords: PasswordChange, current_user: CurrentUserDep, db: DBDep):
    """Mevcut kullanıcının şifresini değiştirir."""
    users_collection = db["users"]
    
    # Kullanıcı kimliğini güvenli bir şekilde al
    user_id = current_user.get("id") or current_user.get("_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Kullanıcı kimliği alınamadı."
        )
    
    # Kullanıcıyı veritabanından getir
    user = await users_collection.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kullanıcı bulunamadı."
        )
    
    # Mevcut şifreyi doğrula
    if not verify_password(passwords.currentPassword, user.get("hashed_password")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mevcut şifre yanlış."
        )
    
    # Yeni şifre uzunluğunu kontrol et
    if len(passwords.newPassword) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Yeni şifre en az 6 karakter olmalıdır."
        )
    
    # Yeni şifreyi hashle
    hashed_password = get_password_hash(passwords.newPassword)
    
    # Şifreyi güncelle
    await users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {
            "hashed_password": hashed_password,
            "updatedAt": datetime.now(timezone.utc)
        }}
    )
    
    return {"message": "Şifreniz başarıyla değiştirildi."}