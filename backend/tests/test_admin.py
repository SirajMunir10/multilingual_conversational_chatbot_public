"""Admin module foundation (PRD FR-30, §7): sign-in, sessions, roles enforced on every endpoint, user rules,
activity trail and conversation persistence for review and analytics (FR-26, FR-31)."""
import asyncio
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from app.admin import users as users_module
from app.admin.activity import ActivityLog
from app.admin.auth import COOKIE_NAME, CSRF_HEADER, CSRF_VALUE, bootstrap_first_admin
from app.admin.permissions import ROLE_PERMISSIONS
from app.admin.users import AdminUserStore, hash_password, verify_password
from app.core.config import settings
from app.core.security import ADMIN_AUDIENCE, Role, issue_token, rate_limiter, verify_token
from app.db.conversation_store import ConversationStore
from app.llm.client import LLMService
from app.main import app
from app.orchestrator.orchestrator import ConversationOrchestrator as O
from app.orchestrator.session_store import SessionStore
from tests.fakes import FakeClient, text_turn

PASSWORD = "correct horse battery"
HEADERS = {CSRF_HEADER: CSRF_VALUE}

# Every admin endpoint and the permission it needs (None: any signed-in admin).
ENDPOINTS = [
    ("GET", "/api/admin/auth/me", None),
    ("GET", "/api/admin/roles", None),
    ("GET", "/api/admin/status", None),
    ("GET", "/api/admin/users", "users.manage"),
    ("GET", "/api/admin/activity", "activity.view"),
    ("GET", "/api/admin/audit", "activity.view"),
    ("GET", "/api/admin/sessions", "conversations.view"),
    ("GET", "/api/admin/usage", "analytics.view"),
    ("GET", "/api/admin/handoffs", "leads.view"),
    ("GET", "/api/admin/leads", "leads.view"),
    ("POST", "/api/admin/reload-config", "config.reload"),
    ("GET", "/api/admin/analytics", "analytics.view"),
    ("GET", "/api/admin/budget", "analytics.view"),
    ("PUT", "/api/admin/budget", "budget.edit"),
    ("GET", "/api/admin/conversations", "conversations.view"),
    ("GET", "/api/admin/review-queue", "conversations.view"),
    ("GET", "/api/admin/kb/articles", "kb.edit"),
    ("GET", "/api/admin/kb/sources", "kb.edit"),
    ("GET", "/api/admin/kb/drafts", "kb.edit"),
]


def run(coro):
    return asyncio.run(coro)


