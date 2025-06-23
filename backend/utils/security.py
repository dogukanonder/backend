# backend/utils/security.py
from passlib.context import CryptContext
from datetime import datetime, timedelta, timezone
from typing import Optional, Annotated, Tuple # Tuple eklendi
import jwt # python-jose kütüphanesinden
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId # ObjectId import et

from config import settings # Ayarları config dosyasından al
from database import get_db_dependency # Veritabanı dependency'si
from models.token_models import TokenData # Token payload modeli
from models.user_models import UserPublic # Kullanıcı response modeli (opsiyonel)

# Şifreleme context'i (bcrypt kullanıyoruz)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = settings.ALGORITHM
JWT_SECRET = settings.JWT_SECRET
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES
REFRESH_TOKEN_EXPIRE_DAYS = settings.REFRESH_TOKEN_EXPIRE_DAYS

# OAuth2 şeması: Token'ın header'dan nasıl alınacağını belirtir
# tokenUrl, Swagger UI'da login olanağı sağlar (login endpoint'imizin yolu)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login") # Login endpoint yolu

# --- Var olan fonksiyonlar ---
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Girilen şifre ile hashlenmiş şifreyi doğrular."""
    # Hashed password yoksa direkt false dön (güvenlik)
    if not hashed_password:
        return False
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as e:
        # Hata durumunda logla ve false dön
        print(f"Password verification error: {e}")
        return False


def get_password_hash(password: str) -> str:
    """Girilen şifreyi hashler."""
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """JWT access token oluşturur."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire, "token_type": "access"})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token(data: dict) -> str:
    """JWT refresh token oluşturur."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    
    to_encode.update({
        "exp": expire, 
        "token_type": "refresh", 
        # Sadece refresh için gerekli alanları tut, hassas verileri temizle
        "role": None if "role" in to_encode else to_encode.get("role")
    })
    
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)
    return encoded_jwt

def create_token_pair(data: dict) -> Tuple[str, str, int]:
    """Hem access hem de refresh token oluşturur ve döndürür."""
    access_token = create_access_token(data)
    refresh_token = create_refresh_token(data)
    
    # Token süresini de döndür
    expires_in = ACCESS_TOKEN_EXPIRE_MINUTES * 60
    
    return access_token, refresh_token, expires_in

def verify_token(token: str, token_type: Optional[str] = None) -> TokenData:
    """Token'ın geçerliliğini doğrular ve payload döndürür."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Kimlik bilgileri doğrulanamadı",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub") or payload.get("id") # 'sub' veya 'id' alanını al
        
        # Token tipini kontrol et (eğer belirtilmişse)
        if token_type and payload.get("token_type") != token_type:
            print(f"Yanlış token tipi. Beklenen: {token_type}, Gelen: {payload.get('token_type')}")
            raise credentials_exception
            
        if user_id is None:
            print("Token payload içinde 'sub' veya 'id' bulunamadı:", payload)
            raise credentials_exception
            
        # TokenData modeli ile payload'u doğrula
        token_data = TokenData(
            id=user_id, 
            email=payload.get("email"), 
            role=payload.get("role"),
            token_type=payload.get("token_type")
        )
        return token_data
        
    except jwt.ExpiredSignatureError:
        print("Token süresi dolmuş.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Oturum süresi dolmuş, lütfen tekrar giriş yapın.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.JWTError as e:
        print(f"JWT Hatası: {e}")
        raise credentials_exception
    except Exception as e: # Beklenmedik hatalar için
        print(f"Token doğrulama sırasında beklenmedik hata: {e}")
        raise credentials_exception

# --- YENİ FONKSİYONLAR ---

async def get_current_user_payload(
    token: Annotated[str, Depends(oauth2_scheme)]
) -> TokenData:
    """
    Token'ı doğrular ve içindeki payload'u döndürür.
    Hata durumunda HTTPException fırlatır.
    """
    return verify_token(token, token_type="access")


async def get_current_active_user(
    token_data: Annotated[TokenData, Depends(get_current_user_payload)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db_dependency)]
) -> dict: # dict döndürdüğümüzü belirtelim
    """
    Doğrulanmış token payload'undan kullanıcıyı veritabanından bulur
    ve aktif olup olmadığını kontrol eder. Kullanıcı verisini dict olarak döndürür.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Kimlik bilgileri doğrulanamadı (kullanıcı bulunamadı/aktif değil)",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token_data.id or not ObjectId.is_valid(token_data.id):
         print(f"Geçersiz kullanıcı ID: {token_data.id}")
         raise credentials_exception

    users_collection = db["users"]
    user = await users_collection.find_one({"_id": ObjectId(token_data.id)})

    if user is None:
        print(f"Kullanıcı bulunamadı: ID {token_data.id}")
        raise credentials_exception

    if not user.get("isActive", False):
         print(f"Kullanıcı aktif değil: {user.get('email')}")
         raise HTTPException(
             status_code=status.HTTP_400_BAD_REQUEST,
             detail="Aktif olmayan kullanıcı."
         )

    # Hassas bilgileri döndürmeden önce temizleyebiliriz veya UserPublic kullanabiliriz
    # Şimdilik dict olarak döndürelim, Pydantic modeli yanıt modelinde kullanılacak
    user["_id"] = str(user["_id"]) # ID'yi string'e çevir
    user.pop("hashed_password", None) # Şifreyi kaldır
    user.pop("passwordResetToken", None)
    user.pop("passwordResetExpires", None)
    user.pop("refreshToken", None) # Refresh token bilgisini de kaldır
    # Adreslerin ID'lerini de string'e çevirelim
    if "addresses" in user and isinstance(user["addresses"], list):
        for address in user["addresses"]:
            if "_id" in address and isinstance(address["_id"], ObjectId):
                address["_id"] = str(address["_id"])


    return user # Ham dictionary döndür

# Sadece admin yetkisi olan endpointler için dependency
async def get_current_admin_user(
    current_user: Annotated[dict, Depends(get_current_active_user)]
) -> dict:
    """Kullanıcının admin olup olmadığını kontrol eder."""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu işlemi yapmak için yetkiniz yok."
        )
    return current_user