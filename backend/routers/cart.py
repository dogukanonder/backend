# backend/routers/cart.py
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import Annotated, Optional
from bson import ObjectId
from uuid import uuid4
from datetime import datetime, timezone
import pymongo

from database import get_db_dependency
from models.cart_models import Cart, CartResponse, AddToCartRequest, UpdateCartItemRequest, ApplyCampaignRequest, PyObjectId
from models.product_models import Product as ProductModel # Ürün modelini import et
from models.campaign_models import Campaign as CampaignModel # Kampanya modelini import et
from utils.security import get_current_user_payload # Opsiyonel: Giriş yapmış kullanıcıyı almak için
from config import settings

router = APIRouter()
DBDep = Annotated[AsyncIOMotorDatabase, Depends(get_db_dependency)]

# Yardımcı fonksiyon: Sepet ID'sini al (Cookie veya User)
async def get_cart_identifier(request: Request, db: DBDep) -> dict:
    """Cookie'den sessionId veya token'dan userId alır."""
    # Önce token'ı kontrol et
    try:
        # Authorization header'ından token'ı al
        authorization = request.headers.get("Authorization")
        if authorization and authorization.startswith("Bearer "):
            token = authorization.split(" ")[1]
            # Token'ı doğrula ve user_id'yi al (burada basit bir kontrol yapıyoruz)
            # Gerçek uygulamada JWT token'ı decode etmek gerekir
            # user_id = "some_user_id_from_token"  # Token'dan user_id çıkarılacak
            pass  # Şimdilik token kontrolü atlandı
    except Exception:
        pass # Token yoksa veya geçersizse devam et (misafir olabilir)

    # Cookie'den session ID'yi al
    session_id = request.cookies.get("cartSessionId")
    user_id = None # Şimdilik token kontrolü yapmıyoruz

    print(f"🍪 [Backend] Cookie'den session ID: {session_id}")
    print(f"👤 [Backend] User ID: {user_id}")
    print(f"🌍 [Backend] Tüm cookies: {request.cookies}")
    print(f"🌐 [Backend] Request headers: {dict(request.headers)}")
    print(f"📍 [Backend] Request URL: {request.url}")
    print(f"🔗 [Backend] Request origin: {request.headers.get('origin', 'N/A')}")

    # Eğer kullanıcı ID varsa önceliklendir
    if user_id:
        print(f"✅ [Backend] User ID ile sepet erişimi: {user_id}")
        return {"user": ObjectId(user_id), "new_session": False}
    elif session_id:
        # Mevcut session ID'yi kullan ve yeni olmadığını belirt
        print(f"✅ [Backend] Mevcut session ID ile sepet erişimi: {session_id}")
        return {"sessionId": session_id, "new_session": False}
    else:
        # Ne kullanıcı ID ne de session ID varsa, yeni session ID oluştur
        new_session_id = str(uuid4())
        print(f"🆕 [Backend] Yeni session ID oluşturuluyor: {new_session_id}")
        return {"sessionId": new_session_id, "new_session": True}

