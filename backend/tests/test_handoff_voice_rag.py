"""Handoff truthfulness (FR-5, FR-16), voice text preparation, RAG scoping (FR-17–FR-20)."""
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import numpy as np

from app.db.lead_store import LeadDatabaseService
from app.orchestrator.session_store import SessionStore
from app.services.handoff_service import HandoffService, valid_phone
from app.services.rag_service import RAGService
from app.services.vector_store import VectorDatabase
import json

import httpx

from app.core.config import settings
from app.voice.tts_service import TTSService, TTSUnavailable, speech_text


class TestHandoff(unittest.IsolatedAsyncioTestCase):
    """Review-card flow: prepare (validate + draft, nothing saved) -> user confirms or edits -> saved."""

    async def asyncSetUp(self):
        LeadDatabaseService.clear_memory()
        self.session = SessionStore.get_or_create(None)

    def prepare(self, phone="+971 50 123 4567", consent=True, language="Hindi"):
        return HandoffService.prepare_callback(self.session, "Aisha Khan", phone, language, consent_confirmed=consent, team="mortgage")

    async def confirm(self, draft, **edits):
        fields = {"name": draft["name"], "phone": draft["phone"], "preferred_language": draft["preferred_language"], "team": draft["team"], **edits}
        return await HandoffService.confirm_callback(self.session, draft["draft_id"], fields["name"], fields["phone"],
                                                     fields["preferred_language"], fields["team"])

    async def test_consent_required(self):
        r = self.prepare(consent=False)
        self.assertEqual(r["status"], "consent_missing")
        self.assertIsNone(self.session.handoff_draft)

    async def test_invalid_phone_rejected_with_format_hint(self):
        for bad in ("12", "+08848237169", "call me maybe"):
            r = self.prepare(phone=bad)
            self.assertEqual(r["status"], "invalid_phone", bad)
            self.assertIn("+971 50 123 4567", r["instruction"])

    async def test_draft_is_not_saved_until_confirmed(self):
        r = self.prepare(phone="050 123 4567")                 # local UAE format gets the country code
        self.assertEqual(r["status"], "awaiting_confirmation")
        self.assertEqual(r["details"]["phone"], "+971 50 123 4567")
        self.assertEqual(r["details"]["preferred_language"], "hi")
        self.assertEqual(await LeadDatabaseService.list_leads(), [])

    async def test_confirm_saves_edited_details(self):
        draft = self.prepare()["details"]
        r = await self.confirm(draft, phone="+44 7911 123456", preferred_language="en", team="sales", name="  Aisha   K. ")
        self.assertTrue(r["lead_saved"])
        self.assertTrue(r["ticket_id"].startswith("XO-"))
        leads = await LeadDatabaseService.list_leads()
        self.assertEqual(len(leads), 1)
        self.assertEqual((leads[0]["full_name"], leads[0]["phone_number"], leads[0]["preferred_language"], leads[0]["advisor_type"]),
                         ("Aisha K.", "+447911123456", "English", "Property Advisory"))
        self.assertEqual(leads[0]["ticket_id"], r["ticket_id"])
        self.assertIsNone(self.session.handoff_draft)          # a card can be submitted once

    async def test_confirm_rejects_bad_edits_and_stale_cards(self):
        draft = self.prepare()["details"]
        self.assertEqual((await self.confirm(draft, phone="+0884"))["field"], "phone")
        self.assertEqual((await self.confirm(draft, name="  "))["field"], "name")
        newer = self.prepare(phone="+971 55 765 4321")["details"]
        self.assertEqual((await self.confirm(draft))["error"], "draft_expired")
        self.assertTrue((await self.confirm(newer))["lead_saved"])

    async def test_database_failure_is_reported_truthfully(self):
        draft = self.prepare()["details"]
        failing_pool = mock.MagicMock()
        failing_pool.acquire.side_effect = RuntimeError("db down")
        with mock.patch.object(LeadDatabaseService, "_pool", failing_pool):
            r = await self.confirm(draft)
        self.assertFalse(r["lead_saved"])
        self.assertEqual(r["error"], "save_failed")
        self.assertIsNotNone(self.session.handoff_draft)       # the user can try again

    def test_phone_validation(self):
        self.assertTrue(valid_phone("+971 50 123 4567"))
        self.assertTrue(valid_phone("00971501234567"))
        self.assertTrue(valid_phone("0501234567"))
        self.assertFalse(valid_phone("+08848237169"))
        self.assertFalse(valid_phone("call me maybe"))


