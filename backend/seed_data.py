# backend/seed_data.py
import asyncio
import random
from bson import ObjectId
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient
from passlib.context import CryptContext
import json
from slugify import slugify

# Şifre hash fonksiyonu
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Veritabanı bağlantısı
client = MongoClient("mongodb://localhost:27017/")
db = client["dovl_db_py"]  # Veritabanı adınızı kullanın

# Koleksiyonlar
users_collection = db["users"]
categories_collection = db["categories"]
products_collection = db["products"]
campaigns_collection = db["campaigns"]
orders_collection = db["orders"]

# Veritabanını temizle
def clear_database():
    print("Veritabanı temizleniyor...")
    users_collection.delete_many({})
    categories_collection.delete_many({})
    products_collection.delete_many({})
    campaigns_collection.delete_many({})
    orders_collection.delete_many({})
    print("Veritabanı temizlendi.")

# Kategorileri oluştur
def create_categories():
    print("Kategoriler oluşturuluyor...")
    categories = [
        {
            "name": "Elbise",
            "slug": "elbise",
            "description": "Modern ve şık elbise koleksiyonu",
            "image": "https://placehold.co/1200x1600/8B0000/FFFFFF/png?text=Elbise",
            "isActive": True,
            "order": 1,
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc)
        },
        {
            "name": "Bluz",
            "slug": "bluz",
            "description": "Günlük ve şık bluzlar",
            "image": "https://placehold.co/1200x1600/000000/FFFFFF/png?text=Bluz",
            "isActive": True,
            "order": 2,
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc)
        },
        {
            "name": "Etek",
            "slug": "etek",
            "description": "Her tarza uygun etekler",
            "image": "https://placehold.co/1200x1600/1A1A1A/FFFFFF/png?text=Etek",
            "isActive": True,
            "order": 3,
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc)
        },
        {
            "name": "Pantolon",
            "slug": "pantolon",
            "description": "Rahat ve şık pantolonlar",
            "image": "https://placehold.co/1200x1600/2D2D2D/FFFFFF/png?text=Pantolon",
            "isActive": True,
            "order": 4,
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc)
        },
        {
            "name": "Ceket",
            "slug": "ceket",
            "description": "Stil sahibi ceketler",
            "image": "https://placehold.co/1200x1600/4A4A4A/FFFFFF/png?text=Ceket",
            "isActive": True,
            "order": 5,
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc)
        },
        {
            "name": "Aksesuar",
            "slug": "aksesuar",
            "description": "Kombinlerinizi tamamlayacak aksesuarlar",
            "image": "https://placehold.co/1200x1600/5C5C5C/FFFFFF/png?text=Aksesuar",
            "isActive": True,
            "order": 6,
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc)
        }
    ]
    
    category_ids = []
    for category in categories:
        result = categories_collection.insert_one(category)
        category_ids.append(result.inserted_id)
        print(f"Kategori oluşturuldu: {category['name']}")
    
    print(f"{len(category_ids)} kategori oluşturuldu.")
    return category_ids

