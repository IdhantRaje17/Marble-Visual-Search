"""
Migration: Make cart_items.tile_id and order_items.tile_id nullable.

This allows safe hard-deletion of tiles while preserving historical
cart and order records (tile_id is set to NULL when tile is deleted).

Run once:
    python migrate_nullable_tile_fk.py
"""
import os
import sys

BACKEND_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(BACKEND_ROOT, ".env"))

from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set in .env")
    sys.exit(1)

engine = create_engine(DATABASE_URL)

migrations = [
    (
        "cart_items.tile_id to nullable",
        "ALTER TABLE cart_items ALTER COLUMN tile_id DROP NOT NULL;"
    ),
    (
        "order_items.tile_id to nullable",
        "ALTER TABLE order_items ALTER COLUMN tile_id DROP NOT NULL;"
    ),
]

with engine.connect() as conn:
    for label, sql in migrations:
        try:
            conn.execute(text(sql))
            conn.commit()
            print(f"[OK]  {label}")
        except Exception as e:
            print(f"[SKIP] {label}: {e}")

print("Migration complete.")
