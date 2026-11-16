import json
import os
import sys
import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.database import Base, get_db
from app.middleware.auth import create_access_token
from app.models.admin import Admin
from app.models.cart import Cart, CartItem, Order, OrderItem
from app.models.categories import ColorFamily, Finish, Material, Style
from app.models.chat import ChatMessage
from app.models.factory import ProductionEntry
from app.models.inventory import Inventory, WarehouseLocation
from app.models.inventory_movement import InventoryMovement
from app.models.order_tracking import OrderTracking, OrderStatusEvent  # noqa: F401
from app.models.quotation import Quotation, QuotationItem
from app.models.search_log import SearchLog  # noqa: F401 – registers quotation FK target
from app.models.tile import Tile
from app.models.tile_image import TileEmbedding, TileImage  # noqa: F401
from app.routers import chat as chat_router
from app.services.chatbot import generate_chat_reply


class TestChatbot(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = self.SessionLocal()

        self.material = Material(name="Marble")
        self.white = ColorFamily(name="White")
        self.black = ColorFamily(name="Black")
        self.polished = Finish(name="Polished")
        self.veined = Style(name="Veined")
        self.db.add_all([
            self.material, self.white, self.black, self.polished, self.veined,
        ])
        self.db.flush()

        self.user = self._account("user", "user")
        self.other_user = self._account("other-user", "user")
        self.admin = self._account("admin", "admin")
        self.super_admin = self._account("super-admin", "super_admin")

        self.white_tile = Tile(
            sku="MARBLE-WHITE-1",
            name="Carrara White",
            description="Natural veined stone",
            material_id=self.material.id,
            color_family_id=self.white.id,
            finish_id=self.polished.id,
            style_id=self.veined.id,
            price_per_sqm=250,
            is_active=True,
        )
        self.black_tile = Tile(
            sku="MARBLE-BLACK-1",
            name="Black Marble",
            material_id=self.material.id,
            color_family_id=self.black.id,
            price_per_sqm=200,
            is_active=True,
        )
        self.inactive_tile = Tile(
            sku="MARBLE-OLD-1",
            name="Inactive White Marble",
            material_id=self.material.id,
            color_family_id=self.white.id,
            finish_id=self.polished.id,
            price_per_sqm=100,
            is_active=False,
        )
        self.db.add_all([self.white_tile, self.black_tile, self.inactive_tile])
        self.db.flush()
        self.db.add_all([
            Inventory(
                tile_id=self.white_tile.id,
                quantity=3,
                unit="pieces",
                low_stock_threshold=5,
            ),
            Inventory(
                tile_id=self.black_tile.id,
                quantity=20,
                unit="pieces",
                low_stock_threshold=5,
            ),
            Inventory(
                tile_id=self.inactive_tile.id,
                quantity=0,
                unit="pieces",
                low_stock_threshold=5,
            ),
        ])
        self.db.add(WarehouseLocation(
            tile_id=self.white_tile.id,
            aisle="A",
            rack="R1",
            bin="B2",
            notes="North warehouse",
        ))

        self.user_order = Order(
            admin_id=self.user.id,
            status="placed",
            total_amount=250,
        )
        self.other_order = Order(
            admin_id=self.other_user.id,
            status="paid",
            total_amount=500,
        )
        self.db.add_all([self.user_order, self.other_order])
        self.db.flush()
        self.db.add_all([
            OrderItem(
                order_id=self.user_order.id,
                tile_id=self.white_tile.id,
                quantity=1,
                unit_price=250,
            ),
            OrderItem(
                order_id=self.other_order.id,
                tile_id=self.black_tile.id,
                quantity=2,
                unit_price=250,
            ),
            OrderTracking(
                order_id=self.user_order.id,
                tracking_number="TRACK-USER",
                carrier="Test Carrier",
            ),
            ProductionEntry(
                tile_id=self.white_tile.id,
                tile_sku=self.white_tile.sku,
                tile_name=self.white_tile.name,
                quantity=12,
                factory_name="Factory North",
                batch_number="B-001",
                produced_at=date.today(),
                notes="First production batch",
                created_by=self.admin.id,
            ),
            InventoryMovement(
                tile_id=self.white_tile.id,
                tile_sku=self.white_tile.sku,
                tile_name=self.white_tile.name,
                movement_type="production_receipt",
                quantity=12,
                direction=1,
                unit="pieces",
                balance_after=15,
                reference_type="production_entry",
                reference_id=1,
                reason="Test production receipt",
                occurred_at=datetime.now(timezone.utc),
                created_by=self.admin.id,
            ),
            SearchLog(
                account_id=self.user.id,
                matched_tile_id=self.white_tile.id,
                confidence=0.93,
                response_time_ms=42,
                status="matched",
            ),
            SearchLog(
                account_id=self.other_user.id,
                matched_tile_id=self.black_tile.id,
                confidence=0.61,
                response_time_ms=55,
                status="low_confidence",
            ),
        ])
        self.user_cart = Cart(admin_id=self.user.id)
        self.other_cart = Cart(admin_id=self.other_user.id)
        self.db.add_all([self.user_cart, self.other_cart])
        self.db.flush()
        self.db.add_all([
            CartItem(cart_id=self.user_cart.id, tile_id=self.white_tile.id, quantity=2),
            CartItem(cart_id=self.other_cart.id, tile_id=self.black_tile.id, quantity=7),
        ])
        self.user_quote = self._quotation(self.user, "QT-USER", 250)
        self.other_quote = self._quotation(self.other_user, "QT-OTHER", 500)
        self.db.commit()

        self.app = FastAPI()
        self.app.include_router(chat_router.router)

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

    def _account(self, name: str, role: str) -> Admin:
        account = Admin(
            name=name,
            email=f"{name}@chatbot.example.com",
            password_hash="unused",
            role=role,
            is_active=True,
            auth_version=0,
        )
        self.db.add(account)
        self.db.flush()
        return account

    def _quotation(self, account: Admin, number: str, total: float) -> Quotation:
        quotation = Quotation(
            quotation_number=number,
            created_by=account.id,
            client_name=f"{account.name} client",
            status="issued",
            gst_rate=18,
            subtotal=total,
            gst_amount=total * 0.18,
            grand_total=total * 1.18,
        )
        self.db.add(quotation)
        self.db.flush()
        self.db.add(QuotationItem(
            quotation_id=quotation.id,
            tile_id=self.white_tile.id,
            tile_name=self.white_tile.name,
            tile_sku=self.white_tile.sku,
            material="Marble",
            quantity=1,
            area_sqm=1,
            rate_per_sqm=total,
            line_total=total,
        ))
        return quotation

    @staticmethod
    def headers(account: Admin) -> dict[str, str]:
        token = create_access_token({
            "sub": account.email,
            "role": account.role,
            "ver": account.auth_version,
        })
        return {"Authorization": f"Bearer {token}"}

    def test_user_product_search_uses_catalog_filters_and_stores_history(self):
        with patch.object(
            chat_router,
            "generate_chat_reply",
            return_value="Carrara White is listed at ₹250 per sqm with 3 pieces in stock.",
        ) as generate:
            response = self.client.post(
                "/api/chat/messages",
                headers=self.headers(self.user),
                json={"message": "Show white polished marble under 300"},
            )

        self.assertEqual(response.status_code, 200, response.text)
        context = generate.call_args.args[2]
        self.assertEqual(context["catalog_match_count"], 1)
        self.assertEqual(
            context["catalog_matches"][0]["sku"],
            "MARBLE-WHITE-1",
        )
        self.assertEqual(context["catalog_matches"][0]["price_per_sqm_inr"], 250)
        self.assertEqual(context["catalog_matches"][0]["stock_quantity"], 3)
        self.assertEqual(self.db.query(ChatMessage).count(), 2)

        conversation_id = response.json()["conversation_id"]
        history = self.client.get(
            "/api/chat/conversation",
            headers=self.headers(self.user),
        )
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.json()["conversation_id"], conversation_id)
        self.assertEqual(len(history.json()["messages"]), 2)

    def test_user_order_and_quotation_context_is_account_scoped(self):
        with patch.object(
            chat_router,
            "generate_chat_reply",
            return_value="Your order and quotation are shown from your account records.",
        ) as generate:
            response = self.client.post(
                "/api/chat/messages",
                headers=self.headers(self.user),
                json={"message": "Show my orders, tracking and quotations"},
            )
            follow_up = self.client.post(
                "/api/chat/messages",
                headers=self.headers(self.user),
                json={
                    "message": "When will it arrive?",
                    "conversation_id": response.json()["conversation_id"],
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(follow_up.status_code, 200, follow_up.text)
        context = generate.call_args_list[0].args[2]
        self.assertEqual([order["id"] for order in context["orders"]], [self.user_order.id])
        self.assertNotIn("quotations", context)
        self.assertNotIn("buyer", context["orders"][0])
        follow_up_context = generate.call_args_list[1].args[2]
        self.assertEqual(
            [order["id"] for order in follow_up_context["orders"]],
            [self.user_order.id],
        )
        self.assertNotIn("quotations", follow_up_context)

        other_history = self.client.get(
            "/api/chat/conversation",
            headers=self.headers(self.other_user),
        )
        self.assertEqual(other_history.json(), {"conversation_id": None, "messages": []})

    def test_admin_can_query_inventory_orders_quotations_and_analytics(self):
        with patch.object(
            chat_router,
            "generate_chat_reply",
            return_value="Database-backed admin details are ready.",
        ) as generate:
            response = self.client.post(
                "/api/chat/messages",
                headers=self.headers(self.admin),
                json={
                    "message": (
                        "Show low stock inventory, all orders, quotations, "
                        "sales revenue and dashboard analytics"
                    )
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        context = generate.call_args.args[2]
        self.assertEqual(context["catalog_matches"][0]["sku"], "MARBLE-WHITE-1")
        self.assertEqual(context["inventory_summary"]["low_stock_items"], 2)
        self.assertEqual(len(context["orders"]), 2)
        self.assertEqual(
            {quote["quotation_number"] for quote in context["quotations"]},
            {"QT-USER", "QT-OTHER"},
        )
        self.assertEqual(
            context["business_summary"]["completed_sales_revenue_inr"],
            500,
        )
        self.assertEqual(context["dashboard_metrics"]["units_sold"], 2)
        self.assertEqual(context["dashboard_analytics"]["orders"]["units_sold"], 2)
        self.assertEqual(
            context["factory_analytics"]["production_vs_sales"]["produced_quantity"],
            12,
        )

    def test_super_admin_can_access_admin_context(self):
        with patch.object(
            chat_router,
            "generate_chat_reply",
            return_value="Super administrator inventory summary.",
        ) as generate:
            response = self.client.post(
                "/api/chat/messages",
                headers=self.headers(self.super_admin),
                json={"message": "Search inventory and low stock items"},
            )

        self.assertEqual(response.status_code, 200, response.text)
        context = generate.call_args.args[2]
        self.assertEqual(context["inventory_summary"]["low_stock_items"], 2)
        self.assertEqual(context["catalog_match_count"], 2)

    def test_admin_can_query_factory_production_and_inventory_movements(self):
        with patch.object(
            chat_router,
            "generate_chat_reply",
            return_value="Factory and stock history from the database.",
        ) as generate:
            response = self.client.post(
                "/api/chat/messages",
                headers=self.headers(self.admin),
                json={
                    "message": (
                        "Show factory production batch B-001 and inventory movement history"
                    )
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        context = generate.call_args.args[2]
        production = context["factory_production"]
        self.assertEqual(production["all_time_produced_quantity"], 12)
        self.assertEqual(production["matching_entries"][0]["batch_number"], "B-001")
        self.assertEqual(context["inventory_movements"]["count"], 1)

    def test_admin_product_context_includes_warehouse_location(self):
        with patch.object(
            chat_router,
            "generate_chat_reply",
            return_value="The catalog location is shown.",
        ) as generate:
            response = self.client.post(
                "/api/chat/messages",
                headers=self.headers(self.admin),
                json={"message": "Where is Carrara White stored?"},
            )

        self.assertEqual(response.status_code, 200, response.text)
        product = generate.call_args.args[2]["catalog_matches"][0]
        self.assertEqual(product["sku"], "MARBLE-WHITE-1")
        self.assertEqual(
            product["warehouse_location"],
            {
                "aisle": "A",
                "rack": "R1",
                "bin": "B2",
                "notes": "North warehouse",
            },
        )

    def test_user_context_includes_only_own_cart_and_visual_searches(self):
        with patch.object(
            chat_router,
            "generate_chat_reply",
            return_value="Your cart and visual-search history are shown.",
        ) as generate:
            response = self.client.post(
                "/api/chat/messages",
                headers=self.headers(self.user),
                json={"message": "Show my cart and visual search history"},
            )

        self.assertEqual(response.status_code, 200, response.text)
        context = generate.call_args.args[2]
        self.assertEqual(context["cart"]["item_count"], 2)
        self.assertEqual(context["cart"]["items"][0]["sku"], "MARBLE-WHITE-1")
        self.assertEqual(context["visual_searches"]["count"], 1)
        self.assertEqual(
            context["visual_searches"]["recent"][0]["matched_tile"]["sku"],
            "MARBLE-WHITE-1",
        )
        self.assertNotIn("query_image_url", context["visual_searches"]["recent"][0])

    def test_application_overview_and_super_admin_user_data_are_permission_scoped(self):
        with patch.object(
            chat_router,
            "generate_chat_reply",
            return_value="Read-only application data summary.",
        ) as generate:
            overview = self.client.post(
                "/api/chat/messages",
                headers=self.headers(self.admin),
                json={"message": "Give me an overview of all data in the entire application"},
            )
            users = self.client.post(
                "/api/chat/messages",
                headers=self.headers(self.super_admin),
                json={"message": "Show user accounts"},
            )

        self.assertEqual(overview.status_code, 200, overview.text)
        self.assertIn("factory production and factory analytics", generate.call_args_list[0].args[2]["application_overview"]["available_areas"])
        self.assertEqual(
            generate.call_args_list[0].args[2]["dashboard_analytics"]["orders"]["units_sold"],
            2,
        )
        self.assertEqual(users.status_code, 200, users.text)
        user_context = generate.call_args_list[1].args[2]["user_management"]
        self.assertEqual(user_context["account_count"], 4)
        self.assertTrue(all(
            "password_hash" not in row
            for row in user_context["recent_accounts"]
        ))

    def test_exact_units_sold_answer_uses_dashboard_sum_without_gemini(self):
        with patch.object(
            chat_router,
            "generate_chat_reply",
            side_effect=AssertionError("Exact dashboard totals must bypass Gemini."),
        ):
            response = self.client.post(
                "/api/chat/messages",
                headers=self.headers(self.admin),
                json={"message": "How many units are sold?"},
            )

        self.assertEqual(response.status_code, 200, response.text)
        reply = response.json()["assistant_message"]["content"]
        self.assertIn("2 units sold", reply)
        self.assertIn("paid, completed, and delivered orders", reply)
        self.assertIn("through", reply)

    def test_user_units_sold_question_does_not_expose_admin_analytics(self):
        with patch.object(
            chat_router,
            "generate_chat_reply",
            side_effect=AssertionError("Unavailable sales totals must not be guessed."),
        ):
            response = self.client.post(
                "/api/chat/messages",
                headers=self.headers(self.user),
                json={"message": "How many units are sold?"},
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn(
            "don't have access to an organization-wide sold-units total",
            response.json()["assistant_message"]["content"],
        )

    def test_chat_requires_auth_and_rejects_another_accounts_conversation(self):
        with patch.object(chat_router, "generate_chat_reply", return_value="Saved."):
            unauthenticated = self.client.get("/api/chat/conversation")
            first = self.client.post(
                "/api/chat/messages",
                headers=self.headers(self.user),
                json={"message": "Hello"},
            )
        self.assertIn(unauthenticated.status_code, (401, 403))
        self.assertEqual(first.status_code, 200, first.text)

        attempted_read = self.client.get(
            "/api/chat/conversation",
            headers=self.headers(self.other_user),
        )
        self.assertIsNone(attempted_read.json()["conversation_id"])
        attempted_write = self.client.post(
            "/api/chat/messages",
            headers=self.headers(self.other_user),
            json={
                "message": "Continue that conversation",
                "conversation_id": first.json()["conversation_id"],
            },
        )
        self.assertEqual(attempted_write.status_code, 404)

    def test_chat_does_not_change_stock_orders_or_quotations(self):
        initial_stock = self.db.query(Inventory).filter_by(
            tile_id=self.white_tile.id
        ).one().quantity
        initial_orders = self.db.query(Order).count()
        initial_quotes = self.db.query(Quotation).count()

        with patch.object(
            chat_router, "generate_chat_reply", return_value="I cannot make that change."
        ):
            response = self.client.post(
                "/api/chat/messages",
                headers=self.headers(self.user),
                json={"message": "Place an order and change stock to 99"},
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.db.expire_all()
        self.assertEqual(
            self.db.query(Inventory).filter_by(tile_id=self.white_tile.id).one().quantity,
            initial_stock,
        )
        self.assertEqual(self.db.query(Order).count(), initial_orders)
        self.assertEqual(self.db.query(Quotation).count(), initial_quotes)

    def test_gemini_request_keeps_key_in_backend_header_and_sends_context(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            @staticmethod
            def read():
                return json.dumps({
                    "candidates": [{
                        "content": {"parts": [{"text": "Grounded reply"}]},
                    }],
                }).encode("utf-8")

        with patch.dict(
            os.environ,
            {"GEMINI_API_KEY": "test-key"},
            clear=True,
        ), patch("app.services.chatbot.urlopen", return_value=FakeResponse()) as urlopen:
            reply = generate_chat_reply(
                self.user,
                [{"role": "user", "content": "Check a product"}],
                {"catalog_matches": [{"sku": "MARBLE-WHITE-1"}]},
            )

        request = urlopen.call_args.args[0]
        self.assertEqual(reply, "Grounded reply")
        self.assertEqual(request.get_header("X-goog-api-key"), "test-key")
        self.assertNotIn("test-key", request.full_url)
        self.assertIn(
            "/models/gemini-3.5-flash-lite:generateContent",
            request.full_url,
        )
        request_body = json.loads(request.data)
        instruction = request_body["systemInstruction"]["parts"][0]["text"]
        self.assertIn("MARBLE-WHITE-1", instruction)


if __name__ == "__main__":
    unittest.main()
