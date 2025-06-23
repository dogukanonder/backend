# backend/models/product_models.py
from pydantic import BaseModel, Field, HttpUrl, ConfigDict, GetJsonSchemaHandler
from pydantic_core import core_schema
from typing import Optional, List, Dict, Any
from datetime import datetime
from bson import ObjectId

# ObjectId'yi JSON'a serileştirmek için özel tip
class PyObjectId(str):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if isinstance(v, ObjectId):
            return str(v)
        if not ObjectId.is_valid(v):
            return v
        return str(v)

    @classmethod
    def __get_pydantic_core_schema__(cls, _source_type, _handler):
        """Pydantic V2 serileştirici için şema"""
        from pydantic_core import PydanticCustomError, core_schema
        
        # Bir string'den ObjectId validation
        def validate_from_str(input_value: str) -> str:
            if ObjectId.is_valid(input_value):
                return str(input_value)
            raise PydanticCustomError("invalid_objectid", "Invalid ObjectId")
            
        # String'den validation için şema
        from_str_schema = core_schema.chain_schema([
            core_schema.str_schema(),
            core_schema.no_info_plain_validator_function(validate_from_str),
        ])
        
        # ObjectId'den string'e dönüşüm için şema
        from_objectid_schema = core_schema.chain_schema([
            core_schema.is_instance_schema(ObjectId),
            core_schema.no_info_plain_validator_function(lambda obj: str(obj)),
        ])
        
        # Birleşik şema
        return core_schema.union_schema([
            from_str_schema,
            from_objectid_schema,
        ])

# --- Varyant Modelleri ---
# ... (önceki gibi) ...
class VariantBase(BaseModel):
    size: str = Field(..., min_length=1, max_length=10)
    colorName: str = Field(..., min_length=1, max_length=50)
    colorHex: str = Field(..., pattern=r'^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$')
    stock: int = Field(..., ge=0)
    sku: str = Field(..., min_length=3, max_length=50)

class VariantCreate(VariantBase):
    pass

class Variant(VariantBase):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        arbitrary_types_allowed=True
    )

# --- Görsel Modelleri ---
# ... (önceki gibi) ...
class ImageBase(BaseModel):
    url: str = Field(..., min_length=1, max_length=500)  # HttpUrl yerine str kullan
    alt: str = ""
    isMain: bool = False

class ImageCreate(ImageBase):
    pass

class Image(ImageBase):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True
    )

# --- Ürün Modelleri ---
# ... (ProductBase, ProductCreate, ProductUpdate önceki gibi) ...
class ProductBase(BaseModel):
    name: str = Field(..., min_length=3, max_length=150)
    slug: str = Field(..., min_length=3, max_length=200, pattern=r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
    description: str = Field(..., min_length=10)
    richDescription: Optional[str] = None
    price: float = Field(..., gt=0)
    salePrice: Optional[float] = Field(None, gt=0)
    category: PyObjectId
    brand: str = Field("DOVL", max_length=50)
    tags: List[str] = []
    attributes: Optional[Dict[str, str]] = None
    isFeatured: bool = False
    isNew: bool = False
    isActive: bool = True

class ProductCreate(ProductBase):
    images: List[ImageCreate] = []
    variants: List[VariantCreate] = []

class ProductUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=3, max_length=150)
    slug: Optional[str] = Field(None, min_length=3, max_length=200, pattern=r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
    description: Optional[str] = Field(None, min_length=10)
    richDescription: Optional[str] = None
    price: Optional[float] = Field(None, gt=0)
    salePrice: Optional[float] = Field(None, ge=0)
    category: Optional[PyObjectId] = None
    brand: Optional[str] = Field(None, max_length=50)
    tags: Optional[List[str]] = None
    attributes: Optional[Dict[str, str]] = None
    isFeatured: Optional[bool] = None
    isNew: Optional[bool] = None
    isActive: Optional[bool] = None

class Product(ProductBase):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        arbitrary_types_allowed=True
    )
    id: PyObjectId = Field(..., alias='_id')
    images: List[Image] = []
    variants: List[Variant] = []
    totalStock: int = 0
    averageRating: float = 0
    numReviews: int = 0
    salesCount: int = 0
    viewCount: int = 0
    createdAt: datetime
    updatedAt: datetime
    category_details: Optional[Any] = Field(None, serialization_alias='categoryDetails', validation_alias='category')

class ProductListResponse(BaseModel):
    success: bool = True
    data: List[Product]
    pagination: Dict[str, int]