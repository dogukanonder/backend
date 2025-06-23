# backend/reset_admin.py
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from passlib.context import CryptContext
from datetime import datetime, timezone

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

async def reset_admin_password():
    # Veritabanı bağlantısı
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["dovl_db_py"]  # Database adınızı kontrol edin
    
    # Yeni şifre belirle
    new_password = "admin123"
    hashed_password = get_password_hash(new_password)
    
    print(f"Yeni şifre: {new_password}")
    print(f"Hashlenmiş: {hashed_password}")
    
    # Admin kullanıcıyı bul ve şifreyi güncelle
    result = await db.users.update_one(
        {"role": "admin"},
        {"$set": {
            "hashed_password": hashed_password,
            "updatedAt": datetime.now(timezone.utc)
        }}
    )
    
    if result.modified_count > 0:
        print(f"✅ Admin şifresi '{new_password}' olarak güncellendi")
        
        # Admin kullanıcının email'ini de göster
        admin = await db.users.find_one({"role": "admin"})
        if admin:
            print(f"Email: {admin.get('email')}")
    else:
        print("❌ Admin kullanıcısı bulunamadı")
        
        # Mevcut kullanıcıları listele
        print("\nMevcut kullanıcılar:")
        async for user in db.users.find({}, {"email": 1, "role": 1}):
            print(f"- {user.get('email')} ({user.get('role')})")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(reset_admin_password())