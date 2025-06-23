# backend/routers/products.py

# backend/routers/products.py - En üstteki import kısmına eklenecek
from datetime import datetime, timezone
import pymongo  # ReturnDocument kullanımı için gerekli
from fastapi import Request
from fastapi import APIRouter, Depends, HTTPException, status, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import Annotated, List, Optional
from bson import ObjectId
import re # Slug oluşturma için re import edilebilir veya slugify kütüphanesi kurulabilir
import traceback
from fastapi import UploadFile, File
from typing import List
import os
import uuid
import shutil
from fastapi.staticfiles import StaticFiles

from database import get_db_dependency
from models.product_models import ProductCreate, ProductUpdate, Product, ProductListResponse, PyObjectId
from utils.security import get_current_admin_user # Sadece admin işlemleri için
from slugify import slugify # slugify kütüphanesini kurun: pip install python-slugify

router = APIRouter()
DBDep = Annotated[AsyncIOMotorDatabase, Depends(get_db_dependency)]
AdminDep = Annotated[dict, Depends(get_current_admin_user)] # Admin yetkisi kontrolü

# Helper function to create slug
def create_product_slug(name: str) -> str:
    return slugify(name, replacements=[('ı', 'i')]) # Türkçe karakter desteği


@router.post("/upload-images/", status_code=status.HTTP_200_OK)
async def upload_product_images(request: Request, files: List[UploadFile] = File(...)):
    """Ürün resimlerini yükler ve URL'lerini döndürür."""
    upload_dir = "static/uploads/products"
    os.makedirs(upload_dir, exist_ok=True)
    
    urls = []
    
    for file in files:
        # Dosya uzantısını al
        file_extension = os.path.splitext(file.filename)[1].lower()
        # Güvenli dosya uzantıları kontrolü
        if file_extension not in ['.jpg', '.jpeg', '.png', '.webp']:
            continue
        
        # Benzersiz dosya adı oluştur
        filename = f"{uuid.uuid4()}{file_extension}"
        file_path = os.path.join(upload_dir, filename)
        
        # Dosyayı kaydet
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Tam URL oluştur (base URL ile)
        base_url = str(request.base_url)
        url = f"{base_url}static/uploads/products/{filename}"
        
        urls.append({
            "url": url,
            "alt": file.filename,
            "isMain": len(urls) == 0  # İlk resmi ana resim olarak işaretle
        })
    
    return {"success": True, "images": urls}

@router.post("/", response_model=Product, status_code=status.HTTP_201_CREATED)
async def create_product(product_data: ProductCreate, db: DBDep, admin_user: AdminDep):
    """Yeni ürün oluşturur (Sadece Admin)."""
    products_collection = db["products"]

    # Slug kontrolü veya otomatik oluşturma
    if not product_data.slug:
        product_data.slug = create_product_slug(product_data.name)
    else:
        # Sağlanan slug'ı temizle
        product_data.slug = create_product_slug(product_data.slug)

    # Slug benzersiz mi kontrol et
    existing_product = await products_collection.find_one({"slug": product_data.slug})
    if existing_product:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bu slug zaten kullanılıyor.")

    # SKU'ların benzersiz olduğundan emin ol (veya modelde unique index kullan)
    skus = [variant.sku for variant in product_data.variants]
    if len(skus) != len(set(skus)):
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Varyant SKU'ları benzersiz olmalıdır.")
    existing_sku = await products_collection.find_one({"variants.sku": {"$in": skus}})
    if existing_sku:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Varyant SKU'larından biri zaten kullanılıyor.")

    # Görselleri işle (Pydantic modelleri dict'e çevirir)
    product_dict = product_data.model_dump()
    
    # HttpUrl nesnelerini string'e dönüştür
    if "images" in product_dict and product_dict["images"]:
        for image in product_dict["images"]:
            if "url" in image and hasattr(image["url"], "__str__"):
                image["url"] = str(image["url"])

    # Toplam stoğu hesapla
    total_stock = sum(variant.get("stock", 0) for variant in product_dict.get("variants", []))
    product_dict["totalStock"] = total_stock

    # Zaman damgalarını ekle
    now = datetime.now(timezone.utc)
    product_dict["createdAt"] = now
    product_dict["updatedAt"] = now

    # Kategori ObjectId'ye çevrildi mi kontrol et (Pydantic modelinde yapıldı)
    if isinstance(product_dict.get("category"), str):
         product_dict["category"] = ObjectId(product_dict["category"])

    try:
        result = await products_collection.insert_one(product_dict)
        created_product_raw = await products_collection.find_one({"_id": result.inserted_id})

        if not created_product_raw:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ürün oluşturuldu ancak getirilemedi.")

        # ObjectId'leri string'e çevir ve response modelini doğrula
        created_product_raw['_id'] = str(created_product_raw['_id'])
        if 'category' in created_product_raw and isinstance(created_product_raw['category'], ObjectId):
             created_product_raw['category'] = str(created_product_raw['category'])

        return Product.model_validate(created_product_raw) # Pydantic V2

    except Exception as e:
        print(f"Ürün oluşturma hatası: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Ürün oluşturulamadı: {e}")

