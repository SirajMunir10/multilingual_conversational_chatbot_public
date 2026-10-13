import sys
import os
import unittest
import io

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from app.main import app
from app.orchestrator.session_store import SessionStore

class TestVoiceUXRefinement(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_voice_interact_with_client_transcribed_text(self):
        """
        Verify that when live transcribed_text is captured on screen by the client
        and confirmed by user (✓ action), /api/voice/interact respects the client text.
        """
        fake_wav = io.BytesIO(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00")
        files = {"audio": ("speech.wav", fake_wav, "audio/wav")}
        session_id = "test_voice_confirmed_sess_1"
        data = {
            "session_id": session_id,
            "language_hint": "en",
            "transcribed_text": "Show me 2 bedroom apartments in Downtown Dubai"
        }
        res = self.client.post("/api/voice/interact", files=files, data=data)
        self.assertEqual(res.status_code, 200)
        res_data = res.json()
        self.assertEqual(res_data["session_id"], session_id)
        self.assertEqual(res_data["transcribed_user_text"], "Show me 2 bedroom apartments in Downtown Dubai")
        self.assertIn("Downtown", res_data["reply_text"])
        self.assertTrue(res_data["audio_base64"].startswith("data:audio/mp3;base64,") or res_data["audio_base64"].startswith("data:audio/mpeg;base64,") or res_data["audio_base64"].startswith("data:audio/wav;base64,"))
        self.assertEqual(res_data["intent"], "property")

    def test_voice_interact_fallback_when_no_transcribed_text(self):
        """
        Verify backwards compatibility: when transcribed_text is not provided,
        it automatically falls back to STTService.transcribe_audio.
        """
        fake_wav = io.BytesIO(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00")
        files = {"audio": ("speech.wav", fake_wav, "audio/wav")}
        session_id = "test_voice_fallback_sess_2"
        data = {
            "session_id": session_id,
            "language_hint": "en"
        }
        res = self.client.post("/api/voice/interact", files=files, data=data)
        self.assertEqual(res.status_code, 200)
        res_data = res.json()
        self.assertEqual(res_data["session_id"], session_id)
        self.assertTrue(len(res_data["transcribed_user_text"]) > 0)
        self.assertTrue(res_data["audio_base64"].startswith("data:audio/mp3;base64,") or res_data["audio_base64"].startswith("data:audio/mpeg;base64,") or res_data["audio_base64"].startswith("data:audio/wav;base64,"))

    def test_voice_greeting_synthesis_all_languages(self):
        """
        Verify that XO can synthesize welcome/greeting speech across all 4 launch languages
        (English, Arabic, Hindi, Urdu) for voice session start.
        """
        greetings = {
            "en": "Welcome to XO! I am your AI assistant for premier properties and mortgages.",
            "ar": "أهلاً بك في XO! أنا مساعدك الذكي للعقارات والتمويل العقاري في الإمارات.",
            "hi": "नमस्ते! मैं XO हूँ, यूएई में प्रॉपर्टी और होम लोन के लिए आपका एआई सहायक।",
            "ur": "خوش آمدید! میں XO ہوں، متحدہ عرب امارات میں پراپرٹی اور مارگیج کے لیے آپ کا AI اسسٹنٹ۔"
        }

        for lang, text in greetings.items():
            res = self.client.post("/api/voice/synthesize", json={
                "text": text,
                "language": lang
            })
            self.assertEqual(res.status_code, 200)
            self.assertIn(res.headers["content-type"], ["audio/mpeg", "audio/wav"])
            self.assertGreater(len(res.content), 40)

    def test_session_state_preserved_across_multiple_interactions(self):
        """
        Verify that session context, slots, and message history remain intact
        across consecutive turns and voice/text interactions in the same session.
        """
        session_id = "test_preserve_sess_3"

        # Turn 1: Text message
        res1 = self.client.post("/api/chat/message", json={
            "session_id": session_id,
            "message": "Show me 2 BHK in Palm Jumeirah"
        })
        self.assertEqual(res1.status_code, 200)

        # Turn 2: Voice message in same session
        fake_wav = io.BytesIO(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00")
        files = {"audio": ("speech.wav", fake_wav, "audio/wav")}
        res2 = self.client.post("/api/voice/interact", files=files, data={
            "session_id": session_id,
            "transcribed_text": "What would be my EMI for this?"
        })
        self.assertEqual(res2.status_code, 200)

        # Check full transcript
        res_sess = self.client.get(f"/api/chat/session/{session_id}")
        self.assertEqual(res_sess.status_code, 200)
        sess_data = res_sess.json()
        self.assertEqual(sess_data["session_id"], session_id)
        self.assertEqual(sess_data["messages_count"], 4)  # 2 user + 2 assistant messages

if __name__ == "__main__":
    unittest.main()
