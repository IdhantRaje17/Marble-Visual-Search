from datetime import datetime
import re

from pydantic import BaseModel, Field, field_validator


class QuotationItemCreate(BaseModel):
    tile_id: int = Field(gt=0)
    quantity: int = Field(ge=1, le=100000)
    area_sqm: float = Field(gt=0, le=1000000, allow_inf_nan=False)
    rate_per_sqm: float = Field(ge=0, le=10000000, allow_inf_nan=False)


class QuotationCreate(BaseModel):
    client_name: str = Field(min_length=1, max_length=200)
    company_name: str | None = Field(default=None, max_length=200)
    project_name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = Field(default=None, max_length=2000)
    gst_rate: float = Field(default=18, ge=0, le=100, allow_inf_nan=False)
    items: list[QuotationItemCreate] = Field(min_length=1, max_length=100)

    @field_validator(
        "client_name", "company_name", "project_name", "email", "phone", "address",
        mode="before",
    )
    @classmethod
    def empty_to_none(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None):
        if value is None:
            return value
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("email must be a valid address")
        return value


class QuotationItemOut(BaseModel):
    id: int
    tile_id: int | None
    tile_name: str
    tile_sku: str
    material: str | None
    size_label: str | None
    catalog_rate_per_sqm: float | None
    quantity: int
    area_sqm: float
    rate_per_sqm: float
    line_total: float

    class Config:
        from_attributes = True


class QuotationOut(BaseModel):
    id: int
    quotation_number: str
    created_by: int
    created_by_name: str
    created_by_email: str
    client_name: str
    company_name: str | None
    project_name: str | None
    email: str | None
    phone: str | None
    address: str | None
    status: str
    gst_rate: float
    currency: str = "INR"
    subtotal: float
    gst_amount: float
    grand_total: float
    created_at: datetime
    valid_until: datetime
    items: list[QuotationItemOut]

    class Config:
        from_attributes = True