class TestSpeechText(unittest.TestCase):

    def test_markdown_removed_for_tts(self):
        spoken = speech_text("**Price:** AED 1,500,000\n\n1. Marina Heights\n- pool\n[link](https://x.y) ###")
        for ch in ("*", "#", "[", "http"):
            self.assertNotIn(ch, spoken)
        self.assertIn("AED 1,500,000", spoken)



class TestTimedSpeech(unittest.IsolatedAsyncioTestCase):
    """Word timings for highlighting the word XO is saying (ElevenLabs stream/with-timestamps)."""

    def use_transport(self, handler):
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        patcher = mock.patch.object(TTSService, "_client", client)
        patcher.start()
        self.addCleanup(patcher.stop)
        key = mock.patch.object(settings, "ELEVENLABS_API_KEY", "test-key")
        key.start()
        self.addCleanup(key.stop)
        return client

    async def test_chunks_carry_audio_and_character_timings(self):
        seen = {}

        def handler(request):
            seen["path"] = request.url.path
            seen["text"] = json.loads(request.content)["text"]
            lines = [
                {"audio_base64": "QUJD", "alignment": {"characters": list("Hi "), "character_start_times_seconds": [0.0, 0.1, 0.2], "character_end_times_seconds": [0.1, 0.2, 0.3]}},
                {"audio_base64": "REVG", "alignment": None},
            ]
            return httpx.Response(200, content="\n".join(json.dumps(x) for x in lines).encode())

        self.use_transport(handler)
        chunks = [c async for c in TTSService.stream_timed("**Hi** there", "en")]
        self.assertTrue(seen["path"].endswith("/stream/with-timestamps"))
        self.assertEqual(seen["text"], "Hi there")            # markdown is never read aloud
        self.assertEqual(chunks[0], {"audio": "QUJD", "chars": ["H", "i", " "], "start": [0.0, 0.1, 0.2], "end": [0.1, 0.2, 0.3]})
        self.assertEqual(chunks[1]["chars"], [])                # audio-only chunk

    async def test_provider_error_is_reported_as_unavailable(self):
        self.use_transport(lambda request: httpx.Response(401, content=b"bad key"))
        with self.assertRaises(TTSUnavailable):
            _ = [c async for c in TTSService.stream_timed("Hello", "en")]

class TestRAG(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        RAGService.clear_cache()
        VectorDatabase.load()

    def _embedding_of(self, title):
        idx = next(i for i, d in enumerate(VectorDatabase._docs) if title.lower() in (d.get("title") or "").lower())
        return VectorDatabase._vectors[idx].tolist()

    async def _retrieve(self, vector, query="q"):
        fake = NS(embeddings=NS(create=mock.AsyncMock(return_value=NS(data=[NS(embedding=vector)], usage=NS(prompt_tokens=5)))))
        with mock.patch("app.services.rag_service.LLMService.client", return_value=fake):
            return await RAGService.retrieve(query)

    async def test_returns_passages_for_synthesis(self):
        r = await self._retrieve(self._embedding_of("Golden Visa"), "golden visa threshold")
        self.assertEqual(r["status"], "success")
        self.assertIn("Golden Visa", r["passages"][0]["title"])
        self.assertTrue(r.get("disclaimer_note"))

    async def test_low_confidence_says_not_found(self):
        r = await self._retrieve(np.random.RandomState(0).randn(1536).tolist(), "who is the ceo")
        self.assertEqual(r["status"], "not_found")
        self.assertIn("advisor", r["instruction"])

    async def test_excluded_calculator_articles_never_returned(self):
        statuses = {d.get("status") for d in VectorDatabase._docs}
        self.assertNotIn("EXCLUDED", statuses)

    async def test_cache_avoids_repeat_embedding(self):
        vec = self._embedding_of("Ejari")
        fake_create = mock.AsyncMock(return_value=NS(data=[NS(embedding=vec)], usage=None))
        with mock.patch("app.services.rag_service.LLMService.client", return_value=NS(embeddings=NS(create=fake_create))):
            await RAGService.retrieve("what is ejari")
            await RAGService.retrieve("what is ejari")
        self.assertEqual(fake_create.await_count, 1)


if __name__ == "__main__":
    unittest.main()
