"""
Minimal non-destructive tests for the Gatekeeper validation layer.
"""
import io
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import torch
from PIL import Image

# Ensure backend package is importable
BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)


def _make_test_image() -> bytes:
    arr = np.random.randint(0, 255, (224, 224, 3), dtype=np.uint8)
    img = Image.fromarray(arr, "RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _make_fixture_image(kind: str) -> bytes:
    from PIL import ImageDraw

    image = Image.new("RGB", (224, 224), "white")
    draw = ImageDraw.Draw(image)
    if kind == "landscape":
        draw.rectangle((0, 0, 224, 105), fill=(120, 180, 220))
        draw.rectangle((0, 106, 224, 224), fill=(60, 140, 55))
        draw.polygon([(0, 150), (100, 95), (224, 155), (224, 224), (0, 224)], fill=(85, 120, 45))
    elif kind == "person":
        draw.ellipse((88, 28, 136, 76), fill=(210, 165, 135))
        draw.line((112, 76, 112, 160), fill=(30, 70, 160), width=22)
        draw.line((112, 95, 65, 130), fill=(30, 70, 160), width=14)
        draw.line((112, 95, 160, 130), fill=(30, 70, 160), width=14)
        draw.line((112, 155, 75, 215), fill=(35, 35, 45), width=16)
        draw.line((112, 155, 150, 215), fill=(35, 35, 45), width=16)
    elif kind == "apple":
        draw.ellipse((50, 65, 174, 190), fill=(205, 25, 35))
        draw.ellipse((87, 49, 130, 105), fill=(205, 25, 35))
        draw.line((110, 60, 115, 35), fill=(75, 45, 20), width=8)
        draw.ellipse((115, 30, 150, 49), fill=(35, 125, 45))
    elif kind == "object":
        draw.rectangle((35, 45, 185, 195), fill=(220, 170, 70), outline=(60, 50, 40), width=8)
        draw.line((55, 75, 165, 165), fill=(90, 60, 35), width=10)
    else:
        draw.rectangle((0, 0, 224, 224), fill=(170, 170, 165))
        for offset in range(-180, 300, 32):
            draw.arc((offset, 25, offset + 230, 195), 15, 165, fill=(95, 95, 92), width=3)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class TestGatekeeperModule(unittest.TestCase):
    def setUp(self):
        os.environ["GATEKEEPER_ENABLED"] = "false"
        import ai.gatekeeper as gk
        gk._gatekeeper = None

    def tearDown(self):
        os.environ.pop("GATEKEEPER_ENABLED", None)
        os.environ.pop("GATEKEEPER_THRESHOLD", None)
        os.environ.pop("GATEKEEPER_CHECKPOINT_PATH", None)
        import ai.gatekeeper as gk
        gk._gatekeeper = None

    def test_disabled_returns_validation_unavailable(self):
        from ai.gatekeeper import validate_tile_image

        result = validate_tile_image(_make_test_image())
        self.assertFalse(result["is_tile"])
        self.assertEqual(result["status"], "VALIDATION_UNAVAILABLE")
        self.assertIsNone(result["score"])

    def test_missing_enabled_setting_defaults_to_disabled_optional_gatekeeper(self):
        from ai.gatekeeper import validate_tile_image

        os.environ.pop("GATEKEEPER_ENABLED", None)
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["GATEKEEPER_CHECKPOINT_PATH"] = os.path.join(tmp, "missing.pt")
            import ai.gatekeeper as gk
            gk._gatekeeper = None

            result = validate_tile_image(_make_test_image())

        self.assertEqual(result["status"], "VALIDATION_UNAVAILABLE")
        self.assertFalse(result["is_tile"])

    def test_enabled_missing_checkpoint_is_unavailable(self):
        from ai.gatekeeper import Gatekeeper, validate_tile_image

        with tempfile.TemporaryDirectory() as tmp:
            missing = os.path.join(tmp, "missing_gatekeeper.pt")
            os.environ["GATEKEEPER_ENABLED"] = "true"
            os.environ["GATEKEEPER_CHECKPOINT_PATH"] = missing

            import ai.gatekeeper as gk
            gk._gatekeeper = None

            result = validate_tile_image(_make_test_image())
            self.assertFalse(result["is_tile"])
            self.assertEqual(result["status"], "VALIDATION_UNAVAILABLE")
            self.assertIsNone(result["score"])

            keeper = Gatekeeper(checkpoint_path=missing)
            self.assertFalse(keeper.load())
            self.assertFalse(keeper.is_ready)

    def test_validate_returns_expected_keys(self):
        from ai.gatekeeper import Gatekeeper

        with tempfile.NamedTemporaryFile(suffix=".pt", delete=False) as f:
            checkpoint_path = f.name

        try:
            from torchvision import models
            import torch.nn as nn

            model = models.mobilenet_v3_small(weights=None)
            in_features = model.classifier[-1].in_features
            model.classifier[-1] = nn.Linear(in_features, 2)
            torch.save({
                "model_state_dict": model.state_dict(),
                "class_to_idx": {"not_tile": 0, "tile": 1},
                "preprocessing": {
                    "input_size": 224,
                    "resize": "shorter_edge",
                    "crop": "center",
                    "mean": [0.485, 0.456, 0.406],
                    "std": [0.229, 0.224, 0.225],
                },
                "training_complete": True,
            }, checkpoint_path)

            keeper = Gatekeeper(checkpoint_path=checkpoint_path)
            self.assertTrue(keeper.load())
            result = keeper.validate(_make_test_image(), threshold=0.70)
            self.assertIn(result["status"], {"VALID_TILE", "NOT_TILE"})
            self.assertIn("is_tile", result)
            self.assertIn("score", result)
            self.assertIsInstance(result["is_tile"], bool)
            self.assertIsInstance(result["score"], float)
        finally:
            os.remove(checkpoint_path)

    def test_rejection_when_score_below_threshold(self):
        from ai.gatekeeper import Gatekeeper

        with tempfile.NamedTemporaryFile(suffix=".pt", delete=False) as f:
            checkpoint_path = f.name

        try:
            from torchvision import models
            import torch.nn as nn

            model = models.mobilenet_v3_small(weights=None)
            in_features = model.classifier[-1].in_features
            model.classifier[-1] = nn.Linear(in_features, 2)
            # Bias class 0 (not_tile) heavily so tile score stays low
            with torch.no_grad():
                model.classifier[-1].bias.copy_(torch.tensor([5.0, -5.0]))
            torch.save({
                "model_state_dict": model.state_dict(),
                "class_to_idx": {"not_tile": 0, "tile": 1},
                "preprocessing": {
                    "input_size": 224,
                    "resize": "shorter_edge",
                    "crop": "center",
                    "mean": [0.485, 0.456, 0.406],
                    "std": [0.229, 0.224, 0.225],
                },
                "training_complete": True,
            }, checkpoint_path)

            keeper = Gatekeeper(checkpoint_path=checkpoint_path)
            keeper.load()
            result = keeper.validate(_make_test_image(), threshold=0.70)
            self.assertFalse(result["is_tile"])
            self.assertLess(result["score"], 0.70)
        finally:
            os.remove(checkpoint_path)

    def test_inference_failure_is_unavailable(self):
        from ai.gatekeeper import Gatekeeper

        class BrokenModel(torch.nn.Module):
            def forward(self, _):
                raise RuntimeError("inference failed")

        keeper = Gatekeeper()
        keeper._model = BrokenModel()
        result = keeper.validate(_make_test_image(), threshold=0.70)
        self.assertEqual(result["status"], "VALIDATION_UNAVAILABLE")
        self.assertFalse(result["is_tile"])


class TestSearchRouterGatekeeper(unittest.TestCase):
    def setUp(self):
        os.environ["GATEKEEPER_ENABLED"] = "false"
        from app.main import app
        from app.database import get_db
        from app.middleware.auth import get_current_account

        self.app = app
        self.get_db = get_db
        self.get_current_account = get_current_account
        self.account = SimpleNamespace(id=1, name="Test", email="test@example.com", role="user")
        self.app.dependency_overrides[get_current_account] = lambda: self.account
        self.app.dependency_overrides[get_db] = lambda: SimpleNamespace(add=lambda _: None, commit=lambda: None)

    def tearDown(self):
        os.environ.pop("GATEKEEPER_ENABLED", None)
        self.app.dependency_overrides.clear()
        import ai.gatekeeper as gk
        gk._gatekeeper = None

    def test_app_starts(self):
        from app.main import app

        self.assertIsNotNone(app)
        self.assertEqual(app.title, "Marble AI API")

    @patch("app.routers.search.run_visual_search")
    @patch("app.routers.search.validate_tile_image")
    def test_user_and_admin_can_search_after_validation(self, mock_validate, mock_search):
        from fastapi.testclient import TestClient
        from app.models.admin import Admin
        import hashlib

        mock_validate.return_value = {"status": "VALID_TILE", "is_tile": True, "score": 0.98}
        mock_search.return_value = {
            "results": [],
            "validation": {"is_valid": True, "is_tile": True, "confidence": 100.0, "message": ""},
        }

        accounts = [
            Admin(id=1, name="User", email="user@example.com", password_hash=hashlib.sha256(b"test-password").hexdigest(), role="user", is_active=True),
            Admin(id=2, name="Admin", email="admin@example.com", password_hash=hashlib.sha256(b"test-password").hexdigest(), role="admin", is_active=True),
        ]

        class AccountQuery:
            def __init__(self):
                self.email = None

            def filter(self, *expressions):
                email_filter = next(
                    expression for expression in expressions
                    if getattr(expression.left, "key", None) == "email"
                )
                self.email = email_filter.right.value
                return self

            def first(self):
                return next((account for account in accounts if account.email == self.email), None)

        class Session:
            def query(self, model):
                return AccountQuery()

            def add(self, _):
                pass

            def commit(self):
                pass

        self.app.dependency_overrides.pop(self.get_current_account)
        self.app.dependency_overrides[self.get_db] = lambda: Session()
        client = TestClient(self.app)
        image_bytes = _make_test_image()

        for account in accounts:
            with self.subTest(role=account.role):
                login = client.post(
                    "/api/auth/login",
                    json={"email": account.email, "password": "test-password"},
                )
                self.assertEqual(login.status_code, 200)
                self.assertEqual(login.json()["role"], account.role)
                response = client.post(
                    "/api/search/image?top_k=3",
                    files={"file": ("test.jpg", image_bytes, "image/jpeg")},
                    headers={"Authorization": f"Bearer {login.json()['access_token']}"},
                )
                self.assertEqual(response.status_code, 200)

        self.assertEqual(mock_validate.call_count, 2)
        self.assertEqual(mock_search.call_count, 2)

    @patch("app.routers.search.run_visual_search")
    @patch("app.routers.search.validate_tile_image")
    def test_gatekeeper_rejection_returns_400(self, mock_validate, mock_search):
        from fastapi.testclient import TestClient

        mock_validate.return_value = {"status": "NOT_TILE", "is_tile": False, "score": 0.12}
        client = TestClient(self.app)
        image_bytes = _make_test_image()
        response = client.post(
            "/api/search/image?top_k=3",
            files={"file": ("test.jpg", image_bytes, "image/jpeg")},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"]["status"], "NOT_TILE")
        mock_search.assert_not_called()

    @patch("app.routers.search.run_visual_search")
    @patch("app.routers.search.validate_tile_image")
    def test_landscape_person_apple_and_object_never_reach_dinov2(self, mock_validate, mock_search):
        from fastapi.testclient import TestClient

        mock_validate.return_value = {"status": "NOT_TILE", "is_tile": False, "score": 0.08}
        client = TestClient(self.app)
        for kind in ("landscape", "person", "apple", "object"):
            with self.subTest(image_kind=kind):
                response = client.post(
                    "/api/search/image",
                    files={"file": (f"{kind}.png", _make_fixture_image(kind), "image/png")},
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["detail"]["status"], "NOT_TILE")
        mock_search.assert_not_called()

    @patch("app.routers.search.run_visual_search")
    @patch("app.routers.search.validate_tile_image")
    def test_genuine_tile_fixture_reaches_dinov2_only_after_validation(self, mock_validate, mock_search):
        from fastapi.testclient import TestClient

        mock_validate.return_value = {"status": "VALID_TILE", "is_tile": True, "score": 0.93}
        mock_search.return_value = {"results": [{"tile_id": 5, "sku": "MRB-005", "confidence": 92.0}], "validation": {}}
        response = TestClient(self.app).post(
            "/api/search/image",
            files={"file": ("tile.png", _make_fixture_image("tile"), "image/png")},
        )
        self.assertEqual(response.status_code, 200)
        mock_validate.assert_called_once()
        mock_search.assert_called_once()

    @patch("app.routers.search.run_visual_search")
    @patch("app.routers.search.validate_tile_image")
    def test_unavailable_validation_falls_back_to_dinov2(self, mock_validate, mock_search):
        from fastapi.testclient import TestClient

        mock_validate.return_value = {
            "status": "VALIDATION_UNAVAILABLE",
            "is_tile": False,
            "score": None,
            "message": "Tile validation unavailable.",
        }
        mock_search.return_value = {"results": [{"tile_id": 5, "sku": "MRB-005", "confidence": 92.0}], "validation": {}}
        response = TestClient(self.app).post(
            "/api/search/image",
            files={"file": ("tile.png", _make_fixture_image("tile"), "image/png")},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["validation"]["status"], "VALIDATION_UNAVAILABLE")
        self.assertEqual(response.json()["results"][0]["sku"], "MRB-005")
        mock_search.assert_called_once()

    @patch("app.routers.search.run_visual_search")
    def test_disabled_gatekeeper_falls_back_to_dinov2(self, mock_search):
        from fastapi.testclient import TestClient

        os.environ["GATEKEEPER_ENABLED"] = "false"
        mock_search.return_value = {"results": [{"tile_id": 5, "sku": "MRB-005", "confidence": 92.0}], "validation": {}}
        response = TestClient(self.app).post(
            "/api/search/image",
            files={"file": ("tile.png", _make_fixture_image("tile"), "image/png")},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["validation"]["status"], "VALIDATION_UNAVAILABLE")
        self.assertEqual(response.json()["results"][0]["sku"], "MRB-005")
        mock_search.assert_called_once()

    def test_user_cannot_access_admin_tile_management(self):
        from fastapi.testclient import TestClient

        self.account.role = "user"
        response = TestClient(self.app).get("/api/tiles/")
        self.assertEqual(response.status_code, 403)

    def test_user_cannot_access_admin_analytics(self):
        from fastapi.testclient import TestClient

        self.account.role = "user"
        response = TestClient(self.app).get("/api/admin/analytics")
        self.assertEqual(response.status_code, 403)

    def test_search_history_is_scoped_to_account(self):
        from fastapi.testclient import TestClient
        from app.models.search_log import SearchLog

        rows = [
            SimpleNamespace(id=1, account_id=1),
            SimpleNamespace(id=2, account_id=2),
        ]
        queried_models = []

        class Query:
            def __init__(self, records):
                self.records = records

            def filter(self, expression):
                account_id = expression.right.value
                self.records = [row for row in self.records if row.account_id == account_id]
                return self

            def order_by(self, *_):
                return self

            def limit(self, *_):
                return self

            def all(self):
                return self.records

        class Session:
            def query(self, model):
                queried_models.append(model)
                return Query(rows)

        self.app.dependency_overrides[self.get_db] = lambda: Session()
        client = TestClient(self.app)

        self.account.id = 1
        first = client.get("/api/search/history").json()
        self.account.id = 2
        second = client.get("/api/search/history").json()

        self.assertTrue(all(model is SearchLog for model in queried_models))
        self.assertEqual([row["id"] for row in first], [1])
        self.assertEqual([row["id"] for row in second], [2])

    def test_cart_is_scoped_to_account(self):
        from app.models.cart import Cart
        from app.routers.cart import _get_or_create_cart

        carts = {1: Cart(id=1, admin_id=1)}

        class Query:
            def filter(self, expression):
                self.account_id = expression.right.value
                return self

            def first(self):
                return carts.get(self.account_id)

        class Session:
            def query(self, _):
                return Query()

            def add(self, cart):
                carts[cart.admin_id] = cart

            def commit(self):
                pass

            def refresh(self, _):
                pass

        db = Session()
        first_cart = _get_or_create_cart(db, 1)
        second_cart = _get_or_create_cart(db, 2)

        self.assertIs(first_cart, carts[1])
        self.assertIs(second_cart, carts[2])
        self.assertNotEqual(first_cart.id, second_cart.id)


class TestVisualSearchInventoryIndependence(unittest.TestCase):
    def _run_search(self, tile, inventory):
        from ai import search as search_module
        from app.models.inventory import Inventory, WarehouseLocation
        from app.models.tile import Tile
        from app.models.tile_image import TileEmbedding, TileImage

        class Rows:
            def fetchall(self):
                return [(tile.id, 7, 0.1)]

        class Query:
            def __init__(self, model):
                self.model = model

            def filter(self, *_):
                return self

            def first(self):
                if self.model is Tile:
                    return tile
                if self.model is Inventory:
                    return inventory
                if self.model is WarehouseLocation:
                    return None
                if self.model is TileImage:
                    return SimpleNamespace(image_url="/static/reference.jpg")
                return None

            def all(self):
                return []

        class Session:
            def execute(self, *_):
                return Rows()

            def query(self, model):
                return Query(model)

        with patch.object(search_module, "get_model", return_value=(object(), object())), \
             patch.object(search_module, "_query_embedding", return_value=np.array([1.0, 0.0], dtype=np.float32)), \
             patch.object(search_module, "_pgvector_unavailable", False):
            return search_module.search_tile(
                image_input=b"validated-image",
                db=Session(),
                top_k=3,
            )

    def test_inactive_catalog_match_without_inventory_is_still_returned(self):
        tile = SimpleNamespace(id=42, sku="MRB-42", name="Inactive reference", is_active=False)
        response = self._run_search(tile, inventory=None)

        self.assertEqual([item["tile_id"] for item in response["results"]], [42])
        self.assertFalse(response["results"][0]["is_active"])
        self.assertEqual(response["results"][0]["stock"]["status"], "INVENTORY_NOT_CONFIGURED")
        self.assertIsNone(response["results"][0]["stock"]["quantity"])

    def test_out_of_stock_catalog_match_is_still_returned(self):
        tile = SimpleNamespace(id=43, sku="MRB-43", name="Out of stock reference", is_active=True)
        inventory = SimpleNamespace(quantity=0, unit="pieces", low_stock_threshold=5)
        response = self._run_search(tile, inventory)

        self.assertEqual([item["tile_id"] for item in response["results"]], [43])
        self.assertEqual(response["results"][0]["stock"]["status"], "OUT_OF_STOCK")
        self.assertEqual(response["results"][0]["stock"]["quantity"], 0)
if __name__ == "__main__":
    unittest.main()
