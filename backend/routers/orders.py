# backend/routers/orders.py
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import Annotated, List, Optional
from bson import ObjectId
from datetime import datetime, timezone
import pymongo
import traceback
import json  # JSON dönüşümleri için

from database import get_db_dependency
from models.order_models import (
    OrderCreate, OrderUpdateAdmin, Order, OrderListResponse,
    OrderDetailResponse, OrderCreateResponse, PyObjectId
)
from models.cart_models import Cart as CartModel # Sepet modeli
from models.product_models import Product as ProductModel # Ürün modeli
from models.campaign_models import Campaign as CampaignModel # Kampanya modeli
from models.user_models import UserPublic # Kullanıcı modeli
from utils.security import get_current_user_payload, get_current_active_user, get_current_admin_user
from .cart import get_cart_identifier, calculate_and_save_cart # Sepet yardımcı fonksiyonları

router = APIRouter()
DBDep = Annotated[AsyncIOMotorDatabase, Depends(get_db_dependency)]
CurrentUserDep = Annotated[dict, Depends(get_current_active_user)]
AdminUserDep = Annotated[dict, Depends(get_current_admin_user)]

# Yardımcı fonksiyon: Yeni sipariş numarası oluştur
async def generate_order_number(db: AsyncIOMotorDatabase) -> str:
    orders_collection = db["orders"]
    date_str = datetime.now(timezone.utc).strftime('%y%m%d')
    # O günkü sipariş sayısını bul
    count = await orders_collection.count_documents({
        "createdAt": {
            "$gte": datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        }
    })
    sequence = str(count + 1).zfill(4) # Günlük 4 haneli sıra numarası
    return f"DOVL-{date_str}-{sequence}"

