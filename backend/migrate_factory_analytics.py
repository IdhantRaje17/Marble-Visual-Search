"""Safe migration for production, inventory movement, and quotation link tables."""
from sqlalchemy import text

from app.database import Base, engine
from app.models import admin, categories, tile, search_log, cart, quotation
from app.models.factory import ProductionEntry
from app.models.inventory_movement import InventoryMovement


def migrate():
    Base.metadata.create_all(
        bind=engine,
        tables=[ProductionEntry.__table__, InventoryMovement.__table__, quotation.Quotation.__table__],
    )
    with engine.begin() as connection:
        connection.execute(text(
            "ALTER TABLE quotations ADD COLUMN IF NOT EXISTS search_id INTEGER"
        ))
        connection.execute(text(
            "ALTER TABLE quotations ADD COLUMN IF NOT EXISTS order_id INTEGER"
        ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_quotations_search_id ON quotations(search_id)"
        ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_quotations_order_id ON quotations(order_id)"
        ))
    print("Factory analytics and inventory movement schema is ready.")


if __name__ == "__main__":
    migrate()
