# backend/routers/admin_dashboard.py
from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import Annotated, List, Dict, Any
from bson import ObjectId
from datetime import datetime, timezone, timedelta
import traceback

from database import get_db_dependency
from utils.security import get_current_admin_user
from models.user_models import UserPublic
from models.product_models import Product
from models.order_models import Order
from models.category_models import Category

router = APIRouter()
DBDep = Annotated[AsyncIOMotorDatabase, Depends(get_db_dependency)]
AdminDep = Annotated[dict, Depends(get_current_admin_user)]

@router.get("/stats")
async def get_dashboard_stats(db: DBDep, admin_user: AdminDep):
    """Admin dashboard için temel istatistikleri getirir."""
    try:
        # Koleksiyonları tanımla
        users_collection = db["users"]
        products_collection = db["products"]
        orders_collection = db["orders"]
        categories_collection = db["categories"]
        
        # Temel sayılar
        total_users = await users_collection.count_documents({"role": {"$ne": "admin"}})
        total_products = await products_collection.count_documents({"isActive": True})
        total_orders = await orders_collection.count_documents({})
        
        # Bekleyen siparişleri say
        pending_orders = await orders_collection.count_documents({
            "status": {"$in": ["pending", "processing"]}
        })
        
        # Toplam satış miktarını hesapla (tamamlanan siparişler)
        pipeline_total_sales = [
            {
                "$match": {
                    "status": {"$in": ["delivered", "completed"]},
                    "isPaid": True
                }
            },
            {
                "$group": {
                    "_id": None,
                    "totalSales": {"$sum": "$total"}
                }
            }
        ]
        total_sales_result = await orders_collection.aggregate(pipeline_total_sales).to_list(1)
        total_sales = total_sales_result[0]["totalSales"] if total_sales_result else 0
        
        # Bu ayki satışları hesapla
        start_of_month = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        pipeline_monthly_sales = [
            {
                "$match": {
                    "status": {"$in": ["delivered", "completed"]},
                    "isPaid": True,
                    "createdAt": {"$gte": start_of_month}
                }
            },
            {
                "$group": {
                    "_id": None,
                    "monthlySales": {"$sum": "$total"}
                }
            }
        ]
        monthly_sales_result = await orders_collection.aggregate(pipeline_monthly_sales).to_list(1)
        monthly_sales = monthly_sales_result[0]["monthlySales"] if monthly_sales_result else 0
        
        return {
            "success": True,
            "data": {
                "totalUsers": total_users,
                "totalProducts": total_products,
                "totalOrders": total_orders,
                "pendingOrders": pending_orders,
                "totalSales": total_sales,
                "monthlySales": monthly_sales
            }
        }
        
    except Exception as e:
        print(f"Dashboard stats error: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Dashboard istatistikleri alınırken hata oluştu."
        )

@router.get("/recent-orders")
async def get_recent_orders(db: DBDep, admin_user: AdminDep, limit: int = 5):
    """Son siparişleri getirir."""
    try:
        orders_collection = db["orders"]
        users_collection = db["users"]
        
        # Son siparişleri al
        pipeline = [
            {
                "$sort": {"createdAt": -1}
            },
            {
                "$limit": limit
            },
            {
                "$lookup": {
                    "from": "users",
                    "localField": "user",
                    "foreignField": "_id",
                    "as": "user_info"
                }
            }
        ]
        
        orders_raw = await orders_collection.aggregate(pipeline).to_list(limit)
        
        # Siparişleri formatla
        recent_orders = []
        for order_raw in orders_raw:
            try:
                # Kullanıcı bilgilerini al
                user_info = order_raw.get("user_info", [])
                customer_name = "Misafir Kullanıcı"
                customer_email = order_raw.get("userEmail", "")
                
                if user_info:
                    user = user_info[0]
                    customer_name = f"{user.get('name', '')} {user.get('surname', '')}".strip()
                    customer_email = user.get('email', customer_email)
                
                # Tarih formatla
                order_date = order_raw.get("createdAt", datetime.now(timezone.utc))
                formatted_date = order_date.strftime("%d.%m.%Y")
                
                # Durum Türkçe'ye çevir
                status_map = {
                    "pending": "Beklemede",
                    "processing": "Hazırlanıyor", 
                    "shipped": "Kargoda",
                    "delivered": "Teslim Edildi",
                    "cancelled": "İptal Edildi",
                    "refunded": "İade Edildi"
                }
                
                order_data = {
                    "id": str(order_raw["_id"]),
                    "orderNumber": order_raw.get("orderNumber", f"ORD-{str(order_raw['_id'])[:8]}"),
                    "customer": customer_name,
                    "email": customer_email,
                    "date": formatted_date,
                    "status": status_map.get(order_raw.get("status"), order_raw.get("status", "Belirsiz")),
                    "statusCode": order_raw.get("status", "pending"),
                    "total": float(order_raw.get("total", 0))
                }
                
                recent_orders.append(order_data)
                
            except Exception as e:
                print(f"Order formatting error: {e}")
                continue
        
        return {
            "success": True,
            "data": recent_orders
        }
        
    except Exception as e:
        print(f"Recent orders error: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Son siparişler alınırken hata oluştu."
        )

