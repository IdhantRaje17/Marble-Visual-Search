from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from sqlalchemy import func
from app.database import get_db
from app.middleware.auth import get_current_admin
from app.models.inventory import Inventory, WarehouseLocation
from app.models.tile import Tile
from app.models.inventory_movement import InventoryMovement
from app.models.admin import Admin
from app.schemas.inventory import (
    InventoryUpdate, InventoryOut, InventoryTileUpdate, StockUpdate,
    LocationCreate, LocationUpdate, LocationOut
)

router = APIRouter(prefix="/api/inventory", tags=["Inventory"])
loc_router = APIRouter(prefix="/api/locations", tags=["Warehouse"])


class MovementCreate(BaseModel):
    tile_id: int = Field(gt=0)
    movement_type: str
    quantity: int = Field(gt=0)
    direction: int | None = None
    reason: str | None = None
    reference_type: str | None = None
    reference_id: int | None = None
    occurred_at: datetime | None = None


def _record_movement(
    db: Session,
    account: Admin | None,
    inv: Inventory,
    movement_type: str,
    quantity: int,
    direction: int,
    reason: str | None = None,
    reference_type: str | None = None,
    reference_id: int | None = None,
    occurred_at: datetime | None = None,
):
    tile = db.query(Tile).filter(Tile.id == inv.tile_id).first()
    db.add(InventoryMovement(
        tile_id=inv.tile_id,
        tile_sku=tile.sku if tile else f"Tile #{inv.tile_id}",
        tile_name=tile.name if tile else "Unavailable tile",
        movement_type=movement_type,
        quantity=quantity,
        direction=direction,
        unit=inv.unit,
        balance_after=inv.quantity,
        reference_type=reference_type,
        reference_id=reference_id,
        reason=reason,
        occurred_at=occurred_at or datetime.now(timezone.utc),
        created_by=account.id if account else None,
    ))

# ── Get All Inventory ────────────────────────────────────
@router.get("/", response_model=list[InventoryOut])
def get_all_inventory(db: Session = Depends(get_db),
                      _=Depends(get_current_admin)):
    return db.query(Inventory).all()

