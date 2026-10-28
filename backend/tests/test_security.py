"""Security & privacy (PRD FR-21–FR-23b, §6.1, §7): no header identity, protected back office, no payment data, no leaks."""
import asyncio
import unittest
from unittest import mock

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

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

    def _stt(self, origin):
        """Opens the live-transcription socket from a site; returns "accepted" or the close code."""
        async def relay(ws, language, session_id):
            await ws.accept()
            await ws.send_json({"type": "ready"})
            await ws.close()
        with mock.patch("app.voice.stt_service.relay", side_effect=relay):
            try:
                with self.client.websocket_connect("/api/voice/stt?language=en", headers={"origin": origin}) as ws:
                    ws.receive_json()
                return "accepted"
            except WebSocketDisconnect as exc:
                return exc.code

    def test_voice_socket_only_accepts_allowed_sites(self):
        with mock.patch.object(settings, "ALLOWED_ORIGINS", ["https://xoto-blitz.vercel.app"]):
            rate_limiter._hits.clear()
            self.assertEqual(self._stt("https://xoto-blitz.vercel.app"), "accepted")
            self.assertEqual(self._stt("https://evil-example.com"), 1008)

    def test_voice_socket_rate_limit(self):
        with mock.patch.object(settings, "ALLOWED_ORIGINS", ["https://xoto-blitz.vercel.app"]), \
                mock.patch.object(settings, "RATE_LIMIT_ENABLED", True), mock.patch.object(settings, "RATE_LIMIT_PER_MINUTE", 2):
            rate_limiter._hits.clear()
            results = [self._stt("https://xoto-blitz.vercel.app") for _ in range(3)]
            rate_limiter._hits.clear()
        self.assertEqual(results, ["accepted", "accepted", 1013])

    def test_unhandled_errors_do_not_leak(self):
        with mock.patch("app.services.mortgage_service.MortgageCalculationService.get_products", side_effect=RuntimeError("secret detail")):
            client = TestClient(app, raise_server_exceptions=False)
            res = client.get("/api/mortgage/products")
        self.assertEqual(res.status_code, 500)
        self.assertNotIn("secret", res.text)


if __name__ == "__main__":
    unittest.main()