@router.get("/", response_model=ProductListResponse)
async def read_products(
    db: DBDep,
    category: Optional[str] = Query(None, description="Kategori slug veya ID'si"),
    q: Optional[str] = Query(None, description="Arama sorgusu (isim, açıklama)"),
    minPrice: Optional[float] = Query(None, ge=0),
    maxPrice: Optional[float] = Query(None, ge=0),
    isNew: Optional[bool] = Query(None),
    isFeatured: Optional[bool] = Query(None),
    sort: str = Query("createdAt_desc", description="Sıralama (örn: price_asc, name_desc)"),
    page: int = Query(1, ge=1),
    limit: int = Query(12, ge=1, le=100)  # Sayfa başına ürün limiti
):
    """Ürünleri filtreleyerek, sıralayarak ve sayfalayarak listeler."""
    try:
        products_collection = db["products"]
        categories_collection = db["categories"]

        filter_query = {"isActive": True}

        # Kategori filtresi (slug veya ID ile)
        if category:
            category_doc = None
            if ObjectId.is_valid(category):
                try:
                    category_doc = await categories_collection.find_one({"_id": ObjectId(category), "isActive": True})
                except Exception as e:
                    print(f"Kategori ID ile arama hatası: {e}")
                    pass
            
            if not category_doc:
                try:
                    category_doc = await categories_collection.find_one({"slug": category, "isActive": True})
                except Exception as e:
                    print(f"Kategori slug ile arama hatası: {e}")
                    pass

            if category_doc:
                filter_query["category"] = category_doc["_id"]
            else:
                # Kategori bulunamazsa boş liste döndür
                return ProductListResponse(
                    data=[], 
                    pagination={"total": 0, "page": page, "limit": limit, "totalPages": 0}
                )

        # Arama filtresi
        if q:
            search_regex = {"$regex": q, "$options": "i"}
            filter_query["$or"] = [
                {"name": search_regex},
                {"description": search_regex},
                {"tags": search_regex}
            ]

        # Fiyat filtresi
        price_filter = {}
        if minPrice is not None:
            price_filter["$gte"] = minPrice
        if maxPrice is not None:
            price_filter["$lte"] = maxPrice
        
        if price_filter:
            # Eğer önceki bir $or varsa, mantığı birleştir
            if "$or" in filter_query:
                orig_or = filter_query.pop("$or")
                filter_query["$and"] = [
                    {"$or": orig_or},
                    {"$or": [
                        {"price": price_filter},
                        {"salePrice": price_filter}
                    ]}
                ]
            else:
                # $or yoksa doğrudan ekle
                filter_query["$or"] = [
                    {"price": price_filter},
                    {"salePrice": price_filter}
                ]

        # Diğer filtreler
        if isNew is not None:
            filter_query["isNew"] = isNew
        if isFeatured is not None:
            filter_query["isFeatured"] = isFeatured

        # Sıralama
        sort_options = {}
        if sort:
            try:
                parts = sort.split('_')
                field = parts[0]
                order = -1 if len(parts) > 1 and parts[1] == 'desc' else 1
                # Güvenlik: Sadece izin verilen alanlara göre sıralama yap
                allowed_sort_fields = ["price", "name", "createdAt", "salesCount", "averageRating"]
                if field in allowed_sort_fields:
                    sort_options[field] = order
                else:
                    sort_options["createdAt"] = -1  # Varsayılan
            except Exception as e:
                print(f"Sıralama hatası: {e}")
                sort_options["createdAt"] = -1  # Hata durumunda varsayılan
        else:
            sort_options["createdAt"] = -1  # Varsayılan

        # Sayfalama
        skip = (page - 1) * limit

        # Hata kontrolü
        try:
            total = await products_collection.count_documents(filter_query)
        except Exception as e:
            print(f"Count hatası: {e}")
            print(f"Sorgu: {filter_query}")
            # Hata durumunda güvenli bir değer
            total = 0

        # Sıralama listesini hazırla
        sort_list = list(sort_options.items())
        
        try:
            product_cursor = products_collection.find(filter_query).sort(sort_list).skip(skip).limit(limit)
            products_raw = await product_cursor.to_list(length=limit)
        except Exception as e:
            print(f"Ürün listesi alma hatası: {e}")
            print(f"Sorgu: {filter_query}, Sıralama: {sort_list}, Skip: {skip}, Limit: {limit}")
            # Hata durumunda boş liste
            products_raw = []

        # ObjectId'leri string'e çevir
        products_validated = []
        for prod_raw in products_raw:
            try:
                if '_id' in prod_raw:
                    prod_raw['_id'] = str(prod_raw['_id'])
                if 'category' in prod_raw and prod_raw['category']:
                    if isinstance(prod_raw['category'], ObjectId):
                        prod_raw['category'] = str(prod_raw['category'])
                products_validated.append(Product.model_validate(prod_raw))
            except Exception as e:
                print(f"Ürün doğrulama hatası: {e}")
                print(f"Hatalı ürün: {prod_raw}")
                # Hatalı ürünü atla ama listeye ekleme
                continue

        total_pages = (total + limit - 1) // limit if limit > 0 else 0  # Math.ceil

        return ProductListResponse(
            data=products_validated,
            pagination={
                "total": total,
                "page": page,
                "limit": limit,
                "totalPages": total_pages
            }
        )
    except Exception as e:
        error_detail = str(e)
        print(f"Ürün listeleme hatası: {error_detail}")
        print(traceback.format_exc())
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Ürünler listelenirken bir hata oluştu: {error_detail}")