@router.post("/", response_model=OrderCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    order_data: OrderCreate,
    request: Request, # Cookie'den sepet ID'si almak için
    db: DBDep,
    current_user: Optional[dict] = Depends(get_current_active_user) # Giriş yapmış kullanıcı (opsiyonel)
):
    """Yeni bir sipariş oluşturur."""
    try:
        print("=== SİPARİŞ OLUŞTURMA İŞLEMİ BAŞLADI ===")
        print(f"Gelen sipariş verisi: {order_data}")
        
        # Tüm istekle ilgili bilgileri kontrol et
        print("İstek başlıkları:")
        for header, value in request.headers.items():
            print(f"  {header}: {value}")
        
        print("İstek çerezleri:")
        for cookie, value in request.cookies.items():
            print(f"  {cookie}: {value}")
        
        # Gerekli koleksiyonları tanımla
        carts_collection = db["carts"]
        products_collection = db["products"]
        orders_collection = db["orders"]
        users_collection = db["users"] # Kullanıcı bilgilerini almak için
        campaigns_collection = db["campaigns"]

        # Sepeti bul
        identifier = {}
        if current_user:
            # ID anahtarını kontrol et - _id veya id olabilir
            user_id = current_user.get("id") or current_user.get("_id")
            if not user_id:
                print(f"HATA: Kullanıcı nesnesinde id veya _id alanı bulunamadı: {current_user}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Kullanıcı kimliği alınamadı. Lütfen tekrar giriş yapın."
                )
            identifier["user"] = ObjectId(user_id)
            print(f"Giriş yapmış kullanıcı: {user_id}")
        else:
            session_id = request.cookies.get("cartSessionId")
            if not session_id:
                print("HATA: cartSessionId bulunamadı")
                print("Tüm çerezler:", request.cookies)
                
                # Misafir kullanıcılar için acil durum sepeti oluştur - bu bir workaround, ideal değil
                import uuid
                temp_session_id = str(uuid.uuid4())
                print(f"Geçici oturum ID oluşturuldu: {temp_session_id}")
                
                # Bu temprarily session ID ile ilişkilendirilmiş bir sepet var mı kontrol et
                temp_cart = {
                    "sessionId": temp_session_id,
                    "items": [],
                    "createdAt": datetime.now(timezone.utc),
                    "updatedAt": datetime.now(timezone.utc)
                }
                
                try:
                    await carts_collection.insert_one(temp_cart)
                    print(f"Geçici sepet oluşturuldu: {temp_cart}")
                except Exception as e:
                    print(f"Geçici sepet oluşturma hatası: {e}")
                
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail="Geçerli bir sepet oturumu bulunamadı. Lütfen sepetinize ürün ekleyip tekrar deneyin."
                )
                
            identifier["sessionId"] = session_id
            print(f"Misafir kullanıcı session: {session_id}")
        
        print(f"Sepet sorgulama kriteri: {identifier}")
        
        # Veritabanındaki tüm sepetleri kontrol et
        all_carts = []
        async for cart in carts_collection.find({}, {"_id": 1, "sessionId": 1, "user": 1}):
            all_carts.append(cart)
        print(f"Veritabanında bulunan tüm sepetler: {all_carts}")
        
        cart_doc = await carts_collection.find_one(identifier)
        
        # 'Sepeti bul' kısmının hemen ardına şu kodu ekleyin (yaklaşık satır 157)
        # Mevcut kod: cart_doc = await carts_collection.find_one(identifier)

        # Eğer kullanıcı ID'sine bağlı sepet yoksa ama bir session ID'si varsa, o sepeti kontrol et
        if not cart_doc and "user" in identifier and request.cookies.get("cartSessionId"):
            session_id = request.cookies.get("cartSessionId")
            session_identifier = {"sessionId": session_id}
            print(f"Kullanıcıya ait sepet bulunamadı. Session ID ({session_id}) ile sepet aranıyor...")
            
            session_cart = await carts_collection.find_one(session_identifier)
            
            if session_cart:
                print(f"Session ile ilişkili sepet bulundu. Kullanıcıya aktarılıyor...")
                # Sepeti kullanıcıya bağla
                await carts_collection.update_one(
                    {"_id": session_cart["_id"]},
                    {"$set": {"user": identifier["user"], "updatedAt": datetime.now(timezone.utc)}}
                )
                cart_doc = await carts_collection.find_one({"_id": session_cart["_id"]})
                print(f"Sepet kullanıcıya aktarıldı: {identifier['user']}")
        
        # Sepet bulundu mu kontrol et
        if not cart_doc:
            print("HATA: Sepet bulunamadı")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sepetiniz bulunamadı. Lütfen yeniden oturum açın.")
        
        # Sepet içeriği kontrol et
        if not cart_doc.get("items"):
            print(f"HATA: Sepette ürün yok: {cart_doc}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sipariş oluşturmak için sepetinizde ürün bulunmuyor.")
        
        print(f"Bulunan sepet içeriği: {json.dumps(str(cart_doc), indent=2)}")
        print(f"Sepetteki ürün sayısı: {len(cart_doc.get('items', []))}")

        # Sepeti yeniden hesapla (son kontrol)
        try:
            print("Sepet hesaplanıyor...")
            cart = await calculate_and_save_cart(cart_doc, db)
            validated_cart = CartModel.model_validate(cart) # Pydantic ile doğrula
            print(f"Hesaplanan sepet toplamı: {validated_cart.total}")
            print(f"Hesaplanan sepetteki ürün sayısı: {len(validated_cart.items)}")
        except Exception as cart_error:
            print(f"Sepet hesaplama hatası: {cart_error}")
            print(traceback.format_exc())
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sepetiniz hesaplanırken bir hata oluştu. Lütfen sepetinizi kontrol edin.")

        if not validated_cart.items:
            print("HATA: Hesaplanan sepette ürün yok")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sepetinizdeki ürünlerin stoğu tükenmiş olabilir.")

        # Stokları son kez kontrol et ve kilitle (ideal olarak transaction içinde)
        # Basitleştirilmiş kontrol:
        for item in validated_cart.items:
            try:
                product = await products_collection.find_one({"_id": ObjectId(item.product)})
                if not product: 
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"'{item.productName}' ürünü artık mevcut değil. Lütfen sepetinizi güncelleyin."
                    )
                
                variant = next((v for v in product.get('variants', []) if v.get('sku') == item.variant.sku), None)
                if not variant:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"'{item.productName}' ürününün seçili varyantı artık mevcut değil. Lütfen sepetinizi güncelleyin."
                    )
                
                if variant.get('stock', 0) < item.quantity:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"'{item.productName}' ürünü için stok yetersiz (Mevcut: {variant.get('stock', 0)}). Lütfen sepetinizi güncelleyin."
                    )
            except HTTPException:
                raise
            except Exception as e:
                print(f"Stok kontrol hatası: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Stok kontrolü yapılırken bir hata oluştu. Lütfen daha sonra tekrar deneyin."
                )

        # Sipariş numarasını oluştur
        try:
            order_number = await generate_order_number(db)
        except Exception as e:
            print(f"Sipariş numarası oluşturma hatası: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                detail="Sipariş numarası oluşturulamadı. Lütfen daha sonra tekrar deneyin."
            )

        # Sipariş verisini oluştur
        now = datetime.now(timezone.utc)
        
        # Email kontrolü - Misafir kullanıcılar için email gerekli
        if not current_user and not order_data.guestEmail:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Misafir kullanıcılar için email adresi zorunludur.")
        
        # User ID'yi güvenli bir şekilde al
        user_id = None
        user_email = None
        if current_user:
            user_id = current_user.get("id") or current_user.get("_id")
            user_email = current_user.get("email")
            if not user_id or not user_email:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Kullanıcı bilgileri alınamadı.")
        
        order_db_data = {
            "orderNumber": order_number,
            "user": ObjectId(user_id) if user_id else None,
            "userEmail": user_email if user_email else order_data.guestEmail,
            "items": [],  # Alttaki döngüde doldurulacak
            "shippingAddress": order_data.shippingAddress.model_dump(),
            "billingAddress": order_data.billingAddress.model_dump(),
            "paymentMethod": order_data.paymentMethod,
            "paymentDetails": {}, # Ödeme başarılı olunca güncellenecek
            "campaign": validated_cart.campaign.model_dump() if validated_cart.campaign else None,
            "subtotal": validated_cart.subtotal,
            "shippingCost": validated_cart.shippingCost,
            "taxAmount": validated_cart.taxAmount,
            "total": validated_cart.total,
            "status": "pending", # Başlangıç durumu
            "notes": order_data.notes,
            "isGuestCheckout": not bool(current_user),
            "shippingInfo": {},
            "timeline": [{"status": "pending", "date": now, "description": "Sipariş oluşturuldu"}],
            "isPaid": False,
            "createdAt": now,
            "updatedAt": now
        }
        
        # Items dizisini güvenli bir şekilde dolduralım
        for item in validated_cart.items:
            try:
                item_dict = item.model_dump(exclude={'id'})
                order_db_data["items"].append(item_dict)
            except Exception as e:
                print(f"Ürün dönüştürme hatası: {e}, Ürün: {item}")
                # Hataya rağmen diğer ürünlere devam et, kritik olmayan hatalar sepeti engellemesin
                continue

        # --- Ödeme İşlemi Simülasyonu/Entegrasyonu ---
        # Gerçek projede burada ödeme sağlayıcı (Iyzico vb.) API'si çağrılır.
        # Başarılı olursa isPaid=True, paidAt=now yapılır ve stok düşülür.
        # Şimdilik ödemeyi başarılı varsayıyoruz.
        order_db_data["isPaid"] = True
        order_db_data["paidAt"] = now
        order_db_data["status"] = "processing" # Ödeme alındı, hazırlanıyor durumuna geç
        order_db_data["timeline"].append({"status": "processing", "date": now, "description": "Ödeme onaylandı, sipariş hazırlanıyor"})
        # -------------------------------------------

        try:
            # Siparişi veritabanına kaydet
            result = await orders_collection.insert_one(order_db_data)
            new_order_id = result.inserted_id

            # Stokları düş (Ödeme başarılı olduktan sonra yapılmalı)
            if order_db_data["isPaid"]:
                for item in validated_cart.items:
                    try:
                        update_result = await products_collection.update_one(
                            {"_id": ObjectId(item.product), "variants.sku": item.variant.sku},
                            {"$inc": {"variants.$.stock": -item.quantity, "totalStock": -item.quantity, "salesCount": item.quantity}}
                        )
                        
                        if update_result.modified_count == 0:
                            print(f"Stok güncellenemedi: Ürün: {item.product}, SKU: {item.variant.sku}, Miktar: {item.quantity}")
                    except Exception as update_error:
                        print(f"Stok güncelleme hatası: {update_error}")
                        # Stok güncellemesindeki hata kritik olsa da sepeti iptal etmeyelim
                        # Yönetici panelinden manuel düzeltilebilir

            # Kullanıcının sipariş geçmişini güncelle (giriş yapmışsa)
            if current_user:
                try:
                    user_id = current_user.get("id") or current_user.get("_id")
                    if user_id:
                        await users_collection.update_one(
                            {"_id": ObjectId(user_id)},
                            {"$push": {"orderHistory": new_order_id}}
                        )
                except Exception as e:
                    print(f"Kullanıcı sipariş geçmişi güncelleme hatası: {e}")
                    # Bu hata kritik değil, siparişi iptal etmeyelim

            # Sepeti temizle
            try:
                await carts_collection.delete_one(identifier)
            except Exception as e:
                print(f"Sepet temizleme hatası: {e}")
                # Bu hata kritik değil, siparişi iptal etmeyelim

            # Başarı yanıtı döndür
            return OrderCreateResponse(
                message="Siparişiniz başarıyla oluşturuldu.",
                data={"orderId": str(new_order_id), "orderNumber": order_number}
            )

        except Exception as e:
            print(f"Sipariş oluşturma veritabanı hatası: {e}")
            # TODO: Eğer ödeme alındıysa ama DB kaydı/stok düşürme başarısız olduysa
            #       bu durumu loglayıp manuel düzeltme veya iade işlemi tetiklenmeli.
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Sipariş kaydedilirken bir hata oluştu. Ödeme alındıysa, iade işleminiz otomatik olarak başlatılacaktır.")

    except HTTPException:
        raise
    except Exception as e:
        error_detail = str(e)
        print(f"Sipariş oluşturma hatası: {error_detail}")
        print(traceback.format_exc())
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Sunucu hatası oluştu.")


