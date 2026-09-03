from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.middleware.auth import get_current_admin
from app.models.admin import Admin
from app.models.cart import Cart, CartItem, Order, OrderItem
from app.models.tile import Tile
from app.models.inventory import Inventory
from app.schemas.cart import (
    CartItemAdd, CartItemUpdate,
    CartItemOut, CartOut,
    OrderItemOut, OrderOut
)

router = APIRouter(prefix="/api/cart", tags=["Cart"])


# ── Helpers ───────────────────────────────────────────────

def _get_or_create_cart(db: Session, admin_id: int) -> Cart:
    """Fetch the admin's cart or create a fresh one."""
    cart = db.query(Cart).filter(Cart.admin_id == admin_id).first()
    if not cart:
        cart = Cart(admin_id=admin_id)
        db.add(cart)
        db.commit()
        db.refresh(cart)
    return cart


def _build_cart_item_out(item: CartItem) -> CartItemOut:
    tile = item.tile
    inv  = tile.inventory if tile else None

    price     = tile.price_per_sqm if tile else None
    subtotal  = (price * item.quantity) if price is not None else None
    image_url = tile.images[0].image_url if (tile and tile.images) else None

    return CartItemOut(
        id             = item.id,
        tile_id        = item.tile_id,
        quantity       = item.quantity,
        tile_name      = tile.name if tile else f"Tile #{item.tile_id}",
        tile_sku       = tile.sku  if tile else "N/A",
        tile_image_url = image_url,
        unit_price     = price,
        subtotal       = subtotal,
        stock_quantity = inv.quantity if inv else None,
        stock_unit     = inv.unit     if inv else "pieces",
        is_low_stock   = tile.low_stock if tile else False,
    )


def _build_cart_out(cart: Cart) -> CartOut:
    items_out = [_build_cart_item_out(i) for i in cart.items]
    subtotals = [i.subtotal for i in items_out if i.subtotal is not None]
    total     = round(sum(subtotals), 2) if subtotals else None
    return CartOut(
        id               = cart.id,
        item_count       = sum(i.quantity for i in cart.items),
        estimated_total  = total,
        items            = items_out,
    )


# ── Endpoints ─────────────────────────────────────────────

@router.get("", response_model=CartOut)
def get_cart(
    db:    Session = Depends(get_db),
    admin: Admin   = Depends(get_current_admin),
):
    """Return (or create) the current admin's cart."""
    cart = _get_or_create_cart(db, admin.id)
    # Eager-load items → tile → images/inventory
    db.refresh(cart)
    return _build_cart_out(cart)


@router.post("/add", response_model=CartItemOut)
def add_to_cart(
    body:  CartItemAdd,
    db:    Session = Depends(get_db),
    admin: Admin   = Depends(get_current_admin),
):
    """Add a tile to the cart, or increment its quantity if already present."""
    if body.quantity < 1:
        raise HTTPException(status_code=400, detail="Quantity must be at least 1")

    tile = db.query(Tile).filter(Tile.id == body.tile_id, Tile.is_active == True).first()
    if not tile:
        raise HTTPException(status_code=404, detail="Tile not found or inactive")

    cart = _get_or_create_cart(db, admin.id)

    existing = db.query(CartItem).filter(
        CartItem.cart_id == cart.id,
        CartItem.tile_id == body.tile_id,
    ).first()

    if existing:
        existing.quantity += body.quantity
        db.commit()
        db.refresh(existing)
        item = existing
    else:
        item = CartItem(cart_id=cart.id, tile_id=body.tile_id, quantity=body.quantity)
        db.add(item)
        db.commit()
        db.refresh(item)

    return _build_cart_item_out(item)


