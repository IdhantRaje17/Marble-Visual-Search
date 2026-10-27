from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, literal
from sqlalchemy.orm import Session, selectinload
from typing import Optional

from app.database import get_db
from app.middleware.auth import get_current_admin
from app.models.admin import Admin
from app.models.cart import Order, OrderItem
from app.models.inventory import Inventory
from app.models.search_log import SearchLog
from app.models.tile import Tile
from app.models.order_tracking import OrderStatusEvent, OrderTracking
from app.schemas.cart import OrderTrackingUpdate

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
                "available": False,
                "reason": "Production records are not stored in the current database.",
            },
            "search_to_quotation_to_order": {
                "available": False,
                "reason": (
                    "Quotations can be stored, but searches, quotations, and orders are not "
                    "linked, so this conversion cannot be measured."
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
                "available": False,
                "reason": (
                    "Inventory movement history is not recorded; current stock alone "
                    "cannot establish age or turnover."
                ),
            },
        },
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
