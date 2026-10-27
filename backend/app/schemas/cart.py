from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


# ── Request bodies ────────────────────────────────────────

class CartItemAdd(BaseModel):
    tile_id: int
    quantity: int = 1


class CartItemUpdate(BaseModel):
    quantity: int


# ── Response shapes ───────────────────────────────────────

class CartItemOut(BaseModel):
    id: int
    tile_id: int
    quantity: int
    tile_name: str
    tile_sku: str
    tile_image_url: Optional[str]
    unit_price: Optional[float]      # price_per_sqm, may be null
    subtotal: Optional[float]        # unit_price * quantity, may be null
    stock_quantity: Optional[int]
    stock_unit: str
    is_low_stock: bool

    class Config:
        from_attributes = True


class CartOut(BaseModel):
    id: int
    item_count: int
    estimated_total: Optional[float]
    items: List[CartItemOut]

    class Config:
        from_attributes = True


class OrderItemOut(BaseModel):
    id: int
    tile_id: int
    tile_name: str
    tile_sku: str
    quantity: int
    unit_price: Optional[float]
    subtotal: Optional[float]

    class Config:
        from_attributes = True


class OrderOut(BaseModel):
    id: int
    status: str
    total_amount: Optional[float]
    placed_at: datetime
    item_count: int
    items: List[OrderItemOut]

    class Config:
        from_attributes = True


class OrderTrackingUpdate(BaseModel):
    status: Optional[str] = None
    tracking_number: Optional[str] = None
    carrier: Optional[str] = None
    dispatched_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    expected_delivery_at: Optional[datetime] = None
