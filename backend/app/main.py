import os
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.database import Base, engine, get_db
from app.middleware.auth import get_current_admin
from app.schemas.inventory import StockUpdate
from app.services.inventory_service import update_stock as update_stock_service

# Import ALL models
from app.models import admin
from app.models import categories
from app.models import tile
from app.models import tile_image
from app.models import inventory
from app.models import search_log
from app.models import cart as cart_models  # registers Cart/CartItem/Order/OrderItem tables
from app.models import order_tracking as order_tracking_models
from app.models import quotation as quotation_models
from app.models import factory as factory_models
from app.models import inventory_movement as inventory_movement_models
from app.models import chat as chat_models

# Import routers
from app.routers import auth
from app.routers import admin_users
from app.routers import dashboard
from app.routers import categories as cat_router
from app.routers import tiles
from app.routers import search
from app.routers.inventory import router as inv_router
from app.routers.inventory import loc_router
from app.routers import cart as cart_router
from app.routers import quotations as quotations_router
from app.routers import chat as chat_router
from ai.search import get_model

# Ensure pgvector extension and index exist (PostgreSQL)
with engine.connect() as connection:
    try:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
    except Exception as e:
        print(f"Warning: pgvector extension not available: {e}")

# Create tables
Base.metadata.create_all(bind=engine)

# PostgreSQL create_all does not alter columns on existing tables. Quotation
# support previously had a partial schema, so repair those compatible columns
# before starting the API.
try:
    from migrate_quotations import migrate as migrate_quotations
    migrate_quotations()
except Exception as e:
    print(f"Warning: quotation migration could not run: {e}")

try:
    from migrate_factory_analytics import migrate as migrate_factory_analytics
    migrate_factory_analytics()
except Exception as e:
    print(f"Warning: factory analytics migration could not run: {e}")

# Create pgvector index only if extension is available
pgvector_enabled = os.getenv("PGVECTOR_ENABLED", "false").lower() in ("1", "true", "yes")
if pgvector_enabled:
    with engine.connect() as connection:
        try:
            connection.execute(text(
                """
                CREATE INDEX IF NOT EXISTS idx_tile_embeddings_vector
                ON tile_embeddings
                USING ivfflat (embedding vector_cosine_ops)
                """
            ))
        except Exception as e:
            print(f"Warning: Could not create pgvector index: {e}")
else:
    print("Info: pgvector disabled, skipping index creation")

# ── Create app FIRST ────────────────────────────────────
app = FastAPI(title="Marble AI API", version="1.0.0")

# ── CORS ────────────────────────────────────────────────
cors_origins = {
    "https://marble-visual-search-yqhm.vercel.app",
}
cors_origins.update(
    origin.strip().rstrip("/")
    for origin in os.getenv("CORS_ORIGINS", "").split(",")
    if origin.strip()
)
frontend_url = os.getenv("FRONTEND_URL", "").strip().rstrip("/")
if frontend_url:
    cors_origins.add(frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(cors_origins),
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static Files (AFTER app is created) ─────────────────
dataset_path = os.path.join(os.path.dirname(__file__), "..", "dataset")
app.mount("/static", StaticFiles(directory=dataset_path), name="static")

# ── Routers ──────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(admin_users.router)
app.include_router(dashboard.router)
app.include_router(cat_router.router)
app.include_router(tiles.router)
app.include_router(tiles.public_router)
app.include_router(inv_router)
app.include_router(loc_router)
app.include_router(search.router)
app.include_router(cart_router.router)
app.include_router(quotations_router.router)
app.include_router(chat_router.router)


@app.on_event("startup")
def warmup_search_model():
    """
    Warm up DINO model once at startup so first search request is fast.
    """
    try:
        get_model()
        print("Info: search model warmup complete")
    except Exception as e:
        print(f"Warning: search model warmup failed: {e}")

@app.get("/")
def health_check():
    return {"status": "Marble AI API is running"}


@app.post("/update-stock")
def update_stock_endpoint(
    body: StockUpdate,
    db=Depends(get_db),
    _=Depends(get_current_admin),
):
    """Update stock for an administrator."""
    updated = update_stock_service(
        db, body.tile_id, body.quantity, body.unit, body.low_stock_threshold
    )
    return {
        "message": "Stock updated",
        "tile_id": updated.tile_id,
        "quantity": updated.quantity,
        "unit": updated.unit,
        "low_stock_threshold": updated.low_stock_threshold,
    }
