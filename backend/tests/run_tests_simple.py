import sys
import os
from pathlib import Path
from datetime import datetime
from bson.objectid import ObjectId

# Proje kök dizinini Python path'ine ekle
project_root = str(Path(__file__).parent.parent)
sys.path.append(project_root)

from models.order_models import Order, OrderItem, OrderItemVariant

def main():
    """Basit bir Order modeli testi"""
    print("===== Order Model Testi =====")
    
    # Test verisini hazırla
    now = datetime.now()
    order_data = {
        "_id": str(ObjectId()),
        "user": str(ObjectId()),
        "items": [
            {
                "product": str(ObjectId()),
                "quantity": 2,
                "price": 100.0
            }
        ],
        "totalAmount": 200.0,
        "status": "pending",
        "createdAt": now,
        "updatedAt": now
    }
    
    try:
        print("\nTest 1: Basit sipariş verisiyle doğrulama")
        # Order modeliyle doğrula
        order = Order(**order_data)
        print(f"Order ID: {order.id}")
        print(f"Order Status: {order.status}")
        print(f"Order Total: {order.total}")
        print("Test başarılı: ✓")
    except Exception as e:
        print(f"Test başarısız: ❌ - Hata: {e}")
    
    # Tam sipariş verisi ile test
    try:
        print("\nTest 2: Tam sipariş verisiyle doğrulama")
        full_order_data = {
            "_id": str(ObjectId()),
            "orderNumber": f"TEST-{now.strftime('%Y%m%d%H%M%S')}",
            "user": str(ObjectId()),
            "userEmail": "test@example.com",
            "items": [
                {
                    "product": str(ObjectId()),
                    "productName": "Test Ürün",
                    "productSlug": "test-urun",
                    "productImage": "https://via.placeholder.com/150",
                    "variant": {
                        "size": "M", 
                        "colorName": "Siyah",
                        "colorHex": "#000000",
                        "sku": "TST-001-S-M"
                    },
                    "price": 100.0,
                    "quantity": 2,
                    "subtotal": 200.0
                }
            ],
            "shippingAddress": {
                "title": "Ev Adresi",
                "fullName": "Test Kullanıcı",
                "address": "Test Adres",
                "street": "Test Sokak",
                "district": "Test Mahalle",
                "city": "Test Şehir",
                "country": "Türkiye",
                "zipCode": "12345",
                "phone": "05551234567"
            },
            "billingAddress": {
                "title": "Fatura Adresi",
                "fullName": "Test Kullanıcı",
                "address": "Test Fatura Adres",
                "street": "Test Fatura Sokak",
                "district": "Test Fatura Mahalle",
                "city": "Test Fatura Şehir",
                "country": "Türkiye",
                "zipCode": "12345",
                "phone": "05551234567"
            },
            "paymentMethod": "credit_card",
            "subtotal": 200.0,
            "shippingCost": 0.0,
            "taxAmount": 0.0,
            "total": 200.0,
            "status": "pending",
            "createdAt": now,
            "updatedAt": now
        }
        order = Order(**full_order_data)
        print(f"Order Number: {order.orderNumber}")
        print(f"Order Email: {order.userEmail}")
        print(f"Order PaymentMethod: {order.paymentMethod}")
        print(f"Order Item Name: {order.items[0].productName}")
        print("Test başarılı: ✓")
    except Exception as e:
        print(f"Test başarısız: ❌ - Hata: {e}")
    
    print("\n===== Test Tamamlandı =====")

if __name__ == "__main__":
    main() 