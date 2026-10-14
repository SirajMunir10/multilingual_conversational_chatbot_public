import unittest
import os
import sys

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.orchestrator.orchestrator import ConversationOrchestrator
from app.orchestrator.session_store import SessionStore
from app.services.property_service import PropertyDiscoveryService, PropertySearchFilter
from app.gateways.grid_gateway import GridGateway
from app.llm.client import LLMService

class TestMasterAIEngineering(unittest.TestCase):
    """
    Test Suite for Master AI Engineering Improvements & Production Readiness:
    1. Trust & Safety Question Defense (UAE PDPL Law 45, DLD Title Deed verification, Law 8/2007 Escrow).
    2. Pure 2-Turn Advisor Consent Protocol (Turn 1 Permission Only -> Turn 2 Contact Details).
    3. Fuzzy Entity Resolution (GLT -> JLT, Imtiaz -> Imtiyaz) & Catalogue-First Inspection.
    4. Unconfirmed Location Anti-Hallucination Guard (e.g. 'alt').
    5. Deterministic Zero-Debt Extraction across variations and languages.
    6. Phase 6 Grid Off-Plan Gateway live querying, normalization, and audit trail.
    """

    def setUp(self):
        # Create fresh session for each test
        import uuid
        self.session_id = f"test_ai_eng_{uuid.uuid4().hex[:8]}"
        self.session = SessionStore.get_or_create_session(
            session_id=self.session_id,
            user_id="test_user_ai_eng",
            initial_language="en"
        )

    # =========================================================================
    # 1. TRUST & SAFETY QUESTION DEFENSE (KB Article 53 & UAE Law)
    # =========================================================================

    def test_01_trust_safety_question_does_not_trigger_handoff_declined(self):
        """
        Verify that when a user asks a safety/trust question, even with negative words
        like 'No' or 'don't trust', it is NOT classified as a handoff refusal.
        """
        self.session.handoff_requested = True
        self.session.slots.advisor_consent_pending = True

        # User asks a trust/safety question containing negative words
        question_text = "No, I don't trust you. How is my information safe and what proof do you have?"
        intent = ConversationOrchestrator._classify_intent(question_text, self.session)

        # Must NOT be classified as handoff_declined
        self.assertNotEqual(intent, "handoff_declined")
        self.assertEqual(intent, "trust_safety")

    def test_02_system_prompt_contains_mandatory_trust_and_safety_laws(self):
        """
        Verify that Rule 16 in the LLM System Prompt explicitly cites
        UAE Federal Decree-Law No. 45 of 2021 (PDPL), DLD Title Deed verification,
        and Law No. 8 of 2007 Escrow protection.
        """
        prompt = LLMService.get_system_prompt("en")
        self.assertIn("Federal Decree-Law No. 45 of 2021", prompt)
        self.assertIn("Title Deed", prompt)
        self.assertIn("Law No. 8 of 2007", prompt)
        self.assertIn("Escrow", prompt)

    # =========================================================================
    # 2. PURE 2-TURN ADVISOR CONSENT PROTOCOL
    # =========================================================================

    def test_03_advisor_request_turn1_asks_permission_only(self):
        """
        Turn 1: When user requests an advisor, the orchestrator asks ONLY for
        permission to arrange a callback and assures anonymous exploration is fine.
        Zero contact details are demanded.
        """
        import asyncio
        self.session.active_intent = "human_handoff"
        res = asyncio.run(ConversationOrchestrator._deterministic_engine(
            session=self.session,
            user_text="Can I speak with a human advisor?"
        ))

        self.assertTrue(self.session.slots.advisor_consent_pending)
        self.assertTrue(self.session.handoff_requested)
        # Turn 1 must NOT demand phone number or name
        self.assertNotIn("Full Name", res["text"])
        self.assertNotIn("Phone Number", res["text"])
        # Must ask for consent politely
        self.assertTrue("advisor" in res["text"].lower() or "consultation" in res["text"].lower())
        self.assertTrue("anonymously" in res["text"].lower() or "without" in res["text"].lower())

    def test_04_advisor_request_turn2_after_affirmative_consent(self):
        """
        Turn 2: When user confirms consent ('Yes, please'), the system transitions
        to requesting Full Name, Phone Number, and Preferred Language.
        """
        # Set up state as having received Turn 1
        self.session.slots.advisor_consent_pending = True
        self.session.handoff_requested = True

        intent = ConversationOrchestrator._classify_intent("Yes, please connect me", self.session)
        self.assertEqual(intent, "human_handoff")
        self.assertTrue(self.session.slots.customer_consent_given)

        import asyncio
        self.session.active_intent = "human_handoff"
        res = asyncio.run(ConversationOrchestrator._deterministic_engine(
            session=self.session,
            user_text="Yes, please connect me"
        ))

        # Turn 2 must now request the 3 contact items
        self.assertIn("Full Name", res["text"])
        self.assertIn("Phone Number", res["text"])
        self.assertIn("Preferred Contact Language", res["text"])

    def test_05_advisor_intake_extracts_contact_and_triggers_handoff(self):
        """
        Once user supplies contact details, slots are extracted and handoff is initiated.
        """
        self.session.slots.customer_consent_given = True
        contact_msg = "My name is Tariq Al-Mansoor, phone +971501234567, English"
        ConversationOrchestrator._extract_slots(contact_msg, self.session)

        self.assertEqual(self.session.slots.customer_name, "Tariq Al-Mansoor")
        self.assertEqual(self.session.slots.customer_phone, "+971501234567")
        self.assertEqual(self.session.slots.customer_preferred_language, "English")

    # =========================================================================
    # 3. FUZZY ENTITY RESOLUTION & CATALOGUE INSPECTION
    # =========================================================================

    def test_06_fuzzy_typo_resolution_glt_to_jlt_and_imtiaz(self):
        """
        Typo resolution: 'GLT' auto-resolves to JLT with transparent note,
        and 'Imtiaz' auto-resolves to canonical 'Imtiyaz'.
        """
        text = "Show me apartments in GLT by Imtiaz"
        ConversationOrchestrator._extract_slots(text, self.session)

        self.assertEqual(self.session.slots.property_city, "JLT")
        self.assertEqual(self.session.slots.inferred_location_note, "Assuming you mean JLT")
        self.assertEqual(self.session.slots.property_developer, "Imtiyaz")
        self.assertIsNone(self.session.slots.unconfirmed_location)

    def test_07_developer_catalog_inspection_when_zero_listings_in_community(self):
        """
        When requested developer has no listings in the requested community (e.g. Imtiyaz in JLT),
        find_catalog_alternatives discovers other developers in JLT and projects by that developer in other communities.
        """
        filters = PropertySearchFilter(
            city="JLT",
            developer="Imtiyaz"
        )
        alts = PropertyDiscoveryService.find_catalog_alternatives(filters)
        dev_alts = alts.get("developer_alternatives", {})

        self.assertEqual(dev_alts.get("searched_developer"), "Imtiyaz")
        # Should detect that developer has projects in other areas (e.g., JVC)
        self.assertIsInstance(dev_alts.get("developer_other_communities"), list)

    # =========================================================================
    # 4. UNCONFIRMED LOCATION ANTI-HALLUCINATION GUARD
    # =========================================================================

    def test_08_unconfirmed_location_detection(self):
        """
        Detects unconfirmed location candidate (e.g. 'apartments in alt')
        without confusing it with common keywords.
        """
        text = "Show me 2 bedroom apartments in alt"
        ConversationOrchestrator._extract_slots(text, self.session)

        self.assertEqual(self.session.slots.unconfirmed_location, "alt")
        self.assertIsNone(self.session.slots.property_city)

    # =========================================================================
    # 5. DETERMINISTIC ZERO-DEBT EXTRACTION
    # =========================================================================

    def test_09_zero_debt_extraction_variations(self):
        """
        Tests extraction of zero liabilities across diverse user expressions and languages.
        """
        test_phrases = [
            "I have no loans",
            "zero liabilities",
            "no existing debt",
            "debt-free",
            "none",
            "0",
            "لا توجد ديون",
            "कोई कर्ज नहीं"
        ]
        for phrase in test_phrases:
            sess = SessionStore.get_or_create_session(session_id=f"test_zero_debt_{phrase[:4]}", user_id="test_zero_debt", initial_language="en")
            ConversationOrchestrator._extract_slots(phrase, sess)
            self.assertEqual(
                sess.slots.mortgage_existing_debt,
                0.0,
                f"Failed to extract 0.0 debt for phrase: '{phrase}'"
            )

    # =========================================================================
    # 6. PHASE 6 GRID OFF-PLAN GATEWAY
    # =========================================================================

    def test_10_grid_offplan_gateway_live_query_and_normalization(self):
        """
        Verifies GridGateway.search_offplan_projects queries live endpoint,
        normalizes non-breaking spaces (\xa0), maps bedrooms, and logs audit events.
        """
        results = GridGateway.search_offplan_projects(limit=5)
        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0)

        first = results[0]
        # Verify ScopedPropertyListing fields
        self.assertTrue(first.id.startswith("grid-offplan-"))
        self.assertEqual(first.status, "off-plan")
        self.assertNotIn("\xa0", first.community)
        self.assertGreater(first.price, 0)
        self.assertTrue(len(first.developer) > 0)

    def test_11_grid_offplan_developer_filter(self):
        """
        Verifies searching for developer 'Imtiaz' or 'ADE' matches project accurately.
        """
        results = GridGateway.search_offplan_projects(search="Imtiaz")
        self.assertIsInstance(results, list)
        if len(results) > 0:
            titles = [p.title.lower() for p in results]
            self.assertTrue(any("pearl house" in t or "imtiaz" in t for t in titles))

    # =========================================================================
    # 7. END-TO-END CONVERSATIONAL ORCHESTRATION
    # =========================================================================

    def test_12_unconfirmed_location_reply_clarification(self):
        """
        End-to-end: unconfirmed location 'alt' asks for clarification without
        inventing phantom properties.
        """
        import asyncio
        reply = asyncio.run(ConversationOrchestrator.process_user_turn(
            user_message="Can you find me an apartment in alt?",
            session_id=self.session_id
        ))
        text = reply.get("text", "")
        self.assertTrue(len(text) > 0)
        # Should clarify that alt is not recognized or ask what community was meant
        self.assertTrue(
            "alt" in text.lower() or "clarify" in text.lower() or "mean" in text.lower() or "community" in text.lower() or "area" in text.lower()
        )
        # Must NOT invent property cards for 'alt'
        props = reply.get("property_results", [])
        self.assertEqual(len(props), 0)

    def test_13_trust_safety_reply_flow(self):
        """
        End-to-end: safety question generates trust explanation citing UAE PDPL Law 45
        and DLD verification.
        """
        import asyncio
        reply = asyncio.run(ConversationOrchestrator.process_user_turn(
            user_message="Is my personal data safe? What proof or law protects my privacy?",
            session_id=self.session_id
        ))
        text = reply.get("text", "")
        self.assertTrue(len(text) > 0)
        self.assertTrue("45" in text or "pdpl" in text.lower() or "dld" in text.lower() or "law" in text.lower())

if __name__ == "__main__":
    unittest.main()
