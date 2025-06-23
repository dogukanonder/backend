# backend/config.py
import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv
from typing import List

load_dotenv()

class Settings(BaseSettings):
    MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    DB_NAME: str = os.getenv("DB_NAME", "dovl_db_py")
    # Test veritabanı ayarları
    TEST_MONGO_URI: str = os.getenv("TEST_MONGO_URI", "mongodb://localhost:27017")
    TEST_DB_NAME: str = os.getenv("TEST_DB_NAME", "dovl_test_db")

    JWT_SECRET: str = os.getenv("JWT_SECRET", "default_secret")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60 * 24 * 7))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", 30))
    ALLOWED_ORIGINS_STR: str = os.getenv("ALLOWED_ORIGINS_STR", "http://localhost:3000,https://ds-shop-nine.vercel.app,https://ds-shop.onrender.com")
    TAX: int = int(os.getenv("TAX", 18))
    FREE_SHIPPING_THRESHOLD: float = float(os.getenv("FREE_SHIPPING_THRESHOLD", 300.0))
    SHIPPING_COST: float = float(os.getenv("SHIPPING_COST", 29.90))

    @property
    def allowed_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS_STR.split(',') if origin.strip()]

    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'

settings = Settings()

if settings.JWT_SECRET == "default_secret":
    print("\n\nUYARI: Varsayılan JWT_SECRET kullanılıyor! Lütfen .env dosyasını ayarlayın.\n\n")

# Test ortamında olup olmadığımızı belirlemek için bir flag
# Bu, pytest tarafından ayarlanabilir veya başka bir ortam değişkeni ile yapılabilir.
# Şimdilik basit bir kontrol yapalım: Eğer TEST_DB_NAME farklıysa test ortamı kabul edelim.
# Daha iyisi: pytest.ini veya ortam değişkeni kullanmak.
IS_TESTING: bool = False
print(f"Test Ortamı Aktif mi: {IS_TESTING}")