# Yardımcı fonksiyon: Sepeti hesapla ve kaydet
async def calculate_and_save_cart(cart_doc: dict, db: DBDep) -> dict:
    """Sepet toplamlarını hesaplar ve veritabanına kaydeder."""
    print(f"💻 [Backend] calculate_and_save_cart başlatıldı")
    print(f"📦 [Backend] Cart doc type: {type(cart_doc)}")
    print(f"📊 [Backend] Cart doc keys: {cart_doc.keys() if cart_doc else 'None'}")
    
    # cart_doc None kontrolü
    if cart_doc is None:
        print(f"⚠️ [Backend] Cart doc None - boş sepet döndürülüyor")
        return {
            "id": "empty",
            "items": [],
            "subtotal": 0,
            "discountAmount": 0,
            "shippingCost": 0,
            "taxAmount": 0,
            "total": 0,
            "campaign": None,
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc)
        }
        
    carts_collection = db["carts"]
    products_collection = db["products"]
    campaigns_collection = db["campaigns"]

    subtotal = 0
    valid_items = []

    print(f"🛍️ [Backend] Sepetteki item sayısı: {len(cart_doc.get('items', []))}")
    
    # Ürünleri tek seferde çekmek için ID listesi
    product_ids = [ObjectId(item['product']) for item in cart_doc.get('items', []) 
                  if 'product' in item and ObjectId.is_valid(str(item['product']))]
    
    print(f"🔍 [Backend] Product ID'ler: {product_ids}")

    # Veritabanından ilgili ürünleri çek
    product_docs = {}
    if product_ids:
        cursor = products_collection.find({"_id": {"$in": product_ids}, "isActive": True})
        async for prod in cursor:
            product_docs[prod['_id']] = prod

    # Sepetteki ürünleri işle
    for item_data in cart_doc.get('items', []):
        if 'product' not in item_data:
            continue  # Geçersiz item, product alanı yok
            
        product_id = item_data.get('product')
        if not product_id:
            continue  # Geçersiz item, product ID yok
            
        # ObjectId kontrolü
        if isinstance(product_id, str) and ObjectId.is_valid(product_id):
            product_id = ObjectId(product_id)
        elif not isinstance(product_id, ObjectId):
            continue  # Geçersiz ObjectId
        
        # Variant ve SKU kontrolü - item_data'dan variantSku'yu doğrudan al
        variant_sku = item_data.get('variantSku')
        if not variant_sku:
            # Eğer variantSku doğrudan yoksa, variant objesi içinde kontrol et (geriye dönük uyumluluk)
            variant_obj = item_data.get('variant', {})
            if isinstance(variant_obj, dict):
                variant_sku = variant_obj.get('sku')
            
            if not variant_sku:
                continue  # Geçersiz item, SKU yok

        # Ürün kontrolü
        product = product_docs.get(product_id)
        if not product:
            continue  # Ürün bulunamadı veya aktif değil

        # Varyant kontrolü
        variant = next((v for v in product.get('variants', []) if v.get('sku') == variant_sku), None)
        if not variant:
            continue  # Varyant bulunamadı

        # Stok kontrolü
        quantity = max(1, item_data.get('quantity', 1))  # En az 1 adet
        if quantity > variant.get('stock', 0):
            quantity = variant.get('stock', 0)  # Miktarı stoğa eşitle
            if quantity == 0:
                continue  # Stok yoksa ürünü atla (veya kaldır)

        # Fiyat hesaplama
        price = product.get('salePrice') if product.get('salePrice') is not None else product.get('price', 0)
        item_subtotal = price * quantity

        # Gerekli alanları güncelle/ekle
        item_data['productName'] = product.get('name', 'Ürün')
        item_data['productSlug'] = product.get('slug', '')
        item_data['productImage'] = product.get('images', [{}])[0].get('url', '') if product.get('images') else ''  # İlk görseli al
        
        # variantSku alanını doğrudan ekle/güncelle
        item_data['variantSku'] = variant_sku
        
        # Variant bilgilerini güncelle
        if not isinstance(item_data.get('variant'), dict):
            item_data['variant'] = {}
            
        item_data['variant']['size'] = variant.get('size', '')
        item_data['variant']['colorName'] = variant.get('colorName', '')
        item_data['variant']['colorHex'] = variant.get('colorHex', '')
        item_data['variant']['sku'] = variant_sku
        
        item_data['price'] = price
        item_data['originalPrice'] = product.get('price')
        item_data['quantity'] = quantity
        item_data['subtotal'] = item_subtotal

        subtotal += item_subtotal
        valid_items.append(item_data)

    cart_doc['items'] = valid_items  # Sadece geçerli ve stoğu olan ürünleri tut
    cart_doc['subtotal'] = subtotal

    # Kampanyayı uygula
    discount_amount = 0
    campaign_applied = None
    
    # Campaign kontrolü
    campaign_obj = cart_doc.get('campaign')
    campaign_id_str = None
    
    if campaign_obj and isinstance(campaign_obj, dict):
        campaign_id = campaign_obj.get('id')
        if campaign_id:
            if isinstance(campaign_id, ObjectId):
                campaign_id_str = str(campaign_id)
            elif isinstance(campaign_id, str) and ObjectId.is_valid(campaign_id):
                campaign_id_str = campaign_id

    if campaign_id_str:
        try:
            campaign = await campaigns_collection.find_one({"_id": ObjectId(campaign_id_str)})
            now = datetime.now(timezone.utc)
            
            # Tarih karşılaştırması için güvenli dönüşüm
            start_date = campaign.get('startDate')
            end_date = campaign.get('endDate')
            
            # Tarihlerin timezone bilgisi yoksa ekle
            if start_date.tzinfo is None:
                start_date = start_date.replace(tzinfo=timezone.utc)
            if end_date.tzinfo is None:
                end_date = end_date.replace(tzinfo=timezone.utc)
            
            if (campaign and campaign.get('isActive') and 
                start_date <= now and 
                end_date >= now and 
                (not campaign.get('minPurchaseAmount') or subtotal >= campaign.get('minPurchaseAmount', 0))):

                # TODO: Ürün/Kategori filtrelerini burada kontrol et
                # TODO: Kullanım limiti kontrolü (toplam ve kullanıcı başına)

                if campaign.get('discountType') == 'percentage':
                    calculated_discount = subtotal * (campaign.get('discountValue', 0) / 100)
                    max_discount = campaign.get('maxDiscount')
                    discount_amount = min(calculated_discount, max_discount) if max_discount is not None else calculated_discount
                elif campaign.get('discountType') == 'fixed_amount':
                    discount_amount = min(campaign.get('discountValue', 0), subtotal)

                campaign_applied = {
                    "id": str(campaign['_id']),  # String olarak sakla
                    "code": campaign.get('code', ''),
                    "discountType": campaign.get('discountType', ''),
                    "discountValue": campaign.get('discountValue', 0),
                    "discountAmount": discount_amount
                }
            else:
                cart_doc['campaign'] = None  # Geçersizse kaldır
        except Exception as e:
            print(f"Kampanya uygulanırken hata: {e}")
            cart_doc['campaign'] = None  # Hata durumunda kaldır

    cart_doc['discountAmount'] = discount_amount
    cart_doc['campaign'] = campaign_applied  # Uygulanan kampanya bilgisini ata

    # Vergi ve kargo hesapla
    tax_base = subtotal - discount_amount
    tax_amount = max(0, tax_base * (settings.TAX / 100))  # %18 KDV varsayımı
    shipping_cost = 0 if tax_base >= settings.FREE_SHIPPING_THRESHOLD else settings.SHIPPING_COST

    cart_doc['taxAmount'] = tax_amount
    cart_doc['shippingCost'] = shipping_cost
    cart_doc['total'] = max(0, tax_base + tax_amount + shipping_cost)
    cart_doc['updatedAt'] = datetime.now(timezone.utc)

    # Veritabanına kaydet/güncelle
    try:
        if '_id' in cart_doc and cart_doc['_id']:
            # Mevcut sepeti güncelle
            cart_id = cart_doc['_id']
            if isinstance(cart_id, str) and ObjectId.is_valid(cart_id):
                cart_id = ObjectId(cart_id)
                
            if isinstance(cart_id, ObjectId):
                print(f"💾 Sepet güncelleniyor - ID: {cart_id}")
                # Items sayısını kontrol et
                print(f"📦 Sepetteki item sayısı: {len(cart_doc.get('items', []))}")
                
                result = await carts_collection.update_one(
                    {"_id": cart_id}, 
                    {"$set": cart_doc}, 
                    upsert=True
                )
                print(f"✅ Güncelleme sonucu: {result.matched_count} eşleşen, {result.modified_count} güncellenen")
                
                # Eğer upsert ile yeni eklendiyse ID'yi ayarla
                if result.upserted_id:
                    cart_doc['_id'] = result.upserted_id
                    print(f"🆕 Upsert ile yeni sepet oluşturuldu: {result.upserted_id}")
                    
        elif 'sessionId' in cart_doc:
            # Session ID ile sepeti bul/oluştur
            print(f"💾 Sepet güncelleniyor - Session ID: {cart_doc['sessionId']}")
            print(f"📦 Sepetteki item sayısı: {len(cart_doc.get('items', []))}")
            
            result = await carts_collection.update_one(
                {"sessionId": cart_doc['sessionId']}, 
                {"$set": cart_doc}, 
                upsert=True
            )
            print(f"✅ Güncelleme sonucu: {result.matched_count} eşleşen, {result.modified_count} güncellenen")
            
            # Upserted ID varsa ata
            if result.upserted_id:
                cart_doc['_id'] = result.upserted_id
                print(f"🆕 Session ile yeni sepet oluşturuldu: {result.upserted_id}")
        else:
            # Ne _id ne de sessionId varsa, yeni belge ekle
            print("💾 Yeni sepet belgesi ekleniyor")
            result = await carts_collection.insert_one(cart_doc)
            cart_doc['_id'] = result.inserted_id
            print(f"🆕 Yeni sepet eklendi - ID: {result.inserted_id}")
            
        # Kaydedilen sepeti kontrol et
        saved_cart = await carts_collection.find_one({"_id": cart_doc['_id']})
        if saved_cart:
            print(f"✅ Sepet başarıyla kaydedildi, items sayısı: {len(saved_cart.get('items', []))}")
        else:
            print("❌ Sepet kaydedilmiş gibi görünmüyor!")
            
    except Exception as e:
        print(f"❌ Sepet kaydedilirken hata: {e}")
        import traceback
        traceback.print_exc()
        # İşleme devam et, veritabanı hatası olsa bile hesaplanmış sepeti döndür

    # Pydantic modeli için _id'yi string'e çevir
    if '_id' in cart_doc:
        cart_doc['id'] = str(cart_doc.pop('_id'))
    if 'user' in cart_doc and isinstance(cart_doc['user'], ObjectId):
        cart_doc['user'] = str(cart_doc['user'])
    if 'campaign' in cart_doc and cart_doc['campaign'] and isinstance(cart_doc['campaign'].get('id'), ObjectId):
        cart_doc['campaign']['id'] = str(cart_doc['campaign']['id'])
        
    # İtem ID'lerini de string'e çevir
    for item in cart_doc.get('items', []):
        if '_id' in item and isinstance(item['_id'], ObjectId):
            item['id'] = str(item.pop('_id'))
        elif '_id' in item:
            item['id'] = str(item['_id'])
            
        if 'product' in item and isinstance(item['product'], ObjectId):
            item['product'] = str(item['product'])
        elif 'product' in item and not isinstance(item['product'], str):
            item['product'] = str(item['product'])

    return cart_doc

