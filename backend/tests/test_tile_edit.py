import os
import sys
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

os.environ["PGVECTOR_ENABLED"] = "false"

from app.database import Base, get_db
from app.middleware.auth import create_access_token
from app.models.admin import Admin
from app.models.categories import (
    Application,
    ColorFamily,
    Finish,
    Material,
    Origin,
    Style,
)
from app.models.inventory import Inventory
from app.models.tile import Tile
from app.models.tile_image import TileEmbedding, TileImage
from app.routers.tiles import router as tiles_router
from app.schemas.tile import TileUpdate


class TestTileEditing(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)

        old_material = Material(name="Granite")
        self.new_material = Material(name="Marble")
        style = Style(name="Veined")
        finish = Finish(name="Polished")
        application = Application(name="Flooring")
        color = ColorFamily(name="Ivory")
        origin = Origin(name="Italy")
        self.db.add_all(
            [old_material, self.new_material, style, finish, application, color, origin]
        )
        self.db.flush()

        self.tile = Tile(
            sku="TEST-001",
            name="Test tile",
            material_id=old_material.id,
        )
        self.db.add(self.tile)
        self.db.flush()
        self.db.add(Inventory(tile_id=self.tile.id, quantity=17, unit="pieces"))
        image = TileImage(
            tile_id=self.tile.id,
            image_url="/static/test-tile.jpg",
            is_primary=True,
        )
        self.db.add(image)
        self.db.flush()
        self.db.add(
            TileEmbedding(
                tile_id=self.tile.id,
                image_id=image.id,
                embedding="preserved-test-embedding",
                model_version="test",
            )
        )
        self.db.commit()

        self.app = FastAPI()
        self.app.include_router(tiles_router)

        def override_get_db():
            yield self.db

        self.app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.db.close()
        self.engine.dispose()

    def create_account(self, role: str) -> Admin:
        account = Admin(
            name=f"{role} account",
            email=f"{role}@example.com",
            password_hash="unused",
            role=role,
            is_active=True,
            auth_version=0,
        )
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        return account

    @staticmethod
    def headers(account: Admin) -> dict[str, str]:
        token = create_access_token(
            {"sub": account.email, "role": account.role, "ver": account.auth_version}
        )
        return {"Authorization": f"Bearer {token}"}

    def test_admin_can_edit_tile_details_without_changing_stock_or_assets(self):
        style = self.db.query(Style).filter_by(name="Veined").one()
        finish = self.db.query(Finish).filter_by(name="Polished").one()
        application = self.db.query(Application).filter_by(name="Flooring").one()
        color = self.db.query(ColorFamily).filter_by(name="Ivory").one()
        origin = self.db.query(Origin).filter_by(name="Italy").one()
        account = self.create_account("admin")

        response = self.client.put(
            f"/api/tiles/{self.tile.id}",
            headers=self.headers(account),
            json={
                "description": "Updated description",
                "texture": "Honed",
                "material_id": self.new_material.id,
                "style_id": style.id,
                "finish_id": finish.id,
                "application_id": application.id,
                "color_family_id": color.id,
                "origin_id": origin.id,
                "width_cm": 60,
                "height_cm": 120,
                "thickness_cm": 2,
                "price_per_sqm": 325.5,
            },
        )

        self.assertEqual(response.status_code, 200)
        updated = response.json()
        self.assertEqual(updated["description"], "Updated description")
        self.assertEqual(updated["texture"], "Honed")
        self.assertEqual(updated["material"]["id"], self.new_material.id)
        self.assertEqual(updated["style"]["id"], style.id)
        self.assertEqual(updated["finish"]["id"], finish.id)
        self.assertEqual(updated["application"]["id"], application.id)
        self.assertEqual(updated["color_family"]["id"], color.id)
        self.assertEqual(updated["origin"]["id"], origin.id)
        self.assertEqual(updated["width_cm"], 60)
        self.assertEqual(updated["height_cm"], 120)
        self.assertEqual(updated["thickness_cm"], 2)
        self.assertEqual(updated["price_per_sqm"], 325.5)
        self.assertEqual(self.db.query(Inventory).filter_by(tile_id=self.tile.id).one().quantity, 17)
        self.assertEqual(self.db.query(TileImage).filter_by(tile_id=self.tile.id).count(), 1)
        self.assertEqual(
            self.db.query(TileEmbedding).filter_by(tile_id=self.tile.id).count(), 1
        )

    def test_super_admin_can_edit_tile_details(self):
        account = self.create_account("super_admin")

        response = self.client.put(
            f"/api/tiles/{self.tile.id}",
            headers=self.headers(account),
            json={"price_per_sqm": 0},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["price_per_sqm"], 0)

    def test_user_cannot_edit_tile_details(self):
        account = self.create_account("user")

        response = self.client.put(
            f"/api/tiles/{self.tile.id}",
            headers=self.headers(account),
            json={"description": "Unauthorized change"},
        )

        self.assertEqual(response.status_code, 403)
        self.db.refresh(self.tile)
        self.assertIsNone(self.tile.description)

    def test_invalid_dimensions_and_price_are_rejected(self):
        account = self.create_account("admin")

        invalid_payloads = (
            {"width_cm": 0},
            {"price_per_sqm": -1},
            {"material_id": None},
        )
        for invalid_data in invalid_payloads:
            with self.subTest(invalid_data=invalid_data):
                response = self.client.put(
                    f"/api/tiles/{self.tile.id}",
                    headers=self.headers(account),
                    json=invalid_data,
                )
                self.assertEqual(response.status_code, 422)

        for invalid_value in (float("inf"), float("nan")):
            with self.subTest(invalid_value=invalid_value):
                with self.assertRaises(ValidationError):
                    TileUpdate(width_cm=invalid_value)

        self.db.refresh(self.tile)
        self.assertIsNone(self.tile.width_cm)
        self.assertIsNone(self.tile.price_per_sqm)


if __name__ == "__main__":
    unittest.main()
