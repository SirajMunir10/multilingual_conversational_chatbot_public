import sys
import os
import unittest
import io

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from app.main import app
from app.orchestrator.language_detector import LanguageDetector
from app.orchestrator.session_store import SessionStore

class TestPhase2ConversationalCore(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_language_detection_all_launch_languages(self):
        # 1. English
        lang_en, conf_en = LanguageDetector.detect_language("Show me luxury apartments in Dubai Hills")
        self.assertEqual(lang_en, "en")
        self.assertGreater(conf_en, 0.8)

        # 2. Arabic
        lang_ar, conf_ar = LanguageDetector.detect_language("أريد شراء شقة في وسط مدينة دبي بميزانية مليوني درهم")
        self.assertEqual(lang_ar, "ar")
        self.assertGreater(conf_ar, 0.8)

        # 3. Hindi
        lang_hi, conf_hi = LanguageDetector.detect_language("मुझे दुबई मरीना में 2 बीएचके फ्लैट चाहिए")
        self.assertEqual(lang_hi, "hi")
        self.assertGreater(conf_hi, 0.8)

        # 4. Urdu
        lang_ur, conf_ur = LanguageDetector.detect_language("مجھے ڈاؤن ٹاؤن دبئی میں 2 بیڈ روم اپارٹمنٹ اور مارگیج کی معلومات چاہیے")
        self.assertEqual(lang_ur, "ur")
        self.assertGreater(conf_ur, 0.75)

    def test_manual_language_override_persistence(self):
        session_id = "test_override_sess_101"
        # Set manual override to Arabic
        res = self.client.post(f"/api/chat/session/{session_id}/language", json={"language": "ar"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["language"], "ar")

        # Send English message, should reply in Arabic due to manual override
        res_msg = self.client.post("/api/chat/message", json={
            "session_id": session_id,
            "message": "Hello there"
        })
        self.assertEqual(res_msg.status_code, 200)
        data = res_msg.json()
        self.assertTrue("مرحب" in data["text"] or data["language"] == "ar")

    def test_mixed_intent_conversation(self):
        session_id = "test_mixed_intent_sess_202"
        # Turn 1: Property search
        res1 = self.client.post("/api/chat/message", json={
            "session_id": session_id,
            "message": "Show me 2 bedroom apartments in Downtown under 3 million"
        })
        self.assertEqual(res1.status_code, 200)
        d1 = res1.json()
        self.assertEqual(d1["intent"], "property")
        self.assertGreater(len(d1["property_results"]), 0)

        # Turn 2: Mixed intent without restart -> Mortgage inquiry (FR-3)
        res2 = self.client.post("/api/chat/message", json={
            "session_id": session_id,
            "message": "What would my EMI be if my monthly income is 45k?"
        })
        self.assertEqual(res2.status_code, 200)
        d2 = res2.json()
        self.assertEqual(d2["intent"], "mortgage")
        self.assertIsNotNone(d2["mortgage_result"])
        # Check Rule 10 mandatory disclaimer
        self.assertIn("estimate only, subject to lender approval", d2["mortgage_result"]["disclaimer"])

        # Check full transcript maintains both turns (FR-2)
        res_sess = self.client.get(f"/api/chat/session/{session_id}")
        self.assertEqual(res_sess.status_code, 200)
        transcript = res_sess.json()["transcript"]
        self.assertEqual(len(transcript), 4)  # 2 user + 2 assistant messages

    def test_clarifying_slot_filling_when_info_incomplete(self):
        session_id = "test_slots_sess_303"
        # Incomplete property query (FR-4)
        res = self.client.post("/api/chat/message", json={
            "session_id": session_id,
            "message": "I want to buy something in the UAE"
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        # Should ask clarifying question about bedrooms/budget/type
        text_lower = data["text"].lower()
        self.assertTrue(any(term in text_lower for term in ["apartment", "villa", "bedroom", "beds", "budget", "property", "area"]))

    def test_voice_stt_endpoint(self):
        # Create dummy wav audio
        fake_wav = io.BytesIO(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00")
        files = {"audio": ("test.wav", fake_wav, "audio/wav")}
        res = self.client.post("/api/voice/transcribe", files=files, data={"language_hint": "en"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["model"], "gpt-live-transcribe")
        self.assertIn("Downtown", data["text"])

    def test_voice_tts_endpoint(self):
        res = self.client.post("/api/voice/synthesize", json={
            "text": "Welcome to XO Assistant.",
            "language": "en"
        })
        self.assertEqual(res.status_code, 200)
        self.assertIn(res.headers["content-type"], ["audio/mpeg", "audio/wav"])
        self.assertGreater(len(res.content), 40)

    def test_composed_v2v_pipeline(self):
        # Tests User Audio -> STT -> Orchestrator -> TTS -> Audio Out
        fake_wav = io.BytesIO(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00")
        files = {"audio": ("speech.wav", fake_wav, "audio/wav")}
        res = self.client.post("/api/voice/interact", files=files, data={"language_hint": "en"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("transcribed_user_text", data)
        self.assertIn("reply_text", data)
        self.assertTrue(data["audio_base64"].startswith("data:audio/mp3;base64,") or data["audio_base64"].startswith("data:audio/mpeg;base64,") or data["audio_base64"].startswith("data:audio/wav;base64,"))
        self.assertEqual(data["pipeline"], "gpt-live-transcribe -> gpt-5-mini -> eleven_flash_v2_5")

if __name__ == "__main__":
    unittest.main()
