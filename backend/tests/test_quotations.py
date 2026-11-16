import os
import sys
import tempfile
import unittest

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
from app.models.cart import Order
from app.models.categories import Material, SizeFormat  # noqa: F401
from app.models.inventory import Inventory
from app.models.order_tracking import OrderTracking, OrderStatusEvent  # noqa: F401 – registers mappers
from app.models.quotation import Quotation
from app.models.tile import Tile
from app.models.tile_image import TileImage, TileEmbedding  # noqa: F401 – registers mapper for Tile.images
from app.routers import quotations as quotations_router


class TestQuotations(unittest.TestCase):
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
        size = SizeFormat(name="60x60")
        self.db.add_all([material, size])
        self.db.flush()
        self.priced = Tile(
            sku="QT-PRICE-1",
            name="Priced marble",
            material_id=material.id,
            size_format_id=size.id,
            width_cm=60,
            height_cm=60,
            price_per_sqm=250,
        )
        self.unpriced = Tile(
            sku="QT-NOPRICE",
            name="Unpriced marble",
            material_id=material.id,
            price_per_sqm=None,
        )
        self.db.add_all([self.priced, self.unpriced])
        self.db.flush()
        self.db.add(Inventory(tile_id=self.priced.id, quantity=20, unit="pieces"))
        self.admin = Admin(
            name="admin",
            email="admin@quotations.example.com",
            password_hash="unused",
            role="admin",
            is_active=True,
            auth_version=0,
        )
        self.user = Admin(
            name="user",
            email="user@quotations.example.com",
            password_hash="unused",
            role="user",
            is_active=True,
            auth_version=0,
        )
        self.db.add_all([self.admin, self.user])
        self.db.commit()

        self.app = FastAPI()
        self.app.include_router(quotations_router.router)

        def override_get_db():
            session = self.SessionLocal()
            try:
                yield session
            finally:
                session.close()

        self.app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.db.close()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def headers(self, account: Admin) -> dict[str, str]:
        token = create_access_token({
            "sub": account.email,
            "role": account.role,
            "ver": account.auth_version,
        })
        return {"Authorization": f"Bearer {token}"}

    def test_user_cannot_create_or_list_quotations(self):
        denied_list = self.client.get("/api/quotations", headers=self.headers(self.user))
        denied_create = self.client.post(
            "/api/quotations",
            headers=self.headers(self.user),
            json={
                "client_name": "Acme",
                "items": [{"tile_id": self.priced.id, "quantity": 1, "area_sqm": 1, "rate_per_sqm": 100}],
            },
        )
        self.assertEqual(denied_list.status_code, 403)
        self.assertEqual(denied_create.status_code, 403)
        self.assertEqual(self.db.query(Quotation).count(), 0)

    def test_create_quotation_calculates_totals_without_touching_stock_or_orders(self):
        response = self.client.post(
            "/api/quotations",
            headers=self.headers(self.admin),
            json={
                "client_name": "Asha Patel",
                "company_name": "Patel Interiors",
                "project_name": "Lobby floor",
                "email": "asha@example.com",
                "gst_rate": 18,
                "items": [{
                    "tile_id": self.priced.id,
                    "quantity": 2,
                    "area_sqm": 1.5,
                    "rate_per_sqm": 200,
                }],
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        payload = response.json()
        self.assertEqual(payload["quotation_number"], f"QT-{payload['id']:06d}")
        self.assertEqual(payload["items"][0]["line_total"], 600)
        self.assertEqual(payload["subtotal"], 600)
        self.assertEqual(payload["gst_amount"], 108)
        self.assertEqual(payload["grand_total"], 708)
        self.assertEqual(payload["items"][0]["tile_sku"], "QT-PRICE-1")
        self.assertEqual(payload["items"][0]["material"], "Marble")
        self.assertEqual(payload["items"][0]["catalog_rate_per_sqm"], 250)
        self.assertEqual(payload["status"], "issued")
        self.assertIn("valid_until", payload)

        self.db.expire_all()
        self.assertEqual(self.db.query(Inventory).filter_by(tile_id=self.priced.id).one().quantity, 20)
        self.assertEqual(self.db.query(Order).count(), 0)
        self.assertEqual(self.priced.price_per_sqm, 250)

        listed = self.client.get("/api/quotations", headers=self.headers(self.admin))
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()), 1)

        fetched = self.client.get(
            f"/api/quotations/{payload['id']}",
            headers=self.headers(self.admin),
        )
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["grand_total"], 708)

    def test_catalog_list_returns_existing_active_tiles_and_multi_line_quote(self):
        quoted = self.client.post(
            "/api/quotations",
            headers=self.headers(self.admin),
            json={
                "client_name": "Multi-line Buyer",
                "gst_rate": 18,
                "items": [
                    {"tile_id": self.priced.id, "quantity": 2, "area_sqm": 1.5, "rate_per_sqm": 200},
                    {"tile_id": self.unpriced.id, "quantity": 3, "area_sqm": 0.5, "rate_per_sqm": 80},
                ],
            },
        )
        self.assertEqual(quoted.status_code, 201, quoted.text)
        payload = quoted.json()
        self.assertEqual(len(payload["items"]), 2)
        self.assertEqual(payload["subtotal"], 720)
        self.assertEqual(payload["gst_amount"], 129.6)
        self.assertEqual(payload["grand_total"], 849.6)
        self.db.expire_all()
        self.assertEqual(self.db.query(Inventory).filter_by(tile_id=self.priced.id).one().quantity, 20)

    def test_quotation_rejects_missing_tiles_and_does_not_invent_prices(self):
        response = self.client.post(
            "/api/quotations",
            headers=self.headers(self.admin),
            json={
                "client_name": "Asha Patel",
                "items": [{
                    "tile_id": 99999,
                    "quantity": 1,
                    "area_sqm": 1,
                    "rate_per_sqm": 100,
                }],
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.db.query(Quotation).count(), 0)

        created = self.client.post(
            "/api/quotations",
            headers=self.headers(self.admin),
            json={
                "client_name": "Asha Patel",
                "items": [{
                    "tile_id": self.unpriced.id,
                    "quantity": 1,
                    "area_sqm": 2,
                    "rate_per_sqm": 80,
                }],
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        self.assertIsNone(created.json()["items"][0]["catalog_rate_per_sqm"])
        self.assertEqual(created.json()["items"][0]["line_total"], 160)


if __name__ == "__main__":
    unittest.main()
