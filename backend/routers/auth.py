# backend/routers/auth.py
from fastapi import APIRouter, Depends, HTTPException, status, Form  # Form'u ekleyin
from fastapi.security import OAuth2PasswordRequestForm
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import Annotated
from pymongo.errors import DuplicateKeyError
import pymongo
from bson import ObjectId # ObjectId'i kontrol etmek için import edebiliriz

import secrets
import string
from datetime import datetime, timedelta, timezone

from database import get_db_dependency
from models.user_models import UserCreate, UserPublic, UserLogin
from models.token_models import Token, RefreshTokenRequest
from utils.security import (
    verify_password, 
    create_access_token, 
    create_refresh_token,
    create_token_pair,
    verify_token,
    get_password_hash
)

router = APIRouter()

DBDep = Annotated[AsyncIOMotorDatabase, Depends(get_db_dependency)]

@router.post("/forgot-password")
async def forgot_password(db: DBDep, email: str = Form(...)):
    """Kullanıcıya şifre sıfırlama bağlantısı gönderir."""
    users_collection = db["users"]
    user = await users_collection.find_one({"email": email})
    
    if not user:
        # Güvenlik için kullanıcı bulunamasa bile başarılı mesajı döndür
        return {"message": "Şifre sıfırlama bağlantısı e-posta adresinize gönderildi (eğer hesap varsa)."}
    
    # Şifre sıfırlama token'ı oluştur
    reset_token = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(64))
    reset_expires = datetime.now(timezone.utc) + timedelta(hours=1)  # 1 saat geçerli
    
    # Token'ı kullanıcı belgesine kaydet
    await users_collection.update_one(
        {"_id": user["_id"]},
        {"$set": {
            "passwordResetToken": reset_token,
            "passwordResetExpires": reset_expires,
            "updatedAt": datetime.now(timezone.utc)
        }}
    )
    
    # E-posta gönderme işlemi burada olacak
    # Bu örnekte sadece token döndürüyoruz
    # Gerçek uygulamada bir e-posta servisi (SMTP) kullanılmalı
    
    # Frontend'e başarılı mesajı döndür
    return {"message": "Şifre sıfırlama bağlantısı e-posta adresinize gönderildi."}

@router.post("/reset-password")
async def reset_password(
    db: DBDep,
    token: str = Form(...),
    password: str = Form(...)
):
    """Şifre sıfırlama token'ı ile yeni şifre belirler."""
    if len(password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Şifre en az 6 karakter olmalıdır."
        )
        
    users_collection = db["users"]
    
    # Token'a sahip kullanıcıyı bul
    user = await users_collection.find_one({
        "passwordResetToken": token,
        "passwordResetExpires": {"$gt": datetime.now(timezone.utc)}  # Token süresi dolmamış olmalı
    })
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Geçersiz veya süresi dolmuş şifre sıfırlama bağlantısı."
        )
    
    # Yeni şifreyi hashle ve kullanıcıyı güncelle
    hashed_password = get_password_hash(password)
    
    await users_collection.update_one(
        {"_id": user["_id"]},
        {"$set": {
            "hashed_password": hashed_password,
            "updatedAt": datetime.now(timezone.utc)
        },
        "$unset": {
            "passwordResetToken": "",
            "passwordResetExpires": ""
        }}
    )
    
    return {"message": "Şifreniz başarıyla sıfırlandı. Şimdi giriş yapabilirsiniz."}

@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
async def register_user(user_data: UserCreate, db: DBDep):
    """Yeni kullanıcı kaydı oluşturur."""
    users_collection = db["users"]

    existing_user = await users_collection.find_one({"email": user_data.email})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bu e-posta adresi zaten kayıtlı."
        )

    hashed_password = get_password_hash(user_data.password)

    user_db_data = user_data.model_dump(exclude={"password"})
    user_db_data["hashed_password"] = hashed_password
    user_db_data["role"] = "user"
    user_db_data["isActive"] = True
    user_db_data["createdAt"] = datetime.now(timezone.utc)
    user_db_data["updatedAt"] = datetime.now(timezone.utc)
    user_db_data["addresses"] = []
    user_db_data["wishlist"] = []
    user_db_data["orderHistory"] = []
    user_db_data["usedCampaigns"] = []


    try:
        result = await users_collection.insert_one(user_db_data)
        # Veritabanından kullanıcıyı tekrar çek
        created_user_raw = await users_collection.find_one({"_id": result.inserted_id})

        if not created_user_raw:
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Kullanıcı kaydedildi ancak getirilemedi.")

        # ----- Pydantic Doğrulama Hatası İçin Düzeltme -----
        # Pydantic modeline göndermeden önce _id'yi string'e çevir
        created_user_for_validation = created_user_raw.copy() # Orijinal dict'i bozmamak için kopyala
        if '_id' in created_user_for_validation and isinstance(created_user_for_validation['_id'], ObjectId):
            created_user_for_validation['_id'] = str(created_user_for_validation['_id'])
        # ----- Düzeltme Sonu -----

        # Düzenlenmiş dict ile modeli doğrula
        return UserPublic.model_validate(created_user_for_validation) # `model_validate` kullanıyoruz

    except DuplicateKeyError:
         raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bu e-posta adresi zaten kayıtlı."
        )
    except Exception as e:
        print(f"Kayıt hatası: {e}") # Genel hatayı logla
        # Pydantic ValidationError hatasını da yakalayabiliriz ama şimdilik genel hata
        if "validation error" in str(e).lower(): # Basit kontrol
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Veri doğrulama hatası: {e}")
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Kullanıcı kaydı sırasında bir sunucu hatası oluştu."
            )


