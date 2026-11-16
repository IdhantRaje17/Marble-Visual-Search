from datetime import date, datetime, timedelta, timezone
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, literal
from sqlalchemy.orm import Session, selectinload
from typing import Optional

from app.database import get_db
from app.middleware.auth import get_current_admin
from app.models.admin import Admin
from app.models.cart import Order, OrderItem
from app.models.categories import Material
from app.models.inventory import Inventory
from app.models.search_log import SearchLog
from app.models.tile import Tile
from app.models.order_tracking import OrderStatusEvent, OrderTracking
from app.models.factory import ProductionEntry
from app.models.inventory_movement import InventoryMovement
from app.models.quotation import Quotation, QuotationItem
from app.schemas.cart import OrderTrackingUpdate
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/admin", tags=["Admin Analytics"])

# Sales metrics use only these statuses. "placed" and in-transit states are not sales.
COMPLETED_ORDER_STATUSES = ("paid", "completed", "delivered")
KNOWN_ORDER_STATUSES = (
    "placed",
    "paid",
    "dispatched",
    "completed",
    "delivered",
    "cancelled",
)
SALES_DEFINITION = (
    "Completed sales are orders with status paid, completed, or delivered. "
    "Placed, dispatched, and cancelled orders are excluded from units sold, revenue, "
    "average order value, best sellers, and top buyers."
)


def _delay_seconds(tracking: Optional[OrderTracking]) -> Optional[int]:
    if not tracking or not tracking.expected_delivery_at:
        return None
    expected = tracking.expected_delivery_at
    end = tracking.delivered_at or datetime.now(timezone.utc)
    if expected.tzinfo is None:
        expected = expected.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return max(0, int((end - expected).total_seconds()))


def _as_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


class ProductionCreate(BaseModel):
    tile_id: int = Field(gt=0)
    quantity: int = Field(gt=0)
    factory_name: str = Field(min_length=1, max_length=200)
    batch_number: str | None = Field(default=None, max_length=100)
    produced_at: date
    notes: str | None = Field(default=None, max_length=2000)


@router.post("/production")
def create_production_entry(
    body: ProductionCreate,
    db: Session = Depends(get_db),
    account: Admin = Depends(get_current_admin),
):
    tile = db.query(Tile).filter(Tile.id == body.tile_id, Tile.is_active.is_(True)).first()
    if not tile:
        raise HTTPException(status_code=422, detail="Active tile not found")
    inv = db.query(Inventory).filter(Inventory.tile_id == tile.id).with_for_update().first()
    if inv is None:
        inv = Inventory(
            tile_id=tile.id,
            quantity=0,
            unit="pieces",
            low_stock_threshold=10,
        )
        db.add(inv)
        db.flush()
    entry = ProductionEntry(
        tile_id=tile.id,
        tile_sku=tile.sku,
        tile_name=tile.name,
        quantity=body.quantity,
        factory_name=body.factory_name.strip(),
        batch_number=body.batch_number.strip() if body.batch_number else None,
        produced_at=body.produced_at,
        notes=body.notes.strip() if body.notes else None,
        created_by=account.id,
    )
    db.add(entry)
    db.flush()
    if inv is not None:
        inv.quantity += body.quantity
        db.add(InventoryMovement(
            tile_id=tile.id,
            tile_sku=tile.sku,
            tile_name=tile.name,
            movement_type="production_receipt",
            quantity=body.quantity,
            direction=1,
            unit=inv.unit,
            balance_after=inv.quantity,
            reference_type="production_entry",
            reference_id=entry.id,
            reason=f"Production batch {entry.batch_number}" if entry.batch_number else "Production receipt",
            occurred_at=datetime.combine(body.produced_at, datetime.min.time(), tzinfo=timezone.utc),
            created_by=account.id,
        ))
    db.commit()
    db.refresh(entry)
    return {
        "id": entry.id,
        "tile_id": entry.tile_id,
        "tile_sku": entry.tile_sku,
        "tile_name": entry.tile_name,
        "quantity": entry.quantity,
        "factory_name": entry.factory_name,
        "batch_number": entry.batch_number,
        "produced_at": entry.produced_at.isoformat(),
        "notes": entry.notes,
        "inventory_receipt": inv is not None,
    }