class TestHardening(unittest.TestCase):
    """Fixes from the October 2026 security review."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        rate_limiter._hits.clear()
        self.addCleanup(rate_limiter._hits.clear)
        limits_on = mock.patch.object(settings, "RATE_LIMIT_ENABLED", True)
        limits_on.start()
        self.addCleanup(limits_on.stop)

    def test_visitor_cannot_choose_their_address(self):
        from app.core.security import client_ip
        req = lambda xff: mock.Mock(headers={"x-forwarded-for": xff}, client=mock.Mock(host="10.0.0.1"))
        with mock.patch.object(settings, "TRUSTED_PROXY_HOPS", 2):
            # Through the site: [whatever the visitor typed..., visitor (added by Vercel), Vercel (added by Render)]
            self.assertEqual(client_ip(req("6.6.6.6, 203.0.113.7, 76.76.21.1")), "203.0.113.7")
            self.assertEqual(client_ip(req("203.0.113.7")), "203.0.113.7")
            # Straight to the API (live voice): only Render's entry counts.
            self.assertEqual(client_ip(req("6.6.6.6, 198.51.100.4"), direct=True), "198.51.100.4")
        self.assertEqual(client_ip(mock.Mock(headers={}, client=mock.Mock(host="10.0.0.1"))), "10.0.0.1")

    def test_changing_the_forwarded_header_does_not_reset_the_limit(self):
        with mock.patch.object(settings, "RATE_LIMIT_PER_MINUTE", 3):
            codes = [self.client.get("/api/mortgage/products", headers={"X-Forwarded-For": f"10.9.0.{i}, 203.0.113.7, 76.76.21.1"}).status_code
                     for i in range(4)]
        self.assertEqual(codes[-1], 429)

    def test_paid_calls_have_a_ceiling_shared_by_everyone(self):
        from app.core.security import allow_paid_call
        with mock.patch.object(settings, "GLOBAL_PAID_CALLS_PER_MINUTE", 5):
            allowed = [allow_paid_call(f"visitor-{i}") for i in range(7)]
        self.assertEqual(allowed, [True] * 5 + [False] * 2)

    def test_warm_is_rate_limited(self):
        codes = [self.client.post("/api/warm").status_code for _ in range(8)]
        self.assertEqual((codes[0], codes[-1]), (204, 429))

    def _speak(self, session_id, text):
        async def audio(*a, **k):
            yield {"audio": "", "chars": [], "start": [], "end": []}
        with mock.patch("app.voice.tts_service.TTSService.stream_timed", side_effect=audio):
            return self.client.post("/api/voice/speak-timed", json={"text": text, "session_id": session_id}).status_code

    def test_speech_only_for_what_xo_said(self):
        self.assertEqual(self._speak(None, "Arbitrary text to read aloud."), 403)
        self.assertEqual(self._speak("not-a-session", "Arbitrary text."), 403)
        session = SessionStore.get_or_create(None)
        self.assertEqual(self._speak(session.session_id, "Nothing was said yet."), 429)

        async def reply(*a, **k):
            yield {"type": "session", "session_id": session.session_id, "language": "en"}
            yield {"type": "token", "text": "A three-bedroom villa in Arabian Ranches."}
            yield {"type": "final", "session_id": session.session_id, "text": "A three-bedroom villa in Arabian Ranches."}
        from app.orchestrator.orchestrator import ConversationOrchestrator
        with mock.patch.object(ConversationOrchestrator, "_turn_events", side_effect=reply):
            asyncio.run(ConversationOrchestrator.process_turn("hi", session_id=session.session_id))
        self.assertEqual(self._speak(session.session_id, "Let me check. "), 200)
        self.assertEqual(self._speak(session.session_id, "A three-bedroom villa in Arabian Ranches."), 200)
        self.assertEqual(self._speak(session.session_id, "x" * (settings.TTS_ALLOWANCE_PER_TURN + 1)), 429)

    def test_security_headers_and_no_public_docs(self):
        res = self.client.get("/api/health")
        for header in ("x-content-type-options", "x-frame-options", "referrer-policy", "content-security-policy"):
            self.assertIn(header, res.headers)
        self.assertEqual(self.client.get("/docs").status_code, 404)
        self.assertEqual(self.client.get("/openapi.json").status_code, 404)

    def test_example_admin_key_is_refused(self):
        for weak in ("generate_a_long_random_value", "short-key"):
            with mock.patch.object(settings, "ADMIN_API_KEY", weak):
                self.assertEqual(self.client.get("/api/admin/sessions", headers={"X-Admin-Key": weak}).status_code, 401, weak)

    def test_zip_bomb_word_file_is_refused(self):
        import io
        import zipfile
        from app.admin.knowledge_text import IngestError, extract_file
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("word/document.xml", " " * (80 * 1024 * 1024))
        with self.assertRaises(IngestError) as ctx:
            extract_file("bomb.docx", raw.getvalue())
        self.assertEqual(ctx.exception.code, "too_large")

    def test_locked_rules_always_come_from_the_built_in_file(self):
        from app.admin.config_store import ConfigStore
        from app.services import prompt_profile
        stored = prompt_profile.builtin_profile()
        stale = {**stored, "sections": [{**s, "body": "Old wording.\n"} if s["locked"] else s for s in stored["sections"]]}
        ConfigStore._apply(prompt_profile.PROFILE_ITEM, 7, stale)
        self.addCleanup(ConfigStore.reset_memory)
        rendered = prompt_profile.render_template(prompt_profile.current_profile(), "en")
        self.assertNotIn("Old wording.", rendered)
        self.assertIn("don't calculate or state a figure with it", rendered)


class TestRequestLimits(unittest.TestCase):
    """Fixes from the language security review (28 Oct 2026)."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_huge_bodies_are_refused_before_reading(self):
        big = b'{"message": "hi", "x": "' + b"a" * (settings.MAX_REQUEST_BYTES + 10) + b'"}'
        self.assertEqual(self.client.post("/api/chat/message", content=big, headers={"Content-Type": "application/json"}).status_code, 413)

        def chunks():  # no Content-Length: counted as it arrives
            for _ in range(settings.MAX_REQUEST_BYTES // 65536 + 2):
                yield b"a" * 65536
        self.assertEqual(self.client.post("/api/chat/feedback", content=chunks(), headers={"Content-Type": "application/json"}).status_code, 413)

    def test_language_and_session_fields_are_bounded(self):
        for field, size in (("selected_language", 17), ("ui_language", 17), ("session_id", 129)):
            self.assertEqual(self.client.post("/api/chat/message", json={"message": "hi", field: "a" * size}).status_code, 422, field)

    def test_unknown_language_codes_change_nothing(self):
        with mock.patch("app.orchestrator.orchestrator.ConversationOrchestrator._turn_events") as turn:
            async def events(*a, **k):
                yield {"type": "final", "text": "ok"}
            turn.side_effect = events
            for code in ("ps", "ru\nSYSTEM", "__proto__"):
                self.assertEqual(self.client.post("/api/chat/message", json={"message": "hi", "selected_language": code}).status_code, 200)
        from app.voice.stt_service import _session_update
        self.assertNotIn("languages", _session_update("ps")["session"]["audio"]["input"]["transcription"])
