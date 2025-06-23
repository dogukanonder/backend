# backend/main.py
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from database import connect_to_mongo, close_mongo_connection, get_database
from config import settings # settings import edildi
from pymongo.errors import ConnectionFailure
import time
import os
import random
from bson import ObjectId
import pymongo
import traceback # Geliştirme için traceback
from routers.admin_dashboard import router as admin_dashboard_router
from fastapi.staticfiles import StaticFiles
import os


# --- Rotaları Import Etme ---
from routers import auth, users, products, categories, orders, campaigns, cart, favorites, addresses

# Ömür Döngüsü Yöneticisi
@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongo()
    yield
    await close_mongo_connection()

# FastAPI Uygulaması
app = FastAPI(
    title="DOVL E-Ticaret API",
    description="Dovl markası için Python FastAPI tabanlı e-ticaret API'si.",
    version="0.1.0",
    lifespan=lifespan
)

os.makedirs("static/uploads/products", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# CORS Middleware
# Property adını allowed_origins_list olarak değiştirdik
if settings.allowed_origins_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list, # <<< Değişiklik burada
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
     print("UYARI: ALLOWED_ORIGINS_STR ayarlanmamış veya boş. CORS Middleware devre dışı.")

# Genel Hata Yakalayıcı
@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    print(f"Beklenmedik Hata: {exc} - İstek: {request.method} {request.url}")
    detail = "Sunucu hatası oluştu."
    status_code = 500
    if isinstance(exc, HTTPException):
        status_code = exc.status_code
        detail = exc.detail
        return JSONResponse(status_code=status_code, content={"error": detail})

    # Geliştirme ortamında daha fazla detay göster
    # Python'da NODE_ENV yerine başka bir değişken kullanılabilir veya basit kontrol
    # if os.getenv("FASTAPI_ENV") == "development":
    #     detail = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"

    return JSONResponse(
        status_code=status_code,
        content={"error": "Internal Server Error", "detail": detail},
    )

# Basit Kök Endpoint
@app.get("/", tags=["Root"])
async def read_root():
    db = get_database()
    db_status = "Bilinmiyor"
    start_time = time.time()
    try:
        await db.command('ping')
        db_status = "Bağlantı Başarılı"
    except ConnectionFailure:
         db_status = "Bağlantı Başarısız (ConnectionFailure)"
    except Exception as e:
        db_status = f"Bağlantı Hatası ({type(e).__name__})"
    finally:
        duration = time.time() - start_time

    return {
        "message": "DOVL API'ye hoş geldiniz!",
        "database_status": db_status,
        "db_ping_ms": round(duration * 1000, 2),
        "docs_url": "/docs",
        "version": app.version
    }

# --- Rotaları (Router) Dahil Etme ---
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(users.router, prefix="/users", tags=["Users"])
app.include_router(products.router, prefix="/products", tags=["Products"])
app.include_router(categories.router, prefix="/categories", tags=["Categories"])
app.include_router(orders.router, prefix="/orders", tags=["Orders"])
app.include_router(campaigns.router, prefix="/campaigns", tags=["Campaigns"])
app.include_router(cart.router, prefix="/cart", tags=["Shopping Cart"])
app.include_router(favorites.router, prefix="/favorites", tags=["Favorites"])
app.include_router(addresses.router, prefix="/addresses", tags=["Addresses"])
app.include_router(admin_dashboard_router, prefix="/admin/dashboard", tags=["Admin Dashboard"])


# Bilgilendirme Logları
print("="*50)
print(f"DOVL API v{app.version} Başlatılıyor...")
# print(f"Ortam: {os.getenv('NODE_ENV', 'development')}")
print(f"MongoDB URI: {settings.MONGO_URI[:15]}...{settings.MONGO_URI[-10:]}")
print(f"Veritabanı Adı: {settings.DB_NAME}")
print(f"JWT Secret: {'Ayarlı' if settings.JWT_SECRET != 'default_secret' else 'Varsayılan!'}")
print(f"İzin Verilen Originler: {settings.allowed_origins_list}") # <<< Değişiklik burada
port = os.getenv("PORT", 8000)
print(f"API Dokümantasyonu: http://localhost:{port}/docs")
print("="*50)