# backend/models/cart_models.py
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime
from .product_models import PyObjectId # ObjectId tipi için import

class CartItemVariant(BaseModel):
    size: str
    colorName: str
    colorHex: str
    sku: str

class CartItemBase(BaseModel):
    product: PyObjectId
    variantSku: str # Hangi varyantın sepete eklendiğini bilmek için SKU önemli
    quantity: int = Field(..., gt=0)

class CartItemCreate(CartItemBase):
    pass

class CartItem(CartItemBase):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        arbitrary_types_allowed=True
    )
    # Veritabanından okunan item detayları (productName vb. dinamik olarak hesaplanır)
    id: Optional[PyObjectId] = Field(None, alias='_id') # Sepet item'ının kendi ID'si
    productName: str
    productSlug: str
    productImage: str
    variant: CartItemVariant
    price: float # Ürünün sepete eklenme anındaki fiyatı
    originalPrice: Optional[float] = None
    subtotal: float

class CartCampaign(BaseModel):
    id: PyObjectId
    code: str
    discountType: str
    discountValue: float
    discountAmount: float # Uygulanan indirim tutarı

class Cart(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        arbitrary_types_allowed=True
    )
    id: Optional[PyObjectId] = Field(None, alias='_id')
    user: Optional[PyObjectId] = None
    sessionId: Optional[str] = None
    items: List[CartItem] = []
    subtotal: float = 0
    discountAmount: float = 0
    shippingCost: float = 0
    taxAmount: float = 0
    total: float = 0
    campaign: Optional[CartCampaign] = None
    createdAt: datetime
    updatedAt: datetime

class CartResponse(BaseModel):
    success: bool = True
    data: Cart

class AddToCartRequest(BaseModel):
    productId: PyObjectId
    variantSku: str
    quantity: int = Field(1, gt=0)

class UpdateCartItemRequest(BaseModel):
    itemId: PyObjectId # Sepet item'ının ID'si
    quantity: int = Field(..., gt=0)

class ApplyCampaignRequest(BaseModel):
    code: str = Field(..., min_length=1)