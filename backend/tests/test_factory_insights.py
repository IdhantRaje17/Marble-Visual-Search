import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

os.environ["PGVECTOR_ENABLED"] = "false"

from app.database import Base, get_db
from app.middleware.auth import create_access_token
from app.models.admin import Admin
from app.models.cart import Order, OrderItem
from app.models.categories import Material
from app.models.factory import ProductionEntry
from app.models.inventory import Inventory
from app.models.inventory_movement import InventoryMovement
from app.models.order_tracking import OrderStatusEvent, OrderTracking  # noqa: F401
from app.models.quotation import Quotation, QuotationItem
from app.models.search_log import SearchLog
from app.models.tile import Tile
from app.models.tile_image import TileEmbedding, TileImage  # noqa: F401
from app.routers import dashboard as dashboard_router
from app.routers import quotations as quotations_router


class TestFactoryInsights(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = self.SessionLocal()

        material = Material(name="Marble")
        self.db.add(material)
        self.db.flush()
        self.tile = Tile(
            sku="FACTORY-AGED",
            name="Aged Marble",
            material_id=material.id,
            width_cm=100,
            height_cm=150,
            price_per_sqm=500,
        )
        self.db.add(self.tile)
        self.db.flush()
        self.db.add_all([
            Inventory(tile_id=self.tile.id, quantity=8, unit="pieces"),
            TileImage(
                tile_id=self.tile.id,
                image_url="/static/factory-aged.jpg",
                is_primary=True,
            ),
        ])
        boundary_tile = Tile(
            sku="FACTORY-180-DAYS",
            name="Exactly 180 days",
            material_id=material.id,
        )
        self.db.add(boundary_tile)
        self.db.flush()
        self.db.add(Inventory(tile_id=boundary_tile.id, quantity=2, unit="pieces"))

        self.admin = Admin(
            name="Analytics Admin",
            email="factory-admin@example.com",
            password_hash="unused",
            role="admin",
            is_active=True,
            auth_version=0,
        )
        buyer = Admin(
            name="Corporate Buyer",
            email="factory-buyer@example.com",
            password_hash="unused",
            role="user",
            is_active=True,
            auth_version=0,
        )
        self.db.add_all([self.admin, buyer])
        self.db.flush()

        now = datetime.now(timezone.utc)
        search = SearchLog(
            account_id=buyer.id,
            matched_tile_id=self.tile.id,
            status="matched",
            searched_at=now - timedelta(days=8),
        )
        order = Order(
            admin_id=buyer.id,
            status="delivered",
            total_amount=1000,
            placed_at=now - timedelta(days=4),
        )
        self.db.add_all([search, order])
        self.db.flush()
        quotation = Quotation(
            created_by=self.admin.id,
            search_id=search.id,
            order_id=order.id,
            client_name="Buyer",
            company_name="Northstar Builders",
            status="issued",
            gst_rate=18,
            subtotal=1500,
            gst_amount=270,
            grand_total=1770,
            created_at=now - timedelta(days=6),
        )
        quotation.items.append(QuotationItem(
            tile_id=self.tile.id,
            tile_name=self.tile.name,
            tile_sku=self.tile.sku,
            material="Marble",
            quantity=2,
            area_sqm=1.5,
            rate_per_sqm=500,
            line_total=1500,
            subtotal=1500,
        ))
        self.db.add_all([
            quotation,
            OrderItem(
                order_id=order.id,
                tile_id=self.tile.id,
                quantity=2,
                unit_price=500,
            ),
            ProductionEntry(
                tile_id=self.tile.id,
                tile_sku=self.tile.sku,
                tile_name=self.tile.name,
                quantity=12,
                factory_name="Factory 1",
                produced_at=date.today(),
            ),
            InventoryMovement(
                tile_id=self.tile.id,
                tile_sku=self.tile.sku,
                tile_name=self.tile.name,
                movement_type="production_receipt",
                quantity=8,
                direction=1,
                unit="pieces",
                balance_after=8,
                occurred_at=now - timedelta(days=200),
            ),
            InventoryMovement(
                tile_id=boundary_tile.id,
                tile_sku=boundary_tile.sku,
                tile_name=boundary_tile.name,
                movement_type="purchase",
                quantity=2,
                direction=1,
                unit="pieces",
                balance_after=2,
                occurred_at=datetime.combine(
                    date.today() - timedelta(days=180),
                    datetime.min.time(),
                    timezone.utc,
                ),
            ),
        ])
        self.db.commit()
        self.search_id = search.id
        self.order_id = order.id

        self.app = FastAPI()
        self.app.include_router(dashboard_router.router)
        self.app.include_router(quotations_router.router)

        def override_get_db():
            session = self.SessionLocal()
            try:
                yield session
            finally:
                session.close()

        self.app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(self.app)
        token = create_access_token({
            "sub": self.admin.email,
            "role": self.admin.role,
            "ver": self.admin.auth_version,
        })
        self.headers = {"Authorization": f"Bearer {token}"}

    def tearDown(self):
        self.client.close()
        self.db.close()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_factory_insights_use_linked_real_records(self):
        response = self.client.get("/api/admin/factory-insights", headers=self.headers)

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["production_vs_sales"], {
            "produced_quantity": 12,
            "sold_quantity": 2,
        })
        self.assertEqual(payload["dead_stock"]["tile_count"], 1)
        self.assertEqual(payload["conversion"]["searches"], 1)
        self.assertEqual(payload["conversion"]["quotations"], 1)
        self.assertEqual(payload["conversion"]["closed_orders"], 1)
        self.assertEqual(payload["conversion"]["search_to_sale_rate"], 100)

        critical = next(
            category for category in payload["stock_aging"]["categories"]
            if category["key"] == "critical"
        )
        items_by_sku = {item["sku"]: item for item in critical["items"]}
        self.assertEqual(items_by_sku["FACTORY-AGED"]["image_url"], "/static/factory-aged.jpg")
        self.assertEqual(items_by_sku["FACTORY-AGED"]["stock_age_days"], 200)
        self.assertEqual(items_by_sku["FACTORY-180-DAYS"]["stock_age_days"], 180)

        self.assertEqual(payload["top_materials"][0]["material"], "Marble")
        self.assertEqual(payload["top_materials"][0]["volume_sqm"], 3)
        self.assertEqual(payload["top_corporate_buyers"][0]["company_name"], "Northstar Builders")
        self.assertEqual(payload["top_corporate_buyers"][0]["completed_orders"], 1)
        self.assertEqual(payload["top_corporate_buyers"][0]["revenue"], 1000)

    def test_link_options_and_quotation_order_link_work(self):
        response = self.client.get("/api/admin/link-options", headers=self.headers)

        self.assertEqual(response.status_code, 200, response.text)
        options = response.json()
        self.assertTrue(any(
            item["tile_sku"] == "FACTORY-AGED" for item in options["searches"]
        ))
        self.assertTrue(any(
            item["status"] == "delivered" and item["buyer_name"] == "Corporate Buyer"
            for item in options["orders"]
        ))

        created = self.client.post(
            "/api/quotations",
            headers=self.headers,
            json={
                "client_name": "Follow-up Buyer",
                "company_name": "Northstar Builders",
                "search_id": self.search_id,
                "items": [{
                    "tile_id": self.tile.id,
                    "quantity": 1,
                    "area_sqm": 1,
                    "rate_per_sqm": 500,
                }],
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()["search_id"], self.search_id)
        self.assertIsNone(created.json()["order_id"])

        linked = self.client.patch(
            f"/api/quotations/{created.json()['id']}/links",
            headers=self.headers,
            json={"order_id": self.order_id},
        )
        self.assertEqual(linked.status_code, 200, linked.text)
        self.assertEqual(linked.json()["search_id"], self.search_id)
        self.assertEqual(linked.json()["order_id"], self.order_id)
