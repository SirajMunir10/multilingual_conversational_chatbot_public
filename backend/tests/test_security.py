"""Security & privacy (PRD FR-21–FR-23b, §6.1, §7): no header identity, protected back office, no payment data, no leaks."""
import asyncio
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import issue_token, rate_limiter, redact_payment_data, verify_token
from app.main import app
from app.orchestrator.session_store import SessionStore, is_valid_session_id
from app.services.account_service import AccountService


class TestSecurity(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_health_exposes_no_internal_details(self):
        body = self.client.get("/api/health").json()
        self.assertEqual(body, {"status": "ok"})

    def test_admin_endpoints_require_key(self):
        for path in ("/api/admin/sessions", "/api/admin/handoffs", "/api/admin/usage", "/api/admin/leads", "/api/admin/audit"):
            self.assertEqual(self.client.get(path).status_code, 401, path)
            self.assertEqual(self.client.get(path, headers={"X-Admin-Key": "wrong"}).status_code, 401, path)
        self.assertEqual(self.client.get("/api/admin/sessions", headers={"X-Admin-Key": settings.ADMIN_API_KEY}).status_code, 200)

    def test_old_leaky_endpoints_are_gone(self):
        for path in ("/api/admin/usage/latest", "/api/gateways/handoff/queue", "/api/gateways/account/applications"):
            self.assertIn(self.client.get(path).status_code, (401, 404, 405), path)
        self.assertEqual(self.client.post("/api/gateways/vault/leads", json={}).status_code, 404)

    def test_header_identity_is_ignored(self):
        self.assertIsNone(self.client.get("/api/health", headers={"X-User-ID": "user_siraj_vip"}).json().get("user"))
        self.assertEqual(AccountService.get_my_application_status(None)["status"], "auth_required")

    def test_signed_tokens(self):
        token = issue_token("usr_1")
        self.assertEqual(verify_token(token), "usr_1")
        self.assertIsNone(verify_token(token[:-2] + "xx"))
        self.assertIsNone(verify_token("user_siraj_vip"))

    def test_payment_details_redacted(self):
        text = redact_payment_data("my card is 4111 1111 1111 1111 cvv 123 and IBAN AE070331234567890123456")
        self.assertNotIn("4111", text)
        self.assertNotIn("AE07", text)
        self.assertNotIn("123 and", text)
        self.assertIn("2,500,000", redact_payment_data("budget 2,500,000"))      # prices are untouched
        self.assertIn("+971 50 123 4567", redact_payment_data("+971 50 123 4567"))   # phone numbers are untouched

    def test_session_ids_are_server_issued(self):
        self.assertFalse(is_valid_session_id("sess_abc"))
        s = SessionStore.get_or_create("sess_attacker_chosen")
        self.assertNotEqual(s.session_id, "sess_attacker_chosen")
        self.assertTrue(is_valid_session_id(s.session_id))

    def test_cors_is_not_wildcard(self):
        res = self.client.options("/api/chat/stream", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
        self.assertNotEqual(res.headers.get("access-control-allow-origin"), "*")
        self.assertNotEqual(res.headers.get("access-control-allow-origin"), "https://evil.example")

    def test_tts_text_length_limited(self):
        self.assertEqual(self.client.post("/api/voice/speak", json={"text": "x" * 5000}).status_code, 422)

    def test_chat_message_length_limited(self):
        self.assertEqual(self.client.post("/api/chat/message", json={"message": "x" * 5000}).status_code, 422)

    def test_rate_limit(self):
        with mock.patch.object(settings, "RATE_LIMIT_ENABLED", True), mock.patch.object(settings, "RATE_LIMIT_PER_MINUTE", 2):
            rate_limiter._hits.clear()
            codes = [self.client.get("/api/mortgage/products").status_code for _ in range(3)]
            rate_limiter._hits.clear()
        self.assertEqual(codes[-1], 429)

    def test_unhandled_errors_do_not_leak(self):
        with mock.patch("app.services.mortgage_service.MortgageCalculationService.get_products", side_effect=RuntimeError("secret detail")):
            client = TestClient(app, raise_server_exceptions=False)
            res = client.get("/api/mortgage/products")
        self.assertEqual(res.status_code, 500)
        self.assertNotIn("secret", res.text)


if __name__ == "__main__":
    unittest.main()
