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
from app.models.tile import Tile
from app.models.tile_image import TileEmbedding, TileImage
from app.routers import cart as cart_router
from app.routers import inventory as inventory_router


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

        # SQLite has no SELECT FOR UPDATE; use an immediate write transaction to
        # exercise checkout serialization in the concurrent API test.
        @event.listens_for(self.engine, "connect")
        def disable_implicit_transactions(connection, _):
            connection.isolation_level = None

        @event.listens_for(self.engine, "begin")
        def begin_immediate(connection):
            connection.exec_driver_sql("BEGIN IMMEDIATE")

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
        self.assertEqual(self.tile.width_cm, 60)
        self.assertEqual(self.tile.price_per_sqm, 150)
        self.assertEqual(self.inventory.quantity, 9)
        self.assertEqual(self.inventory.low_stock_threshold, 3)

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