# Kullanıcıları oluştur
def create_users():
    print("Kullanıcılar oluşturuluyor...")
    # Admin kullanıcısı
    admin_user = {
        "name": "Admin",
        "surname": "User",
        "email": "admin@dovl.com",
        "hashed_password": pwd_context.hash("admin123"),
        "phone": "5551112233",
        "role": "admin",
        "isActive": True,
        "addresses": [
            {
                "_id": ObjectId(),
                "title": "İş Adresi",
                "fullName": "Admin User",
                "address": "Örnek Mahallesi, Admin Sokak No:1",
                "city": "İstanbul",
                "district": "Kadıköy",
                "postalCode": "34000",
                "country": "Türkiye",
                "phone": "5551112233",
                "isDefaultShipping": True,
                "isDefaultBilling": True
            }
        ],
        "wishlist": [],
        "orderHistory": [],
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc)
    }
    
    admin_id = users_collection.insert_one(admin_user).inserted_id
    print(f"Admin kullanıcı oluşturuldu: {admin_user['email']}")
    
    # 10 normal kullanıcı
    users = []
    for i in range(1, 11):
        user = {
            "name": f"Kullanıcı{i}",
            "surname": f"Soyad{i}",
            "email": f"user{i}@example.com",
            "hashed_password": pwd_context.hash(f"password{i}"),
            "phone": f"555{i:07d}",
            "role": "user",
            "isActive": True,
            "addresses": [
                {
                    "_id": ObjectId(),
                    "title": "Ev Adresi",
                    "fullName": f"Kullanıcı{i} Soyad{i}",
                    "address": f"Örnek Mahallesi, {i}. Sokak No:{i}",
                    "city": random.choice(["İstanbul", "Ankara", "İzmir", "Bursa", "Antalya"]),
                    "district": random.choice(["Kadıköy", "Beşiktaş", "Beyoğlu", "Üsküdar", "Şişli"]),
                    "postalCode": f"34{i:03d}",
                    "country": "Türkiye",
                    "phone": f"555{i:07d}",
                    "isDefaultShipping": True,
                    "isDefaultBilling": True
                }
            ],
            "wishlist": [],
            "orderHistory": [],
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc)
        }
        users.append(user)
    
    user_ids = [admin_id]
    if users:
        result = users_collection.insert_many(users)
        user_ids.extend(result.inserted_ids)
        print(f"{len(users)} normal kullanıcı oluşturuldu.")
    
    print(f"Toplam {len(user_ids)} kullanıcı oluşturuldu.")
    return user_ids

