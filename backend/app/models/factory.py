from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class ProductionEntry(Base):
    __tablename__ = "production_entries"

    id = Column(Integer, primary_key=True, index=True)
    tile_id = Column(Integer, ForeignKey("tiles.id", ondelete="SET NULL"), nullable=True, index=True)
    tile_sku = Column(String, nullable=False)
    tile_name = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    factory_name = Column(String, nullable=False)
    batch_number = Column(String, nullable=True)
    produced_at = Column(Date, nullable=False)
    notes = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("admins.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    tile = relationship("Tile")
