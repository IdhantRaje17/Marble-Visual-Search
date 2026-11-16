import os
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

os.environ["PGVECTOR_ENABLED"] = "false"

from app.database import Base, get_db
from app.middleware.auth import create_access_token
from app.models.admin import Admin
from app.models.cart import Cart, CartItem, Order, OrderItem
from app.models.categories import Material
from app.models.inventory import Inventory
from app.models.search_log import SearchLog
from app.models.tile import Tile
from app.models.tile_image import TileEmbedding, TileImage
from app.models.factory import ProductionEntry
from app.models.inventory_movement import InventoryMovement
from app.routers import cart as cart_router
from app.routers import inventory as inventory_router
from app.routers import dashboard as dashboard_router


class TestInventoryAndOrders(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = os.path.join(self.temp_dir.name, "inventory-orders.sqlite")
        self.engine = create_engine(
            f"sqlite:///{database_path}",
            connect_args={"check_same_thread": False, "timeout": 15},
        )

        @event.listens_for(self.engine, "connect")
        def set_sqlite_timeout(connection, _):
            cursor = connection.cursor()
            cursor.execute("PRAGMA busy_timeout=15000")
            cursor.close()

        # SQLite has no SELECT FOR UPDATE; keep normal transaction semantics in
        # the test fixture so read-only auth dependencies do not acquire write locks.
        @event.listens_for(self.engine, "connect")
        def disable_implicit_transactions(connection, _):
            connection.isolation_level = None


        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = self.SessionLocal()

        material = Material(name="Marble")
        self.db.add(material)
        self.db.flush()
        self.tile = Tile(
            sku="ORDER-001",
            name="Order test tile",
            material_id=material.id,
            price_per_sqm=120,
        )
        self.db.add(self.tile)
        self.db.flush()
        self.inventory = Inventory(
            tile_id=self.tile.id,
            quantity=5,
            unit="pieces",
            low_stock_threshold=1,
        )
        self.db.add(self.inventory)
        image = TileImage(
            tile_id=self.tile.id,
            image_url="/static/order-test.jpg",
            is_primary=True,
        )
        self.db.add(image)
        self.db.flush()
        self.db.add(
            TileEmbedding(
                tile_id=self.tile.id,
                image_id=image.id,
                embedding="order-test-embedding",
                model_version="test",
            )
        )
        self.admin = self._create_account("admin")
        self.user = self._create_account("user")
        self.db.commit()
        self.db.refresh(self.tile)
        self.db.refresh(self.inventory)
        self.db.commit()

        self.app = FastAPI()
        self.app.include_router(inventory_router.router)
        self.app.include_router(cart_router.router)
        self.app.include_router(dashboard_router.router)

        def override_get_db():
            session = self.SessionLocal()
            try:
                yield session
            finally:
                session.close()

        self.app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(self.app, raise_server_exceptions=False)

    def tearDown(self):
        self.client.close()
        self.db.close()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def _create_account(self, role: str) -> Admin:
        account = Admin(
            name=role,
            email=f"{role}@inventory-orders.example.com",
            password_hash="unused",
            role=role,
            is_active=True,
            auth_version=0,
        )
        self.db.add(account)
        self.db.flush()
        return account

    @staticmethod
    def headers(account: Admin) -> dict[str, str]:
        token = create_access_token({
            "sub": account.email,
            "role": account.role,
            "ver": account.auth_version,
        })
        return {"Authorization": f"Bearer {token}"}

    def add_cart_item(self, account: Admin, quantity: int) -> None:
        cart = Cart(admin_id=account.id)
        self.db.add(cart)
        self.db.flush()
        self.db.add(CartItem(cart_id=cart.id, tile_id=self.tile.id, quantity=quantity))
        self.db.commit()

    def test_admin_can_edit_tile_and_stock_from_inventory_route(self):
        response = self.client.put(
            f"/api/inventory/{self.tile.id}/details",
            headers=self.headers(self.admin),
            json={
                "name": "Updated tile",
                "description": "Updated from inventory",
                "texture": "Brushed",
                "material_id": self.tile.material_id,
                "width_cm": 60,
                "height_cm": 120,
                "thickness_cm": 2,
                "price_per_sqm": 150,
                "quantity": 9,
                "unit": "pieces",
                "low_stock_threshold": 3,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.db.refresh(self.tile)
        self.db.refresh(self.inventory)
        self.assertEqual(self.tile.name, "Updated tile")
        self.assertEqual(self.tile.description, "Updated from inventory")
        self.assertEqual(self.tile.texture, "Brushed")
        self.assertEqual(self.tile.width_cm, 60)
        self.assertEqual(self.tile.price_per_sqm, 150)
        self.assertEqual(self.inventory.quantity, 9)
        self.assertEqual(self.inventory.low_stock_threshold, 3)

    def test_order_history_is_limited_to_authenticated_account(self):
        own_order = Order(admin_id=self.user.id, status="placed", total_amount=120)
        other_order = Order(admin_id=self.admin.id, status="completed", total_amount=240)
        self.db.add_all([own_order, other_order])
        self.db.flush()
        self.db.add_all([
            OrderItem(order_id=own_order.id, tile_id=self.tile.id, quantity=1, unit_price=120),
            OrderItem(order_id=other_order.id, tile_id=self.tile.id, quantity=2, unit_price=120),
        ])
        self.db.commit()

        response = self.client.get(
            "/api/cart/orders/mine",
            headers=self.headers(self.user),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual([order["id"] for order in response.json()], [own_order.id])
        self.assertEqual(response.json()[0]["items"][0]["quantity"], 1)

    def test_order_tracking_is_admin_only_and_status_filterable(self):
        placed_order = Order(admin_id=self.user.id, status="placed", total_amount=120)
        completed_order = Order(admin_id=self.admin.id, status="completed", total_amount=240)
        self.db.add_all([placed_order, completed_order])
        self.db.commit()

        denied = self.client.get(
            "/api/admin/orders",
            headers=self.headers(self.user),
        )
        response = self.client.get(
            "/api/admin/orders?status=placed",
            headers=self.headers(self.admin),
        )

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([order["id"] for order in response.json()], [placed_order.id])
        self.assertIsNone(response.json()[0]["shipment_details"])

        updated = self.client.patch(
            f"/api/admin/orders/{placed_order.id}/tracking",
            headers=self.headers(self.admin),
            json={
                "status": "dispatched",
                "carrier": "Recorded carrier",
                "tracking_number": "TRACK-100",
                "dispatched_at": "2026-10-25T10:00:00Z",
                "expected_delivery_at": "2020-01-01T10:00:00Z",
            },
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["tracking_number"], "TRACK-100")
        filtered_after_update = self.client.get(
            "/api/admin/orders?status=dispatched",
            headers=self.headers(self.admin),
        )
        self.assertEqual(len(filtered_after_update.json()), 1)
        self.assertEqual(filtered_after_update.json()[0]["timeline"][-1]["status"], "dispatched")
        self.assertGreater(filtered_after_update.json()[0]["delay_seconds"], 0)

    def test_production_movement_threshold_and_ledger_persist(self):
        produced = self.client.post(
            "/api/admin/production",
            headers=self.headers(self.admin),
            json={
                "tile_id": self.tile.id,
                "quantity": 7,
                "factory_name": "Main Factory",
                "batch_number": "BATCH-1",
                "produced_at": "2026-11-01",
                "notes": "Recorded production",
            },
        )
        self.assertEqual(produced.status_code, 200, produced.text)
        self.db.expire_all()
        entry = self.db.query(ProductionEntry).one()
        self.assertEqual(entry.quantity, 7)
        self.assertEqual(entry.batch_number, "BATCH-1")
        self.inventory = self.db.query(Inventory).filter_by(tile_id=self.tile.id).one()
        self.assertEqual(self.inventory.quantity, 12)
        receipt = self.db.query(InventoryMovement).filter_by(
            movement_type="production_receipt",
            tile_id=self.tile.id,
        ).one()
        self.assertEqual(receipt.quantity, 7)
        self.assertEqual(receipt.direction, 1)
        self.assertEqual(receipt.balance_after, 12)
        self.db.commit()

        movement = self.client.post(
            "/api/inventory/movements",
            headers=self.headers(self.admin),
            json={
                "tile_id": self.tile.id,
                "movement_type": "adjustment",
                "quantity": 2,
                "direction": -1,
                "reason": "Damage adjustment",
            },
        )
        self.assertEqual(movement.status_code, 200, movement.text)
        self.db.expire_all()
        self.assertEqual(
            self.db.query(Inventory).filter_by(tile_id=self.tile.id).one().quantity,
            10,
        )

        threshold = self.client.put(
            f"/api/inventory/{self.tile.id}",
            headers=self.headers(self.admin),
            json={"quantity": 10, "unit": "pieces", "low_stock_threshold": 3},
        )
        self.assertEqual(threshold.status_code, 200, threshold.text)
        self.db.expire_all()
        inventory = self.db.query(Inventory).filter_by(tile_id=self.tile.id).one()
        self.assertEqual(inventory.low_stock_threshold, 3)
        ledger = self.client.get(
            "/api/inventory/movements",
            headers=self.headers(self.admin),
        )
        self.assertEqual(ledger.status_code, 200)
        self.assertGreaterEqual(len(ledger.json()), 2)

    def test_analytics_marks_unrecorded_metrics_unavailable(self):
        response = self.client.get(
            "/api/admin/analytics",
            headers=self.headers(self.admin),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["orders"]["production_vs_sales"]["available"])
        self.assertEqual(payload["orders"]["production_vs_sales"]["produced_quantity"], 0)
        self.assertEqual(payload["orders"]["production_vs_sales"]["sold_quantity"], 0)
        self.assertFalse(payload["orders"]["search_to_quotation_to_order"]["available"])
        self.assertFalse(payload["inventory"]["stock_aging_and_turnover"]["available"])
        self.assertTrue(payload["orders"]["revenue_available"])
        self.assertEqual(payload["orders"]["completed"], 0)
        self.assertEqual(payload["orders"]["units_sold"], 0)
        self.assertEqual(payload["orders"]["revenue"], 0)
        self.assertIsNone(payload["orders"]["average_order_value"])

    def test_analytics_excludes_placed_orders_and_counts_completed_sales(self):
        placed = Order(admin_id=self.user.id, status="placed", total_amount=120)
        paid = Order(admin_id=self.user.id, status="paid", total_amount=240)
        incomplete = Order(admin_id=self.admin.id, status="completed", total_amount=None)
        self.db.add_all([placed, paid, incomplete])
        self.db.flush()
        self.db.add_all([
            OrderItem(order_id=placed.id, tile_id=self.tile.id, quantity=1, unit_price=120),
            OrderItem(order_id=paid.id, tile_id=self.tile.id, quantity=2, unit_price=120),
            OrderItem(order_id=incomplete.id, tile_id=self.tile.id, quantity=3, unit_price=None),
        ])
        self.db.add(SearchLog(matched_tile_id=self.tile.id, status="matched", confidence=0.9))
        self.db.commit()

        denied = self.client.get("/api/admin/analytics", headers=self.headers(self.user))
        self.assertEqual(denied.status_code, 403)

        payload = self.client.get(
            "/api/admin/analytics",
            headers=self.headers(self.admin),
        ).json()
        self.assertEqual(payload["orders"]["total"], 3)
        self.assertEqual(payload["orders"]["completed"], 2)
        self.assertEqual(payload["orders"]["units_sold"], 5)
        self.assertFalse(payload["orders"]["revenue_available"])
        self.assertIsNone(payload["orders"]["revenue"])
        self.assertEqual(payload["orders"]["best_sellers"][0]["units_sold"], 5)
        self.assertFalse(payload["orders"]["best_sellers"][0]["revenue_available"])
        self.assertEqual(payload["orders"]["top_searched_tiles"][0]["searches"], 1)
        self.assertNotEqual(
            payload["orders"]["best_sellers"][0]["units_sold"],
            payload["orders"]["top_searched_tiles"][0]["searches"],
        )

        self.db.query(OrderItem).filter(OrderItem.order_id == incomplete.id).delete()
        self.db.delete(incomplete)
        self.db.commit()
        complete_payload = self.client.get(
            "/api/admin/analytics",
            headers=self.headers(self.admin),
        ).json()
        self.assertTrue(complete_payload["orders"]["revenue_available"])
        self.assertEqual(complete_payload["orders"]["completed"], 1)
        self.assertEqual(complete_payload["orders"]["units_sold"], 2)
        self.assertEqual(complete_payload["orders"]["revenue"], 240)
        self.assertEqual(complete_payload["orders"]["average_order_value"], 240)
        self.assertEqual(complete_payload["orders"]["best_sellers"][0]["revenue"], 240)
        self.assertEqual(complete_payload["orders"]["top_buyers"][0]["completed_orders"], 1)

    def test_user_cannot_edit_tile_or_inventory(self):
        response = self.client.put(
            f"/api/inventory/{self.tile.id}/details",
            headers=self.headers(self.user),
            json={
                "name": "Unauthorized",
                "quantity": 99,
                "unit": "pieces",
                "low_stock_threshold": 1,
            },
        )

        self.assertEqual(response.status_code, 403)
        self.db.refresh(self.tile)
        self.db.refresh(self.inventory)
        self.assertEqual(self.tile.name, "Order test tile")
        self.assertEqual(self.inventory.quantity, 5)

    def test_super_admin_can_edit_tile_and_stock(self):
        super_admin = self._create_account("super_admin")
        self.db.commit()

        response = self.client.put(
            f"/api/inventory/{self.tile.id}/details",
            headers=self.headers(super_admin),
            json={
                "name": "Super admin edit",
                "quantity": 7,
                "unit": "pieces",
                "low_stock_threshold": 2,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.db.refresh(self.tile)
        self.db.refresh(self.inventory)
        self.assertEqual(self.tile.name, "Super admin edit")
        self.assertEqual(self.inventory.quantity, 7)

    def test_invalid_inventory_edit_rolls_back_tile_and_stock(self):
        response = self.client.put(
            f"/api/inventory/{self.tile.id}/details",
            headers=self.headers(self.admin),
            json={
                "name": "Must roll back",
                "material_id": self.tile.material_id,
                "width_cm": 0,
                "quantity": 20,
                "unit": "pieces",
                "low_stock_threshold": 1,
            },
        )

        self.assertEqual(response.status_code, 422)
        self.db.refresh(self.tile)
        self.db.refresh(self.inventory)
        self.assertEqual(self.tile.name, "Order test tile")
        self.assertEqual(self.inventory.quantity, 5)

    def test_cart_changes_do_not_deduct_stock_and_successful_order_does(self):
        headers = self.headers(self.user)
        add_response = self.client.post(
            "/api/cart/add",
            headers=headers,
            json={"tile_id": self.tile.id, "quantity": 2},
        )
        self.assertEqual(add_response.status_code, 200)
        self.db.refresh(self.inventory)
        self.assertEqual(self.inventory.quantity, 5)
        self.db.commit()

        order_response = self.client.post("/api/cart/checkout", headers=headers)
        self.assertEqual(order_response.status_code, 200, order_response.text)
        self.db.refresh(self.inventory)
        self.assertEqual(self.inventory.quantity, 3)
        self.db.commit()
        self.assertEqual(self.db.query(Order).filter_by(admin_id=self.user.id).count(), 1)
        self.db.commit()
        self.assertEqual(
            self.db.query(OrderItem).join(Order).filter(Order.admin_id == self.user.id).one().quantity,
            2,
        )
        self.assertEqual(self.db.query(CartItem).count(), 0)
        sale_movement = self.db.query(InventoryMovement).filter_by(
            movement_type="sale",
            tile_id=self.tile.id,
        ).one()
        self.assertEqual(sale_movement.quantity, 2)
        self.assertEqual(sale_movement.direction, -1)
        self.assertEqual(sale_movement.balance_after, 3)
        self.assertEqual(self.db.query(TileImage).filter_by(tile_id=self.tile.id).count(), 1)
        self.assertEqual(self.db.query(TileEmbedding).filter_by(tile_id=self.tile.id).count(), 1)
        self.db.commit()

        retry_response = self.client.post("/api/cart/checkout", headers=headers)
        self.assertEqual(retry_response.status_code, 400)
        self.db.refresh(self.inventory)
        self.assertEqual(self.inventory.quantity, 3)
        self.assertEqual(self.db.query(Order).filter_by(admin_id=self.user.id).count(), 1)

    def test_insufficient_stock_does_not_create_order_or_clear_cart(self):
        self.add_cart_item(self.user, quantity=6)

        response = self.client.post(
            "/api/cart/checkout", headers=self.headers(self.user)
        )

        self.assertEqual(response.status_code, 409)
        self.db.refresh(self.inventory)
        self.assertEqual(self.inventory.quantity, 5)
        self.assertEqual(self.db.query(Order).filter_by(admin_id=self.user.id).count(), 0)
        self.assertEqual(self.db.query(CartItem).count(), 1)

    def test_failed_order_creation_rolls_back_stock_and_keeps_cart(self):
        self.add_cart_item(self.user, quantity=2)

        def fail_order_item_insert(*_):
            raise RuntimeError("simulated order item insert failure")

        event.listen(OrderItem, "before_insert", fail_order_item_insert)
        try:
            response = self.client.post(
                "/api/cart/checkout", headers=self.headers(self.user)
            )
        finally:
            event.remove(OrderItem, "before_insert", fail_order_item_insert)

        self.assertEqual(response.status_code, 500)
        self.db.expire_all()
        self.assertEqual(
            self.db.query(Inventory).filter_by(tile_id=self.tile.id).one().quantity, 5
        )
        self.assertEqual(self.db.query(Order).filter_by(admin_id=self.user.id).count(), 0)
        self.assertEqual(self.db.query(CartItem).count(), 1)

    def test_concurrent_checkouts_do_not_oversell(self):
        second_user = self._create_account("second_user")
        self.db.commit()
        self.add_cart_item(self.user, quantity=1)
        self.add_cart_item(second_user, quantity=1)
        barrier = threading.Barrier(2)

        def checkout_for(account: Admin):
            barrier.wait(timeout=5)
            return self.client.post(
                "/api/cart/checkout", headers=self.headers(account)
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(checkout_for, (self.user, second_user)))

        self.assertCountEqual([response.status_code for response in responses], [200, 200])
        self.db.expire_all()
        self.assertEqual(
            self.db.query(Inventory).filter_by(tile_id=self.tile.id).one().quantity, 3
        )
        self.assertEqual(self.db.query(Order).count(), 2)

    def test_concurrent_orders_for_last_item_allow_only_one(self):
        self.db.query(Inventory).filter_by(tile_id=self.tile.id).update(
            {Inventory.quantity: 1}
        )
        second_user = self._create_account("last_item_user")
        self.db.commit()
        self.add_cart_item(self.user, quantity=1)
        self.add_cart_item(second_user, quantity=1)
        barrier = threading.Barrier(2)

        def checkout_for(account: Admin):
            barrier.wait(timeout=5)
            return self.client.post(
                "/api/cart/checkout", headers=self.headers(account)
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(checkout_for, (self.user, second_user)))

        self.assertCountEqual([response.status_code for response in responses], [200, 409])
        self.db.expire_all()
        self.assertEqual(
            self.db.query(Inventory).filter_by(tile_id=self.tile.id).one().quantity, 0
        )
        self.assertEqual(self.db.query(Order).count(), 1)


if __name__ == "__main__":
    unittest.main()