@router.get("/", response_model=CartResponse)
async def get_cart(request: Request, response: Response, db: DBDep):
    """Mevcut kullanıcının veya oturumun sepetini getirir."""
    try:
        identifier = await get_cart_identifier(request, db)
        carts_collection = db["carts"]

        # Identifier'dan new_session'ı ayır
        cart_identifier = {k: v for k, v in identifier.items() if k != "new_session"}
        is_new_session = identifier.get("new_session", False)

        # Session ID cookie'sini her zaman ayarla (güvence için)
        if "sessionId" in cart_identifier:
            session_id = cart_identifier["sessionId"]
            print(f"🍪 [GET] Session ID cookie ZORLA ayarlanıyor: {session_id}")
            
            # Environment'a göre cookie ayarları
            is_production = settings.ALLOWED_ORIGINS_STR.find('localhost') == -1
            print(f"🏭 [Backend] Is production: {is_production}")
            print(f"🔧 [Backend] Allowed origins: {settings.ALLOWED_ORIGINS_STR}")
            
            response.set_cookie(
                key="cartSessionId", 
                value=session_id, 
                max_age=60*60*24*30,  # 30 gün
                httponly=False,       # Frontend'in cookie'ye erişebilmesi için 
                samesite='none' if is_production else 'lax',
                secure=is_production,  # Production'da secure, development'te False
                path="/",             # Tüm path'lerde geçerli
            )
            print(f"✅ [Backend] Cookie ayarlandı - Session ID: {session_id}, SameSite: {'none' if is_production else 'lax'}, Secure: {is_production}")

        # Session ID veya user ile sepeti bul
        cart_doc = None
        if cart_identifier:
            cart_doc = await carts_collection.find_one(cart_identifier)

        if not cart_doc:
                
            # Boş sepet oluştur
            cart_doc = {
                "items": [],
                "subtotal": 0,
                "discountAmount": 0,
                "shippingCost": 0,
                "taxAmount": 0,
                "total": 0,
                "campaign": None,
                "createdAt": datetime.now(timezone.utc),
                "updatedAt": datetime.now(timezone.utc),
                **cart_identifier  # sessionId veya user ekle
            }
            
            # Boş sepeti DB'ye kaydet
            try:
                result = await carts_collection.insert_one(cart_doc)
                cart_doc["_id"] = result.inserted_id
            except Exception as e:
                print(f"Boş sepet kaydedilirken hata: {e}")
                # Hata olsa bile devam et, sepet hesaplamasını yapmaya çalış

        # Sepeti hesapla ve kaydet
        calculated_cart = await calculate_and_save_cart(cart_doc, db)
        
        try:
            return CartResponse(data=Cart.model_validate(calculated_cart))
        except Exception as e:
            print(f"Sepet modeli doğrulanırken hata: {e}")
            # Model doğrulama hatası durumunda manuel bir sepet oluştur
            emergency_cart = {
                "id": calculated_cart.get("id", "temp-id"),
                "items": calculated_cart.get("items", []),
                "subtotal": calculated_cart.get("subtotal", 0),
                "discountAmount": calculated_cart.get("discountAmount", 0),
                "shippingCost": calculated_cart.get("shippingCost", 0),
                "taxAmount": calculated_cart.get("taxAmount", 0),
                "total": calculated_cart.get("total", 0),
                "campaign": calculated_cart.get("campaign"),
                "createdAt": datetime.now(timezone.utc),
                "updatedAt": datetime.now(timezone.utc)
            }
            return CartResponse(data=Cart.model_validate(emergency_cart))
            
    except Exception as e:
        print(f"Sepet alınırken hata: {e}")
        
        # Hata durumunda boş sepet döndür
        empty_cart = {
            "id": "empty",
            "items": [],
            "subtotal": 0,
            "discountAmount": 0,
            "shippingCost": 0,
            "taxAmount": 0,
            "total": 0,
            "campaign": None,
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc)
        }
        return CartResponse(data=Cart.model_validate(empty_cart))