@router.get("/popular-products")
async def get_popular_products(db: DBDep, admin_user: AdminDep, limit: int = 5):
    """Popüler ürünleri getirir (satış sayısına göre)."""
    try:
        products_collection = db["products"]
        
        # Satış sayısına göre sırala
        pipeline = [
            {
                "$match": {"isActive": True}
            },
            {
                "$sort": {"salesCount": -1}
            },
            {
                "$limit": limit
            },
            {
                "$lookup": {
                    "from": "categories",
                    "localField": "category",
                    "foreignField": "_id",
                    "as": "category_info"
                }
            }
        ]
        
        products_raw = await products_collection.aggregate(pipeline).to_list(limit)
        
        # Ürünleri formatla
        popular_products = []
        for product_raw in products_raw:
            try:
                # Ana görseli al
                main_image = "https://placehold.co/150x200/gray/white?text=Ürün"
                if product_raw.get("images") and len(product_raw["images"]) > 0:
                    images = product_raw["images"]
                    # Ana görseli bul
                    main_img = next((img for img in images if img.get("isMain")), images[0])
                    main_image = str(main_img.get("url", main_image))
                
                # Kategori bilgisi
                category_info = product_raw.get("category_info", [])
                category_name = category_info[0].get("name", "Kategorisiz") if category_info else "Kategorisiz"
                
                product_data = {
                    "id": str(product_raw["_id"]),
                    "name": product_raw.get("name", ""),
                    "slug": product_raw.get("slug", ""),
                    "image": main_image,
                    "category": category_name,
                    "price": float(product_raw.get("price", 0)),
                    "salePrice": float(product_raw.get("salePrice", 0)) if product_raw.get("salePrice") else None,
                    "salesCount": product_raw.get("salesCount", 0),
                    "stock": product_raw.get("totalStock", 0),
                    "isActive": product_raw.get("isActive", True)
                }
                
                popular_products.append(product_data)
                
            except Exception as e:
                print(f"Product formatting error: {e}")
                continue
        
        return {
            "success": True,
            "data": popular_products
        }
        
    except Exception as e:
        print(f"Popular products error: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Popüler ürünler alınırken hata oluştu."
        )

@router.get("/category-distribution")
async def get_category_distribution(db: DBDep, admin_user: AdminDep):
    """Kategorilere göre ürün dağılımını getirir."""
    try:
        products_collection = db["products"]
        categories_collection = db["categories"]
        
        # Kategorilere göre ürün sayısı
        pipeline = [
            {
                "$match": {"isActive": True}
            },
            {
                "$group": {
                    "_id": "$category",
                    "count": {"$sum": 1}
                }
            },
            {
                "$lookup": {
                    "from": "categories",
                    "localField": "_id",
                    "foreignField": "_id",
                    "as": "category_info"
                }
            }
        ]
        
        category_counts = await products_collection.aggregate(pipeline).to_list(None)
        
        # Formatla
        distribution = []
        for item in category_counts:
            category_info = item.get("category_info", [])
            if category_info:
                category = category_info[0]
                distribution.append({
                    "categoryId": str(item["_id"]),
                    "categoryName": category.get("name", "Belirsiz"),
                    "productCount": item["count"]
                })
        
        return {
            "success": True,
            "data": distribution
        }
        
    except Exception as e:
        print(f"Category distribution error: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Kategori dağılımı alınırken hata oluştu."
        )

@router.get("/sales-chart")
async def get_sales_chart(db: DBDep, admin_user: AdminDep, days: int = 7):
    """Belirtilen gün sayısı için satış grafiği verilerini getirir."""
    try:
        orders_collection = db["orders"]
        
        # Son X günlük satış verilerini al
        start_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        pipeline = [
            {
                "$match": {
                    "status": {"$in": ["delivered", "completed"]},
                    "isPaid": True,
                    "createdAt": {"$gte": start_date}
                }
            },
            {
                "$group": {
                    "_id": {
                        "year": {"$year": "$createdAt"},
                        "month": {"$month": "$createdAt"},
                        "day": {"$dayOfMonth": "$createdAt"}
                    },
                    "totalSales": {"$sum": "$total"},
                    "orderCount": {"$sum": 1}
                }
            },
            {
                "$sort": {"_id": 1}
            }
        ]
        
        sales_data = await orders_collection.aggregate(pipeline).to_list(None)
        
        # Formatla
        chart_data = []
        for item in sales_data:
            date_obj = datetime(
                item["_id"]["year"],
                item["_id"]["month"], 
                item["_id"]["day"]
            )
            chart_data.append({
                "date": date_obj.strftime("%d.%m.%Y"),
                "sales": float(item["totalSales"]),
                "orders": item["orderCount"]
            })
        
        return {
            "success": True,
            "data": chart_data
        }
        
    except Exception as e:
        print(f"Sales chart error: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Satış grafiği verileri alınırken hata oluştu."
        )