@router.get("/production")
def list_production_entries(
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    query = db.query(ProductionEntry)
    if start_date:
        query = query.filter(ProductionEntry.produced_at >= start_date)
    if end_date:
        query = query.filter(ProductionEntry.produced_at <= end_date)
    rows = query.order_by(ProductionEntry.produced_at.desc(), ProductionEntry.id.desc()).limit(500).all()
    return [{
        "id": row.id,
        "tile_id": row.tile_id,
        "tile_sku": row.tile_sku,
        "tile_name": row.tile_name,
        "quantity": row.quantity,
        "factory_name": row.factory_name,
        "batch_number": row.batch_number,
        "produced_at": row.produced_at.isoformat(),
        "notes": row.notes,
    } for row in rows]


@router.get("/link-options")
def analytics_link_options(
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    searches = db.query(
        SearchLog.id,
        SearchLog.status,
        SearchLog.searched_at,
        Tile.sku.label("tile_sku"),
        Tile.name.label("tile_name"),
    ).outerjoin(
        Tile, Tile.id == SearchLog.matched_tile_id
    ).order_by(
        SearchLog.searched_at.desc(), SearchLog.id.desc()
    ).limit(500).all()

    orders = db.query(
        Order.id,
        Order.status,
        Order.placed_at,
        Admin.name.label("buyer_name"),
    ).join(
        Admin, Admin.id == Order.admin_id
    ).order_by(
        Order.placed_at.desc(), Order.id.desc()
    ).limit(500).all()

    return {
        "searches": [{
            "id": row.id,
            "status": row.status,
            "searched_at": row.searched_at.isoformat() if row.searched_at else None,
            "tile_sku": row.tile_sku,
            "tile_name": row.tile_name,
        } for row in searches],
        "orders": [{
            "id": row.id,
            "status": row.status,
            "placed_at": row.placed_at.isoformat() if row.placed_at else None,
            "buyer_name": row.buyer_name,
        } for row in orders],
    }


@router.get("/analytics")
def dashboard_analytics(
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    today = date.today()
    range_end = end_date or today
    range_start = start_date or range_end - timedelta(days=29)
    if range_start > range_end:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date")
    if (range_end - range_start).days > 365:
        raise HTTPException(status_code=422, detail="Date range cannot exceed 366 days")

    def date_filter(column):
        return (func.date(column) >= range_start) & (func.date(column) <= range_end)

    def complete_trend(rows):
        counts = {}
        for day, count in rows:
            parsed = _as_date(day)
            if parsed is not None:
                counts[parsed] = count
        days = (range_end - range_start).days + 1
        return [
            {
                "date": (range_start + timedelta(days=offset)).isoformat(),
                "count": counts.get(range_start + timedelta(days=offset), 0),
            }
            for offset in range(days)
        ]

    catalog = db.query(
        func.count(Tile.id),
        func.sum(case((Tile.is_active.is_(True), 1), else_=0)),
        func.sum(case((Tile.is_active.is_(False), 1), else_=0)),
    ).one()

    inventory_counts = db.query(
        func.count(Inventory.id),
        func.coalesce(func.sum(Inventory.quantity), 0),
        func.sum(case((Inventory.quantity <= 0, 1), else_=0)),
        func.sum(case(
            ((Inventory.quantity > 0) & (Inventory.quantity <= Inventory.low_stock_threshold), 1),
            else_=0,
        )),
        func.sum(case((Inventory.quantity > Inventory.low_stock_threshold, 1), else_=0)),
    ).one()
    missing_inventory_count = db.query(func.count(Tile.id)).outerjoin(
        Inventory, Inventory.tile_id == Tile.id
    ).filter(Inventory.id.is_(None)).scalar()
    low_stock_items = db.query(
        Tile.id.label("tile_id"),
        Tile.sku,
        Tile.name,
        Inventory.quantity,
        Inventory.low_stock_threshold,
    ).join(Inventory, Inventory.tile_id == Tile.id).filter(
        Inventory.quantity <= Inventory.low_stock_threshold
    ).order_by(Inventory.quantity.asc(), Tile.name.asc()).limit(8).all()

    search_day = func.date(SearchLog.searched_at)
    search_filters = [date_filter(SearchLog.searched_at)]
    searches_total = db.query(func.count(SearchLog.id)).filter(*search_filters).scalar()
    search_trend = db.query(
        search_day.label("day"),
        func.count(SearchLog.id),
    ).filter(*search_filters).group_by(search_day).order_by(search_day).all()
    recent_searches = db.query(
        SearchLog.id,
        SearchLog.status,
        SearchLog.confidence,
        SearchLog.searched_at,
        SearchLog.matched_tile_id,
        Tile.name.label("tile_name"),
    ).outerjoin(Tile, Tile.id == SearchLog.matched_tile_id).filter(
        *search_filters
    ).order_by(SearchLog.searched_at.desc()).limit(8).all()

    production_filters = [
        ProductionEntry.produced_at >= range_start,
        ProductionEntry.produced_at <= range_end,
    ]
    produced_total = db.query(func.coalesce(func.sum(ProductionEntry.quantity), 0)).filter(
        *production_filters
    ).scalar() or 0
    production_rows = db.query(
        ProductionEntry.produced_at.label("day"),
        func.coalesce(func.sum(ProductionEntry.quantity), 0).label("quantity"),
    ).filter(*production_filters).group_by(ProductionEntry.produced_at).order_by(
        ProductionEntry.produced_at
    ).all()
    production_by_day = {_as_date(row.day): int(row.quantity or 0) for row in production_rows}
    production_trend = [
        {
            "date": (range_start + timedelta(days=offset)).isoformat(),
            "produced": production_by_day.get(range_start + timedelta(days=offset), 0),
            "sold": 0,
        }
        for offset in range((range_end - range_start).days + 1)
    ]

    linked_search_ids = db.query(func.count(func.distinct(Quotation.search_id))).filter(
        Quotation.search_id.isnot(None),
        date_filter(Quotation.created_at),
    ).scalar() or 0
    quoted_orders = db.query(func.count(func.distinct(Quotation.order_id))).filter(
        Quotation.order_id.isnot(None),
        date_filter(Quotation.created_at),
    ).scalar() or 0
    linked_quotes = db.query(func.count(Quotation.id)).filter(
        Quotation.search_id.isnot(None),
        date_filter(Quotation.created_at),
    ).scalar() or 0
    search_to_quote_rate = (
        round(linked_quotes / searches_total * 100, 2) if searches_total else 0.0
    )
    quote_to_order_rate = (
        round(quoted_orders / linked_quotes * 100, 2) if linked_quotes else 0.0
    )

    order_day = func.date(Order.placed_at)
    order_filters = [date_filter(Order.placed_at)]
    order_statuses = db.query(Order.status, func.count(Order.id)).filter(
        *order_filters
    ).group_by(Order.status).all()
    total_orders = sum(count for _, count in order_statuses)
    paid_filters = [
        date_filter(Order.placed_at),
        func.lower(Order.status).in_(COMPLETED_ORDER_STATUSES),
    ]
    completed_order_rows = db.query(
        Order.id, Order.admin_id, Order.total_amount, Order.placed_at,
    ).filter(*paid_filters).all()
    completed_orders = len(completed_order_rows)
    order_item_totals = {}
    if completed_order_rows:
        order_item_totals = {
            order_id: (item_count, priced_count, float(item_revenue or 0))
            for order_id, item_count, priced_count, item_revenue in db.query(
                OrderItem.order_id,
                func.count(OrderItem.id),
                func.count(OrderItem.unit_price),
                func.sum(OrderItem.unit_price * OrderItem.quantity),
            ).filter(
                OrderItem.order_id.in_([row.id for row in completed_order_rows])
            ).group_by(OrderItem.order_id).all()
        }

    def order_revenue(row):
        item_count, priced_count, item_revenue = order_item_totals.get(row.id, (0, 0, 0.0))
        if item_count == 0:
            return float(row.total_amount) if row.total_amount is not None else None
        if item_count != priced_count:
            return None
        if row.total_amount is not None:
            return float(row.total_amount)
        return item_revenue

    order_revenues = {row.id: order_revenue(row) for row in completed_order_rows}
    known_revenues = [amount for amount in order_revenues.values() if amount is not None]
    incomplete_revenue_orders = completed_orders - len(known_revenues)
    # Zero completed sales is a real zero, not missing data.
    revenue_available = incomplete_revenue_orders == 0
    revenue = sum(known_revenues) if revenue_available else None
    if completed_orders == 0:
        average_order_value = None
        aov_available = True
        aov_reason = "No completed orders in this date range, so average order value is not applicable."
        revenue_reason = "No completed orders in this date range."
    elif revenue_available:
        average_order_value = (revenue or 0) / completed_orders
        aov_available = True
        aov_reason = "Average of stored totals for completed orders."
        revenue_reason = "Sum of stored totals for completed orders."
    else:
        average_order_value = None
        aov_available = False
        aov_reason = (
            f"{incomplete_revenue_orders} completed order(s) are missing line prices or a stored total."
        )
        revenue_reason = aov_reason

    units_sold = int(db.query(func.coalesce(func.sum(OrderItem.quantity), 0)).join(
        Order, Order.id == OrderItem.order_id
    ).filter(*paid_filters).scalar() or 0)

    sold_by_day_rows = db.query(
        func.date(Order.placed_at).label("day"),
        func.coalesce(func.sum(OrderItem.quantity), 0).label("quantity"),
    ).join(OrderItem, OrderItem.order_id == Order.id).filter(
        *paid_filters
    ).group_by(func.date(Order.placed_at)).all()
    sold_by_day = {_as_date(row.day): int(row.quantity or 0) for row in sold_by_day_rows}
    for point in production_trend:
        point["sold"] = sold_by_day.get(_as_date(point["date"]), 0)

    movement_filters = [
        func.date(InventoryMovement.occurred_at) >= range_start,
        func.date(InventoryMovement.occurred_at) <= range_end,
    ]
    movement_rows = db.query(
        InventoryMovement.tile_id,
        InventoryMovement.tile_sku,
        InventoryMovement.tile_name,
        func.sum(InventoryMovement.quantity * InventoryMovement.direction).label("net_change"),
        func.sum(case(
            ((InventoryMovement.direction == -1) & (InventoryMovement.movement_type == "sale"), InventoryMovement.quantity),
            else_=0,
        )).label("outflows"),
        func.max(InventoryMovement.occurred_at).label("last_movement"),
    ).filter(*movement_filters).group_by(
        InventoryMovement.tile_id,
        InventoryMovement.tile_sku,
        InventoryMovement.tile_name,
    ).order_by(func.sum(InventoryMovement.quantity).desc()).limit(20).all()

    stock_aging_items = []
    for row in movement_rows:
        inv = db.query(Inventory).filter(Inventory.tile_id == row.tile_id).first() if row.tile_id else None
        if inv is None:
            continue
        beginning_stock = inv.quantity - int(row.net_change or 0)
        ending_stock = inv.quantity
        average_stock = (max(beginning_stock, 0) + max(ending_stock, 0)) / 2
        sales_outflow = int(row.outflows or 0)
        turnover = (
            round(sales_outflow / average_stock, 2)
            if average_stock > 0
            else 0.0
        )
        last_receipt = db.query(func.max(InventoryMovement.occurred_at)).filter(
            InventoryMovement.tile_id == row.tile_id,
            InventoryMovement.direction == 1,
            InventoryMovement.occurred_at <= datetime.now(timezone.utc),
        ).scalar()
        stock_age_days = None
        if last_receipt:
            if last_receipt.tzinfo is None:
                last_receipt = last_receipt.replace(tzinfo=timezone.utc)
            stock_age_days = max(0, (datetime.now(timezone.utc) - last_receipt).days)
        stock_aging_items.append({
            "tile_id": row.tile_id,
            "sku": row.tile_sku,
            "name": row.tile_name,
            "current_stock": ending_stock,
            "average_stock": round(average_stock, 2),
            "outflow_quantity": sales_outflow,
            "turnover": turnover,
            "stock_age_days": stock_age_days,
            "available": True,
        })

    order_trend = db.query(
        order_day.label("day"),
        func.count(Order.id),
    ).filter(*order_filters).group_by(order_day).order_by(order_day).all()

    daily_revenue = {}
    for row in completed_order_rows:
        day = _as_date(row.placed_at)
        if day is None:
            continue
        entry = daily_revenue.setdefault(day, {"amount": 0.0, "complete": True})
        amount = order_revenues[row.id]
        if amount is None:
            entry["complete"] = False
        else:
            entry["amount"] += amount

    days = (range_end - range_start).days + 1
    revenue_trend = []
    for offset in range(days):
        day = range_start + timedelta(days=offset)
        values = daily_revenue.get(day)
        if values is None:
            revenue_trend.append({"date": day.isoformat(), "amount": 0.0, "complete": True})
        elif values["complete"]:
            revenue_trend.append({
                "date": day.isoformat(),
                "amount": float(values["amount"]),
                "complete": True,
            })
        else:
            revenue_trend.append({"date": day.isoformat(), "amount": None, "complete": False})

    recent_orders = db.query(
        Order.id,
        Order.status,
        Order.total_amount,
        Order.placed_at,
        Admin.email.label("account_email"),
    ).join(Admin, Admin.id == Order.admin_id).filter(
        *order_filters
    ).order_by(Order.placed_at.desc()).limit(8).all()

    best_sellers = db.query(
        OrderItem.tile_id.label("tile_id"),
        func.coalesce(Tile.sku, literal("Unavailable")).label("sku"),
        func.coalesce(Tile.name, literal("Deleted or missing tile")).label("name"),
        func.sum(OrderItem.quantity).label("units_sold"),
        func.sum(OrderItem.unit_price * OrderItem.quantity).label("revenue"),
        func.count(OrderItem.id).label("item_count"),
        func.count(OrderItem.unit_price).label("priced_item_count"),
    ).join(Order, Order.id == OrderItem.order_id).outerjoin(
        Tile, Tile.id == OrderItem.tile_id
    ).filter(*paid_filters).group_by(
        OrderItem.tile_id, Tile.sku, Tile.name
    ).order_by(func.sum(OrderItem.quantity).desc()).limit(5).all()

    top_searched_tiles = db.query(
        Tile.id.label("tile_id"),
        Tile.sku,
        Tile.name,
        func.count(SearchLog.id).label("searches"),
    ).join(SearchLog, SearchLog.matched_tile_id == Tile.id).filter(
        date_filter(SearchLog.searched_at)
    ).group_by(Tile.id, Tile.sku, Tile.name).order_by(
        func.count(SearchLog.id).desc()
    ).limit(5).all()

    top_buyers = db.query(
        Admin.id.label("account_id"),
        Admin.name,
        Admin.email,
        func.count(Order.id).label("orders"),
    ).join(Order, Order.admin_id == Admin.id).filter(
        *paid_filters
    ).group_by(Admin.id, Admin.name, Admin.email).order_by(
        func.count(Order.id).desc()
    ).limit(5).all()
    buyer_revenues = {}
    for row in completed_order_rows:
        stats = buyer_revenues.setdefault(row.admin_id, {"amount": 0.0, "complete": True})
        amount = order_revenues[row.id]
        if amount is None:
            stats["complete"] = False
        else:
            stats["amount"] += amount

    return {
        "date_range": {
            "start_date": range_start.isoformat(),
            "end_date": range_end.isoformat(),
        },
        "definitions": {
            "completed_statuses": list(COMPLETED_ORDER_STATUSES),
            "sales": SALES_DEFINITION,
            "visual_search_popularity": (
                "Ranked by matched visual-search logs in the selected date range, "
                "independent of sales quantity."
            ),
            "inventory": (
                "Stock distribution uses current on-hand quantity versus each product's "
                "low-stock threshold. It is not filtered by date."
            ),
        },
        "catalog": {
            "total": catalog[0] or 0,
            "active": catalog[1] or 0,
            "inactive": catalog[2] or 0,
        },
        "searches": {
            "total": searches_total or 0,
            "trend": complete_trend(search_trend),
            "recent": [{
                "id": row.id,
                "status": row.status,
                "confidence": row.confidence,
                "searched_at": row.searched_at.isoformat() if row.searched_at else None,
                "matched_tile_id": row.matched_tile_id,
                "tile_name": row.tile_name,
            } for row in recent_searches],
        },
        "orders": {
            "total": total_orders,
            "status_counts": {status: count for status, count in order_statuses},
            "completed": completed_orders,
            "units_sold": units_sold,
            "revenue": revenue,
            "average_order_value": average_order_value,
            "revenue_available": revenue_available,
            "revenue_reason": revenue_reason,
            "aov_available": aov_available,
            "aov_reason": aov_reason,
            "incomplete_revenue_orders": incomplete_revenue_orders,
            "conversion_rate": None,
            "conversion_available": False,
            "trend": complete_trend(order_trend),
            "revenue_trend": revenue_trend,
            "recent": [{
                "id": row.id,
                "status": row.status,
                "total_amount": row.total_amount,
                "placed_at": row.placed_at.isoformat() if row.placed_at else None,
                "account_email": row.account_email,
            } for row in recent_orders],
            "best_sellers": [{
                "tile_id": row.tile_id,
                "sku": row.sku,
                "name": row.name,
                "units_sold": int(row.units_sold or 0),
                "revenue": (
                    float(row.revenue)
                    if row.item_count == row.priced_item_count and row.revenue is not None
                    else None
                ),
                "revenue_available": row.item_count == row.priced_item_count,
            } for row in best_sellers],
            "top_searched_tiles": [{
                "tile_id": row.tile_id,
                "sku": row.sku,
                "name": row.name,
                "searches": row.searches,
            } for row in top_searched_tiles],
            "top_buyers": [{
                "account_id": row.account_id,
                "name": row.name,
                "email": row.email,
                "completed_orders": row.orders,
                "revenue": (
                    buyer_revenues.get(row.account_id, {}).get("amount", 0.0)
                    if buyer_revenues.get(row.account_id, {}).get("complete")
                    else None
                ),
                "revenue_available": buyer_revenues.get(row.account_id, {}).get("complete", False),
            } for row in top_buyers],
            "production_vs_sales": {
                "available": True,
                "produced_quantity": produced_total,
                "sold_quantity": units_sold,
                "trend": production_trend,
                "reason": (
                    "Produced quantity comes from factory production entries; "
                    "sold quantity comes only from completed orders."
                ),
            },
            "search_to_quotation_to_order": {
                "available": searches_total > 0 or linked_quotes > 0,
                "searches": searches_total or 0,
                "linked_searches": linked_search_ids,
                "linked_quotes": linked_quotes,
                "linked_orders": quoted_orders,
                "search_to_quote_rate": search_to_quote_rate,
                "quote_to_order_rate": quote_to_order_rate,
                "reason": (
                    "Rates use explicit search_id and order_id links stored on quotations. "
                    "No historical links are inferred."
                ),
            },
        },
        "inventory": {
            "records": inventory_counts[0] or 0,
            "not_configured_products": missing_inventory_count or 0,
            "quantity_total": inventory_counts[1] or 0,
            "out_of_stock": inventory_counts[2] or 0,
            "low_stock": inventory_counts[3] or 0,
            "in_stock": inventory_counts[4] or 0,
            "low_stock_items": [{
                "tile_id": row.tile_id,
                "sku": row.sku,
                "name": row.name,
                "quantity": row.quantity,
                "threshold": row.low_stock_threshold,
            } for row in low_stock_items],
            "stock_aging_and_turnover": {
                "available": bool(stock_aging_items),
                "items": stock_aging_items,
                "reason": (
                    "Stock aging uses the latest positive inventory movement; turnover uses "
                    "sales movements and opening/closing stock in the selected range."
                ),
            },
        },
    }


@router.get("/factory-insights")
def factory_insights(
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    today = date.today()
    range_end = end_date or today
    range_start = start_date or range_end - timedelta(days=29)
    if range_start > range_end:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date")
    if (range_end - range_start).days > 365:
        raise HTTPException(status_code=422, detail="Date range cannot exceed 366 days")

    def date_filter(column):
        return (func.date(column) >= range_start) & (func.date(column) <= range_end)

    searches = int(db.query(func.count(SearchLog.id)).filter(
        date_filter(SearchLog.searched_at)
    ).scalar() or 0)
    linked_search_quotes = db.query(
        Quotation.id, Quotation.search_id,
    ).join(SearchLog, SearchLog.id == Quotation.search_id).filter(
        date_filter(Quotation.created_at),
        date_filter(SearchLog.searched_at),
    ).all()
    linked_search_ids = {row.search_id for row in linked_search_quotes}
    linked_quote_ids = {row.id for row in linked_search_quotes}

    closed_search_quotes = db.query(
        Quotation.id,
        Quotation.search_id,
        Quotation.order_id,
    ).join(SearchLog, SearchLog.id == Quotation.search_id).join(
        Order, Order.id == Quotation.order_id,
    ).filter(
        date_filter(Quotation.created_at),
        date_filter(SearchLog.searched_at),
        date_filter(Order.placed_at),
        func.lower(Order.status).in_(COMPLETED_ORDER_STATUSES),
    ).all()
    closed_quote_ids = {row.id for row in closed_search_quotes}
    closed_order_ids = {row.order_id for row in closed_search_quotes}
    closed_search_ids = {row.search_id for row in closed_search_quotes}

    linked_conversion_quotes = len(linked_quote_ids)
    search_to_quote_rate = (
        round(len(linked_search_ids) / searches * 100, 2) if searches else 0.0
    )
    quote_to_order_rate = (
        round(len(closed_quote_ids) / linked_conversion_quotes * 100, 2)
        if linked_conversion_quotes else 0.0
    )
    search_to_sale_rate = (
        round(len(closed_search_ids) / searches * 100, 2) if searches else 0.0
    )

    produced_quantity = int(db.query(
        func.coalesce(func.sum(ProductionEntry.quantity), 0)
    ).filter(
        ProductionEntry.produced_at >= range_start,
        ProductionEntry.produced_at <= range_end,
    ).scalar() or 0)
    sold_quantity = int(db.query(
        func.coalesce(func.sum(OrderItem.quantity), 0)
    ).join(Order, Order.id == OrderItem.order_id).filter(
        date_filter(Order.placed_at),
        func.lower(Order.status).in_(COMPLETED_ORDER_STATUSES),
    ).scalar() or 0)

    receipt_rows = db.query(
        InventoryMovement.tile_id,
        func.max(InventoryMovement.occurred_at),
    ).filter(
        InventoryMovement.tile_id.isnot(None),
        InventoryMovement.direction == 1,
        func.date(InventoryMovement.occurred_at) <= today.isoformat(),
    ).group_by(InventoryMovement.tile_id).all()
    latest_receipt = {tile_id: occurred_at for tile_id, occurred_at in receipt_rows}
    stock_categories = {
        "fresh": [],
        "medium": [],
        "critical": [],
    }
    unaged_stock_count = 0
    inventory_rows = db.query(Inventory, Tile).join(
        Tile, Tile.id == Inventory.tile_id
    ).options(selectinload(Tile.images)).filter(Inventory.quantity > 0).all()
    for inventory, tile in inventory_rows:
        receipt_date = _as_date(latest_receipt.get(tile.id))
        if receipt_date is None:
            unaged_stock_count += 1
            continue
        age_days = max(0, (today - receipt_date).days)
        if age_days < 90:
            category = "fresh"
        elif age_days < 180:
            category = "medium"
        else:
            category = "critical"
        images = sorted(tile.images, key=lambda image: (not image.is_primary, image.id))
        stock_categories[category].append({
            "tile_id": tile.id,
            "name": tile.name,
            "sku": tile.sku,
            "quantity": inventory.quantity,
            "unit": inventory.unit or "pieces",
            "stock_date": receipt_date.isoformat(),
            "stock_age_days": age_days,
            "image_url": images[0].image_url if images else None,
        })

    quote_order_rows = db.query(
        Quotation.id,
        Quotation.order_id,
        Quotation.company_name,
    ).join(Order, Order.id == Quotation.order_id).filter(
        Quotation.order_id.isnot(None),
        date_filter(Quotation.created_at),
        date_filter(Order.placed_at),
        func.lower(Order.status).in_(COMPLETED_ORDER_STATUSES),
    ).all()
    quote_ids_by_order = defaultdict(set)
    companies_by_order = defaultdict(dict)
    for quotation_id, order_id, company_name in quote_order_rows:
        quote_ids_by_order[order_id].add(quotation_id)
        if company_name and company_name.strip():
            normalized_name = company_name.strip().casefold()
            companies_by_order[order_id].setdefault(normalized_name, company_name.strip())

    quoted_order_ids = list(quote_ids_by_order)
    order_rows = []
    order_item_totals = {}
    if quoted_order_ids:
        order_rows = db.query(
            Order.id, Order.total_amount,
        ).filter(Order.id.in_(quoted_order_ids)).all()
        order_item_totals = {
            order_id: (item_count, priced_count, float(item_revenue or 0))
            for order_id, item_count, priced_count, item_revenue in db.query(
                OrderItem.order_id,
                func.count(OrderItem.id),
                func.count(OrderItem.unit_price),
                func.sum(OrderItem.unit_price * OrderItem.quantity),
            ).filter(
                OrderItem.order_id.in_(quoted_order_ids)
            ).group_by(OrderItem.order_id).all()
        }

    order_revenues = {}
    for order_id, total_amount in order_rows:
        item_count, priced_count, item_revenue = order_item_totals.get(
            order_id, (0, 0, 0.0)
        )
        if item_count == 0:
            order_revenues[order_id] = (
                float(total_amount) if total_amount is not None else None
            )
        elif item_count != priced_count:
            order_revenues[order_id] = None
        elif total_amount is not None:
            order_revenues[order_id] = float(total_amount)
        else:
            order_revenues[order_id] = item_revenue

    buyer_totals = {}
    unattributed_corporate_orders = 0
    for order_id in quoted_order_ids:
        company_names = companies_by_order[order_id]
        if len(company_names) != 1:
            unattributed_corporate_orders += 1
            continue
        company_key, company_name = next(iter(company_names.items()))
        totals = buyer_totals.setdefault(company_key, {
            "company_name": company_name,
            "order_ids": set(),
            "revenue": 0.0,
            "revenue_available": True,
        })
        totals["order_ids"].add(order_id)
        revenue = order_revenues.get(order_id)
        if revenue is None:
            totals["revenue_available"] = False
        else:
            totals["revenue"] += revenue

    top_corporate_buyers = sorted(
        buyer_totals.values(),
        key=lambda buyer: (
            len(buyer["order_ids"]),
            buyer["revenue"] if buyer["revenue_available"] else -1,
        ),
        reverse=True,
    )[:5]

    unambiguous_quote_ids = [
        next(iter(quote_ids))
        for order_id, quote_ids in quote_ids_by_order.items()
        if len(quote_ids) == 1
    ]
    top_materials = []
    if unambiguous_quote_ids:
        material_expression = func.coalesce(QuotationItem.material, Material.name)
        material_rows = db.query(
            material_expression.label("material"),
            func.sum(QuotationItem.quantity * QuotationItem.area_sqm).label("volume_sqm"),
            func.sum(QuotationItem.line_total).label("revenue"),
        ).join(
            Quotation, Quotation.id == QuotationItem.quotation_id
        ).outerjoin(
            Tile, Tile.id == QuotationItem.tile_id
        ).outerjoin(
            Material, Material.id == Tile.material_id
        ).filter(
            Quotation.id.in_(unambiguous_quote_ids),
            material_expression.isnot(None),
            func.trim(material_expression) != "",
        ).group_by(material_expression).order_by(
            func.sum(QuotationItem.quantity * QuotationItem.area_sqm).desc()
        ).limit(5).all()
        top_materials = [{
            "material": row.material,
            "volume_sqm": round(float(row.volume_sqm or 0), 2),
            "revenue": float(row.revenue or 0),
        } for row in material_rows]

    return {
        "date_range": {
            "start_date": range_start.isoformat(),
            "end_date": range_end.isoformat(),
        },
        "production_vs_sales": {
            "produced_quantity": produced_quantity,
            "sold_quantity": sold_quantity,
        },
        "dead_stock": {
            "tile_count": sum(
                item["stock_age_days"] > 180
                for item in stock_categories["critical"]
            ),
            "age_days": 180,
        },
        "conversion": {
            "searches": searches,
            "linked_searches": len(linked_search_ids),
            "quotations": linked_conversion_quotes,
            "closed_quotations": len(closed_quote_ids),
            "closed_orders": len(closed_order_ids),
            "closed_searches": len(closed_search_ids),
            "search_to_quotation_rate": search_to_quote_rate,
            "quotation_to_order_rate": quote_to_order_rate,
            "search_to_sale_rate": search_to_sale_rate,
        },
        "stock_aging": {
            "categories": [{
                "key": "fresh",
                "label": "Fresh",
                "range": "<90 days",
                "items": stock_categories["fresh"],
            }, {
                "key": "medium",
                "label": "Medium",
                "range": "90-179 days",
                "items": stock_categories["medium"],
            }, {
                "key": "critical",
                "label": "Critical",
                "range": "180+ days",
                "items": stock_categories["critical"],
            }],
            "unaged_tile_count": unaged_stock_count,
            "note": (
                "Stock dates use each tile's latest recorded positive inventory movement. "
                "Inventory is not lot-tracked, so these dates estimate the age of on-hand "
                "stock; tiles without a recorded receipt are left unclassified."
            ),
        },
        "top_materials": top_materials,
        "top_corporate_buyers": [{
            "company_name": buyer["company_name"],
            "completed_orders": len(buyer["order_ids"]),
            "revenue": (
                round(buyer["revenue"], 2) if buyer["revenue_available"] else None
            ),
            "revenue_available": buyer["revenue_available"],
        } for buyer in top_corporate_buyers],
        "unattributed_corporate_orders": unattributed_corporate_orders,
        "material_note": (
            "Volumes and revenue use quotation lines explicitly linked to completed orders. "
            "Orders with multiple linked quotations are excluded to avoid double-counting."
        ),
    }


@router.get("/orders")
def order_tracking(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    query = db.query(Order).options(
        selectinload(Order.admin),
        selectinload(Order.tracking),
        selectinload(Order.status_events),
        selectinload(Order.items).selectinload(OrderItem.tile).selectinload(Tile.inventory),
    ).join(Admin, Admin.id == Order.admin_id)
    if status:
        query = query.filter(func.lower(Order.status) == status.lower())
    orders = query.order_by(Order.placed_at.desc(), Order.id.desc()).limit(500).all()
    return [{
        "id": order.id,
        "status": order.status,
        "total_amount": order.total_amount,
        "placed_at": order.placed_at,
        "buyer_name": order.admin.name,
        "buyer_email": order.admin.email,
        "shipment_details": ({
            "tracking_number": order.tracking.tracking_number,
            "carrier": order.tracking.carrier,
        } if order.tracking else None),
        "dispatched_at": order.tracking.dispatched_at if order.tracking else None,
        "delivered_at": order.tracking.delivered_at if order.tracking else None,
        "expected_delivery_at": order.tracking.expected_delivery_at if order.tracking else None,
        "delay_seconds": _delay_seconds(order.tracking),
        "known_statuses": list(KNOWN_ORDER_STATUSES),
        "timeline": [{
            "status": event.status,
            "timestamp": event.created_at,
        } for event in order.status_events],
        "items": [{
            "tile_id": item.tile_id,
            "tile_name": item.tile.name if item.tile else f"Tile #{item.tile_id}",
            "tile_sku": item.tile.sku if item.tile else "Unavailable",
            "quantity": item.quantity,
            "unit_price": item.unit_price,
            "current_stock": (
                item.tile.inventory.quantity
                if item.tile and item.tile.inventory else None
            ),
        } for item in order.items],
    } for order in orders]


@router.patch("/orders/{order_id}/tracking")
def update_order_tracking(
    order_id: int,
    body: OrderTrackingUpdate,
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    order = db.query(Order).filter(Order.id == order_id).with_for_update().first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    updates = body.model_dump(exclude_unset=True)
    next_status = updates.pop("status", None)
    if next_status is not None and not next_status.strip():
        raise HTTPException(status_code=422, detail="Order status cannot be empty")

    if updates:
        if order.tracking is None:
            order.tracking = OrderTracking(order_id=order.id)
        for field, value in updates.items():
            setattr(order.tracking, field, value)

    if next_status is not None and next_status.strip() != order.status:
        order.status = next_status.strip()
        db.add(OrderStatusEvent(order_id=order.id, status=order.status))

    db.commit()
    db.refresh(order)
    return {
        "id": order.id,
        "status": order.status,
        "tracking_number": order.tracking.tracking_number if order.tracking else None,
        "carrier": order.tracking.carrier if order.tracking else None,
        "dispatched_at": order.tracking.dispatched_at if order.tracking else None,
        "delivered_at": order.tracking.delivered_at if order.tracking else None,
        "expected_delivery_at": order.tracking.expected_delivery_at if order.tracking else None,
    }
