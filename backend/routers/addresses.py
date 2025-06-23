# backend/routers/addresses.py
from fastapi import APIRouter, Depends, HTTPException, status, Body
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import Annotated, List
from bson import ObjectId
from datetime import datetime, timezone

from database import get_db_dependency
from models.user_models import Address, AddressCreate
from utils.security import get_current_active_user

router = APIRouter()

# Dependency Injection
DBDep = Annotated[AsyncIOMotorDatabase, Depends(get_db_dependency)]
CurrentUserDep = Annotated[dict, Depends(get_current_active_user)]

@router.get("", response_model=List[Address])
async def get_addresses(current_user: CurrentUserDep, db: DBDep):
    """
    Kullanıcının adreslerini getirir.
    """
    user_id = current_user.get("_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Kullanıcı kimliği alınamadı."
        )
    
    # Kullanıcı bilgilerini ve adreslerini getir
    users_collection = db["users"]
    user = await users_collection.find_one({"_id": ObjectId(user_id)})
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kullanıcı bulunamadı."
        )
    
    # Kullanıcının adresleri yoksa boş liste döndür
    if "addresses" not in user or not user["addresses"]:
        return []
    
    # Adresleri ID'leri ile birlikte döndür
    addresses = user["addresses"]
    for address in addresses:
        if "_id" not in address:
            address["_id"] = str(ObjectId())
        elif isinstance(address["_id"], ObjectId):  # ObjectId türündeki değerleri string'e dönüştür
            address["_id"] = str(address["_id"])
    
    return addresses

@router.post("", status_code=status.HTTP_201_CREATED)
async def add_address(address: AddressCreate, current_user: CurrentUserDep, db: DBDep):
    """
    Kullanıcıya yeni adres ekler.
    """
    user_id = current_user.get("_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Kullanıcı kimliği alınamadı."
        )
    
    users_collection = db["users"]
    
    # Adres verilerini hazırla
    address_data = address.model_dump()
    address_data["_id"] = ObjectId()  # Adres için ObjectId oluştur
    address_data["createdAt"] = datetime.now(timezone.utc)
    address_data["updatedAt"] = datetime.now(timezone.utc)
    
    # Kullanıcıyı getir
    user = await users_collection.find_one({"_id": ObjectId(user_id)})
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kullanıcı bulunamadı."
        )
    
    # Kullanıcı adreslerini kontrol et, yoksa dizi oluştur
    if "addresses" not in user:
        user["addresses"] = []
    
    # Varsayılan adres ayarlarını kontrol et
    if address.isDefaultShipping:
        # Diğer varsayılan teslimat adreslerini güncelle
        for existing_address in user["addresses"]:
            if existing_address.get("isDefaultShipping"):
                existing_address["isDefaultShipping"] = False
    
    if address.isDefaultBilling:
        # Diğer varsayılan fatura adreslerini güncelle
        for existing_address in user["addresses"]:
            if existing_address.get("isDefaultBilling"):
                existing_address["isDefaultBilling"] = False
    
    # Adresi kullanıcının adresler listesine ekle
    user["addresses"].append(address_data)
    
    # Kullanıcı verisini güncelle
    result = await users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"addresses": user["addresses"], "updatedAt": datetime.now(timezone.utc)}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Adres eklenirken bir hata oluştu."
        )
    
    return {"message": "Adres başarıyla eklendi.", "id": str(address_data["_id"])}

