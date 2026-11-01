"""Regression: browser sessions can open the registered admin-only user page.

Run with python -m unittest tests.test_user_management_access. All accounts and
sessions here belong to an isolated in-memory database, never the running app.
"""
import asyncio
import unittest
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.routes.v1.admin_users import router as users_router
from api.routes.v1.auth import router as auth_router
from core.auth import session
from core.config.settings import settings
from core.db.engine import Base, get_db
from core.db.models import UserShadow
from features.workbench import catalog
from features.marketplace.api.agent_marketplace import _require_can_add_agent
from core.infra.exceptions import AccessDeniedError


class UserManagementAccessTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine)
        self.factory = sessionmaker(bind=engine)
        self.patch("core.db.engine.SessionLocal", self.factory)
        self.patch("features.workbench.plugin_catalog.items", return_value=[])
        self.patch("core.auth.session._use_memory_store", return_value=True)
        with self.factory() as db:
            for user_id, meta in [
                ("owner", {"role": "super_admin"}),
                ("member", {}),
                ("content_admin", {"can_content_manage": True, "can_manage_users": True}),
            ]:
                db.add(UserShadow(user_id=user_id, username=user_id, extra_data=meta))
            db.commit()
        app = FastAPI()
        app.include_router(users_router)
        app.include_router(auth_router)

        def database():
            with self.factory() as db:
                yield db

        app.dependency_overrides[get_db] = database
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def patch(self, target, *args, **kwargs):
        context = patch(target, *args, **kwargs)
        value = context.start()
        self.addCleanup(context.stop)
        return value

    def sign_in(self, user_id):
        token = asyncio.run(session.create_session({"user_id": user_id, "username": user_id}))
        self.addCleanup(lambda: asyncio.run(session.revoke_session(token)))
        self.client.cookies.set(settings.session.cookie_name, token)

    def test_owner_cookie_lists_users_and_has_registered_application(self):
        self.sign_in("owner")
        check = self.client.get("/v1/auth/session/check")
        self.assertEqual(check.status_code, 200)
        self.assertTrue(check.json()["data"]["can_manage_users"])
        response = self.client.get("/v1/admin/users")
        self.assertEqual(response.status_code, 200)
        self.assertEqual({u["username"] for u in response.json()["data"]}, {"owner", "member", "content_admin"})
        with self.factory() as db:
            entry = catalog.readable(db, "owner", "builtin:user_management")
            self.assertTrue(entry["availability"]["available"])
            self.assertEqual(entry["declaration"]["target"]["componentId"], "user_management")
            self.assertIn("builtin:user_management", {i["applicationKey"] for i in catalog.directory(db, "owner")["items"]})

    def test_members_and_delegated_content_admins_cannot_manage_users(self):
        for user_id in ["member", "content_admin"]:
            with self.subTest(user_id=user_id):
                self.sign_in(user_id)
                check = self.client.get("/v1/auth/session/check")
                self.assertFalse(check.json()["data"]["can_manage_users"])
                self.assertEqual(self.client.get("/v1/admin/users").status_code, 403)
                with self.factory() as db:
                    self.assertNotIn("builtin:user_management", {i["applicationKey"] for i in catalog.directory(db, user_id)["items"]})
                    with self.assertRaises(HTTPException) as error:
                        catalog.readable(db, user_id, "builtin:user_management")
                    self.assertEqual(error.exception.status_code, 404)

    def test_missing_or_expired_cookie_cannot_list_accounts(self):
        self.assertEqual(self.client.get("/v1/admin/users").status_code, 401)
        self.client.cookies.set(settings.session.cookie_name, "expired-test-session")
        self.assertEqual(self.client.get("/v1/admin/users").status_code, 401)

    def test_agent_install_permission_matches_session_and_admin_role(self):
        for user_id, allowed in [("owner", True), ("member", False), ("content_admin", False)]:
            with self.subTest(user_id=user_id):
                self.sign_in(user_id)
                check = self.client.get("/v1/auth/session/check")
                self.assertEqual(check.json()["data"]["can_add_agent"], allowed)
                with self.factory() as db:
                    if allowed:
                        _require_can_add_agent(user_id, db)
                    else:
                        with self.assertRaises(AccessDeniedError):
                            _require_can_add_agent(user_id, db)

        # An explicit grant allows a member; an old false flag cannot lock out
        # the administrator while other authorization helpers allow access.
        with self.factory() as db:
            for user_id, value in [("member", True), ("owner", False)]:
                row = db.query(UserShadow).filter_by(user_id=user_id).one()
                row.extra_data = {**(row.extra_data or {}), "can_add_agent": value}
            db.commit()
            _require_can_add_agent("member", db)
            _require_can_add_agent("owner", db)

    def test_only_owner_can_explicitly_grant_member_agent_permission(self):
        self.sign_in('member')
        self.assertEqual(self.client.patch('/v1/admin/users/member/agent-permission',json={'can_add_agent':True}).status_code,403)
        self.sign_in('owner')
        result=self.client.patch('/v1/admin/users/member/agent-permission',json={'can_add_agent':True})
        self.assertEqual(result.status_code,200)
        self.assertTrue(result.json()['data']['can_add_agent'])
        self.sign_in('member')
        self.assertTrue(self.client.get('/v1/auth/session/check').json()['data']['can_add_agent'])



if __name__ == "__main__":
    unittest.main()