class AdminTestCase(unittest.TestCase):

    def setUp(self):
        patches = [mock.patch.object(settings, "JWT_SECRET", "test-secret-for-admin-tests"),
                   mock.patch.object(settings, "ADMIN_API_KEY", "test-admin-key-0123456789abcdef-0123456789"),
                   mock.patch.object(users_module, "PBKDF2_ITERATIONS", 1000)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        AdminUserStore.reset_memory()
        ActivityLog.reset_memory()
        rate_limiter._hits.clear()
        self.addCleanup(rate_limiter._hits.clear)

    def make_user(self, role, email=None):
        email = email or f"{role}@xoto.ae"
        return run(AdminUserStore.create(email, role.replace("_", " ").title(), role, PASSWORD))

    def sign_in(self, email, password=PASSWORD):
        client = TestClient(app)
        res = client.post("/api/admin/auth/login", json={"email": email, "password": password})
        return client, res


class TestPasswordsAndTokens(AdminTestCase):

    def test_password_hash_round_trip(self):
        stored = hash_password(PASSWORD)
        self.assertNotIn(PASSWORD, stored)
        self.assertTrue(verify_password(PASSWORD, stored))
        self.assertFalse(verify_password("wrong password!", stored))
        self.assertFalse(verify_password(PASSWORD, "garbage"))

    def test_admin_and_visitor_tokens_are_not_interchangeable(self):
        admin_token = issue_token("1", audience=ADMIN_AUDIENCE, claims={"tv": 0})
        self.assertIsNone(verify_token(admin_token))
        user = self.make_user(Role.ADMIN)
        visitor_token = issue_token(str(user["id"]))
        client = TestClient(app)
        client.cookies.set(COOKIE_NAME, visitor_token)
        self.assertEqual(client.get("/api/admin/auth/me").status_code, 401)


class TestSignIn(AdminTestCase):

    def test_sign_in_sets_a_protected_cookie(self):
        self.make_user(Role.ADMIN)
        client, res = self.sign_in("ADMIN@xoto.ae ")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["user"]["role"], Role.ADMIN)
        cookie = res.headers["set-cookie"].lower()
        for flag in ("httponly", "samesite=strict", "path=/api/admin"):
            self.assertIn(flag, cookie)
        self.assertNotIn("password", res.text)
        self.assertEqual(client.get("/api/admin/auth/me").json()["user"]["email"], "admin@xoto.ae")

    def test_wrong_password_unknown_email_and_inactive_look_the_same(self):
        user = self.make_user(Role.BOT_TRAINER)
        _, wrong = self.sign_in(user["email"], "not the password")
        _, unknown = self.sign_in("nobody@xoto.ae")
        run(AdminUserStore.update(user["id"], active=False))
        _, inactive = self.sign_in(user["email"])
        for res in (wrong, unknown, inactive):
            self.assertEqual((res.status_code, res.json()["detail"]), (401, "invalid_credentials"))

    def test_repeated_failures_are_rate_limited(self):
        self.make_user(Role.ADMIN)
        with mock.patch.object(settings, "ADMIN_LOGIN_ATTEMPTS_PER_15_MIN", 3):
            codes = [self.sign_in("admin@xoto.ae", "wrong password!!")[1].status_code for _ in range(4)]
        self.assertEqual(codes, [401, 401, 401, 429])

    def test_successful_sign_ins_do_not_count_towards_the_limit(self):
        self.make_user(Role.ADMIN)
        with mock.patch.object(settings, "ADMIN_LOGIN_ATTEMPTS_PER_15_MIN", 3):
            codes = [self.sign_in("admin@xoto.ae")[1].status_code for _ in range(6)]
        self.assertEqual(codes, [200] * 6)

    def test_sign_in_unavailable_without_secret(self):
        with mock.patch.object(settings, "JWT_SECRET", ""):
            self.assertEqual(self.sign_in("admin@xoto.ae")[1].status_code, 503)

    def test_sign_out_revokes_the_session(self):
        self.make_user(Role.ADMIN)
        client, _ = self.sign_in("admin@xoto.ae")
        old_cookie = client.cookies.get(COOKIE_NAME)
        self.assertEqual(client.post("/api/admin/auth/logout", headers=HEADERS).status_code, 200)
        replay = TestClient(app)
        replay.cookies.set(COOKIE_NAME, old_cookie)
        self.assertEqual(replay.get("/api/admin/auth/me").status_code, 401)

    def test_signing_out_ends_only_that_browser_session(self):
        self.make_user(Role.ADMIN)
        laptop, _ = self.sign_in("admin@xoto.ae")
        phone, _ = self.sign_in("admin@xoto.ae")
        laptop.post("/api/admin/auth/logout", headers=HEADERS)
        self.assertEqual(laptop.get("/api/admin/auth/me").status_code, 401)
        self.assertEqual(phone.get("/api/admin/auth/me").status_code, 200)

    def test_cookie_without_a_live_session_is_rejected(self):
        user = self.make_user(Role.ADMIN)
        forged = issue_token(str(user["id"]), audience=ADMIN_AUDIENCE, claims={"tv": 0, "sid": "made-up"})
        client = TestClient(app)
        client.cookies.set(COOKIE_NAME, forged)
        self.assertEqual(client.get("/api/admin/auth/me").status_code, 401)

    def test_changes_need_the_page_header(self):
        self.make_user(Role.ADMIN)
        client, _ = self.sign_in("admin@xoto.ae")
        self.assertEqual(client.post("/api/admin/reload-config").status_code, 403)
        self.assertEqual(client.post("/api/admin/reload-config", headers=HEADERS).status_code, 200)

    def test_change_own_password(self):
        self.make_user(Role.CONTENT_EDITOR)
        client, _ = self.sign_in("content_editor@xoto.ae")
        res = client.post("/api/admin/auth/password", headers=HEADERS,
                          json={"current_password": "wrong one here", "new_password": "a brand new password"})
        self.assertEqual(res.json()["detail"], "wrong_current_password")
        res = client.post("/api/admin/auth/password", headers=HEADERS,
                          json={"current_password": PASSWORD, "new_password": "short"})
        self.assertEqual(res.json()["detail"], "password_too_short")
        res = client.post("/api/admin/auth/password", headers=HEADERS,
                          json={"current_password": PASSWORD, "new_password": "a brand new password"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(client.get("/api/admin/auth/me").status_code, 200)  # this browser stays signed in
        self.assertEqual(self.sign_in("content_editor@xoto.ae")[1].status_code, 401)
        self.assertEqual(self.sign_in("content_editor@xoto.ae", "a brand new password")[1].status_code, 200)


class TestRolePermissions(AdminTestCase):

    def call(self, client, method, path, **kwargs):
        if method == "PUT" and path.endswith("/budget"):
            kwargs.setdefault("json", {"monthly_usd": 100, "alert_pct": 80})
        return client.request(method, path, headers=HEADERS, **kwargs)

    def test_every_endpoint_enforces_its_permission_for_every_role(self):
        for role, granted in ROLE_PERMISSIONS.items():
            self.make_user(role)
            client, res = self.sign_in(f"{role}@xoto.ae")
            self.assertEqual(res.status_code, 200, role)
            for method, path, permission in ENDPOINTS:
                code = self.call(client, method, path).status_code
                allowed = permission is None or permission in granted
                self.assertEqual(code == 403, not allowed, f"{role} {method} {path} -> {code}")
                self.assertIn(code, (200, 201) if allowed else (403,), f"{role} {method} {path}")

    def test_no_credentials_and_wrong_key_are_rejected(self):
        client = TestClient(app)
        for method, path, _ in ENDPOINTS:
            self.assertEqual(client.request(method, path).status_code, 401, path)
            self.assertEqual(client.request(method, path, headers={"X-Admin-Key": "wrong"}).status_code, 401, path)

    def test_admin_key_still_works_for_scripts(self):
        client = TestClient(app)
        for method, path, _ in ENDPOINTS:
            body = {"monthly_usd": 100, "alert_pct": 80} if method == "PUT" else None
            self.assertEqual(client.request(method, path, json=body, headers={"X-Admin-Key": "test-admin-key-0123456789abcdef-0123456789"}).status_code, 200, path)

    def test_analyst_is_read_only(self):
        self.make_user(Role.READ_ONLY_ANALYST)
        client, _ = self.sign_in("read_only_analyst@xoto.ae")
        res = self.call(client, "POST", "/api/admin/users",
                        json={"email": "x@xoto.ae", "name": "X", "role": Role.ADMIN, "password": PASSWORD})
        self.assertEqual(res.status_code, 403)
        self.assertEqual(run(AdminUserStore.count()), 1)


class TestUserManagement(AdminTestCase):

    def setUp(self):
        super().setUp()
        self.admin = self.make_user(Role.ADMIN)
        self.client, _ = self.sign_in("admin@xoto.ae")

    def post(self, path, body):
        return self.client.post(path, json=body, headers=HEADERS)

    def patch(self, path, body):
        return self.client.patch(path, json=body, headers=HEADERS)

    def test_create_user_validates_input(self):
        ok = self.post("/api/admin/users", {"email": "Sara@xoto.ae", "name": "Sara", "role": Role.CONTENT_EDITOR, "password": PASSWORD})
        self.assertEqual(ok.status_code, 201)
        self.assertEqual(ok.json()["email"], "sara@xoto.ae")
        self.assertNotIn("password_hash", ok.json())
        cases = [({"email": "sara@xoto.ae", "role": Role.CONTENT_EDITOR, "password": PASSWORD}, "email_taken"),
                 ({"email": "not-an-email", "role": Role.CONTENT_EDITOR, "password": PASSWORD}, "invalid_email"),
                 ({"email": "a@xoto.ae", "role": "superuser", "password": PASSWORD}, "invalid_role"),
                 ({"email": "b@xoto.ae", "role": Role.CONTENT_EDITOR, "password": "short"}, "password_too_short")]
        for body, code in cases:
            res = self.post("/api/admin/users", {"name": "Test", **body})
            self.assertEqual((res.status_code, res.json()["detail"]), (400, code))

    def test_role_change_and_deactivation_sign_the_person_out(self):
        editor = self.make_user(Role.CONTENT_EDITOR)
        editor_client, _ = self.sign_in(editor["email"])
        self.assertEqual(editor_client.get("/api/admin/users").status_code, 403)
        self.assertEqual(self.patch(f"/api/admin/users/{editor['id']}", {"role": Role.BOT_TRAINER}).json()["role"], Role.BOT_TRAINER)
        self.assertEqual(editor_client.get("/api/admin/auth/me").status_code, 401)
        editor_client, _ = self.sign_in(editor["email"])
        self.assertEqual(editor_client.get("/api/admin/auth/me").json()["user"]["role"], Role.BOT_TRAINER)
        self.patch(f"/api/admin/users/{editor['id']}", {"active": False})
        self.assertEqual(editor_client.get("/api/admin/auth/me").status_code, 401)
        self.assertEqual(self.sign_in(editor["email"])[1].status_code, 401)

    def test_admins_cannot_lock_themselves_or_everyone_out(self):
        res = self.patch(f"/api/admin/users/{self.admin['id']}", {"active": False})
        self.assertEqual(res.json()["detail"], "cannot_change_own_access")
        res = self.patch(f"/api/admin/users/{self.admin['id']}", {"name": "Head of Product"})
        self.assertEqual(res.json()["name"], "Head of Product")
        with self.assertRaises(users_module.AdminUserError) as ctx:
            run(AdminUserStore.update(self.admin["id"], role=Role.READ_ONLY_ANALYST))
        self.assertEqual(str(ctx.exception), "last_admin")

    def test_password_reset_by_admin(self):
        editor = self.make_user(Role.CONTENT_EDITOR)
        res = self.post(f"/api/admin/users/{editor['id']}/password", {"password": "reset by the admin"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.sign_in(editor["email"], "reset by the admin")[1].status_code, 200)
        self.assertEqual(self.post("/api/admin/users/999/password", {"password": "reset by the admin"}).status_code, 404)

    def test_changes_are_recorded_in_the_activity_trail(self):
        res = self.post("/api/admin/users", {"email": "omar@xoto.ae", "name": "Omar", "role": Role.READ_ONLY_ANALYST, "password": PASSWORD})
        self.patch(f"/api/admin/users/{res.json()['id']}", {"role": Role.CONTENT_EDITOR})
        entries = self.client.get("/api/admin/activity").json()
        actions = [(e["action"], e["resource"], e["actor_email"]) for e in entries]
        self.assertIn(("user_created", "user:omar@xoto.ae", "admin@xoto.ae"), actions)
        self.assertIn(("signed_in", "user:admin@xoto.ae", "admin@xoto.ae"), actions)
        updated = next(e for e in entries if e["action"] == "user_updated")
        self.assertEqual(updated["details"], {"role": {"from": Role.READ_ONLY_ANALYST, "to": Role.CONTENT_EDITOR}})
        self.assertNotIn(PASSWORD, str(entries))


class TestBootstrap(AdminTestCase):

    def test_first_admin_is_created_once_from_environment(self):
        with mock.patch.object(settings, "ADMIN_BOOTSTRAP_EMAIL", "owner@xoto.ae"), \
                mock.patch.object(settings, "ADMIN_BOOTSTRAP_PASSWORD", PASSWORD):
            self.assertEqual(run(bootstrap_first_admin())["role"], Role.ADMIN)
            self.assertIsNone(run(bootstrap_first_admin()))
        self.assertEqual(run(AdminUserStore.count()), 1)

    def test_no_bootstrap_without_both_settings(self):
        with mock.patch.object(settings, "ADMIN_BOOTSTRAP_EMAIL", "owner@xoto.ae"), \
                mock.patch.object(settings, "ADMIN_BOOTSTRAP_PASSWORD", ""):
            self.assertIsNone(run(bootstrap_first_admin()))


class TestConversationPersistence(unittest.IsolatedAsyncioTestCase):

    def use(self, client):
        patcher = mock.patch.object(LLMService, "client", return_value=client)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def asyncSetUp(self):
        SessionStore.clear_all()
        ConversationStore.reset_memory()

    async def test_turns_are_saved_for_review_and_analytics(self):
        self.use(FakeClient([text_turn("Hello! How can I help?"), text_turn("Sure.")]))
        first = [e async for e in O.stream_turn("hi there", channel="voice")][-1]
        [e async for e in O.stream_turn("card 4111 1111 1111 1111 thanks", session_id=first["session_id"])]
        await ConversationStore.flush()
        conv = await ConversationStore.get(first["session_id"])
        self.assertEqual(conv["user_turns"], 2)
        self.assertEqual(sorted(conv["channels"]), ["text", "voice"])
        self.assertEqual([m["role"] for m in conv["messages"]], ["user", "assistant", "user", "assistant"])
        self.assertEqual(conv["messages"][1]["content"], "Hello! How can I help?")
        self.assertNotIn("4111", conv["messages"][2]["content"])  # payment data never stored (FR-23b)
        self.assertGreater(conv["cost_usd"], 0)

    async def test_failed_turns_are_counted(self):
        self.use(FakeClient([], fail=True))
        final = [e async for e in O.stream_turn("hello")]
        await ConversationStore.flush()
        sid = final[0]["session_id"]
        conv = await ConversationStore.get(sid)
        self.assertEqual((conv["user_turns"], conv["failed_turns"]), (1, 1))
        self.assertEqual([m["role"] for m in conv["messages"]], ["user"])

    async def test_handoff_marks_the_conversation(self):
        await ConversationStore.record_turn("sess_handoff_test_0001", language="en", channel="text", user_text="advisor please",
                                            reply="Sure.", tools=["request_human_handoff"], latency_ms=900, cost_usd=0.001)
        await ConversationStore.record_handoff("sess_handoff_test_0001", "XO-261021-ABC123")
        conv = await ConversationStore.get("sess_handoff_test_0001")
        self.assertEqual((conv["handoff_ticket"], conv["lead_saved"]), ("XO-261021-ABC123", True))


if __name__ == "__main__":
    unittest.main()
