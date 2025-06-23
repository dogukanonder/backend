# backend/routers/categories.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import Annotated, List, Optional
from bson import ObjectId
from slugify import slugify
from datetime import datetime, timezone
import pymongo
import traceback

from database import get_db_dependency
from models.category_models import CategoryCreate, CategoryUpdate, Category, CategoryListResponse, PyObjectId
from utils.security import get_current_admin_user

router = APIRouter()
DBDep = Annotated[AsyncIOMotorDatabase, Depends(get_db_dependency)]
AdminDep = Annotated[dict, Depends(get_current_admin_user)]

# Helper function to create slug
def create_category_slug(name: str) -> str:
    return slugify(name, replacements=[('ı', 'i')])  # Türkçe karakter desteği

@router.post("/", response_model=Category, status_code=status.HTTP_201_CREATED)
async def create_category(category_data: CategoryCreate, db: DBDep, admin_user: AdminDep):
    """Yeni kategori oluşturur (Sadece Admin)."""
    categories_collection = db["categories"]

    try:
        # Slug kontrolü veya otomatik oluşturma
        if not category_data.slug:
            category_data.slug = create_category_slug(category_data.name)
        else:
            category_data.slug = create_category_slug(category_data.slug)

        # Slug benzersiz mi kontrol et
        existing_category = await categories_collection.find_one({"slug": category_data.slug})
        if existing_category:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bu slug zaten kullanılıyor.")

        # Üst kategori varsa ObjectId'ye çevir
        if category_data.parentCategory and isinstance(category_data.parentCategory, str):
            if not ObjectId.is_valid(category_data.parentCategory):
                 raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz Üst Kategori ID formatı.")
            category_data.parentCategory = ObjectId(category_data.parentCategory)

        category_dict = category_data.model_dump()
        now = datetime.now(timezone.utc)
        category_dict["createdAt"] = now
        category_dict["updatedAt"] = now

        result = await categories_collection.insert_one(category_dict)
        created_category_raw = await categories_collection.find_one({"_id": result.inserted_id})

        if not created_category_raw:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Kategori oluşturuldu ancak getirilemedi.")

        # ObjectId'leri string'e çevir
        created_category_raw['_id'] = str(created_category_raw['_id'])
        if 'parentCategory' in created_category_raw and created_category_raw['parentCategory']:
            if isinstance(created_category_raw['parentCategory'], ObjectId):
                created_category_raw['parentCategory'] = str(created_category_raw['parentCategory'])

        return Category.model_validate(created_category_raw)
    except HTTPException:
        raise
    except Exception as e:
        error_detail = str(e)
        print(f"Kategori oluşturma hatası: {error_detail}")
        print(traceback.format_exc())
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Kategori oluşturulamadı: {error_detail}")


@router.get("/", response_model=CategoryListResponse)
async def read_categories(
    db: DBDep,
    include_inactive: bool = Query(False, description="Aktif olmayanları da dahil et (Admin için)")
):
    """Kategorileri listeler (varsayılan olarak sadece aktif olanlar)."""
    categories_collection = db["categories"]
    filter_query = {} if include_inactive else {"isActive": True}

    try:
        # Hata kontrolü ile sorgu yap
        try:
            category_cursor = categories_collection.find(filter_query).sort([("order", 1), ("name", 1)])
            categories_raw = await category_cursor.to_list(length=None)  # Tüm kategorileri al
        except Exception as e:
            print(f"Kategori listesi alma hatası: {e}")
            print(f"Sorgu: {filter_query}")
            # Hata durumunda boş liste döndür
            categories_raw = []

        # ObjectId'leri string'e çevir ve response modelini doğrula
        categories_validated = []
        for cat_raw in categories_raw:
            try:
                # ID kontrolü
                if '_id' in cat_raw:
                    cat_raw['_id'] = str(cat_raw['_id'])
                else:
                    print(f"Hatalı kategori verisi - '_id' alanı yok: {cat_raw}")
                    continue
                
                # Üst kategori varsa kontrol et
                if 'parentCategory' in cat_raw and cat_raw['parentCategory']:
                    if isinstance(cat_raw['parentCategory'], ObjectId):
                        cat_raw['parentCategory'] = str(cat_raw['parentCategory'])
                
                # Modeli doğrula
                try:
                    category = Category.model_validate(cat_raw)
                    categories_validated.append(category)
                except Exception as validation_error:
                    print(f"Kategori modeli doğrulama hatası: {validation_error}")
                    print(f"Hatalı kategori: {cat_raw}")
                    # Hatalı kategoriyi atla
                    continue
            except Exception as e:
                print(f"Kategori işleme hatası: {e}")
                print(f"Hatalı kategori: {cat_raw}")
                # Hatalı kategoriyi atla
                continue

        return CategoryListResponse(data=categories_validated)
    except Exception as e:
        error_detail = str(e)
        print(f"Kategori listeleme hatası: {error_detail}")
        print(traceback.format_exc())
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Kategoriler listelenirken bir hata oluştu: {error_detail}")