@router.patch("/item/{item_id}", response_model=CartItemOut)
def update_cart_item(
    item_id: int,
    body:    CartItemUpdate,
    db:      Session = Depends(get_db),
    admin:   Admin   = Depends(get_current_admin),
):
    """Update quantity for a specific cart item."""
    if body.quantity < 1:
        raise HTTPException(status_code=400, detail="Quantity must be at least 1")

    cart = _get_or_create_cart(db, admin.id)
    item = db.query(CartItem).filter(
        CartItem.id      == item_id,
        CartItem.cart_id == cart.id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Cart item not found")

    item.quantity = body.quantity
    db.commit()
    db.refresh(item)
    return _build_cart_item_out(item)


@router.delete("/item/{item_id}")
def remove_cart_item(
    item_id: int,
    db:      Session = Depends(get_db),
    admin:   Admin   = Depends(get_current_admin),
):
    """Remove a single item from the cart."""
    cart = _get_or_create_cart(db, admin.id)
    item = db.query(CartItem).filter(
        CartItem.id      == item_id,
        CartItem.cart_id == cart.id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Cart item not found")

    db.delete(item)
    db.commit()
    return {"message": "Item removed"}


@router.delete("/clear")
def clear_cart(
    db:    Session = Depends(get_db),
    admin: Admin   = Depends(get_current_admin),
):
    """Remove all items from the cart without deleting the cart itself."""
    cart = _get_or_create_cart(db, admin.id)
    db.query(CartItem).filter(CartItem.cart_id == cart.id).delete()
    db.commit()
    return {"message": "Cart cleared"}


@router.post("/checkout", response_model=OrderOut)
def checkout(
    db:    Session = Depends(get_db),
    admin: Admin   = Depends(get_current_admin),
):
    """
    Place an order from the current cart.
    - Validates stock availability (Option A: read-only check, no deduction).
    - Creates Order + OrderItem snapshot.
    - Clears cart items on success.
    """
    cart = _get_or_create_cart(db, admin.id)

    if not cart.items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    # ── Stock validation (read-only, no writes to inventory) ──
    stock_errors: List[str] = []
    for item in cart.items:
        tile = item.tile
        inv  = db.query(Inventory).filter(Inventory.tile_id == item.tile_id).first()
        if inv is None:
            continue  # inventory not configured — allow through
        if inv.quantity < item.quantity:
            name = tile.name if tile else f"Tile #{item.tile_id}"
            stock_errors.append(
                f"'{name}': requested {item.quantity}, only {inv.quantity} in stock"
            )

    if stock_errors:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Some items have insufficient stock",
                "errors": stock_errors,
            },
        )

    # ── Build order snapshot ──────────────────────────────────
    order_items_data = []
    total = 0.0
    has_price = False

    for item in cart.items:
        tile       = item.tile
        unit_price = tile.price_per_sqm if tile else None
        subtotal   = (unit_price * item.quantity) if unit_price is not None else None
        if subtotal is not None:
            total    += subtotal
            has_price = True
        order_items_data.append({
            "tile_id":    item.tile_id,
            "quantity":   item.quantity,
            "unit_price": unit_price,
        })

    order = Order(
        admin_id     = admin.id,
        status       = "placed",
        total_amount = round(total, 2) if has_price else None,
    )
    db.add(order)
    db.flush()  # get order.id without full commit

    for od in order_items_data:
        db.add(OrderItem(order_id=order.id, **od))

    # ── Clear cart items ──────────────────────────────────────
    db.query(CartItem).filter(CartItem.cart_id == cart.id).delete()

    db.commit()
    db.refresh(order)

    # ── Build response ────────────────────────────────────────
    order_items_out = []
    for oi in order.items:
        tile    = oi.tile
        sub     = (oi.unit_price * oi.quantity) if oi.unit_price is not None else None
        order_items_out.append(OrderItemOut(
            id         = oi.id,
            tile_id    = oi.tile_id,
            tile_name  = tile.name if tile else f"Tile #{oi.tile_id}",
            tile_sku   = tile.sku  if tile else "N/A",
            quantity   = oi.quantity,
            unit_price = oi.unit_price,
            subtotal   = sub,
        ))

    return OrderOut(
        id           = order.id,
        status       = order.status,
        total_amount = order.total_amount,
        placed_at    = order.placed_at,
        item_count   = sum(oi.quantity for oi in order.items),
        items        = order_items_out,
    )
