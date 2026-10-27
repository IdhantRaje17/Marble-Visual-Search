import os
import sys
import unittest

from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.database import Base, get_db
from app.middleware.auth import create_access_token, get_current_admin
from app.models.admin import Admin
from app.routers import admin_users, auth


class TestRoleBasedAccessControl(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine, tables=[Admin.__table__])
        self.db = Session(self.engine)

        self.app = FastAPI()
        self.app.include_router(auth.router)
        self.app.include_router(admin_users.router)

        @self.app.get("/operational")
        def operational(_: Admin = Depends(get_current_admin)):
            return {"ok": True}

        def override_get_db():
            yield self.db

        self.app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.db.close()
        self.engine.dispose()

    def create_account(
        self,
        email: str,
        role: str = "user",
        is_active: bool = True,
        auth_version: int = 0,
    ) -> Admin:
        account = Admin(
            name=email.split("@")[0],
            email=email,
            password_hash="unused",
            role=role,
            is_active=is_active,
            auth_version=auth_version,
        )
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        return account

    @staticmethod
    def token(account: Admin, claimed_role: str | None = None) -> str:
        return create_access_token({
            "sub": account.email,
            "role": claimed_role or account.role,
            "ver": account.auth_version,
        })

    def headers(self, account: Admin, claimed_role: str | None = None):
        return {"Authorization": f"Bearer {self.token(account, claimed_role)}"}

    def test_public_registration_ignores_client_supplied_role(self):
        response = self.client.post(
            "/api/auth/register",
            json={
                "name": "New User",
                "email": "new-user@example.com",
                "password": "test-password",
                "role": "super_admin",
                "is_active": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["role"], "user")
        self.assertIn("account_id", response.json())
        account = self.db.query(Admin).filter_by(email="new-user@example.com").one()
        self.assertEqual(response.json()["account_id"], account.id)
        self.assertEqual(account.role, "user")
        self.assertTrue(account.password_hash.startswith(("$2a$", "$2b$", "$2y$")))

    def test_admin_and_super_admin_have_operational_access(self):
        for role in ("admin", "super_admin"):
            with self.subTest(role=role):
                account = self.create_account(f"{role}@example.com", role=role)
                response = self.client.get(
                    "/operational", headers=self.headers(account)
                )
                self.assertEqual(response.status_code, 200)

    def test_three_concurrent_role_tokens_keep_independent_identities(self):
        accounts = [
            self.create_account(f"{role}@concurrent.example.com", role=role)
            for role in ("user", "admin", "super_admin")
        ]
        sessions = [self.headers(account) for account in accounts]

        for account, session in zip(accounts, sessions):
            with self.subTest(role=account.role):
                response = self.client.get("/api/auth/me", headers=session)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["id"], account.id)
                self.assertEqual(response.json()["role"], account.role)

        self.assertEqual(
            self.client.get("/operational", headers=sessions[0]).status_code,
            403,
        )
        self.assertEqual(
            self.client.get("/operational", headers=sessions[1]).status_code,
            200,
        )
        self.assertEqual(
            self.client.get("/api/admin/users", headers=sessions[1]).status_code,
            403,
        )
        self.assertEqual(
            self.client.get("/api/admin/users", headers=sessions[2]).status_code,
            200,
        )
        self.assertEqual(
            self.client.post("/api/auth/logout", headers=sessions[0]).status_code,
            200,
        )
        self.assertEqual(
            self.client.get("/api/auth/me", headers=sessions[1]).status_code,
            200,
        )
        self.assertEqual(
            self.client.get("/api/auth/me", headers=sessions[2]).status_code,
            200,
        )

    def test_user_cannot_use_admin_routes_even_with_forged_role_claim(self):
        account = self.create_account("user@example.com")
        response = self.client.get(
            "/operational",
            headers=self.headers(account, claimed_role="super_admin"),
        )
        self.assertEqual(response.status_code, 403)
        management_response = self.client.get(
            "/api/admin/users",
            headers=self.headers(account, claimed_role="super_admin"),
        )
        self.assertEqual(management_response.status_code, 403)

    def test_only_super_admin_can_manage_users(self):
        admin_account = self.create_account("admin@example.com", role="admin")
        response = self.client.get(
            "/api/admin/users", headers=self.headers(admin_account)
        )
        self.assertEqual(response.status_code, 403)

    def test_role_change_invalidates_existing_token_and_blocks_self_demotion(self):
        super_admin = self.create_account(
            "super@example.com", role="super_admin"
        )
        target = self.create_account("target@example.com", role="user")
        old_target_token = {
            "Authorization": (
                "Bearer "
                + create_access_token({
                    "sub": target.email,
                    "role": "super_admin",
                })
            )
        }
        self.assertEqual(
            self.client.get("/api/auth/me", headers=old_target_token).json()["role"],
            "user",
        )

        change_response = self.client.patch(
            f"/api/admin/users/{target.id}/role",
            json={"role": "admin"},
            headers=self.headers(super_admin),
        )
        self.assertEqual(change_response.status_code, 200)
        self.assertEqual(change_response.json()["role"], "admin")
        self.assertEqual(
            self.client.get("/api/auth/me", headers=old_target_token).status_code,
            401,
        )

        self_demotion = self.client.patch(
            f"/api/admin/users/{super_admin.id}/role",
            json={"role": "admin"},
            headers=self.headers(super_admin),
        )
        self.assertEqual(self_demotion.status_code, 400)
        self.assertEqual(
            self.db.query(Admin).filter_by(id=super_admin.id).one().role,
            "super_admin",
        )

    def test_super_admin_cannot_demote_or_suspend_self(self):
        super_admin = self.create_account(
            "only-super@example.com", role="super_admin"
        )
        demotion = self.client.patch(
            f"/api/admin/users/{super_admin.id}/role",
            json={"role": "admin"},
            headers=self.headers(super_admin),
        )
        self.assertEqual(demotion.status_code, 400)
        suspension = self.client.patch(
            f"/api/admin/users/{super_admin.id}/status",
            json={"is_active": False},
            headers=self.headers(super_admin),
        )
        self.assertEqual(suspension.status_code, 400)

    def test_active_super_admin_cannot_be_the_last_one_removed(self):
        super_admin = self.create_account(
            "sole-super@example.com", role="super_admin"
        )
        with self.assertRaises(HTTPException) as raised:
            admin_users._ensure_active_super_admin_remains(self.db, super_admin)
        self.assertEqual(raised.exception.status_code, 409)

        other_super_admin = self.create_account(
            "another-super@example.com", role="super_admin"
        )
        response = self.client.patch(
            f"/api/admin/users/{other_super_admin.id}/role",
            json={"role": "admin"},
            headers=self.headers(super_admin),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.db.query(Admin).filter_by(role="super_admin", is_active=True).count(),
            1,
        )

    def test_suspend_and_reactivate_revokes_old_tokens(self):
        super_admin = self.create_account(
            "manager@example.com", role="super_admin"
        )
        target = self.create_account("customer@example.com")
        old_token = self.headers(target)

        suspended = self.client.patch(
            f"/api/admin/users/{target.id}/status",
            json={"is_active": False},
            headers=self.headers(super_admin),
        )
        self.assertEqual(suspended.status_code, 200)
        self.assertFalse(suspended.json()["is_active"])

        reactivated = self.client.patch(
            f"/api/admin/users/{target.id}/status",
            json={"is_active": True},
            headers=self.headers(super_admin),
        )
        self.assertEqual(reactivated.status_code, 200)
        self.assertTrue(reactivated.json()["is_active"])
        self.assertEqual(
            self.client.get("/api/auth/me", headers=old_token).status_code,
            401,
        )


if __name__ == "__main__":
    unittest.main()