# Ürünleri oluştur
def create_products(category_ids):
    print("Ürünler oluşturuluyor...")
    products = []
    
    # Ürün isimleri
    product_names = {
        "elbise": ["Çiçekli Elbise", "Midi Boy Elbise", "Mini Elbise", "Maxi Elbise", "Keten Elbise", 
                "Günlük Elbise", "Gece Elbisi", "Kokteyl Elbise", "Yazlık Elbise", "Kışlık Elbise",
                "Triko Elbise", "İpek Elbise", "Pamuklu Elbise", "Saten Elbise", "Volanlı Elbise",
                "Asimetrik Kesim Elbise", "Vintage Elbise", "Modern Elbise", "Dantelli Elbise", "Basic Elbise"],
        "bluz": ["V Yaka Bluz", "Kruvaze Bluz", "Fırfırlı Bluz", "Gömlek Bluz", "Crop Bluz", 
               "Kolsuz Bluz", "Uzun Kollu Bluz", "İpek Bluz", "Saten Bluz", "Dantelli Bluz",
               "Desenli Bluz", "Çizgili Bluz", "Basic Bluz", "Volanlı Bluz", "Düğmeli Bluz",
               "Yırtmaçlı Bluz", "Bol Kesim Bluz", "Dar Kesim Bluz", "Asimetrik Bluz", "Omzu Açık Bluz"],
        "etek": ["Mini Etek", "Midi Etek", "Maxi Etek", "Kalem Etek", "Pileli Etek",
               "Denim Etek", "Kloş Etek", "Wrap Etek", "Çiçekli Etek", "Triko Etek",
               "Deri Etek", "Tüllü Etek", "Volanlı Etek", "Asimetrik Etek", "Düz Kesim Etek",
               "Yüksek Bel Etek", "Ekose Etek", "Çizgili Etek", "Saten Etek", "İpek Etek"],
        "pantolon": ["Skinny Jean", "Mom Jean", "Boyfriend Jean", "Wide Leg Pantolon", "Bol Paça Pantolon",
                   "Palazzo Pantolon", "Slim Fit Pantolon", "Jogger Pantolon", "Kalem Pantolon", "Chino Pantolon",
                   "Cargo Pantolon", "Kumaş Pantolon", "Keten Pantolon", "Deri Pantolon", "Kaprici Pantolon",
                   "Tayt", "Yüksek Bel Pantolon", "Düşük Bel Pantolon", "Paperbag Pantolon", "Flare Pantolon"],
        "ceket": ["Blazer Ceket", "Denim Ceket", "Deri Ceket", "Bomber Ceket", "Trençkot",
                "Kaşe Kaban", "Biker Ceket", "Kısa Ceket", "Uzun Ceket", "Oversized Ceket",
                "Kruvaze Ceket", "Düğmeli Ceket", "Kadife Ceket", "Kapitone Ceket", "Yün Ceket",
                "Ekose Ceket", "Çizgili Ceket", "Boyfriend Ceket", "Slim Fit Ceket", "Crop Ceket"],
        "aksesuar": ["Kolye", "Küpe", "Bileklik", "Yüzük", "Şal",
                   "Kemer", "Çanta", "Şapka", "Güneş Gözlüğü", "Saç Aksesuarı",
                   "Broş", "Halhal", "Saat", "Anahtarlık", "Eldiven",
                   "Bere", "Atkı", "Şemsiye", "Gözlük Zinciri", "Telefon Kılıfı"]
    }
    
    # Renkler
    colors = [
        {"name": "Siyah", "hex": "#000000"},
        {"name": "Beyaz", "hex": "#FFFFFF"},
        {"name": "Kırmızı", "hex": "#FF0000"},
        {"name": "Lacivert", "hex": "#000080"},
        {"name": "Mavi", "hex": "#0000FF"},
        {"name": "Yeşil", "hex": "#008000"},
        {"name": "Sarı", "hex": "#FFFF00"},
        {"name": "Pembe", "hex": "#FFC0CB"},
        {"name": "Mor", "hex": "#800080"},
        {"name": "Gri", "hex": "#808080"},
        {"name": "Bej", "hex": "#F5F5DC"},
        {"name": "Kahverengi", "hex": "#A52A2A"},
        {"name": "Turuncu", "hex": "#FFA500"},
        {"name": "Turkuaz", "hex": "#40E0D0"},
        {"name": "Bordo", "hex": "#800000"}
    ]
    
    # Bedenler
    sizes = ["XS", "S", "M", "L", "XL"]
    
    # Ürün oluşturma
    for category_id in category_ids:
        category = categories_collection.find_one({"_id": category_id})
        category_slug = category["slug"]
        
        # Bu kategori için ürün sayısı
        product_count = 20 if category_slug in product_names else 10
        
        for i in range(product_count):
            if category_slug in product_names and i < len(product_names[category_slug]):
                name = product_names[category_slug][i]
            else:
                name = f"{category['name']} {i+1}"
            
            slug = slugify(f"{name}-{random.randint(100, 999)}")
            
            # Fiyat
            price = float(random.randint(10, 50)) * 10  # 100 - 500 arası
            
            # İndirim
            has_discount = random.choice([True, False, False])  # %33 ihtimalle indirim
            sale_price = round(price * random.uniform(0.5, 0.9), 2) if has_discount else None
            
            # Özellikler
            variants = []
            total_stock = 0
            
            for color in random.sample(colors, random.randint(1, 3)):  # 1-3 arası renk
                for size in sizes:  # Tüm bedenler
                    stock = random.randint(0, 20)  # 0-20 arası stok
                    total_stock += stock
                    
                    variants.append({
                        "size": size,
                        "colorName": color["name"],
                        "colorHex": color["hex"],
                        "stock": stock,
                        "sku": f"{category_slug.upper()}-{slugify(color['name'])}-{size}-{random.randint(1000, 9999)}"
                    })
            
            # Görüntüler
            images = [
                {
                    "url": f"https://placehold.co/800x1100/{color['hex'].replace('#', '')}/FFFFFF/png?text={slugify(name)}",
                    "alt": name,
                    "isMain": index == 0
                }
                for index, color in enumerate(random.sample(colors, random.randint(1, 3)))
            ]
            
            # Ürün
            product = {
                "name": name,
                "slug": slug,
                "description": f"Bu {name.lower()}, günlük kullanım için uygundur. Modern tasarımı ve rahat yapısı ile kombinlerinizin vazgeçilmezi olacak.",
                "richDescription": f"<h3>{name} Özellikleri</h3><p>Bu {name.lower()}, premium kalite kumaştan üretilmiştir. Nefes alabilen yapısı ve şık tasarımı ile her ortama uyum sağlar.</p><h4>Malzeme Bilgisi</h4><p>%80 Pamuk, %20 Polyester</p><h4>Yıkama Talimatları</h4><p>30 derecede yıkayınız. Kuru temizleme yapılmaz. Ütü düşük ısıda yapılmalıdır.</p>",
                "images": images,
                "brand": "DOVL",
                "price": price,
                "salePrice": sale_price,
                "category": category_id,
                "tags": [category_slug, name.split()[0].lower(), "yeni", "trend"],
                "attributes": {
                    "Malzeme": random.choice(["Pamuk", "Polyester", "Keten", "İpek", "Viskon", "Denim", "Yün"]),
                    "Desen": random.choice(["Düz", "Çizgili", "Desenli", "Kareli", "Puantiyeli", "Baskılı"]),
                    "Mevsim": random.choice(["İlkbahar", "Yaz", "Sonbahar", "Kış", "Dört Mevsim"]),
                    "Kol Tipi": random.choice(["Uzun Kol", "Kısa Kol", "Kolsuz", "Yarım Kol", "Truvakar Kol"]),
                    "Yaka Tipi": random.choice(["V Yaka", "Bisiklet Yaka", "Boğazlı", "Hakim Yaka", "Kayık Yaka"])
                },
                "variants": variants,
                "totalStock": total_stock,
                "isFeatured": random.choice([True, False, False, False]),  # %25 ihtimalle öne çıkan
                "isNew": random.choice([True, False, False]),  # %33 ihtimalle yeni
                "isActive": True,
                "averageRating": round(random.uniform(3.5, 5.0), 1),
                "numReviews": random.randint(0, 50),
                "salesCount": random.randint(0, 100),
                "viewCount": random.randint(10, 500),
                "createdAt": datetime.now(timezone.utc) - timedelta(days=random.randint(0, 90)),
                "updatedAt": datetime.now(timezone.utc)
            }
            
            products.append(product)
    
    if products:
        result = products_collection.insert_many(products)
        print(f"{len(products)} ürün oluşturuldu.")
        return result.inserted_ids
    else:
        print("Ürün oluşturulamadı.")
        return []