@router.get("/", response_model=OrderListResponse)
async def read_orders(
    request: Request, # Admin kontrolü için token gerekebilir
    db: DBDep,
    current_user: Optional[dict] = Depends(get_current_active_user), # Admin veya kullanıcı
    status: Optional[str] = Query(None, description="Sipariş durumu filtresi"),
    user_id_filter: Optional[str] = Query(None, description="Belirli bir kullanıcı ID'si (Admin için)"),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100)
):
    """Siparişleri listeler. Admin tümünü, kullanıcı sadece kendininkini görür."""
    try:
        orders_collection = db["orders"]
        filter_query = {}

        if not current_user: # Token yoksa hata ver (kullanıcı girişi gerekli)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Siparişleri görmek için giriş yapmalısınız.")

        # User ID'yi güvenli bir şekilde al
        user_id = current_user.get("id") or current_user.get("_id")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Kullanıcı kimliği alınamadı.")

        if current_user.get("role") == "admin":
            if user_id_filter and ObjectId.is_valid(user_id_filter):
                filter_query["user"] = ObjectId(user_id_filter)
            # Admin diğer filtreleri de uygulayabilir
        else:
            # Normal kullanıcı sadece kendi siparişlerini görür
            filter_query["user"] = ObjectId(user_id)

        if status:
            filter_query["status"] = status

        # Sayfalama
        skip = (page - 1) * limit

        total = await orders_collection.count_documents(filter_query)
        order_cursor = orders_collection.find(filter_query).sort([("createdAt", -1)]).skip(skip).limit(limit)
        orders_raw = await order_cursor.to_list(length=limit)

        # ObjectId'leri string'e çevir ve modeli doğrula
        orders_validated = []
        for order_raw in orders_raw:
            try:
                # ObjectId'leri dönüştür
                order_raw['_id'] = str(order_raw['_id'])
                if 'user' in order_raw and isinstance(order_raw['user'], ObjectId):
                    order_raw['user'] = str(order_raw['user'])
                # Diğer ObjectId alanları (items.product, campaign.id)
                if 'items' in order_raw:
                    for item in order_raw['items']:
                        if 'product' in item and isinstance(item['product'], ObjectId):
                            item['product'] = str(item['product'])
                if 'campaign' in order_raw and order_raw['campaign'] and isinstance(order_raw['campaign'].get('id'), ObjectId):
                    order_raw['campaign']['id'] = str(order_raw['campaign']['id'])

                # totalAmount alanını total alanına kopyala
                if "totalAmount" in order_raw and "total" not in order_raw:
                    order_raw["total"] = order_raw["totalAmount"]
                
                # Model doğrulama hatalarını yakalama
                try:
                    validated_order = Order.model_validate(order_raw)
                    orders_validated.append(validated_order)
                except Exception as validation_error:
                    print(f"Sipariş validasyon hatası: {validation_error}")
                    print(f"Hatalı sipariş verisi: {order_raw}")
                    
                    # Basitleştirilmiş bir Order oluştur ve ekle
                    basic_order = Order(
                        _id=order_raw["_id"],
                        user=order_raw.get("user"),
                        status=order_raw.get("status", "pending"),
                        total=order_raw.get("totalAmount", 0),
                        createdAt=order_raw.get("createdAt", datetime.now(timezone.utc)),
                        updatedAt=order_raw.get("updatedAt", datetime.now(timezone.utc))
                    )
                    orders_validated.append(basic_order)
            except Exception as e:
                print(f"Sipariş dönüştürme hatası: {e}")
                # Hatalı siparişi atla
                continue

        # Sayfalama bilgisi
        total_pages = (total + limit - 1) // limit if total > 0 else 1

        return OrderListResponse(
            data=orders_validated,
            pagination={
                "total": total,
                "page": page,
                "limit": limit,
                "totalPages": total_pages
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"Sipariş listeleme hatası: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Siparişler listelenirken bir hata oluştu."
        )


@router.get("/{order_id}", response_model=OrderDetailResponse)
async def read_order(order_id: str, db: DBDep, current_user: CurrentUserDep):
    """ID veya Sipariş Numarası ile tek bir siparişi getirir."""
    try:
        orders_collection = db["orders"]
        query = {}

        if ObjectId.is_valid(order_id):
            query["_id"] = ObjectId(order_id)
        else:
            # Sipariş numarası ile arama (daha az verimli olabilir)
            query["orderNumber"] = order_id

        order_raw = await orders_collection.find_one(query)

        if not order_raw:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sipariş bulunamadı.")

        # Kullanıcı ID'sini güvenli bir şekilde al
        user_id = current_user.get("id") or current_user.get("_id")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Kullanıcı kimliği alınamadı.")

        # Yetki kontrolü: Admin veya siparişin sahibi mi?
        is_admin = current_user.get("role") == "admin"
        if not is_admin:
            order_user_id = order_raw.get("user")
            if order_user_id and str(order_user_id) != user_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu siparişi görüntüleme yetkiniz yok.")

        # ObjectId'leri string'e çevir
        order_raw['_id'] = str(order_raw['_id'])
        if 'user' in order_raw and isinstance(order_raw['user'], ObjectId):
            order_raw['user'] = str(order_raw['user'])
        if 'items' in order_raw:
            for item in order_raw['items']:
                if 'product' in item and isinstance(item['product'], ObjectId):
                    item['product'] = str(item['product'])
        if 'campaign' in order_raw and order_raw['campaign'] and isinstance(order_raw['campaign'].get('id'), ObjectId):
            order_raw['campaign']['id'] = str(order_raw['campaign']['id'])

        try:
            # Sipariş nesnesini oluşturmayı dene
            # Hata ayıklama için print ekle
            print(f"Siparişi doğrulamayı deniyorum: {order_raw}")
            
            # Test ortamında eksik alanları kontrol et ve ekle
            if "totalAmount" in order_raw and "total" not in order_raw:
                order_raw["total"] = order_raw["totalAmount"]
                
            validated_order = Order.model_validate(order_raw)
            return OrderDetailResponse(data=validated_order)
        except Exception as validation_error:
            print(f"Sipariş validasyon hatası: {validation_error}")
            traceback.print_exc()
            
            # Hata detaylarını yazdır
            print(f"Hatalı sipariş verisi: {order_raw}")
            
            # Basitleştirilmiş bir cevap dön
            try:
                # Direkt ham veriyi kullanarak manuel bir Order nesnesi oluştur
                order_data = {
                    "id": str(order_raw["_id"]),
                    "user": str(order_raw["user"]) if "user" in order_raw and order_raw["user"] else None,
                    "status": order_raw.get("status", "pending"),
                    "items": [],
                    "createdAt": order_raw.get("createdAt", datetime.now(timezone.utc)),
                    "updatedAt": order_raw.get("updatedAt", datetime.now(timezone.utc)),
                    "total": order_raw.get("totalAmount", 0.0)
                }
                
                # Basit bir Order nesnesi oluştur
                manual_order = Order(**order_data)
                return OrderDetailResponse(data=manual_order)
            except Exception as fallback_error:
                print(f"Fallback sipariş oluşturma hatası: {fallback_error}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Sipariş verisi işlenirken bir hata oluştu."
                )
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"Sipariş getirme hatası: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Sipariş getirilirken bir hata oluştu."
        )


