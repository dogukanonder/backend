# backend/database.py
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from config import settings, IS_TESTING # IS_TESTING import edildi
from typing import Optional

class Database:
    client: Optional[AsyncIOMotorClient] = None
    db: Optional[AsyncIOMotorDatabase] = None

db_instance = Database()

async def connect_to_mongo():
    """MongoDB'ye bağlanır. Test ortamı için farklı veritabanı kullanır."""
    # Kullanılacak URI ve DB adını belirle
    mongo_uri = settings.TEST_MONGO_URI if IS_TESTING else settings.MONGO_URI
    db_name = settings.TEST_DB_NAME if IS_TESTING else settings.DB_NAME

    print(f"MongoDB'ye bağlanılıyor ({'TEST' if IS_TESTING else 'NORMAL'}) -> {db_name}...")
    try:
        db_instance.client = AsyncIOMotorClient(mongo_uri, serverSelectionTimeoutMS=5000)
        await db_instance.client.admin.command('ping') # Bağlantıyı test et
        db_instance.db = db_instance.client[db_name]
        print(f"MongoDB bağlantısı başarılı: Veritabanı '{db_name}'")
    except Exception as e:
        print(f"MongoDB bağlantı hatası ({db_name}): {e}")
        db_instance.client = None
        db_instance.db = None
        raise RuntimeError(f"Database connection failed for {db_name}: {e}") # Testlerin başarısız olması için hata fırlat

async def close_mongo_connection():
    """MongoDB bağlantısını kapatır."""
    db_name = settings.TEST_DB_NAME if IS_TESTING else settings.DB_NAME
    print(f"MongoDB bağlantısı kapatılıyor ({db_name})...")
    if db_instance.client:
        db_instance.client.close()
        print(f"MongoDB bağlantısı kapatıldı ({db_name}).")
    # Test sonrası için db nesnesini sıfırla
    db_instance.client = None
    db_instance.db = None


def get_database() -> AsyncIOMotorDatabase:
    """Veritabanı nesnesini döndürür."""
    if db_instance.db is None:
        print("Hata: Veritabanı bağlantısı henüz kurulmamış veya başarısız olmuş.")
        raise RuntimeError("Database connection not established.")
    return db_instance.db

async def get_db_dependency():
    """FastAPI dependency to get database instance."""
    return get_database()