# Kampanyaları oluştur
def create_campaigns():
    print("Kampanyalar oluşturuluyor...")
    campaigns = [
        {
            "name": "Hoş Geldin İndirimi",
            "code": "HOSGELDIN20",
            "description": "Yeni üyeler için %20 indirim",
            "discountType": "percentage",
            "discountValue": 20,
            "minPurchaseAmount": 100,
            "maxDiscount": 200,
            "startDate": datetime.now(timezone.utc) - timedelta(days=30),
            "endDate": datetime.now(timezone.utc) + timedelta(days=60),
            "isActive": True,
            "maxUses": 1000,
            "usageCount": 0,
            "usagePerCustomer": 1,
            "applicableTo": "all_products",
            "categories": [],
            "products": [],
            "excludedCategories": [],
            "excludedProducts": [],
            "forNewCustomers": True,
            "showInStore": True,
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc)
        },
        {
            "name": "Sezon Sonu İndirimi",
            "code": "SEZON50",
            "description": "Seçili ürünlerde %50'ye varan indirim",
            "discountType": "percentage",
            "discountValue": 50,
            "minPurchaseAmount": 200,
            "maxDiscount": None,
            "startDate": datetime.now(timezone.utc) - timedelta(days=10),
            "endDate": datetime.now(timezone.utc) + timedelta(days=20),
            "isActive": True,
            "maxUses": None,
            "usageCount": 0,
            "usagePerCustomer": 0,
            "applicableTo": "all_products",
            "categories": [],
            "products": [],
            "excludedCategories": [],
            "excludedProducts": [],
            "forNewCustomers": False,
            "showInStore": True,
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc)
        },
        {
            "name": "500TL Üzeri Kargo Bedava",
            "code": "KARGO500",
            "description": "500TL üzeri alışverişlerde kargo bedava",
            "discountType": "fixed_amount",
            "discountValue": 0,
            "minPurchaseAmount": 500,
            "maxDiscount": None,
            "startDate": datetime.now(timezone.utc) - timedelta(days=90),
            "endDate": datetime.now(timezone.utc) + timedelta(days=365),
            "isActive": True,
            "maxUses": None,
            "usageCount": 0,
            "usagePerCustomer": 0,
            "applicableTo": "all_products",
            "categories": [],
            "products": [],
            "excludedCategories": [],
            "excludedProducts": [],
            "forNewCustomers": False,
            "showInStore": True,
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc)
        },
        {
            "name": "Test Kuponu",
            "code": "DOVL20",
            "description": "Test amaçlı %20 indirim kuponu",
            "discountType": "percentage",
            "discountValue": 20,
            "minPurchaseAmount": 0,
            "maxDiscount": None,
            "startDate": datetime.now(timezone.utc) - timedelta(days=365),
            "endDate": datetime.now(timezone.utc) + timedelta(days=365),
            "isActive": True,
            "maxUses": None,
            "usageCount": 0,
            "usagePerCustomer": 0,
            "applicableTo": "all_products",
            "categories": [],
            "products": [],
            "excludedCategories": [],
            "excludedProducts": [],
            "forNewCustomers": False,
            "showInStore": True,
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc)
        }
    ]
    
    if campaigns:
        result = campaigns_collection.insert_many(campaigns)
        print(f"{len(campaigns)} kampanya oluşturuldu.")
        return result.inserted_ids
    else:
        print("Kampanya oluşturulamadı.")
        return []

