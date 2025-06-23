# backend/routers/favorites.py
from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import Annotated
from bson import ObjectId
from datetime import datetime, timezone

from database import get_db_dependency
from models.favorites_models import FavoriteItemCreate, FavoriteList, FavoriteItem
from utils.security import get_current_active_user

router = APIRouter()

# Dependency Injection
DBDep = Annotated[AsyncIOMotorDatabase, Depends(get_db_dependency)]
CurrentUserDep = Annotated[dict, Depends(get_current_active_user)]

@router.get("", response_model=FavoriteList)
async def get_favorites(current_user: CurrentUserDep, db: DBDep):
    """
    Kullanıcının favori ürünlerini getirir.
    """
    user_id = current_user.get("_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Kullanıcı kimliği alınamadı."
        )

    favorites_collection = db["favorites"]
    products_collection = db["products"]
    
    # Kullanıcının favori ürünlerini bul
    favorites_cursor = favorites_collection.find({"userId": ObjectId(user_id)})
    favorites_list = await favorites_cursor.to_list(length=100)
    
    # Favori ürün yoksa boş liste döndür
    if not favorites_list:
        return FavoriteList(favorites=[])
    
    # Her favori için ürün detaylarını getir
    for favorite in favorites_list:
        if "productId" in favorite:
            product = await products_collection.find_one({"_id": favorite["productId"]})
            if product:
                # Ürün varsa, özet ürün bilgilerini ekle
                favorite["product"] = {
                    "id": str(product["_id"]),
                    "name": product["name"],
                    "slug": product["slug"],
                    "price": product["price"],
                    "salePrice": product.get("salePrice"),
                    "image": product["images"][0]["url"] if product.get("images") and len(product["images"]) > 0 else None,
                    "inStock": sum(variant["stock"] for variant in product.get("variants", [])) > 0 if product.get("variants") else True
                }
    
    return FavoriteList(favorites=favorites_list)

@router.post("", status_code=status.HTTP_201_CREATED)
async def add_to_favorites(favorite: FavoriteItemCreate, current_user: CurrentUserDep, db: DBDep):
    """
    Ürünü favorilere ekler.
    """
    user_id = current_user.get("_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Kullanıcı kimliği alınamadı."
        )
    
    favorites_collection = db["favorites"]
    products_collection = db["products"]
    
    # Ürünün var olup olmadığını kontrol et
    product_id = favorite.productId
    product = await products_collection.find_one({"_id": ObjectId(product_id)})
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ürün bulunamadı."
        )
    
    # Kullanıcının bu ürünü önceden favorilere ekleyip eklemediğini kontrol et
    existing_favorite = await favorites_collection.find_one({
        "userId": ObjectId(user_id),
        "productId": ObjectId(product_id)
    })
    
    if existing_favorite:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bu ürün zaten favorilerinizde."
        )
    
    # Yeni favori oluştur
    new_favorite = {
        "userId": ObjectId(user_id),
        "productId": ObjectId(product_id),
        "createdAt": datetime.now(timezone.utc)
    }
    
    # Veri tabanına ekle
    result = await favorites_collection.insert_one(new_favorite)
    
    # Eklenen favoriyi döndür
    created_favorite = await favorites_collection.find_one({"_id": result.inserted_id})
    
    return {"message": "Ürün favorilere eklendi.", "id": str(result.inserted_id)}

@router.delete("/{favorite_id}")
async def remove_from_favorites(favorite_id: str, current_user: CurrentUserDep, db: DBDep):
    """
    Ürünü favorilerden çıkarır.
    """
    user_id = current_user.get("_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Kullanıcı kimliği alınamadı."
        )
    
    favorites_collection = db["favorites"]
    
    # Favori öğesini bul
    try:
        favorite = await favorites_collection.find_one({
            "_id": ObjectId(favorite_id),
            "userId": ObjectId(user_id)
        })
    except:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Geçersiz favori kimliği."
        )
    
    if not favorite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Favori bulunamadı veya sizin değil."
        )
    
    # Favori öğesini sil
    result = await favorites_collection.delete_one({"_id": ObjectId(favorite_id)})
    
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Favori silinirken bir hata oluştu."
        )
    
    return {"message": "Ürün favorilerden çıkarıldı."} 