@router.put("/{address_id}")
async def update_address(
    address_id: str,
    address_update: AddressCreate,
    current_user: CurrentUserDep,
    db: DBDep
):
    """
    Kullanıcının belirli bir adresini günceller.
    """
    user_id = current_user.get("_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Kullanıcı kimliği alınamadı."
        )
    
    users_collection = db["users"]
    
    # Kullanıcıyı getir
    user = await users_collection.find_one({"_id": ObjectId(user_id)})
    
    if not user or "addresses" not in user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kullanıcı veya adresler bulunamadı."
        )
    
    # Güncellenecek adresi bul
    address_index = None
    for i, addr in enumerate(user["addresses"]):
        if str(addr.get("_id")) == address_id:
            address_index = i
            break
    
    if address_index is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Belirtilen adres bulunamadı."
        )
    
    # Güncellenecek adresi al
    address_to_update = user["addresses"][address_index]
    
    # Güncellenecek verileri hazırla
    update_data = address_update.model_dump()
    update_data["_id"] = address_to_update["_id"]  # ID'yi koru
    update_data["updatedAt"] = datetime.now(timezone.utc)
    
    # Varsayılan teslimat adresi değişiyorsa
    if update_data.get("isDefaultShipping") and not address_to_update.get("isDefaultShipping"):
        # Diğer varsayılan teslimat adreslerini güncelle
        for addr in user["addresses"]:
            if addr.get("isDefaultShipping") and str(addr.get("_id")) != address_id:
                addr["isDefaultShipping"] = False
    
    # Varsayılan fatura adresi değişiyorsa
    if update_data.get("isDefaultBilling") and not address_to_update.get("isDefaultBilling"):
        # Diğer varsayılan fatura adreslerini güncelle
        for addr in user["addresses"]:
            if addr.get("isDefaultBilling") and str(addr.get("_id")) != address_id:
                addr["isDefaultBilling"] = False
    
    # Eski adresi yenisiyle değiştir
    user["addresses"][address_index] = update_data
    
    # Kullanıcı verisini güncelle
    result = await users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"addresses": user["addresses"], "updatedAt": datetime.now(timezone.utc)}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Adres güncellenirken bir hata oluştu."
        )
    
    return {"message": "Adres başarıyla güncellendi."}

@router.delete("/{address_id}")
async def delete_address(address_id: str, current_user: CurrentUserDep, db: DBDep):
    """
    Kullanıcının belirli bir adresini siler.
    """
    user_id = current_user.get("_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Kullanıcı kimliği alınamadı."
        )
    
    users_collection = db["users"]
    
    # Kullanıcıyı getir
    user = await users_collection.find_one({"_id": ObjectId(user_id)})
    
    if not user or "addresses" not in user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kullanıcı veya adresler bulunamadı."
        )
    
    # Silinecek adresi bul
    address_found = False
    new_addresses = []
    for addr in user["addresses"]:
        if str(addr.get("_id")) == address_id:
            address_found = True
        else:
            new_addresses.append(addr)
    
    if not address_found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Belirtilen adres bulunamadı."
        )
    
    # Kullanıcı verisini güncelle
    result = await users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"addresses": new_addresses, "updatedAt": datetime.now(timezone.utc)}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Adres silinirken bir hata oluştu."
        )
    
    return {"message": "Adres başarıyla silindi."}

@router.put("/{address_id}/default", status_code=status.HTTP_200_OK)
async def set_default_address(
    address_id: str,
    current_user: CurrentUserDep,
    db: DBDep,
    type_data: dict = Body(..., example={"type": "shipping"})
):
    """
    Belirli bir adresi varsayılan olarak ayarlar.
    Tip olarak "shipping", "billing" veya "both" değerleri kabul edilir.
    """
    user_id = current_user.get("_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Kullanıcı kimliği alınamadı."
        )
    
    users_collection = db["users"]
    
    # Adres tipini kontrol et
    address_type = type_data.get("type", "").lower()
    if address_type not in ["shipping", "billing", "both"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Geçersiz adres tipi. "shipping", "billing" veya "both" olmalıdır.'
        )
    
    # Kullanıcıyı getir
    user = await users_collection.find_one({"_id": ObjectId(user_id)})
    
    if not user or "addresses" not in user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kullanıcı veya adresler bulunamadı."
        )
    
    # Varsayılan yapılacak adresi bul
    address_found = False
    for addr in user["addresses"]:
        if str(addr.get("_id")) == address_id:
            address_found = True
            # Adres tipine göre varsayılan ayarla
            if address_type in ["shipping", "both"]:
                addr["isDefaultShipping"] = True
            if address_type in ["billing", "both"]:
                addr["isDefaultBilling"] = True
        else:
            # Diğer adresleri varsayılan değil olarak ayarla
            if address_type in ["shipping", "both"]:
                addr["isDefaultShipping"] = False
            if address_type in ["billing", "both"]:
                addr["isDefaultBilling"] = False
    
    if not address_found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Belirtilen adres bulunamadı."
        )
    
    # Kullanıcı verisini güncelle
    result = await users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"addresses": user["addresses"], "updatedAt": datetime.now(timezone.utc)}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Varsayılan adres ayarlanırken bir hata oluştu."
        )
    
    return {"message": "Varsayılan adres başarıyla ayarlandı."} 