@router.get("/{product_id_or_slug}", response_model=Product)
async def read_product(product_id_or_slug: str, db: DBDep):
    """ID veya slug ile tek bir ürünü getirir."""
    products_collection = db["products"]

    query = {}
    if ObjectId.is_valid(product_id_or_slug):
        query["_id"] = ObjectId(product_id_or_slug)
    else:
        query["slug"] = product_id_or_slug

    product_raw = await products_collection.find_one(query)

    if not product_raw:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ürün bulunamadı.")

    # Görüntülenme sayısını artır (performans için ayrı bir işlem olabilir)
    await products_collection.update_one(query, {"$inc": {"viewCount": 1}})

    # ObjectId'leri string'e çevir
    product_raw['_id'] = str(product_raw['_id'])
    if 'category' in product_raw and isinstance(product_raw['category'], ObjectId):
        product_raw['category'] = str(product_raw['category'])

    # İsteğe bağlı: Kategori detayını populate et
    category_detail = await db["categories"].find_one({"_id": ObjectId(product_raw['category'])}) if 'category' in product_raw else None
    product_raw['category_details'] = category_detail if category_detail else None


    return Product.model_validate(product_raw)

@router.put("/{product_id}", response_model=Product)
async def update_product(product_id: str, product_data: ProductUpdate, db: DBDep, admin_user: AdminDep):
    """Bir ürünü günceller (Sadece Admin)."""
    products_collection = db["products"]

    if not ObjectId.is_valid(product_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz Ürün ID formatı.")

    # Güncelleme verisini hazırla, None olanları alma
    update_data = product_data.model_dump(exclude_unset=True)

    # Slug değiştiyse kontrol et
    if "slug" in update_data:
        update_data["slug"] = create_product_slug(update_data["slug"])
        existing_product = await products_collection.find_one({"slug": update_data["slug"], "_id": {"$ne": ObjectId(product_id)}})
        if existing_product:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bu slug başka bir üründe kullanılıyor.")

    # Kategori ObjectId'ye çevrildi mi kontrol et
    if "category" in update_data and isinstance(update_data["category"], str):
        if ObjectId.is_valid(update_data["category"]):
            update_data["category"] = ObjectId(update_data["category"])

    # Görsel verilerini işle - özel olarak ele alınması gerekiyor
    if "images" in update_data:
        # MongoDB'deki mevcut ürünü getir
        current_product = await products_collection.find_one({"_id": ObjectId(product_id)})
        if not current_product:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Güncellenecek ürün bulunamadı.")
        
        # Görsel verilerini güncelleme işlemi
        # Bu işlem tüm görsel dizisini yeni görsel dizisiyle değiştirir
        images_data = update_data["images"]
        
        # HttpUrl nesnelerini string'e dönüştür
        for image in images_data:
            if "url" in image and hasattr(image["url"], "__str__"):
                image["url"] = str(image["url"])
        
        # Debug için loglama
        print(f"Güncellenen görseller: {images_data}")

    # Varyantlar güncelleniyorsa SKU'ları kontrol et ve totalStock'u yeniden hesapla
    if "variants" in update_data:
        skus = [variant.get("sku") for variant in update_data["variants"] if variant.get("sku")]
        if len(skus) != len(set(skus)):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Yeni varyant SKU'ları benzersiz olmalıdır.")
        
        existing_sku = await products_collection.find_one({
            "variants.sku": {"$in": skus}, 
            "_id": {"$ne": ObjectId(product_id)}
        })
        
        if existing_sku:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Yeni varyant SKU'larından biri zaten başka üründe kullanılıyor.")
        
        # Toplam stok hesaplama
        update_data["totalStock"] = sum(variant.get("stock", 0) for variant in update_data["variants"])

    # Zaman damgasını güncelle
    update_data["updatedAt"] = datetime.now(timezone.utc)

    try:
        # Tüm güncellemeleri bir seferde yap
        updated_product = await products_collection.find_one_and_update(
            {"_id": ObjectId(product_id)},
            {"$set": update_data},
            return_document=pymongo.ReturnDocument.AFTER # Güncellenmiş belgeyi döndür
        )
        
        if not updated_product:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ürün güncellendikten sonra bulunamadı.")
        
        # Debug için güncel ürünü logla
        print(f"Güncellenmiş ürün görsel sayısı: {len(updated_product.get('images', []))}")
        
        # ObjectId'leri string'e çevir
        updated_product['_id'] = str(updated_product['_id'])
        if 'category' in updated_product and isinstance(updated_product['category'], ObjectId):
            updated_product['category'] = str(updated_product['category'])
        
        # Ürün nesnesini Pydantic modeliyle doğrula ve döndür    
        return Product.model_validate(updated_product)
    
    except Exception as e:
        print(f"Ürün güncelleme hatası: {e}")
        print(traceback.format_exc())  # Detaylı hata bilgisi
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Ürün güncellenirken hata oluştu: {e}"
        )