# Siparişleri oluştur (opsiyonel)
def create_orders(user_ids, product_ids):
    print("Siparişler oluşturuluyor...")
    # Admin hariç kullanıcılar için siparişler
    orders = []
    
    # Sipariş durumları
    statuses = ["pending", "processing", "shipped", "delivered", "cancelled"]
    
    for user_id in user_ids[1:]:  # Adminleri geç
        # Her kullanıcı için 1-3 sipariş
        for _ in range(random.randint(1, 3)):
            # Random ürünler seç (2-5 arası)
            order_products = random.sample(product_ids, random.randint(2, 5))
            items = []
            subtotal = 0
            
            for product_id in order_products:
                product = products_collection.find_one({"_id": product_id})
                if not product:
                    continue
                
                # Random variant seç
                if not product.get("variants"):
                    continue
                
                variant = random.choice(product["variants"])
                quantity = random.randint(1, 3)
                price = product.get("salePrice") or product.get("price")
                
                item = {
                    "product": product_id,
                    "productName": product["name"],
                    "productSlug": product["slug"],
                    "productImage": product["images"][0]["url"] if product.get("images") else "",
                    "variant": {
                        "size": variant["size"],
                        "colorName": variant["colorName"],
                        "colorHex": variant["colorHex"],
                        "sku": variant["sku"]
                    },
                    "price": price,
                    "originalPrice": product["price"],
                    "quantity": quantity,
                    "subtotal": price * quantity
                }
                
                items.append(item)
                subtotal += price * quantity
            
            if not items:
                continue
            
            # Kullanıcı bilgilerini al
            user = users_collection.find_one({"_id": user_id})
            if not user or not user.get("addresses"):
                continue
            
            address = user["addresses"][0]
            
            # Sipariş verisi
            order_date = datetime.now(timezone.utc) - timedelta(days=random.randint(0, 60))
            status = random.choice(statuses)
            shipping_cost = 0 if subtotal >= 500 else 29.90
            tax_amount = subtotal * 0.18
            
            order = {
                "orderNumber": f"DOVL-{order_date.strftime('%y%m%d')}-{random.randint(1000, 9999)}",
                "user": user_id,
                "userEmail": user["email"],
                "items": items,
                "shippingAddress": {
                    "title": address.get("title"),
                    "fullName": address.get("fullName"),
                    "address": address.get("address"),
                    "city": address.get("city"),
                    "district": address.get("district"),
                    "postalCode": address.get("postalCode"),
                    "country": address.get("country"),
                    "phone": address.get("phone")
                },
                "billingAddress": {
                    "title": address.get("title"),
                    "fullName": address.get("fullName"),
                    "address": address.get("address"),
                    "city": address.get("city"),
                    "district": address.get("district"),
                    "postalCode": address.get("postalCode"),
                    "country": address.get("country"),
                    "phone": address.get("phone")
                },
                "paymentMethod": "credit_card",
                "paymentDetails": {
                    "provider": "Iyzico",
                    "transactionId": f"trx_{random.randint(10000000, 99999999)}",
                    "amount": subtotal + shipping_cost + tax_amount,
                    "status": "paid" if status != "cancelled" else "refunded",
                    "cardLast4": f"{random.randint(1000, 9999)}"
                },
                "subtotal": subtotal,
                "shippingCost": shipping_cost,
                "taxAmount": tax_amount,
                "total": subtotal + shipping_cost + tax_amount,
                "status": status,
                "notes": "",
                "isGuestCheckout": False,
                "shippingInfo": {},
                "timeline": [
                    {"status": "pending", "date": order_date, "description": "Sipariş oluşturuldu"},
                    {"status": "processing", "date": order_date + timedelta(hours=2), "description": "Ödeme onaylandı, sipariş hazırlanıyor"}
                ],
                "isPaid": status != "cancelled",
                "paidAt": order_date + timedelta(minutes=5) if status != "cancelled" else None,
                "deliveredAt": order_date + timedelta(days=3) if status == "delivered" else None,
                "createdAt": order_date,
                "updatedAt": order_date + timedelta(days=random.randint(0, 3))
            }
            
            # Sipariş durumuna göre zaman çizelgesini güncelle
            if status in ["shipped", "delivered"]:
                order["timeline"].append({
                    "status": "shipped",
                    "date": order_date + timedelta(days=1),
                    "description": "Sipariş kargoya verildi"
                })
                
                order["shippingInfo"] = {
                    "carrier": random.choice(["Yurtiçi Kargo", "Aras Kargo", "MNG Kargo"]),
                    "trackingNumber": f"TRK{random.randint(100000000, 999999999)}",
                    "trackingUrl": f"https://example.com/track/{random.randint(100000000, 999999999)}",
                    "estimatedDeliveryDate": order_date + timedelta(days=3)
                }
            
            if status == "delivered":
                order["timeline"].append({
                    "status": "delivered",
                    "date": order_date + timedelta(days=3),
                    "description": "Sipariş teslim edildi"
                })
            
            if status == "cancelled":
                order["timeline"].append({
                    "status": "cancelled",
                    "date": order_date + timedelta(days=1),
                    "description": "Sipariş iptal edildi"
                })
            
            orders.append(order)
    
    if orders:
        result = orders_collection.insert_many(orders)
        print(f"{len(orders)} sipariş oluşturuldu.")
        
        # Kullanıcıların sipariş geçmişlerini güncelle
        for order in orders:
            users_collection.update_one(
                {"_id": order["user"]},
                {"$push": {"orderHistory": order["_id"]}}
            )
        return result.inserted_ids
    else:
        print("Sipariş oluşturulamadı.")
        return []

# Ana fonksiyon
def seed_database():
    # Veritabanını temizle
    clear_database()
    
    # Kategorileri oluştur
    category_ids = create_categories()
    
    # Kullanıcıları oluştur
    user_ids = create_users()
    
    # Ürünleri oluştur
    product_ids = create_products(category_ids)
    
    # Kampanyaları oluştur
    campaign_ids = create_campaigns()
    
    # Siparişleri oluştur
    order_ids = create_orders(user_ids, product_ids)
    
    print("Veri tabanı hazırlama işlemi tamamlandı.")
    print(f"- {len(category_ids)} kategori")
    print(f"- {len(user_ids)} kullanıcı")
    print(f"- {len(product_ids)} ürün")
    print(f"- {len(campaign_ids)} kampanya")
    print(f"- {len(order_ids)} sipariş")
    
    # Admin bilgilerini göster
    print("\nAdmin kullanıcı bilgileri:")
    print("E-posta: admin@dovl.com")
    print("Şifre: admin123")
    
    print("\nTest kullanıcısı bilgileri:")
    print("E-posta: user1@example.com")
    print("Şifre: password1")

# Scripti çalıştır
if __name__ == "__main__":
    seed_database()