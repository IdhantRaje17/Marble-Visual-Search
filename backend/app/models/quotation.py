import uuid

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


def _temp_quotation_number() -> str:
    return f"QT-TEMP-{uuid.uuid4().hex}"


class Quotation(Base):
    __tablename__ = "quotations"

    id = Column(Integer, primary_key=True, index=True)
    quotation_number = Column(
        String, unique=True, nullable=False, default=_temp_quotation_number
    )
    created_by = Column(Integer, ForeignKey("admins.id"), nullable=False)
    search_id = Column(Integer, ForeignKey("search_logs.id", ondelete="SET NULL"), nullable=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True)
    client_name = Column(String, nullable=False)
    company_name = Column(String, nullable=True)
    project_name = Column(String, nullable=True)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    address = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="issued", server_default="issued")
    gst_rate = Column(Float, nullable=False, default=18)
    subtotal = Column(Float, nullable=False)
    gst_amount = Column(Float, nullable=False)
    grand_total = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    creator = relationship("Admin")
    items = relationship(
        "QuotationItem",
        back_populates="quotation",
        cascade="all, delete-orphan",
        order_by="QuotationItem.id",
    )


class QuotationItem(Base):
    __tablename__ = "quotation_items"

    id = Column(Integer, primary_key=True, index=True)
    quotation_id = Column(
        Integer, ForeignKey("quotations.id", ondelete="CASCADE"), nullable=False
    )
    tile_id = Column(Integer, ForeignKey("tiles.id", ondelete="SET NULL"), nullable=True)
    tile_name = Column(String, nullable=False)
    tile_sku = Column(String, nullable=False)
    material = Column(String, nullable=True)
    size_label = Column(String, nullable=True)
    catalog_rate_per_sqm = Column(Float, nullable=True)
    quantity = Column(Integer, nullable=False)
    area_sqm = Column(Float, nullable=False)
    rate_per_sqm = Column(Float, nullable=False)
    line_total = Column(Float, nullable=False)
    # Retained so databases created by the partial implementation remain writable.
    subtotal = Column(Float, nullable=True)

    quotation = relationship("Quotation", back_populates="items")
    tile = relationship("Tile")
