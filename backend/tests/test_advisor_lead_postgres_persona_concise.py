import unittest
import asyncio
import os
import sys

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from app.main import app
from app.db.lead_store import LeadDatabaseService
from app.orchestrator.orchestrator import ConversationOrchestrator
from app.orchestrator.session_store import SessionStore
from app.services.handoff_service import HandoffService
from app.core.config import settings

class TestAdvisorLeadPostgresPersonaConcise(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        # Reset in-memory leads and sessions before each test
        LeadDatabaseService.clear_all()

    # =========================================================================
    # 1. POSTGRESQL LEAD DATABASE SERVICE & DEDUPLICATION (LEAD-1, LEAD-2, LEAD-3)
    # =========================================================================

    def test_01_lead_database_save_and_retrieve(self):
        """Lead is correctly persisted in LeadDatabaseService with full metadata."""
        saved = asyncio.run(LeadDatabaseService.save_advisor_lead(
            session_id="sess_lead_01",
            full_name="Fatima Al-Zahra",
            phone_number="+971509876543",
            preferred_language="Arabic",
            advisor_type="Prime & Ultra-Luxury Sales",
            conversation_context={"budget": 15000000, "area": "Palm Jumeirah"}
        ))
        self.assertTrue(saved)

        # Verify retrieval
        lead = asyncio.run(LeadDatabaseService.get_lead_by_session("sess_lead_01"))
        self.assertIsNotNone(lead)
        self.assertEqual(lead["session_id"], "sess_lead_01")
        self.assertEqual(lead["full_name"], "Fatima Al-Zahra")
        self.assertEqual(lead["phone_number"], "+971509876543")
        self.assertEqual(lead["preferred_language"], "Arabic")
        self.assertEqual(lead["advisor_type"], "Prime & Ultra-Luxury Sales")
        self.assertEqual(lead["status"], "pending_contact")

    def test_02_lead_database_deduplication(self):
        """Re-submitting with identical (session_id, phone_number) updates record without duplicating."""
        # First save
        saved1 = asyncio.run(LeadDatabaseService.save_advisor_lead(
            session_id="sess_lead_dedup",
            full_name="Kareem Tariq",
            phone_number="+971551234567",
            preferred_language="English",
            advisor_type="Mortgage Advisory",
            conversation_context={"turn": 1}
        ))
        self.assertTrue(saved1)

        # Second save with updated context/language
        saved2 = asyncio.run(LeadDatabaseService.save_advisor_lead(
            session_id="sess_lead_dedup",
            full_name="Kareem Tariq",
            phone_number="+971551234567",
            preferred_language="French",
            advisor_type="Mortgage Advisory",
            conversation_context={"turn": 2, "updated": True}
        ))
        self.assertTrue(saved2)

        # Ensure deduplicated: exactly 1 record exists in total
        self.assertEqual(LeadDatabaseService.get_lead_count(), 1)
        lead = asyncio.run(LeadDatabaseService.get_lead_by_session("sess_lead_dedup"))
        self.assertIsNotNone(lead)
        self.assertEqual(lead["preferred_language"], "French")
        self.assertTrue(lead["conversation_context"].get("updated"))

    def test_03_lead_database_validation_rejects_missing_info(self):
        """LeadDatabaseService requires phone number and valid full name."""
        # Missing phone number
        saved_no_phone = asyncio.run(LeadDatabaseService.save_advisor_lead(
            session_id="sess_invalid_1",
            full_name="Siraj Munir",
            phone_number="",
            preferred_language="English",
            advisor_type="Support",
            conversation_context={}
        ))
        self.assertFalse(saved_no_phone)

        # Generic uncollected name
        saved_generic_name = asyncio.run(LeadDatabaseService.save_advisor_lead(
            session_id="sess_invalid_2",
            full_name="Valued Client",
            phone_number="+971501112233",
            preferred_language="English",
            advisor_type="Support",
            conversation_context={}
        ))
        self.assertFalse(saved_generic_name)
        self.assertEqual(LeadDatabaseService.get_lead_count(), 0)

    # =========================================================================
    # 2. ADVISOR REQUESTS & CONSENT PROTOCOL (LEAD-4, LEAD-5, LEAD-6, LEAD-7)
    # =========================================================================

    def test_04_advisor_request_prompts_consent_and_no_advisor_names(self):
        """When user requests an advisor, bot asks for consent and contact info without displaying individual advisor profiles."""
        session_id = "sess_advisor_consent_gate"
        result = asyncio.run(ConversationOrchestrator.process_user_turn(
            user_message="Can I speak with a mortgage advisor?",
            session_id=session_id
        ))

        text = result["text"]
        # Must request consent / required contact fields
        self.assertTrue(any(term in text.lower() for term in ["name", "phone", "language", "contact you", "touch"]))
        # Must NOT leak individual advisor names or personal licenses
        self.assertNotIn("Omar Farooq", text)
        self.assertNotIn("Sarah Al-Maktoum", text)
        self.assertNotIn("Rashid Bin Zayed", text)
        self.assertNotIn("RERA Broker #", text)
        self.assertNotIn("wa.me", text)
        # Handoff card not yet offered until details provided
        self.assertFalse(result.get("handoff_offered", False))

        # Ensure NO lead has been persisted yet
        lead = asyncio.run(LeadDatabaseService.get_lead_by_session(session_id))
        self.assertIsNone(lead)

    def test_05_advisor_request_declined_persists_zero_leads(self):
        """When user explicitly declines advisor contact, bot responds politely and persists zero leads."""
        session_id = "sess_advisor_declined"
        
        # Turn 1: User asks for advisor
        asyncio.run(ConversationOrchestrator.process_user_turn(
            user_message="I want an advisor",
            session_id=session_id
        ))

        # Turn 2: User explicitly declines to share details
        res_decline = asyncio.run(ConversationOrchestrator.process_user_turn(
            user_message="No, I don't want to provide my phone number. Cancel that.",
            session_id=session_id
        ))

        decline_text = res_decline["text"].lower()
        # Polite acknowledgement
        self.assertTrue(any(term in decline_text for term in ["no problem", "understood", "all right", "assist you right here", "help you here", "here"]))
        # No handoff offered
        self.assertFalse(res_decline.get("handoff_offered", False))

        # Strictly 0 leads persisted
        lead = asyncio.run(LeadDatabaseService.get_lead_by_session(session_id))
        self.assertIsNone(lead)
        self.assertEqual(LeadDatabaseService.get_lead_count(), 0)

    def test_06_advisor_request_accepted_persists_lead_and_confirms(self):
        """When user provides details, lead is persisted and callback from department is confirmed."""
        session_id = "sess_advisor_confirmed"

        # Turn 1: Request
        asyncio.run(ConversationOrchestrator.process_user_turn(
            user_message="I want to speak with a luxury property consultant",
            session_id=session_id
        ))

        # Turn 2: Consent provided with details
        res_confirm = asyncio.run(ConversationOrchestrator.process_user_turn(
            user_message="Yes please. My name is Tariq Mansoor, phone +971 50 445 6789, preferred language Arabic",
            session_id=session_id
        ))

        self.assertTrue(res_confirm.get("handoff_offered", False))
        handoff_data = res_confirm.get("handoff_data", {})
        self.assertTrue(handoff_data.get("lead_saved", False))
        self.assertEqual(handoff_data.get("applicant_phone"), "+971 50 445 6789")

        # Confirmation message references departmental team, not individual names
        confirm_text = res_confirm["text"]
        self.assertNotIn("Omar Farooq", confirm_text)
        self.assertNotIn("Sarah Al-Maktoum", confirm_text)
        self.assertNotIn("Rashid Bin Zayed", confirm_text)
        self.assertNotIn("wa.me", confirm_text)

        # Check DB lead record
        lead = asyncio.run(LeadDatabaseService.get_lead_by_session(session_id))
        self.assertIsNotNone(lead)
        self.assertEqual(lead["full_name"], "Tariq Mansoor")
        self.assertEqual(lead["phone_number"], "+971 50 445 6789")
        self.assertEqual(lead["preferred_language"], "Arabic")

    # =========================================================================
    # 3. CONSISTENT MASCULINE PERSONA ACROSS 15 LANGUAGES (PERS-1, PERS-2, PERS-3, PERS-4)
    # =========================================================================

    def test_07_identity_gender_question_affirms_boy(self):
        """When asked if XO is a boy or a girl, assistant consistently affirms he is a boy."""
        session_id = "sess_gender_id"
        result = asyncio.run(ConversationOrchestrator.process_user_turn(
            user_message="Are you a boy or a girl?",
            session_id=session_id
        ))
        
        reply = result["text"].lower()
        self.assertTrue("boy" in reply or "male" in reply or "larka" in reply)
        self.assertNotIn("girl", reply.split()[0:5]) # First sentence should affirm boy

    def test_08_multilingual_deterministic_boy_identity_all_languages(self):
        """Deterministic identity replies for gender query affirm young boy persona across languages."""
        supported_langs = ["en", "ar", "ur", "hi", "fr", "es", "ru", "zh", "de", "it"]
        for lang in supported_langs:
            session = SessionStore.get_or_create_session(f"sess_det_gender_{lang}")
            session.language = lang
            session.active_intent = "identity"
            det_res = asyncio.run(ConversationOrchestrator._deterministic_engine(session, "Are you a boy?"))
            det_reply = det_res["text"]
            self.assertIsNotNone(det_reply)
            # In Urdu/Hindi: confirms larka / ladka
            if lang == "ur":
                self.assertTrue("لڑکا" in det_reply or "larka" in det_reply.lower())
            elif lang == "hi":
                self.assertTrue("लड़का" in det_reply or "ladka" in det_reply.lower())
            elif lang == "ar":
                self.assertTrue("فتى" in det_reply or "ولد" in det_reply)
            elif lang == "fr":
                self.assertTrue("garçon" in det_reply.lower())
            elif lang == "es":
                self.assertTrue("chico" in det_reply.lower() or "niño" in det_reply.lower())

    def test_09_voice_synthesis_preserves_elevenlabs_horatius_configuration(self):
        """ElevenLabs configuration strictly retains Flash v2.5 and voice Horatius qXpMhyvQqiRxWQs4qSSB."""
        from app.voice.tts_service import TTSService
        self.assertEqual(TTSService.VOICE_PROFILES["en"], "qXpMhyvQqiRxWQs4qSSB")
        self.assertEqual(settings.TTS_MODEL, "eleven_flash_v2_5")

    # =========================================================================
    # 4. CONCISE, INTELLIGENT RESPONSES (RESP-1, RESP-2, RESP-3, RESP-4)
    # =========================================================================

    def test_10_no_cheerleading_filler_greetings(self):
        """Responses do not begin with fluffy cheerleading intros like 'Yay — love this!'."""
        session_id = "sess_concise_greeting"
        result = asyncio.run(ConversationOrchestrator.process_user_turn(
            user_message="Calculate affordability for 45000 AED income, zero debt, 1 million down payment.",
            session_id=session_id
        ))

        text = result["text"]
        # Ensure cheerleading filler is strictly absent
        self.assertFalse(text.startswith("Yay"))
        self.assertFalse(text.startswith("Woohoo"))
        self.assertNotIn("Yay — love this", text)
        self.assertNotIn("Yay — I've connected", text)

        # Essential figures and disclaimer must be present
        self.assertTrue("AED" in text or "aed" in text.lower())
        self.assertTrue("estimate only" in text.lower() or "subject to lender approval" in text.lower() or "estimate" in text.lower())

if __name__ == "__main__":
    unittest.main(verbosity=2)