@router.post("/items", response_model=CartResponse)
async def add_item_to_cart(item_data: AddToCartRequest, request: Request, response: Response, db: DBDep):
    """Sepete yeni ürün ekler veya mevcut ürünün miktarını artırır."""
    try:
        print(f"Sepete ekleme isteği alındı: {item_data}")
        identifier = await get_cart_identifier(request, db)
        print(f"Cart identifier: {identifier}")
        carts_collection = db["carts"]
        products_collection = db["products"]

        # Ürünü ve varyantı kontrol et
        if not ObjectId.is_valid(str(item_data.productId)):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz ürün ID formatı.")
            
        product = await products_collection.find_one({"_id": ObjectId(item_data.productId), "isActive": True})
        if not product:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ürün bulunamadı veya aktif değil.")

        variant = next((v for v in product.get('variants', []) if v.get('sku') == item_data.variantSku), None)
        if not variant:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ürün varyantı bulunamadı.")

        # Stoğu kontrol et
        if variant.get('stock', 0) < item_data.quantity:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Yetersiz stok. Mevcut: {variant.get('stock', 0)}")

        # Identifier'dan new_session'ı ayır
        cart_identifier = {k: v for k, v in identifier.items() if k != "new_session"}
        is_new_session = identifier.get("new_session", False)
        
        # Sepeti bul veya oluştur
        cart_doc = await carts_collection.find_one(cart_identifier)
        print(f"🔍 Bulunan sepet: {cart_doc is not None}")
        
        if not cart_doc:
            cart_doc = {
                "_id": ObjectId(),  # Yeni sepet için ObjectId oluştur
                "items": [],
                "subtotal": 0,
                "discountAmount": 0,
                "shippingCost": 0,
                "taxAmount": 0,
                "total": 0,
                "campaign": None,
                "createdAt": datetime.now(timezone.utc),
                "updatedAt": datetime.now(timezone.utc),
                **cart_identifier
            }
            print(f"🆕 Yeni sepet oluşturuldu: {cart_doc['_id']}")
            
        # Session ID cookie'sini her zaman ayarla (güvence için)
        if "sessionId" in cart_identifier:
            session_id = cart_identifier["sessionId"]
            print(f"🍪 Session ID cookie ZORLA ayarlanıyor: {session_id}")
            
            # Environment'a göre cookie ayarları
            is_production = settings.ALLOWED_ORIGINS_STR.find('localhost') == -1
            print(f"🏭 [Backend] Is production: {is_production}")
            print(f"🔧 [Backend] Allowed origins: {settings.ALLOWED_ORIGINS_STR}")
            
            response.set_cookie(
                key="cartSessionId",
                value=session_id,
                max_age=60*60*24*30,  # 30 gün
                httponly=False,       # Frontend'in cookie'ye erişebilmesi için
                samesite='none' if is_production else 'lax',
                secure=is_production,  # Production'da secure, development'te False
                path="/",             # Tüm path'lerde geçerli
            )
            print(f"✅ [Backend] Cookie ayarlandı - Session ID: {session_id}, SameSite: {'none' if is_production else 'lax'}, Secure: {is_production}")

        # Sepetteki item'ı bul veya oluştur
        item_index = -1
        for i, item in enumerate(cart_doc.get('items', [])):
            product_match = False
            if isinstance(item.get('product'), ObjectId) and str(item.get('product')) == str(item_data.productId):
                product_match = True
            elif isinstance(item.get('product'), str) and item.get('product') == str(item_data.productId):
                product_match = True
                
            if (product_match and 
                item.get('variantSku') == item_data.variantSku):
                item_index = i
                break

        price = product.get('salePrice') if product.get('salePrice') is not None else product.get('price', 0)
        product_image = product.get('images', [{}])[0].get('url', '') if product.get('images') else ''

        if item_index != -1:
            # Miktarı güncelle
            new_quantity = cart_doc['items'][item_index]['quantity'] + item_data.quantity
            if new_quantity > variant.get('stock', 0):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail=f"Maksimum stok aşıldı. Sepete ekleyebileceğiniz: {variant.get('stock', 0) - cart_doc['items'][item_index]['quantity']}"
                )
                
            cart_doc['items'][item_index]['quantity'] = new_quantity
            cart_doc['items'][item_index]['subtotal'] = new_quantity * price  # Subtotal'ı da güncelle
        else:
            # Yeni item ekle
            new_item = {
                "_id": ObjectId(),  # Yeni item için ID oluştur
                "product": ObjectId(item_data.productId),
                "variantSku": item_data.variantSku,  # variantSku'yu doğrudan ekle
                "productName": product.get('name', 'Ürün'),
                "productSlug": product.get('slug', ''),
                "productImage": product_image,
                "variant": {
                    "size": variant.get('size', ''),
                    "colorName": variant.get('colorName', ''),
                    "colorHex": variant.get('colorHex', '#000000'),
                    "sku": variant.get('sku', '')
                },
                "price": price,
                "originalPrice": product.get('price', price),
                "quantity": item_data.quantity,
                "subtotal": item_data.quantity * price
            }
            
            if 'items' not in cart_doc:
                cart_doc['items'] = []
                
            cart_doc['items'].append(new_item)

        # Sepeti hesapla ve kaydet
        calculated_cart = await calculate_and_save_cart(cart_doc, db)

        return CartResponse(data=Cart.model_validate(calculated_cart))
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"Sepete ürün eklerken beklenmedik hata: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Sepete ürün eklenirken bir hata oluştu."
        )


