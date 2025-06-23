# backend/models/token_models.py
from pydantic import BaseModel
from typing import Optional

# Token Yanıt Modeli
class Token(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str
    expires_in: Optional[int] = None

# Token Payload Modeli (JWT içindeki veri)
class TokenData(BaseModel):
    id: Optional[str] = None # Kullanıcı ID'si (veya sub)
    email: Optional[str] = None
    role: Optional[str] = None
    token_type: Optional[str] = None # "access" veya "refresh"

# Refresh Token İsteği
class RefreshTokenRequest(BaseModel):
    refresh_token: str