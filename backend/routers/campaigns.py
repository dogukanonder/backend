# backend/routers/campaigns.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import Annotated, List, Optional
from bson import ObjectId
from slugify import slugify
from datetime import datetime, timezone
import pymongo
import random

from database import get_db_dependency
# Gerekli modelleri import et
from models.campaign_models import (
    CampaignCreate, CampaignUpdate, Campaign, CampaignListResponse,
    CampaignDetailResponse, PyObjectId, CampaignCheckResponse
)
from models.token_models import TokenData
from models.user_models import UserPublic # Kullanıcı modeli (opsiyonel)
from models.product_models import Product as ProductModel # Ürün modeli (opsiyonel)
from models.cart_models import ApplyCampaignRequest # <<< ApplyCampaignRequest import edildi
# Güvenlik fonksiyonları
from utils.security import get_current_admin_user, get_current_user_payload

router = APIRouter()
DBDep = Annotated[AsyncIOMotorDatabase, Depends(get_db_dependency)]
AdminDep = Annotated[dict, Depends(get_current_admin_user)]

# Opsiyonel Kullanıcı Dependency
async def get_optional_current_user(
     # Token payload'unu isteğe bağlı olarak alır
     # get_current_user_payload hata fırlatırsa None dönmez,
     # bu yüzden try-except kullanmak daha doğru olabilir veya
     # security.py'de hata fırlatmayan bir versiyonu yazılabilir.
     # Şimdilik bu şekilde bırakalım, hata olursa 401 dönecektir.
     # VEYA: oauth2_scheme'i optional yapabiliriz
     token_payload: Optional[TokenData] = Depends(get_current_user_payload)
 ) -> Optional[dict]:
     if not token_payload:
         return None
     return {"id": token_payload.id, "email": token_payload.email, "role": token_payload.role}

OptionalUserDep = Annotated[Optional[dict], Depends(get_optional_current_user)]


@router.post("/", response_model=CampaignDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_campaign(campaign_data: CampaignCreate, db: DBDep, admin_user: AdminDep):
    # ... (kod önceki gibi) ...
    """Yeni kampanya oluşturur (Sadece Admin)."""
    campaigns_collection = db["campaigns"]

    # Kod kontrolü ve oluşturma
    if campaign_data.code:
        campaign_data.code = campaign_data.code.upper().strip()
        if not campaign_data.code:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Kampanya kodu boş olamaz.")
        existing = await campaigns_collection.find_one({"code": campaign_data.code})
        if existing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bu kampanya kodu zaten kullanılıyor.")
    else:
        is_unique = False
        generated_code = "" # Tanımla
        while not is_unique:
            generated_code = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=8))
            existing = await campaigns_collection.find_one({"code": generated_code})
            if not existing:
                is_unique = True
        campaign_data.code = generated_code


    # Tarihleri UTC yap
    now = datetime.now(timezone.utc)
    # Tarihlerin None olup olmadığını kontrol et
    start_date = campaign_data.startDate
    end_date = campaign_data.endDate

    if start_date:
        campaign_data.startDate = start_date.replace(tzinfo=timezone.utc) if start_date.tzinfo is None else start_date.astimezone(timezone.utc)
    else:
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Başlangıç tarihi gereklidir.")

    if end_date:
        campaign_data.endDate = end_date.replace(tzinfo=timezone.utc) if end_date.tzinfo is None else end_date.astimezone(timezone.utc)
    else:
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bitiş tarihi gereklidir.")


    campaign_dict = campaign_data.model_dump()
    campaign_dict["usageCount"] = 0
    campaign_dict["createdAt"] = now
    campaign_dict["updatedAt"] = now

    # ObjectId listelerini işle (varsa)
    for field in ["categories", "products", "excludedCategories", "excludedProducts"]:
         if field in campaign_dict and isinstance(campaign_dict[field], list):
             # Gelen ID'lerin geçerli ObjectId olduğundan emin ol
             try:
                campaign_dict[field] = [ObjectId(id_val) for id_val in campaign_dict[field]]
             except Exception:
                 raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"'{field}' alanındaki ID'ler geçersiz.")

    try:
        result = await campaigns_collection.insert_one(campaign_dict)
        created_campaign_raw = await campaigns_collection.find_one({"_id": result.inserted_id})

        if not created_campaign_raw:
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Kampanya oluşturuldu ancak getirilemedi.")

        # ObjectId'leri string'e çevir
        created_campaign_raw['_id'] = str(created_campaign_raw['_id'])
        for field in ["categories", "products", "excludedCategories", "excludedProducts"]:
            if field in created_campaign_raw and isinstance(created_campaign_raw[field], list):
                created_campaign_raw[field] = [str(oid) for oid in created_campaign_raw[field]]


        return CampaignDetailResponse(data=Campaign.model_validate(created_campaign_raw))

    except Exception as e:
        print(f"Kampanya oluşturma hatası: {e}")
        if "duplicate key" in str(e).lower():
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bu kampanya kodu zaten kullanılıyor.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Kampanya oluşturulamadı: {e}")

