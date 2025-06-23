# backend/models/category_models.py
from pydantic import BaseModel, Field, ConfigDict, HttpUrl
from typing import Optional, List, Any, Dict
from datetime import datetime
from bson import ObjectId
from .product_models import PyObjectId # ObjectId tipi için import

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

class CategoryBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    slug: str = Field(..., min_length=2, max_length=150, pattern=r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
    description: Optional[str] = None
    image: Optional[HttpUrl] = None
    parentCategory: Optional[PyObjectId] = None
    isActive: bool = True
    order: int = 0

class CategoryCreate(CategoryBase):
    pass

class CategoryUpdate(BaseModel):
    # Güncellemede alanlar opsiyonel
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    slug: Optional[str] = Field(None, min_length=2, max_length=150, pattern=r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
    description: Optional[str] = None
    image: Optional[HttpUrl] = None
    parentCategory: Optional[PyObjectId] = None # None gönderilirse üst kategori silinir
    isActive: Optional[bool] = None
    order: Optional[int] = None


class Category(CategoryBase):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        arbitrary_types_allowed=True # ObjectId için
    )
    id: PyObjectId = Field(..., alias='_id')
    createdAt: datetime
    updatedAt: datetime
    # Üst kategori detayını da içerebiliriz
    parent_details: Optional[Any] = Field(None, alias='parentCategory')

class CategoryListResponse(BaseModel):
    success: bool = True
    data: List[Category]