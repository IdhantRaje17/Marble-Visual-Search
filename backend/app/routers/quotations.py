from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.middleware.auth import get_current_admin
from app.models.admin import Admin
from app.models.quotation import Quotation, QuotationItem
from app.models.tile import Tile
from app.schemas.quotation import QuotationCreate, QuotationOut

router = APIRouter(prefix="/api/quotations", tags=["Quotations"])
VALIDITY_DAYS = 15


def _size_label(tile: Tile) -> str | None:
    if tile.size_format and tile.size_format.name:
        return tile.size_format.name
    if tile.width_cm and tile.height_cm:
        return f"{tile.width_cm:g} x {tile.height_cm:g} cm"
    return None


def _serialize(quotation: Quotation) -> dict:
    created_at = quotation.created_at
    return {
        "id": quotation.id,
        "quotation_number": quotation.quotation_number,
        "created_by": quotation.created_by,
        "created_by_name": quotation.creator.name if quotation.creator else "Unknown",
        "created_by_email": quotation.creator.email if quotation.creator else "",
        "client_name": quotation.client_name,
        "company_name": quotation.company_name,
        "project_name": quotation.project_name,
        "email": quotation.email,
        "phone": quotation.phone,
        "address": quotation.address,
        "status": quotation.status,
        "gst_rate": quotation.gst_rate,
        "currency": "INR",
        "subtotal": quotation.subtotal,
        "gst_amount": quotation.gst_amount,
        "grand_total": quotation.grand_total,
        "created_at": created_at,
        "valid_until": created_at + timedelta(days=VALIDITY_DAYS) if created_at else None,
        "items": [
            {
                "id": item.id,
                "tile_id": item.tile_id,
                "tile_name": item.tile_name,
                "tile_sku": item.tile_sku,
                "material": item.material,
                "size_label": item.size_label,
                "catalog_rate_per_sqm": item.catalog_rate_per_sqm,
                "quantity": item.quantity,
                "area_sqm": item.area_sqm,
                "rate_per_sqm": item.rate_per_sqm,
                "line_total": item.line_total,
            }
            for item in quotation.items
        ],
    }


def _load_query(db: Session):
    return db.query(Quotation).options(
        selectinload(Quotation.items),
        selectinload(Quotation.creator),
    )


@router.get("", response_model=list[QuotationOut])
def list_quotations(
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    quotations = (
        _load_query(db)
        .order_by(Quotation.created_at.desc(), Quotation.id.desc())
        .limit(100)
        .all()
    )
    return [_serialize(quotation) for quotation in quotations]


@router.get("/{quotation_id}", response_model=QuotationOut)
def get_quotation(
    quotation_id: int,
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    quotation = _load_query(db).filter(Quotation.id == quotation_id).first()
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    return _serialize(quotation)


@router.post("", response_model=QuotationOut, status_code=201)
def create_quotation(
    body: QuotationCreate,
    db: Session = Depends(get_db),
    account: Admin = Depends(get_current_admin),
):
    tile_ids = {item.tile_id for item in body.items}
    tiles = {
        tile.id: tile
        for tile in db.query(Tile).options(
            selectinload(Tile.material),
            selectinload(Tile.size_format),
        ).filter(Tile.id.in_(tile_ids), Tile.is_active.is_(True)).all()
    }
    missing = tile_ids - tiles.keys()
    if missing:
        raise HTTPException(
            status_code=422,
            detail="One or more selected tiles are missing or inactive. Dummy products cannot be quoted.",
        )

    quotation = Quotation(
        created_by=account.id,
        client_name=body.client_name,
        company_name=body.company_name,
        project_name=body.project_name,
        email=body.email,
        phone=body.phone,
        address=body.address,
        status="issued",
        gst_rate=body.gst_rate,
        subtotal=0,
        gst_amount=0,
        grand_total=0,
    )
    subtotal = 0.0
    for item in body.items:
        line_total = round(item.quantity * item.area_sqm * item.rate_per_sqm, 2)
        subtotal += line_total
        tile = tiles[item.tile_id]
        quotation.items.append(QuotationItem(
            tile_id=tile.id,
            tile_name=tile.name,
            tile_sku=tile.sku,
            material=tile.material.name if tile.material else None,
            size_label=_size_label(tile),
            catalog_rate_per_sqm=tile.price_per_sqm,
            quantity=item.quantity,
            area_sqm=item.area_sqm,
            rate_per_sqm=item.rate_per_sqm,
            line_total=line_total,
            subtotal=line_total,
        ))

    quotation.subtotal = round(subtotal, 2)
    quotation.gst_amount = round(quotation.subtotal * quotation.gst_rate / 100, 2)
    quotation.grand_total = round(quotation.subtotal + quotation.gst_amount, 2)
    db.add(quotation)
    db.flush()
    quotation.quotation_number = f"QT-{quotation.id:06d}"
    db.commit()
    quotation = _load_query(db).filter(Quotation.id == quotation.id).one()
    return _serialize(quotation)
