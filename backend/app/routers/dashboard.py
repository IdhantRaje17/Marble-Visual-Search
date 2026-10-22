from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.auth import get_current_admin
from app.models.admin import Admin
from app.models.cart import Order, OrderItem
from app.models.inventory import Inventory
from app.models.search_log import SearchLog
from app.models.tile import Tile

router = APIRouter(prefix="/api/admin", tags=["Admin Analytics"])
COMPLETED_ORDER_STATUSES = ("paid", "completed")


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

    date_filter = lambda column: (func.date(column) >= range_start) & (func.date(column) <= range_end)

    def complete_trend(rows):
        counts = {day: count for day, count in rows}
        days = (range_end - range_start).days + 1
        return [
            {"date": (range_start + timedelta(days=offset)).isoformat(),
             "count": counts.get(range_start + timedelta(days=offset), 0)}
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
        func.sum(case(((Inventory.quantity > 0) & (Inventory.quantity <= Inventory.low_stock_threshold), 1), else_=0)),
        func.sum(case((Inventory.quantity > Inventory.low_stock_threshold, 1), else_=0)),
    ).one()
    missing_inventory_count = db.query(func.count(Tile.id)).outerjoin(
        Inventory, Inventory.tile_id == Tile.id
    ).filter(Inventory.id.is_(None)).scalar()

    search_filters = [date_filter(SearchLog.searched_at)]
    searches_total = db.query(func.count(SearchLog.id)).filter(*search_filters).scalar()
    search_trend = db.query(
        func.date(SearchLog.searched_at).label("day"),
        func.count(SearchLog.id),
    ).filter(*search_filters).group_by("day").order_by("day").all()
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

    order_filters = [date_filter(Order.placed_at)]
    order_statuses = db.query(Order.status, func.count(Order.id)).filter(
        *order_filters
    ).group_by(Order.status).all()
    total_orders = sum(count for _, count in order_statuses)
    paid_filters = [
        date_filter(Order.placed_at),
        func.lower(Order.status).in_(COMPLETED_ORDER_STATUSES),
    ]
    completed_orders = db.query(func.count(Order.id)).filter(*paid_filters).scalar()
    completed_orders_with_totals = db.query(func.count(Order.id)).filter(
        *paid_filters,
        Order.total_amount.is_not(None),
    ).scalar()
    revenue = db.query(func.coalesce(func.sum(Order.total_amount), 0.0)).filter(
        *paid_filters,
        Order.total_amount.is_not(None),
    ).scalar()
    average_order_value = db.query(func.avg(Order.total_amount)).filter(
        *paid_filters,
        Order.total_amount.is_not(None),
    ).scalar()
    units_sold = db.query(func.coalesce(func.sum(OrderItem.quantity), 0)).join(
        Order, Order.id == OrderItem.order_id
    ).filter(*paid_filters).scalar()

    order_trend = db.query(
        func.date(Order.placed_at).label("day"),
        func.count(Order.id),
    ).filter(*order_filters).group_by("day").order_by("day").all()
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
        Tile.id.label("tile_id"),
        Tile.sku,
        Tile.name,
        func.sum(OrderItem.quantity).label("units_sold"),
    ).join(OrderItem, OrderItem.tile_id == Tile.id).join(
        Order, Order.id == OrderItem.order_id
    ).filter(*paid_filters).group_by(Tile.id, Tile.sku, Tile.name).order_by(
        func.sum(OrderItem.quantity).desc()
    ).limit(5).all()

    return {
        "date_range": {"start_date": range_start.isoformat(), "end_date": range_end.isoformat()},
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
            "completed": completed_orders or 0,
            "units_sold": units_sold or 0,
            "revenue": float(revenue or 0),
            "average_order_value": float(average_order_value) if completed_orders and completed_orders_with_totals == completed_orders else None,
            "revenue_available": bool(completed_orders) and completed_orders_with_totals == completed_orders,
            "conversion_rate": None,
            "conversion_available": False,
            "trend": complete_trend(order_trend),
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
                "units_sold": row.units_sold,
            } for row in best_sellers],
        },
        "inventory": {
            "records": inventory_counts[0] or 0,
            "not_configured_products": missing_inventory_count or 0,
            "quantity_total": inventory_counts[1] or 0,
            "out_of_stock": inventory_counts[2] or 0,
            "low_stock": inventory_counts[3] or 0,
            "in_stock": inventory_counts[4] or 0,
        },
    }