@router.put("/items", response_model=CartResponse)
async def update_cart_item(item_update: UpdateCartItemRequest, request: Request, db: DBDep):
    """Sepetteki bir ürünün miktarını günceller."""
    try:
        identifier = await get_cart_identifier(request, db)
        carts_collection = db["carts"]
        products_collection = db["products"]

        cart_doc = await carts_collection.find_one(identifier)
        if not cart_doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sepet bulunamadı.")

        # Item'ı bul
        item_index = -1
        for i, item in enumerate(cart_doc.get('items', [])):
            item_id_match = False
            
            if '_id' in item:
                # ObjectId karşılaştırması
                if isinstance(item['_id'], ObjectId) and str(item['_id']) == str(item_update.itemId):
                    item_id_match = True
                elif isinstance(item['_id'], str) and item['_id'] == str(item_update.itemId):
                    item_id_match = True
                    
            if 'id' in item and not item_id_match:
                # id alanı kontrolü
                if item['id'] == str(item_update.itemId):
                    item_id_match = True
                    
            if item_id_match:
                item_index = i
                break

        if item_index == -1:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sepette güncellenecek ürün bulunamadı.")

        # Stok kontrolü
        item_to_update = cart_doc['items'][item_index]
        
        product_id = item_to_update.get('product')
        if isinstance(product_id, str) and ObjectId.is_valid(product_id):
            product_id = ObjectId(product_id)
            
        product = await products_collection.find_one({"_id": product_id})
        if not product:
            # Ürün bulunamazsa sepetten kaldırabiliriz
            cart_doc['items'].pop(item_index)
            calculated_cart = await calculate_and_save_cart(cart_doc, db)
            return CartResponse(data=Cart.model_validate(calculated_cart))

        variant_sku = item_to_update.get('variant', {}).get('sku')
        variant = next((v for v in product.get('variants', []) if v.get('sku') == variant_sku), None)
        if not variant:
            # Varyant bulunamazsa sepetten kaldır
            cart_doc['items'].pop(item_index)
            calculated_cart = await calculate_and_save_cart(cart_doc, db)
            return CartResponse(data=Cart.model_validate(calculated_cart))

        if item_update.quantity > variant.get('stock', 0):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Yetersiz stok. Mevcut: {variant.get('stock', 0)}")

        # Miktarı güncelle
        item_to_update['quantity'] = item_update.quantity
        price = item_to_update.get('price', 0)
        item_to_update['subtotal'] = item_update.quantity * price

        # Sepeti hesapla ve kaydet
        calculated_cart = await calculate_and_save_cart(cart_doc, db)

        return CartResponse(data=Cart.model_validate(calculated_cart))
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Sepet ürünü güncellenirken hata: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Sepet ürünü güncellenirken bir hata oluştu."
        )


