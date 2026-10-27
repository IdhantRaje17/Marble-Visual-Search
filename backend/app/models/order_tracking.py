from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class OrderTracking(Base):
    __tablename__ = "order_tracking"

    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), primary_key=True)
    tracking_number = Column(String, nullable=True)
    carrier = Column(String, nullable=True)
    dispatched_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    expected_delivery_at = Column(DateTime(timezone=True), nullable=True)

    order = relationship("Order", back_populates="tracking")


class OrderStatusEvent(Base):
    __tablename__ = "order_status_events"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    order = relationship("Order", back_populates="status_events")
