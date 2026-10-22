from sqlalchemy import (
    Column, Integer, Float, String, DateTime,
    ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Cart(Base):
    __tablename__ = "carts"

    id         = Column(Integer, primary_key=True, index=True)
    admin_id   = Column(Integer, ForeignKey("admins.id"), unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    admin = relationship("Admin")
    items = relationship("CartItem", back_populates="cart",
                         cascade="all, delete-orphan")


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (
        UniqueConstraint("cart_id", "tile_id", name="uq_cart_tile"),
    )

    id       = Column(Integer, primary_key=True, index=True)
    cart_id  = Column(Integer, ForeignKey("carts.id"), nullable=False)
    tile_id  = Column(Integer, ForeignKey("tiles.id"), nullable=True)   # nullable: tile may be deleted
    quantity = Column(Integer, default=1, nullable=False)
    added_at = Column(DateTime(timezone=True), server_default=func.now())

    cart = relationship("Cart", back_populates="items")
    tile = relationship("Tile")


class Order(Base):
    __tablename__ = "orders"

    id           = Column(Integer, primary_key=True, index=True)
    admin_id     = Column(Integer, ForeignKey("admins.id"), nullable=False)
    status       = Column(String, default="placed", nullable=False)
    total_amount = Column(Float, nullable=True)   # null when prices unavailable
    placed_at    = Column(DateTime(timezone=True), server_default=func.now())

    admin = relationship("Admin")
    items = relationship("OrderItem", back_populates="order",
                         cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id         = Column(Integer, primary_key=True, index=True)
    order_id   = Column(Integer, ForeignKey("orders.id"), nullable=False)
    tile_id    = Column(Integer, ForeignKey("tiles.id"), nullable=True)   # nullable: tile may be deleted
    quantity   = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=True)   # snapshot of price_per_sqm at checkout

    order = relationship("Order", back_populates="items")
    tile  = relationship("Tile")
