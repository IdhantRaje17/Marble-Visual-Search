"""Create quotation tables and add missing columns without altering existing data.

Run from the backend directory with DATABASE_URL configured:
    python migrate_quotations.py
"""
from sqlalchemy import text

from app.database import Base, engine
from app.models.quotation import Quotation, QuotationItem

# Register related tables so ForeignKeys resolve if create_all runs on a fresh DB.
from app.models import admin, tile  # noqa: F401


def _has_column(connection, table_name: str, column_name: str) -> bool:
    return connection.execute(
        text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = :table_name AND column_name = :column_name
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    ).first() is not None


def migrate():
    Base.metadata.create_all(bind=engine, tables=[Quotation.__table__, QuotationItem.__table__])
    statements = [
        "ALTER TABLE quotations ADD COLUMN IF NOT EXISTS project_name VARCHAR",
        "ALTER TABLE quotations ADD COLUMN IF NOT EXISTS status VARCHAR NOT NULL DEFAULT 'issued'",
        "ALTER TABLE quotations ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ",
        "ALTER TABLE quotation_items ADD COLUMN IF NOT EXISTS material VARCHAR",
        "ALTER TABLE quotation_items ADD COLUMN IF NOT EXISTS size_label VARCHAR",
        "ALTER TABLE quotation_items ADD COLUMN IF NOT EXISTS catalog_rate_per_sqm FLOAT",
        "ALTER TABLE quotation_items ADD COLUMN IF NOT EXISTS line_total FLOAT",
    ]
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
        if _has_column(connection, "quotation_items", "subtotal") and _has_column(
            connection, "quotation_items", "line_total"
        ):
            connection.execute(text(
                """
                UPDATE quotation_items
                SET line_total = subtotal
                WHERE line_total IS NULL
                """
            ))
    print("Quotation tables are ready.")


if __name__ == "__main__":
    migrate()