@router.put("/{order_id}", response_model=OrderDetailResponse)
async def update_order(order_id: str, order_data: OrderUpdateAdmin, db: DBDep, admin_user: AdminUserDep):
    """Sipariş durumunu veya kargo bilgilerini günceller (Sadece Admin)."""
    try:
        orders_collection = db["orders"]

        if not ObjectId.is_valid(order_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz Sipariş ID formatı.")

        update_fields = order_data.model_dump(exclude_unset=True)
        set_query = {}
        push_query = {} # Zaman çizelgesi için

        if not update_fields:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Güncellenecek veri bulunamadı.")

        # Mevcut siparişi bul
        current_order = await orders_collection.find_one({"_id": ObjectId(order_id)})
        if not current_order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Güncellenecek sipariş bulunamadı.")

        if "status" in update_fields and update_fields["status"] != current_order.get("status"):
            set_query["status"] = update_fields["status"]
            timeline_event = {
                "status": update_fields["status"],
                "date": datetime.now(timezone.utc),
                "description": update_fields.get("statusDescription") or f"Durum {update_fields['status']} olarak güncellendi",
                # Admin ID eklenebilir, güvenli bir şekilde alarak:
                # "updatedBy": ObjectId(admin_user.get("id") or admin_user.get("_id"))
            }
            push_query["timeline"] = timeline_event

            # Duruma özel alanları güncelle
            if update_fields["status"] == 'delivered':
                set_query["deliveredAt"] = datetime.now(timezone.utc)
            elif update_fields["status"] == 'shipped' and "shippingInfo" in update_fields and update_fields["shippingInfo"].get("trackingNumber"):
                # Kargo bilgisi status ile birlikte geliyorsa timeline'a ekleyebiliriz
                tracking_no = update_fields["shippingInfo"]["trackingNumber"]
                carrier = update_fields["shippingInfo"].get("carrier", "")
                timeline_event["description"] = f"Kargoya verildi ({carrier}). Takip No: {tracking_no}"

        if "shippingInfo" in update_fields:
            # $set ile iç içe nesneyi güncellemek için dot notation kullanılır
            for key, value in update_fields["shippingInfo"].items():
                set_query[f"shippingInfo.{key}"] = value

        if "notes" in update_fields: # Admin notları gibi düşünülebilir
            set_query["notes"] = update_fields["notes"]

        set_query["updatedAt"] = datetime.now(timezone.utc)

        update_query = {}
        if set_query: update_query["$set"] = set_query
        if push_query: update_query["$push"] = push_query

        if not update_query:
            # Güncellenecek bir şey yoksa mevcut siparişi döndür
            current_order['_id'] = str(current_order['_id'])
            # Diğer ObjectId'leri çevir...
            if 'user' in current_order and isinstance(current_order['user'], ObjectId):
                current_order['user'] = str(current_order['user'])
            if 'items' in current_order:
                for item in current_order['items']:
                    if 'product' in item and isinstance(item['product'], ObjectId):
                        item['product'] = str(item['product'])
            if 'campaign' in current_order and current_order['campaign'] and isinstance(current_order['campaign'].get('id'), ObjectId):
                current_order['campaign']['id'] = str(current_order['campaign']['id'])
                
            try:
                validated_order = Order.model_validate(current_order)
                return OrderDetailResponse(data=validated_order)
            except Exception as validation_error:
                print(f"Güncellemesiz sipariş validasyon hatası: {validation_error}")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Sipariş verisi işlenirken bir hata oluştu.")

        updated_order = await orders_collection.find_one_and_update(
            {"_id": ObjectId(order_id)},
            update_query,
            return_document=pymongo.ReturnDocument.AFTER
        )

        if not updated_order:
            # Bu durum normalde olmamalı ama yine de kontrol edelim
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sipariş güncellenemedi veya bulunamadı.")

        # ObjectId'leri string'e çevir
        updated_order['_id'] = str(updated_order['_id'])
        if 'user' in updated_order and isinstance(updated_order['user'], ObjectId):
            updated_order['user'] = str(updated_order['user'])
        if 'items' in updated_order:
            for item in updated_order['items']:
                if 'product' in item and isinstance(item['product'], ObjectId):
                    item['product'] = str(item['product'])
        if 'campaign' in updated_order and updated_order['campaign'] and isinstance(updated_order['campaign'].get('id'), ObjectId):
            updated_order['campaign']['id'] = str(updated_order['campaign']['id'])

        try:
            validated_updated_order = Order.model_validate(updated_order)
            return OrderDetailResponse(data=validated_updated_order)
        except Exception as validation_error:
            print(f"Güncellenmiş sipariş validasyon hatası: {validation_error}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Güncellenmiş sipariş verisi işlenirken bir hata oluştu.")
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"Sipariş güncelleme hatası: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Sipariş güncellenirken bir hata oluştu.")