@router.put("/{product_id}/images", status_code=status.HTTP_200_OK)
async def update_product_images(product_id: str, images: List[dict], db: DBDep, admin_user: AdminDep):
    """Ürün görsellerini günceller (Sadece Admin)."""
    products_collection = db["products"]

    if not ObjectId.is_valid(product_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz Ürün ID formatı.")

    # HttpUrl nesnelerini string'e dönüştür
    for image in images:
        if "url" in image and hasattr(image["url"], "__str__"):
            image["url"] = str(image["url"])
    
    try:
        # Doğrudan images alanını güncelle
        result = await products_collection.update_one(
            {"_id": ObjectId(product_id)},
            {"$set": {"images": images}}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ürün bulunamadı.")
        
        return {"success": True, "message": "Ürün görselleri başarıyla güncellendi"}
    
    except Exception as e:
        print(f"Görsel güncelleme hatası: {e}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Görseller güncellenirken hata oluştu: {e}"
        )

@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(product_id: str, db: DBDep, admin_user: AdminDep):
    """Bir ürünü siler (Sadece Admin)."""
    products_collection = db["products"]

    if not ObjectId.is_valid(product_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz Ürün ID formatı.")

    delete_result = await products_collection.delete_one({"_id": ObjectId(product_id)})

    if delete_result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Silinecek ürün bulunamadı.")

    return None # 204 No Content yanıtı için body olmaz

@router.get("/similar/{product_id}", response_model=ProductListResponse)
async def get_similar_products(
    product_id: str, 
    db: DBDep,
    limit: int = Query(4, ge=1, le=12)
):
    """Verilen ürüne benzer ürünleri getirir."""
    try:
        products_collection = db["products"]
        
        # Önce mevcut ürünü bul
        if ObjectId.is_valid(product_id):
            product = await products_collection.find_one({"_id": ObjectId(product_id)})
        else:
            product = await products_collection.find_one({"slug": product_id})
            
        if not product:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ürün bulunamadı.")
        
        # Benzer ürünleri bulmak için kategori ve mevcut ürün ID'sini kullan
        category_id = product.get("category")
        
        # Benzer ürünleri bul: Aynı kategorideki, ancak farklı ID'ye sahip, aktif ürünler
        filter_query = {
            "category": category_id,
            "_id": {"$ne": product["_id"] if "_id" in product else ObjectId(product_id)},
            "isActive": True
        }
        
        # Benzer ürünleri çek
        similar_products_cursor = products_collection.find(filter_query).limit(limit)
        similar_products_raw = await similar_products_cursor.to_list(length=limit)
        
        # ObjectId'leri string'e çevir
        similar_products_validated = []
        for prod_raw in similar_products_raw:
            if '_id' in prod_raw:
                prod_raw['_id'] = str(prod_raw['_id'])
            if 'category' in prod_raw and prod_raw['category']:
                if isinstance(prod_raw['category'], ObjectId):
                    prod_raw['category'] = str(prod_raw['category'])
            similar_products_validated.append(Product.model_validate(prod_raw))
        
        return ProductListResponse(
            data=similar_products_validated,
            pagination={
                "total": len(similar_products_validated),
                "page": 1,
                "limit": limit,
                "totalPages": 1
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Benzer ürünleri getirme hatası: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Benzer ürünler listelenirken bir hata oluştu.")