@router.get("/", response_model=CampaignListResponse)
async def read_campaigns(
    db: DBDep,
    active_only: bool = Query(True, description="Sadece aktif ve geçerli kampanyaları göster"),
    admin_view: bool = Query(False, description="Tüm kampanyaları göster (Admin için)")
):
    # ... (kod önceki gibi) ...
    """Kampanyaları listeler."""
    campaigns_collection = db["campaigns"]
    filter_query = {}
    now = datetime.now(timezone.utc)

    if not admin_view:
        filter_query["isActive"] = True
        filter_query["startDate"] = {"$lte": now}
        filter_query["endDate"] = {"$gte": now}
        # filter_query["showInStore"] = True # Modelde varsa

    elif active_only and admin_view:
        filter_query["isActive"] = True
        # Opsiyonel olarak tarih kontrolü de eklenebilir


    try:
        campaign_cursor = campaigns_collection.find(filter_query).sort([("endDate", 1), ("createdAt", -1)])
        campaigns_raw = await campaign_cursor.to_list(length=None)

        campaigns_validated = []
        for camp_raw in campaigns_raw:
            camp_raw['_id'] = str(camp_raw['_id'])
            for field in ["categories", "products", "excludedCategories", "excludedProducts"]:
                 if field in camp_raw and isinstance(camp_raw[field], list):
                     camp_raw[field] = [str(oid) for oid in camp_raw[field]]

            campaigns_validated.append(Campaign.model_validate(camp_raw))

        return CampaignListResponse(data=campaigns_validated)
    except Exception as e:
        print(f"Kampanya listeleme hatası: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Kampanyalar listelenirken bir hata oluştu.")

@router.post("/check", response_model=CampaignCheckResponse)
async def check_campaign_code(
    # ApplyCampaignRequest import edildiği için artık hata vermemeli
    campaign_data: ApplyCampaignRequest,
    db: DBDep,
    current_user: OptionalUserDep,
    cart_total: float = Query(..., description="İndirimin uygulanacağı sepet ara toplamı")
):
    # ... (kod önceki gibi) ...
    """Verilen kampanya kodunun geçerliliğini ve uygulanabilirliğini kontrol eder."""
    campaigns_collection = db["campaigns"]
    users_collection = db["users"] # Kullanıcı kontrolü için

    code = campaign_data.code.upper().strip()
    campaign_raw = await campaigns_collection.find_one({"code": code})

    if not campaign_raw:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Geçersiz kampanya kodu.")

    # Pydantic modeline çevirerek validasyon yapabiliriz (ama ObjectId'ler sorun çıkarabilir)
    # Şimdilik dict üzerinden gidelim
    campaign = campaign_raw # Dict olarak kullan

    # Geçerlilik kontrolleri
    now = datetime.now(timezone.utc)
    if not campaign.get('isActive'): raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Kampanya aktif değil.")
    if now < campaign.get('startDate'): raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Kampanya henüz başlamadı.")
    if now > campaign.get('endDate'): raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Kampanya süresi doldu.")
    if campaign.get('maxUses') is not None and campaign.get('usageCount', 0) >= campaign.get('maxUses', float('inf')):
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Kampanya kullanım limiti doldu.")
    if cart_total < campaign.get('minPurchaseAmount', 0):
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Minimum sepet tutarı ({campaign.get('minPurchaseAmount', 0):.2f} TL) gerekli.")

    # Kullanıcıya özel kontroller (kullanıcı giriş yapmışsa)
    if current_user:
        user_id = current_user.get("id")
        if user_id and ObjectId.is_valid(user_id):
            user_doc = await users_collection.find_one({"_id": ObjectId(user_id)})
            if user_doc:
                if campaign.get('forNewCustomers') and len(user_doc.get('orderHistory', [])) > 0:
                     raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bu kampanya sadece ilk sipariş için geçerlidir.")

                usage_limit = campaign.get('usagePerCustomer', 0)
                if usage_limit > 0:
                    used_info = next((uc for uc in user_doc.get('usedCampaigns', []) if str(uc.get('campaign')) == str(campaign['_id'])), None)
                    if used_info and used_info.get('usageCount', 0) >= usage_limit:
                         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Bu kampanyayı maksimum {usage_limit} kez kullanabilirsiniz.")

    # TODO: Ürün/Kategori kontrolleri (Sepet verisi gerektirir)

    # İndirim hesapla
    discount_amount = 0
    discount_value = campaign.get('discountValue', 0)
    if campaign.get('discountType') == 'percentage':
        calculated_discount = cart_total * (discount_value / 100)
        max_discount = campaign.get('maxDiscount')
        discount_amount = min(calculated_discount, max_discount) if max_discount is not None else calculated_discount
    elif campaign.get('discountType') == 'fixed_amount':
        discount_amount = min(discount_value, cart_total) # Sepet tutarını geçemez

    # Yanıt için ObjectId'leri string'e çevir
    campaign['_id'] = str(campaign['_id'])
    for field in ["categories", "products", "excludedCategories", "excludedProducts"]:
         if field in campaign and isinstance(campaign[field], list):
             campaign[field] = [str(oid) for oid in campaign[field]]


    return CampaignCheckResponse(
        message="Kampanya kodu geçerli.",
        data={
            "campaign": Campaign.model_validate(campaign), # Doğrula ve döndür
            "discountAmount": round(discount_amount, 2)
        }
    )

