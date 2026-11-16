from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload
from typing import List

from app.database import get_db
from app.middleware.auth import get_current_account
from app.models.admin import Admin
from app.models.cart import Cart, CartItem, Order, OrderItem
from app.models.order_tracking import OrderStatusEvent
from app.models.tile import Tile
from app.models.inventory import Inventory
from app.models.inventory_movement import InventoryMovement
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
    admin: Admin   = Depends(get_current_account),
):
    """Return (or create) the current admin's cart."""
    cart = _get_or_create_cart(db, admin.id)
    # Eager-load items → tile → images/inventory
    db.refresh(cart)
    return _build_cart_out(cart)


@router.get("/orders/mine")
def get_my_orders(
    db: Session = Depends(get_db),
    account: Admin = Depends(get_current_account),
):
    """Return only orders owned by the authenticated account."""
    orders = (
        db.query(Order)
        .options(selectinload(Order.items).selectinload(OrderItem.tile))
        .options(selectinload(Order.tracking), selectinload(Order.status_events))
        .filter(Order.admin_id == account.id)
        .order_by(Order.placed_at.desc(), Order.id.desc())
        .all()
    )
    return [{
        "id": order.id,
        "status": order.status,
        "total_amount": order.total_amount,
        "placed_at": order.placed_at,
        "shipment": ({
            "tracking_number": order.tracking.tracking_number,
            "carrier": order.tracking.carrier,
            "dispatched_at": order.tracking.dispatched_at,
            "delivered_at": order.tracking.delivered_at,
            "expected_delivery_at": order.tracking.expected_delivery_at,
        } if order.tracking else None),
        "timeline": [{
            "status": event.status,
            "timestamp": event.created_at,
        } for event in order.status_events],
        "items": [{
            "tile_id": item.tile_id,
            "tile_name": item.tile.name if item.tile else f"Tile #{item.tile_id}",
            "tile_sku": item.tile.sku if item.tile else "N/A",
            "quantity": item.quantity,
            "unit_price": item.unit_price,
            "subtotal": item.unit_price * item.quantity if item.unit_price is not None else None,
        } for item in order.items],
    } for order in orders]


@router.post("/add", response_model=CartItemOut)
def add_to_cart(
    body:  CartItemAdd,
    db:    Session = Depends(get_db),
    admin: Admin   = Depends(get_current_account),
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
    admin:   Admin   = Depends(get_current_account),
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
    admin:   Admin   = Depends(get_current_account),
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
    admin: Admin   = Depends(get_current_account),
):
    """Remove all items from the cart without deleting the cart itself."""
    cart = _get_or_create_cart(db, admin.id)
    db.query(CartItem).filter(CartItem.cart_id == cart.id).delete()
    db.commit()
    return {"message": "Cart cleared"}


@router.post("/checkout", response_model=OrderOut)
def checkout(
    db:    Session = Depends(get_db),
    admin: Admin   = Depends(get_current_account),
):
    """
    Place an order from the current cart.
    - Locks the cart and inventory rows to prevent duplicate orders and overselling.
    - Deducts stock in the same transaction as order creation.
    - Creates Order + OrderItem snapshot.
    - Clears cart items on success.
    """
    try:
        if db.bind.dialect.name == "sqlite":
            db.connection().exec_driver_sql("BEGIN IMMEDIATE")
        cart = db.query(Cart).filter(Cart.admin_id == admin.id).with_for_update().first()
        if cart is None:
            cart = _get_or_create_cart(db, admin.id)
            raise HTTPException(status_code=400, detail="Cart is empty")

        cart_items = (
            db.query(CartItem)
            .options(selectinload(CartItem.tile))
            .filter(CartItem.cart_id == cart.id)
            .order_by(CartItem.tile_id, CartItem.id)
            .with_for_update()
            .all()
        )
        if not cart_items:
            raise HTTPException(status_code=400, detail="Cart is empty")

        inventory_by_tile = {
            inv.tile_id: inv
            for inv in (
                db.query(Inventory)
                .filter(Inventory.tile_id.in_([item.tile_id for item in cart_items]))
                .order_by(Inventory.tile_id)
                .with_for_update()
                .all()
            )
        }

        stock_errors: List[str] = []
        for item in cart_items:
            inv = inventory_by_tile.get(item.tile_id)
            name = item.tile.name if item.tile else f"Tile #{item.tile_id}"
            if inv is None:
                stock_errors.append(f"'{name}': inventory is not configured")
            elif inv.quantity < item.quantity:
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

        order_items_data = []
        total = 0.0
        has_all_prices = True
        for item in cart_items:
            tile = item.tile
            unit_price = tile.price_per_sqm if tile else None
            if unit_price is not None:
                total += unit_price * item.quantity
            else:
                has_all_prices = False
            order_items_data.append({
                "tile_id": item.tile_id,
                "quantity": item.quantity,
                "unit_price": unit_price,
            })

        order = Order(
            admin_id=admin.id,
            status="placed",
            total_amount=round(total, 2) if has_all_prices else None,
        )
        db.add(order)
        db.flush()
        db.add(OrderStatusEvent(order_id=order.id, status="placed"))

        for order_item_data in order_items_data:
            db.add(OrderItem(order_id=order.id, **order_item_data))

        for item in cart_items:
            inv = inventory_by_tile[item.tile_id]
            updated = (
                db.query(Inventory)
                .filter(
                    Inventory.id == inv.id,
                    Inventory.quantity >= item.quantity,
                )
                .update(
                    {Inventory.quantity: Inventory.quantity - item.quantity},
                    synchronize_session=False,
                )
            )
            if updated != 1:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "Some items have insufficient stock",
                        "errors": [f"'{item.tile.name if item.tile else item.tile_id}': stock changed during checkout"],
                    },
                )
            db.add(InventoryMovement(
                tile_id=item.tile_id,
                tile_sku=item.tile.sku if item.tile else f"Tile #{item.tile_id}",
                tile_name=item.tile.name if item.tile else "Unavailable tile",
                movement_type="sale",
                quantity=item.quantity,
                direction=-1,
                unit=inv.unit,
                balance_after=inv.quantity - item.quantity,
                reference_type="order",
                reference_id=order.id,
                reason="Completed checkout stock deduction",
                created_by=admin.id,
            ))

        db.query(CartItem).filter(CartItem.cart_id == cart.id).delete(
            synchronize_session=False
        )
        db.commit()
        db.refresh(order)

    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    order_items_out = []
    for order_item in order.items:
        tile = order_item.tile
        subtotal = (
            order_item.unit_price * order_item.quantity
            if order_item.unit_price is not None
            else None
        )
        order_items_out.append(OrderItemOut(
            id=order_item.id,
            tile_id=order_item.tile_id,
            tile_name=tile.name if tile else f"Tile #{order_item.tile_id}",
            tile_sku=tile.sku if tile else "N/A",
            quantity=order_item.quantity,
            unit_price=order_item.unit_price,
            subtotal=subtotal,
        ))

    return OrderOut(
        id=order.id,
        status=order.status,
        total_amount=order.total_amount,
        placed_at=order.placed_at,
        item_count=sum(order_item.quantity for order_item in order.items),
        items=order_items_out,
    )
