from pydantic import BaseModel, Field, model_validator
from typing import Optional

class InventoryUpdate(BaseModel):
    quantity: int = Field(ge=0)
    unit: str = "pieces"
    low_stock_threshold: int = Field(default=10, ge=0)


class InventoryTileUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    texture: Optional[str] = None
    material_id: Optional[int] = Field(default=None, gt=0)
    style_id: Optional[int] = Field(default=None, gt=0)
    finish_id: Optional[int] = Field(default=None, gt=0)
    size_format_id: Optional[int] = Field(default=None, gt=0)
    application_id: Optional[int] = Field(default=None, gt=0)
    color_family_id: Optional[int] = Field(default=None, gt=0)
    origin_id: Optional[int] = Field(default=None, gt=0)
    width_cm: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    height_cm: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    thickness_cm: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    price_per_sqm: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    quantity: int = Field(ge=0)
    unit: str
    low_stock_threshold: int = Field(ge=0)

    @model_validator(mode="after")
    def material_cannot_be_cleared(self):
        if "material_id" in self.model_fields_set and self.material_id is None:
            raise ValueError("material_id cannot be null")
        return self

class InventoryOut(BaseModel):
    id: int
    tile_id: int
    quantity: int
    unit: str
    low_stock_threshold: int

    class Config:
        from_attributes = True

class StockUpdate(BaseModel):
    tile_id: int = Field(gt=0)
    quantity: int = Field(ge=0)
    unit: str = "pieces"
    low_stock_threshold: int = Field(default=10, ge=0)

class LocationCreate(BaseModel):
    tile_id: int
    aisle: str
    rack: str
    bin: str
    notes: Optional[str] = None

class LocationUpdate(BaseModel):
    aisle: Optional[str] = None
    rack: Optional[str] = None
    bin: Optional[str] = None
    notes: Optional[str] = None

class LocationOut(BaseModel):
    id: int
    tile_id: Optional[int]
    aisle: str
    rack: str
    bin: str
    notes: Optional[str]

    class Config:
        from_attributes = True