@router.delete("/items/{item_id}", response_model=CartResponse)
async def remove_item_from_cart(item_id: str, request: Request, db: DBDep):
    """Sepetten bir ürünü kaldırır."""
    try:
        if not ObjectId.is_valid(item_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz ürün ID formatı.")

        identifier = await get_cart_identifier(request, db)
        carts_collection = db["carts"]

        cart_doc = await carts_collection.find_one(identifier)
        if not cart_doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sepet bulunamadı.")

        initial_length = len(cart_doc.get('items', []))
        
        # Yeni items listesi oluştur
        new_items = []
        for item in cart_doc.get('items', []):
            item_id_match = False
            
            if '_id' in item:
                # ObjectId karşılaştırması
                if isinstance(item['_id'], ObjectId) and str(item['_id']) == item_id:
                    item_id_match = True
                elif isinstance(item['_id'], str) and item['_id'] == item_id:
                    item_id_match = True
                    
            if 'id' in item and not item_id_match:
                # id alanı kontrolü
                if item['id'] == item_id:
                    item_id_match = True
                    
            # Eşleşme yoksa listeye ekle
            if not item_id_match:
                new_items.append(item)
        
        # Yeni items listesini cart_doc'a ata
        cart_doc['items'] = new_items

        if len(cart_doc.get('items', [])) == initial_length:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sepette silinecek ürün bulunamadı.")

        # Sepeti hesapla ve kaydet
        calculated_cart = await calculate_and_save_cart(cart_doc, db)

        return CartResponse(data=Cart.model_validate(calculated_cart))
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Sepetten ürün kaldırılırken hata: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Sepetten ürün kaldırılırken bir hata oluştu."
        )


