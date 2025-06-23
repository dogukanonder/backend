from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from datetime import datetime
from bson import ObjectId

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

class FavoriteItemCreate(BaseModel):
    productId: PyObjectId = Field(..., description="Ürün ID'si")

class FavoriteItem(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        arbitrary_types_allowed=True
    )
    id: PyObjectId = Field(..., alias='_id', description="Favori öğesi ID'si")
    userId: PyObjectId = Field(..., description="Kullanıcı ID'si")
    productId: PyObjectId = Field(..., description="Ürün ID'si")
    createdAt: datetime = Field(..., description="Oluşturulma tarihi")
    product: Optional[dict] = Field(None, description="Ürün detayları")

class FavoriteList(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "favorites": [
                    {
                        "id": "605c72aadd70e9a3e4e1f1ab",
                        "productId": "605c72aadd70e9a3e4e1f2cd",
                        "createdAt": "2023-01-01T10:00:00Z",
                        "product": {
                            "id": "605c72aadd70e9a3e4e1f2cd",
                            "name": "Çiçek Desenli Midi Elbise",
                            "slug": "cicek-desenli-midi-elbise",
                            "price": 750.00,
                            "salePrice": 550.00,
                            "image": "https://example.com/images/dresses/dress1.jpg",
                            "inStock": True
                        }
                    }
                ]
            }
        }
    )
    favorites: List[FavoriteItem] = [] 