@router.get("/{category_id_or_slug}", response_model=Category)
async def read_category(category_id_or_slug: str, db: DBDep):
    """ID veya slug ile tek bir kategoriyi getirir."""
    categories_collection = db["categories"]
    
    try:
        query = {}
        if ObjectId.is_valid(category_id_or_slug):
            query["_id"] = ObjectId(category_id_or_slug)
        else:
            query["slug"] = category_id_or_slug

        category_raw = await categories_collection.find_one(query)

        if not category_raw:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kategori bulunamadı.")

        # ObjectId'leri string'e çevir
        category_raw['_id'] = str(category_raw['_id'])
        if 'parentCategory' in category_raw and category_raw['parentCategory']:
            if isinstance(category_raw['parentCategory'], ObjectId):
                category_raw['parentCategory'] = str(category_raw['parentCategory'])

        return Category.model_validate(category_raw)
    except HTTPException:
        raise
    except Exception as e:
        error_detail = str(e)
        print(f"Kategori getirme hatası: {error_detail}")
        print(traceback.format_exc())
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Kategori getirilirken bir hata oluştu: {error_detail}")


@router.patch("/{category_id}", response_model=Category)
async def update_category(category_id: str, category_data: CategoryUpdate, db: DBDep, admin_user: AdminDep):
    """Bir kategoriyi günceller (Sadece Admin)."""
    categories_collection = db["categories"]

    try:
        if not ObjectId.is_valid(category_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz Kategori ID formatı.")

        # Güncelleme verisini hazırla, None olanları alma
        update_data = category_data.model_dump(exclude_unset=True)

        # Slug değiştiyse kontrol et
        if "slug" in update_data:
            update_data["slug"] = create_category_slug(update_data["slug"])
            existing_category = await categories_collection.find_one({"slug": update_data["slug"], "_id": {"$ne": ObjectId(category_id)}})
            if existing_category:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bu slug başka bir kategoride kullanılıyor.")

        # Üst kategori ID'sini işle
        if "parentCategory" in update_data:
            if update_data["parentCategory"] is None:
                 update_data["parentCategory"] = None  # Üst kategoriyi kaldır
            elif isinstance(update_data["parentCategory"], str) and ObjectId.is_valid(update_data["parentCategory"]):
                update_data["parentCategory"] = ObjectId(update_data["parentCategory"])
            elif isinstance(update_data["parentCategory"], PyObjectId):  # Zaten ObjectId ise dokunma
                pass
            else:
                 raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz Üst Kategori ID formatı.")

        # Zaman damgasını güncelle
        update_data["updatedAt"] = datetime.now(timezone.utc)

        updated_category = await categories_collection.find_one_and_update(
            {"_id": ObjectId(category_id)},
            {"$set": update_data},
            return_document=pymongo.ReturnDocument.AFTER
        )

        if not updated_category:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Güncellenecek kategori bulunamadı.")

        # ObjectId'leri string'e çevir
        updated_category['_id'] = str(updated_category['_id'])
        if 'parentCategory' in updated_category and updated_category['parentCategory']:
            if isinstance(updated_category['parentCategory'], ObjectId):
                updated_category['parentCategory'] = str(updated_category['parentCategory'])

        return Category.model_validate(updated_category)
    except HTTPException:
        raise
    except Exception as e:
        error_detail = str(e)
        print(f"Kategori güncelleme hatası: {error_detail}")
        print(traceback.format_exc())
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Kategori güncellenirken bir hata oluştu: {error_detail}")


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(category_id: str, db: DBDep, admin_user: AdminDep):
    """Bir kategoriyi siler (Sadece Admin)."""
    categories_collection = db["categories"]
    products_collection = db["products"]

    try:
        if not ObjectId.is_valid(category_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz Kategori ID formatı.")

        # Kategoriye bağlı ürün var mı kontrol et
        products_count = await products_collection.count_documents({"category": ObjectId(category_id)})
        if products_count > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Bu kategoride {products_count} ürün bulunuyor. Önce ürünleri taşıyın veya silin."
            )

        # Kategoriye bağlı alt kategori var mı kontrol et
        sub_categories_count = await categories_collection.count_documents({"parentCategory": ObjectId(category_id)})
        if sub_categories_count > 0:
             raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Bu kategorinin {sub_categories_count} alt kategorisi bulunuyor. Önce alt kategorileri taşıyın veya silin."
            )

        delete_result = await categories_collection.delete_one({"_id": ObjectId(category_id)})

        if delete_result.deleted_count == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Silinecek kategori bulunamadı.")

        return None
    except HTTPException:
        raise
    except Exception as e:
        error_detail = str(e)
        print(f"Kategori silme hatası: {error_detail}")
        print(traceback.format_exc())
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Kategori silinirken bir hata oluştu: {error_detail}")