# ── Update Stock ─────────────────────────────────────────
@router.put("/{tile_id}", response_model=InventoryOut)
def update_stock(tile_id: int, body: InventoryUpdate,
                 db: Session = Depends(get_db),
                 account=Depends(get_current_admin)):
    inv = db.query(Inventory).filter(Inventory.tile_id == tile_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Inventory not found")

    previous = inv.quantity
    inv.quantity = body.quantity
    inv.unit = body.unit
    inv.low_stock_threshold = body.low_stock_threshold
    if body.quantity != previous:
        _record_movement(
            db, account, inv, "adjustment",
            abs(body.quantity - previous),
            1 if body.quantity >= previous else -1,
            "Manual stock update",
        )
    db.commit()
    db.refresh(inv)
    return inv


@router.post("/movements")
def create_movement(
    body: MovementCreate,
    db: Session = Depends(get_db),
    account=Depends(get_current_admin),
):
    allowed = {"purchase", "production_receipt", "sale", "return", "adjustment"}
    if body.movement_type not in allowed:
        raise HTTPException(status_code=422, detail="Unsupported movement type")

    inv = db.query(Inventory).filter(Inventory.tile_id == body.tile_id).with_for_update().first()
    if not inv:
        raise HTTPException(status_code=404, detail="Inventory not found for this tile")

    if body.movement_type == "adjustment":
        direction = body.direction if body.direction in (-1, 1) else 0
    else:
        direction = -1 if body.movement_type == "sale" else 1
        if body.movement_type == "return":
            direction = 1

    if direction == 0:
        raise HTTPException(status_code=422, detail="Adjustment direction must be 1 or -1")
    new_quantity = inv.quantity + direction * body.quantity
    if new_quantity < 0:
        raise HTTPException(status_code=409, detail="Movement would make stock negative")

    inv.quantity = new_quantity
    _record_movement(
        db, account, inv, body.movement_type, body.quantity, direction,
        body.reason, body.reference_type, body.reference_id, body.occurred_at,
    )
    db.commit()
    db.refresh(inv)
    return {
        "tile_id": inv.tile_id,
        "quantity": inv.quantity,
        "movement_type": body.movement_type,
    }


@router.get("/movements")
def list_movements(
    tile_id: int | None = Query(None),
    movement_type: str | None = Query(None),
    start_date=None,
    end_date=None,
    db: Session = Depends(get_db),
    account=Depends(get_current_admin),
):
    query = db.query(InventoryMovement)
    if tile_id is not None:
        query = query.filter(InventoryMovement.tile_id == tile_id)
    if movement_type:
        query = query.filter(InventoryMovement.movement_type == movement_type)
    if start_date:
        query = query.filter(func.date(InventoryMovement.occurred_at) >= str(start_date))
    if end_date:
        query = query.filter(func.date(InventoryMovement.occurred_at) <= str(end_date))
    rows = query.order_by(InventoryMovement.occurred_at.desc(), InventoryMovement.id.desc()).limit(500).all()
    return [{
        "id": row.id,
        "tile_id": row.tile_id,
        "tile_sku": row.tile_sku,
        "tile_name": row.tile_name,
        "movement_type": row.movement_type,
        "quantity": row.quantity,
        "direction": row.direction,
        "unit": row.unit,
        "balance_after": row.balance_after,
        "reference_type": row.reference_type,
        "reference_id": row.reference_id,
        "reason": row.reason,
        "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
    } for row in rows]


# ── Get Inventory for One Tile ───────────────────────────
@router.get("/{tile_id}", response_model=InventoryOut)
def get_inventory(tile_id: int, db: Session = Depends(get_db),
                  _=Depends(get_current_admin)):
    inv = db.query(Inventory).filter(Inventory.tile_id == tile_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Inventory not found")
    return inv


@router.put("/{tile_id}/details", response_model=InventoryOut)
def update_tile_and_stock(tile_id: int, body: InventoryTileUpdate,
                          db: Session = Depends(get_db),
                          account=Depends(get_current_admin)):
    inv = db.query(Inventory).filter(Inventory.tile_id == tile_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Inventory not found")

    tile = db.query(Tile).filter(Tile.id == tile_id).first()
    if not tile:
        raise HTTPException(status_code=404, detail="Tile not found")

    tile_fields = body.model_dump(
        exclude_unset=True,
        exclude={"quantity", "unit", "low_stock_threshold"},
    )
    for field, value in tile_fields.items():
        setattr(tile, field, value)

    previous = inv.quantity
    inv.quantity = body.quantity
    inv.unit = body.unit
    inv.low_stock_threshold = body.low_stock_threshold
    if body.quantity != previous:
        _record_movement(
            db, account, inv, "adjustment",
            abs(body.quantity - previous),
            1 if body.quantity >= previous else -1,
            "Tile details and stock update",
        )
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(inv)
    return inv


# ── Update Stock via POST (support UI endpoint) ───────────
@router.post("/update-stock", response_model=InventoryOut)
def update_stock_post(body: StockUpdate,
                      db: Session = Depends(get_db),
                      account=Depends(get_current_admin)):
    inv = db.query(Inventory).filter(Inventory.tile_id == body.tile_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Inventory not found")

    previous = inv.quantity
    inv.quantity = body.quantity
    inv.unit = body.unit
    inv.low_stock_threshold = body.low_stock_threshold
    if body.quantity != previous:
        _record_movement(
            db, account, inv, "adjustment",
            abs(body.quantity - previous),
            1 if body.quantity >= previous else -1,
            "Stock update",
        )
    db.commit()
    db.refresh(inv)
    return inv

# ── Low Stock Alert ──────────────────────────────────────
@router.get("/alerts/low-stock")
def low_stock(db: Session = Depends(get_db),
              _=Depends(get_current_admin)):
    items = db.query(Inventory).filter(
        Inventory.quantity <= Inventory.low_stock_threshold
    ).all()
    return {
        "count": len(items),
        "items": [{"tile_id": i.tile_id,
                   "quantity": i.quantity,
                   "threshold": i.low_stock_threshold} for i in items]
    }

# ── Warehouse Locations ──────────────────────────────────
@loc_router.post("/", response_model=LocationOut)
def create_location(body: LocationCreate, db: Session = Depends(get_db),
                    _=Depends(get_current_admin)):
    existing = db.query(WarehouseLocation).filter(
        WarehouseLocation.tile_id == body.tile_id
    ).first()
    if existing:
        raise HTTPException(status_code=400,
                            detail="Location already assigned for this tile")

    loc = WarehouseLocation(**body.model_dump())
    db.add(loc)
    db.commit()
    db.refresh(loc)
    return loc

@loc_router.get("/", response_model=list[LocationOut])
def get_locations(db: Session = Depends(get_db),
                  _=Depends(get_current_admin)):
    return db.query(WarehouseLocation).all()

@loc_router.put("/{tile_id}", response_model=LocationOut)
def update_location(tile_id: int, body: LocationUpdate,
                    db: Session = Depends(get_db),
                    _=Depends(get_current_admin)):
    loc = db.query(WarehouseLocation).filter(
        WarehouseLocation.tile_id == tile_id
    ).first()
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(loc, field, value)

    db.commit()
    db.refresh(loc)
    return loc