# backend/models/campaign_models.py
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Any, Dict # <<< Dict'i buraya ekleyin
from datetime import datetime
from .product_models import PyObjectId # ObjectId tipi için import

class CampaignBase(BaseModel):
    name: str = Field(..., min_length=3, max_length=150)
    code: str = Field(..., min_length=3, max_length=50, pattern=r'^[A-Z0-9_]+$', description="Sadece büyük harf, rakam ve alt çizgi")
    description: Optional[str] = None
    discountType: str = Field(..., pattern=r'^(percentage|fixed_amount)$')
    discountValue: float = Field(..., gt=0)
    minPurchaseAmount: Optional[float] = Field(None, ge=0)
    maxDiscount: Optional[float] = Field(None, ge=0, description="Yüzde indirimler için maksimum TL tutarı")
    startDate: datetime
    endDate: datetime
    isActive: bool = True
    maxUses: Optional[int] = Field(None, ge=1, description="Toplam kullanım limiti")
    usagePerCustomer: Optional[int] = Field(1, ge=0, description="Müşteri başına kullanım (0=limitsiz)")
    applicableTo: str = Field("all_products", pattern=r'^(all_products|specific_categories|specific_products)$')
    categories: List[PyObjectId] = [] # Uygulanacak kategoriler
    products: List[PyObjectId] = [] # Uygulanacak ürünler
    excludedCategories: List[PyObjectId] = [] # Hariç tutulan kategoriler
    excludedProducts: List[PyObjectId] = [] # Hariç tutulan ürünler
    forNewCustomers: bool = False
    showInStore: bool = True # Mağazada gösterilsin mi?

class CampaignCreate(CampaignBase):
    code: Optional[str] = Field(None, min_length=3, max_length=50, pattern=r'^[A-Z0-9_]+$')

class CampaignUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=3, max_length=150)
    description: Optional[str] = None
    discountType: Optional[str] = Field(None, pattern=r'^(percentage|fixed_amount)$')
    discountValue: Optional[float] = Field(None, gt=0)
    minPurchaseAmount: Optional[float] = Field(None, ge=0)
    maxDiscount: Optional[float] = Field(None, ge=0)
    startDate: Optional[datetime] = None
    endDate: Optional[datetime] = None
    isActive: Optional[bool] = None
    maxUses: Optional[int] = Field(None, ge=1)
    usagePerCustomer: Optional[int] = Field(None, ge=0)
    applicableTo: Optional[str] = Field(None, pattern=r'^(all_products|specific_categories|specific_products)$')
    categories: Optional[List[PyObjectId]] = None
    products: Optional[List[PyObjectId]] = None
    excludedCategories: Optional[List[PyObjectId]] = None
    excludedProducts: Optional[List[PyObjectId]] = None
    forNewCustomers: Optional[bool] = None
    showInStore: Optional[bool] = None

class Campaign(CampaignBase):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        arbitrary_types_allowed=True
    )
    id: PyObjectId = Field(..., alias='_id')
    usageCount: int = 0
    createdAt: datetime
    updatedAt: datetime

class CampaignListResponse(BaseModel):
    success: bool = True
    data: List[Campaign]

class CampaignDetailResponse(BaseModel):
    success: bool = True
    data: Campaign

class CampaignCheckResponse(BaseModel):
    success: bool = True
    message: str
    # Dict import edildiği için artık hata vermemeli
    data: Dict[str, Any] # campaign ve discountAmount içerir