@router.get("/{campaign_id}", response_model=CampaignDetailResponse)
async def read_campaign(campaign_id: str, db: DBDep):
    # ... (kod önceki gibi) ...
    """ID ile tek bir kampanyayı getirir."""
    campaigns_collection = db["campaigns"]
    if not ObjectId.is_valid(campaign_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz Kampanya ID formatı.")

    campaign_raw = await campaigns_collection.find_one({"_id": ObjectId(campaign_id)})
    if not campaign_raw:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kampanya bulunamadı.")

    campaign_raw['_id'] = str(campaign_raw['_id'])
    for field in ["categories", "products", "excludedCategories", "excludedProducts"]:
         if field in campaign_raw and isinstance(campaign_raw[field], list):
             campaign_raw[field] = [str(oid) for oid in campaign_raw[field]]

    return CampaignDetailResponse(data=Campaign.model_validate(campaign_raw))

@router.put("/{campaign_id}", response_model=CampaignDetailResponse)
async def update_campaign(campaign_id: str, campaign_data: CampaignUpdate, db: DBDep, admin_user: AdminDep):
    # ... (kod önceki gibi) ...
    """Bir kampanyayı günceller (Sadece Admin)."""
    campaigns_collection = db["campaigns"]
    if not ObjectId.is_valid(campaign_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz Kampanya ID formatı.")

    update_data = campaign_data.model_dump(exclude_unset=True)

    # Tarihleri UTC yap
    if "startDate" in update_data and update_data["startDate"]:
         update_data["startDate"] = update_data["startDate"].replace(tzinfo=timezone.utc) if update_data["startDate"].tzinfo is None else update_data["startDate"].astimezone(timezone.utc)
    if "endDate" in update_data and update_data["endDate"]:
         update_data["endDate"] = update_data["endDate"].replace(tzinfo=timezone.utc) if update_data["endDate"].tzinfo is None else update_data["endDate"].astimezone(timezone.utc)


    # ObjectId listelerini işle
    for field in ["categories", "products", "excludedCategories", "excludedProducts"]:
         if field in update_data and isinstance(update_data[field], list):
             try:
                update_data[field] = [ObjectId(id_str) for id_str in update_data[field]]
             except Exception:
                 raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"'{field}' alanındaki ID'ler geçersiz.")

    update_data["updatedAt"] = datetime.now(timezone.utc)

    updated_campaign = await campaigns_collection.find_one_and_update(
        {"_id": ObjectId(campaign_id)},
        {"$set": update_data},
        return_document=pymongo.ReturnDocument.AFTER
    )

    if not updated_campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Güncellenecek kampanya bulunamadı.")

    updated_campaign['_id'] = str(updated_campaign['_id'])
    for field in ["categories", "products", "excludedCategories", "excludedProducts"]:
         if field in updated_campaign and isinstance(updated_campaign[field], list):
             updated_campaign[field] = [str(oid) for oid in updated_campaign[field]]

    return CampaignDetailResponse(data=Campaign.model_validate(updated_campaign))

@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(campaign_id: str, db: DBDep, admin_user: AdminDep):
    # ... (kod önceki gibi) ...
    """Bir kampanyayı siler (Sadece Admin)."""
    campaigns_collection = db["campaigns"]
    if not ObjectId.is_valid(campaign_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz Kampanya ID formatı.")

    delete_result = await campaigns_collection.delete_one({"_id": ObjectId(campaign_id)})

    if delete_result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Silinecek kampanya bulunamadı.")

    return None