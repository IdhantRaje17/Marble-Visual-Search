from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class InventoryMovement(Base):
    __tablename__ = "inventory_movements"

    id = Column(Integer, primary_key=True, index=True)
    tile_id = Column(Integer, ForeignKey("tiles.id", ondelete="SET NULL"), nullable=True, index=True)
    tile_sku = Column(String, nullable=False)
    tile_name = Column(String, nullable=False)
    movement_type = Column(String, nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    direction = Column(Integer, nullable=False)
    unit = Column(String, nullable=False, default="pieces")
    balance_after = Column(Integer, nullable=True)
    reference_type = Column(String, nullable=True)
    reference_id = Column(Integer, nullable=True)
    reason = Column(Text, nullable=True)
    occurred_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    created_by = Column(Integer, ForeignKey("admins.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    tile = relationship("Tile")