@router.post("/login", response_model=Token)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DBDep
):
    """Kullanıcı girişi yapar ve access token döndürür."""
    users_collection = db["users"]
    user = await users_collection.find_one({"email": form_data.username})

    # ----- bcrypt/AttributeError Hatası İçin Kontrol -----
    # verify_password fonksiyonu içinde bir sorun varsa burada hata alabiliriz
    # Bu genellikle bcrypt kütüphanesinin doğru kurulmamasından kaynaklanır
    try:
        password_field = user.get("hashed_password") if user else None
        if not user or not password_field or not verify_password(form_data.password, password_field):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="E-posta veya şifre hatalı.",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except AttributeError as ae:
        if "'bcrypt'" in str(ae): # Bcrypt hatasıysa daha açıklayıcı log
             print("\n\n *** Bcrypt/Passlib Hatası: 'bcrypt' modülü ile ilgili bir sorun var. 'pip install bcrypt' komutunu çalıştırdınız mı? ***\n\n")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Şifre doğrulama sırasında bir hata oluştu."
        )
    # ----- Kontrol Sonu -----


    if not user.get("isActive", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Hesabınız askıya alınmış.",
        )

    # Token payload'unu hazırla
    token_payload = {
        "sub": str(user["_id"]),
        "id": str(user["_id"]),
        "email": user["email"],
        "role": user["role"]
    }
    
    # Hem access hem de refresh token oluştur
    access_token, refresh_token, expires_in = create_token_pair(token_payload)

    try:
        # Kullanıcı belgesine refresh token'ı ekle
        await users_collection.update_one(
            {"_id": user["_id"]},
            {"$set": {
                "lastLogin": datetime.now(timezone.utc),
                "refreshToken": refresh_token
            }}
        )
    except Exception as e:
        print(f"Giriş bilgileri güncellenirken hata (kullanıcı: {user['email']}): {e}")

    # Token yanıtı
    return {
        "access_token": access_token, 
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": expires_in
    }

@router.post("/refresh", response_model=Token)
async def refresh_token_endpoint(
    refresh_data: RefreshTokenRequest,
    db: DBDep
):
    """Refresh token ile yeni access token oluşturur."""
    try:
        # Refresh token'ı doğrula
        token_data = verify_token(refresh_data.refresh_token, token_type="refresh")
        
        # Veritabanında refresh token kontrolü yap
        users_collection = db["users"]
        user = await users_collection.find_one({
            "_id": ObjectId(token_data.id),
            "refreshToken": refresh_data.refresh_token
        })
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Geçersiz refresh token.",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        if not user.get("isActive", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Hesabınız askıya alınmış.",
            )
            
        # Yeni token payload'ı
        token_payload = {
            "sub": str(user["_id"]),
            "id": str(user["_id"]),
            "email": user["email"],
            "role": user["role"]
        }
        
        # Yeni token çifti oluştur
        access_token, refresh_token, expires_in = create_token_pair(token_payload)
        
        # Veritabanında yeni refresh token'ı güncelle
        await users_collection.update_one(
            {"_id": user["_id"]},
            {"$set": {"refreshToken": refresh_token}}
        )
        
        # Yeni token çiftini döndür
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": expires_in
        }
        
    except HTTPException:
        # verify_token'dan gelen hataları tekrar fırlat
        raise
    except Exception as e:
        print(f"Refresh token hatası: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token işlemi başarısız.",
            headers={"WWW-Authenticate": "Bearer"},
        )

@router.post("/logout")
async def logout(
    refresh_data: RefreshTokenRequest,
    db: DBDep
):
    """Kullanıcı çıkış yapar ve refresh token'ı geçersizleştirir."""
    try:
        # Refresh token'ı doğrula
        token_data = verify_token(refresh_data.refresh_token, token_type="refresh")
        
        # Veritabanında refresh token'ı temizle
        users_collection = db["users"]
        await users_collection.update_one(
            {"_id": ObjectId(token_data.id)},
            {"$unset": {"refreshToken": ""}}
        )
        
        return {"message": "Başarıyla çıkış yapıldı."}
    except:
        # Hata olsa da başarılı döndür (silent fail for security)
        return {"message": "Başarıyla çıkış yapıldı."}