@router.post("/campaign", response_model=CartResponse)
async def apply_campaign_to_cart(campaign_data: ApplyCampaignRequest, request: Request, db: DBDep):
    """Sepete kampanya kodu uygular."""
    try:
        # Kullanıcının sepetini tanımlayan kimliği al (session veya user ID)
        identifier = await get_cart_identifier(request, db)
        carts_collection = db["carts"]
        campaigns_collection = db["campaigns"]

        # Sepeti veritabanından getir
        cart_doc = await carts_collection.find_one(identifier)
        
        # Sepet yoksa veya boşsa hata döndür
        if not cart_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="Sepet bulunamadı. Lütfen önce ürün ekleyin."
            )
            
        if not cart_doc.get('items') or len(cart_doc.get('items', [])) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Kampanya uygulamak için sepette ürün olmalı."
            )

        # Kampanya kodunu standartlaştır (büyük harf)
        code = campaign_data.code.upper().strip()
        
        # Kampanyayı veritabanından getir
        campaign = await campaigns_collection.find_one({"code": code, "isActive": True})
        if not campaign:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="Geçersiz veya aktif olmayan kampanya kodu."
            )

        # Geçerlilik kontrolleri
        now = datetime.now(timezone.utc)
        
        # Tarih kontrolü için tarih karşılaştırması öncesi güvenli dönüşüm yap
        start_date = campaign.get('startDate')
        end_date = campaign.get('endDate')

        # Tarihlerin timezone bilgisi yoksa ekle
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)

        # Şimdi güvenli karşılaştırma yap
        if now < start_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=f"Bu kampanya henüz başlamadı. Başlangıç tarihi: {start_date.strftime('%d.%m.%Y')}"
            )
            
        if now > end_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=f"Bu kampanya süresi doldu. Bitiş tarihi: {end_date.strftime('%d.%m.%Y')}"
            )
        
        # Minimum sepet tutarı kontrolü
        min_amount = campaign.get('minPurchaseAmount', 0)
        if min_amount > 0 and cart_doc.get('subtotal', 0) < min_amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Bu kampanya için minimum sepet tutarı {min_amount:.2f} TL olmalıdır. Mevcut sepet tutarınız: {cart_doc.get('subtotal', 0):.2f} TL"
            )
        
        # Kullanım limiti kontrolü
        max_uses = campaign.get('maxUses')
        if max_uses is not None and campaign.get('usageCount', 0) >= max_uses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Bu kampanya maksimum kullanım limitine ({max_uses}) ulaştı."
            )
            
        # Spesifik kategori/ürün kontrolleri
        if campaign.get('applicableTo') == 'specific_categories' and campaign.get('categories'):
            # Kategori bazlı kampanya, sepetteki ürünler bu kategorilere ait mi kontrol et
            categories = campaign.get('categories', [])
            products_collection = db["products"]
            
            # Sepetteki ürünlerin ID'lerini al
            product_ids = []
            for item in cart_doc.get('items', []):
                if item.get('product'):
                    product_id = item.get('product')
                    if isinstance(product_id, str) and ObjectId.is_valid(product_id):
                        product_ids.append(ObjectId(product_id))
                    elif isinstance(product_id, ObjectId):
                        product_ids.append(product_id)
            
            # Bu ürünlerin kategori bilgilerini getir
            if product_ids:
                products_cursor = products_collection.find(
                    {"_id": {"$in": product_ids}},
                    {"category": 1}  # Sadece kategori alanını getir
                )
                
                product_categories = []
                async for prod in products_cursor:
                    if prod.get('category'):
                        product_categories.append(prod['category'])
                
                # Sepetteki ürünlerin en az biri kampanya kategorilerinde mi?
                valid_category_found = False
                for cat in product_categories:
                    if str(cat) in [str(c) for c in categories]:
                        valid_category_found = True
                        break
                
                if not valid_category_found:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Bu kampanya sadece belirli kategorilerdeki ürünler için geçerlidir."
                    )
        
        # Kampanyayı sepete ekle
        cart_doc['campaign'] = {
            "id": campaign['_id'],  # ObjectId olarak sakla
            "code": campaign.get('code', ''),
            "discountType": campaign.get('discountType', ''),
            "discountValue": campaign.get('discountValue', 0),
            # discountAmount hesaplaması calculate_and_save_cart fonksiyonunda yapılacak
        }

        # Kampanya kullanım sayısını artır (henüz veritabanına yansıtma)
        usage_count = campaign.get('usageCount', 0) + 1
        
        # Sepeti hesapla ve kaydet
        calculated_cart = await calculate_and_save_cart(cart_doc, db)

        # Eğer calculate_and_save_cart fonksiyonu kampanyayı geçersiz kıldıysa hata döndür
        if not calculated_cart.get('campaign'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Kampanya sepetinize uygulanamadı. Lütfen koşulları kontrol edin."
            )

        # Kampanya kullanım sayısını artır (veritabanına yansıt)
        await campaigns_collection.update_one(
            {"_id": campaign['_id']},
            {"$set": {"usageCount": usage_count, "updatedAt": datetime.now(timezone.utc)}}
        )

        return CartResponse(data=Cart.model_validate(calculated_cart))
        
    except HTTPException:
        # HTTPException'ları olduğu gibi yukarı ilet
        raise
    except Exception as e:
        # Beklenmedik hataları logla ve genel bir hata mesajı döndür
        print(f"Kampanya uygulanırken beklenmedik hata: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Kampanya uygulanırken bir hata oluştu. Lütfen daha sonra tekrar deneyin."
        )


@router.delete("/campaign", response_model=CartResponse)
async def remove_campaign_from_cart(request: Request, db: DBDep):
   """Sepetteki kampanyayı kaldırır."""
   try:
       identifier = await get_cart_identifier(request, db)
       carts_collection = db["carts"]

       cart_doc = await carts_collection.find_one(identifier)
       if not cart_doc:
           raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sepet bulunamadı.")

       if not cart_doc.get('campaign'):
           # Zaten kampanya yoksa bir şey yapma
           calculated_cart = await calculate_and_save_cart(cart_doc, db)
           return CartResponse(data=Cart.model_validate(calculated_cart))

       # Kampanyayı kaldır
       cart_doc['campaign'] = None
       cart_doc['discountAmount'] = 0

       # Sepeti hesapla ve kaydet
       calculated_cart = await calculate_and_save_cart(cart_doc, db)

       return CartResponse(data=Cart.model_validate(calculated_cart))
       
   except HTTPException:
       raise
   except Exception as e:
       print(f"Kampanya kaldırılırken hata: {e}")
       raise HTTPException(
           status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
           detail="Kampanya kaldırılırken bir hata oluştu."
       )
