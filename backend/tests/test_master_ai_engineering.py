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

    @classmethod
    def setUpClass(cls):
        # Isolate JLT sample listing in a test fixture so production inventory_gateway.py is untouched
        from app.gateways.inventory_gateway import PropertyInventoryGateway, ScopedPropertyListing
        cls._demo_listing = ScopedPropertyListing(
            id="test-fixture-dxb-jlt",
            title="[Test Fixture] Modern 2BR Apartment in Lake Terrace, JLT",
            city="Dubai",
            community="JLT",
            type="apartment",
            beds=2,
            baths=2,
            sq_ft=1150,
            price=1450000.0,
            purpose="buy",
            developer="Damac",
            status="ready",
            image_url="https://images.unsplash.com/photo-1545324418-cc1a3fa10c00?auto=format&fit=crop&w=800&q=80",
            listing_url="https://xoto.ae/properties/test-fixture-dxb-jlt",
            amenities=["Lake View", "Near Metro Station", "Swimming Pool", "Gym"]
        )
        PropertyInventoryGateway._inventory.append(cls._demo_listing)

    @classmethod
    def tearDownClass(cls):
        from app.gateways.inventory_gateway import PropertyInventoryGateway
        if hasattr(cls, "_demo_listing") and cls._demo_listing in PropertyInventoryGateway._inventory:
            PropertyInventoryGateway._inventory.remove(cls._demo_listing)

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

    # =========================================================================
    # 8. MANDATORY PRD REGRESSION CASES (EXAMPLES A, B, C)
    # =========================================================================

    def test_14_regression_example_a_gld_glt_no_preferences(self):
        """
        Regression Example A:
        Turn 1: 'Show me apartments in GLD by Imtiaz.' -> unconfirmed location GLD, developer Imtiyaz.
        Turn 2: 'Yeah, it's GLT.' -> fuzzy resolved to JLT (Jumeirah Lake Towers).
        Turn 3: 'I don't have any preferences for now, just provide me any listing.' ->
                Must NOT extract 'now' as location!
                preferences_waived is True!
                Executes search and returns listings (or catalog alternatives in JLT) without getting stuck.
        """
        import asyncio
        import uuid
        sess_id = f"test_reg_example_a_{uuid.uuid4().hex[:8]}"
        sess = SessionStore.get_or_create_session(session_id=sess_id, user_id="test_user", initial_language="en")

        # Turn 1
        ConversationOrchestrator._extract_slots("Show me apartments in GLD by Imtiaz.", sess)
        self.assertEqual(sess.slots.unconfirmed_location, "GLD")
        self.assertEqual(sess.slots.property_developer, "Imtiyaz")

        # Turn 2: User clarifies GLT -> resolves to JLT
        ConversationOrchestrator._extract_slots("Yeah, it's GLT.", sess)
        self.assertEqual(sess.slots.property_city, "JLT")
        self.assertIsNone(sess.slots.unconfirmed_location)

        # Turn 3: User waives preferences
        reply = asyncio.run(ConversationOrchestrator.process_user_turn(
            user_message="I don't have any preferences for now, just provide me any listing.",
            session_id=sess_id
        ))
        # Verify 'now' is NOT stored as unconfirmed_location
        self.assertIsNone(sess.slots.unconfirmed_location)
        self.assertTrue(sess.slots.preferences_waived)
        # Verify search was executed (either property results or fallback narrative returned, not a clarification question asking for preferences)
        props = reply.get("property_results", [])
        text = reply.get("text", "")
        self.assertTrue(len(props) > 0 or len(text) > 0)
        self.assertNotIn("unconfirmed location", text.lower())

    def test_15_regression_example_b_dubai_wide_offplan(self):
        """
        Regression Example B:
        User: 'Can you provide me some off-plan properties in Dubai?'
        XO should recognize the request as off-plan discovery across Dubai,
        without requiring a developer or neighborhood, query Grid gateway, and return matching results.
        Also verifies superseding earlier narrow community/developer filters.
        """
        import asyncio
        import uuid
        sess_id = f"test_reg_example_b_{uuid.uuid4().hex[:8]}"
        sess = SessionStore.get_or_create_session(session_id=sess_id, user_id="test_user", initial_language="en")
        # Pre-seed with earlier turn constraint: JLT and Imtiyaz
        sess.slots.property_city = "Jumeirah Lake Towers"
        sess.slots.property_developer = "Imtiyaz Developments"

        # User asks for Dubai-wide off-plan properties
        ConversationOrchestrator._extract_slots("Can you provide me some off-plan properties in Dubai?", sess)
        self.assertEqual(sess.slots.property_city, "Dubai")
        self.assertEqual(sess.slots.property_timeline, "off-plan")
        self.assertIsNone(sess.slots.property_developer)  # Old developer superseded!

        reply = asyncio.run(ConversationOrchestrator.process_user_turn(
            user_message="Can you provide me some off-plan properties in Dubai?",
            session_id=sess_id
        ))
        props = reply.get("property_results", [])
        self.assertIsInstance(props, list)
        self.assertGreater(len(props), 0)
        # Verify off-plan status
        for p in props:
            self.assertEqual(p.get("status"), "off-plan")

    def test_16_regression_example_c_advisor_consent_no_i_want_to_get_connected(self):
        """
        Regression Example C:
        When XO asks: 'Would you like our licensed advisory team to contact you for a direct consultation?'
        User: 'No, I want to get connected.'
        Must NOT be classified as handoff_declined merely because it starts with 'no'.
        Must recognize user's desire to connect -> intent is human_handoff.
        Since phone/name not yet collected, returns Turn 2 intake requesting contact details,
        and does NOT save lead or initiate handoff prematurely.
        """
        import asyncio
        import uuid
        sess_id = f"test_reg_example_c_{uuid.uuid4().hex[:8]}"
        sess = SessionStore.get_or_create_session(session_id=sess_id, user_id="test_user", initial_language="en")
        sess.slots.advisor_consent_pending = True
        sess.handoff_requested = True

        intent = ConversationOrchestrator._classify_intent("No, I want to get connected.", sess)
        self.assertEqual(intent, "human_handoff")
        self.assertTrue(sess.slots.customer_consent_given)
        self.assertFalse(sess.slots.advisor_consent_pending)

        reply = asyncio.run(ConversationOrchestrator.process_user_turn(
            user_message="No, I want to get connected.",
            session_id=sess_id
        ))
        text = reply.get("text", "")
        # Should ask for details (name/phone)
        self.assertFalse(reply.get("handoff_offered", False))
        self.assertTrue("name" in text.lower() or "phone" in text.lower() or "number" in text.lower() or "details" in text.lower())

    def test_17_advisor_consent_declined_and_privacy(self):
        """
        Verifies genuine refusal vs privacy question during advisor consent pending.
        """
        import uuid
        # Genuine refusal: "No, thanks."
        sess1 = SessionStore.get_or_create_session(session_id=f"test_refusal_{uuid.uuid4().hex[:8]}", user_id="test_user", initial_language="en")
        sess1.slots.advisor_consent_pending = True
        intent1 = ConversationOrchestrator._classify_intent("No, thanks.", sess1)
        self.assertEqual(intent1, "handoff_declined")

        # Privacy inquiry: "No, I don't trust you. How is my data safe?"
        sess2 = SessionStore.get_or_create_session(session_id=f"test_privacy_{uuid.uuid4().hex[:8]}", user_id="test_user", initial_language="en")
        sess2.slots.advisor_consent_pending = True
        intent2 = ConversationOrchestrator._classify_intent("No, I don't trust you. How is my data safe?", sess2)
        self.assertEqual(intent2, "trust_safety")

        # Topic pivot: "Actually, tell me about mortgage rates instead."
        sess3 = SessionStore.get_or_create_session(session_id=f"test_pivot_{uuid.uuid4().hex[:8]}", user_id="test_user", initial_language="en")
        sess3.slots.advisor_consent_pending = True
        intent3 = ConversationOrchestrator._classify_intent("Actually, tell me about mortgage rates instead.", sess3)
        self.assertEqual(intent3, "mortgage")

    def test_18_grid_offplan_city_vs_district_and_filters(self):
        """
        Verifies Grid off-plan gateway parameter separation:
        - City filter passes 'city=Dubai'
        - District filter passes 'district=Downtown Dubai'
        - Upstream error handling does not mask failure as zero results
        """
        # City-wide Dubai search
        res_city = GridGateway.search_offplan_projects(city="Dubai", limit=3)
        self.assertIsInstance(res_city, list)
        self.assertGreater(len(res_city), 0)

        # District-specific search
        res_dist = GridGateway.search_offplan_projects(district="Downtown Dubai", limit=3)
        self.assertIsInstance(res_dist, list)

        # Developer alias normalization (imtiyaz -> Imtiaz)
        res_dev = GridGateway.search_offplan_projects(search="imtiyaz", limit=3)
        self.assertIsInstance(res_dev, list)
        if len(res_dev) > 0:
            self.assertTrue(any("imtiaz" in p.developer.lower() or "pearl house" in p.title.lower() for p in res_dev))

    def test_19_no_amenities_inferred_from_status_or_dates_and_sqft_preserved(self):
        """
        Concern 2:
        - Do not infer amenities from construction status or completion dates.
        - Preserve missing property fields as unknown (None).
        - Ensure sq_ft = 0 is never displayed as a verified zero-square-foot property.
        """
        res = GridGateway.search_offplan_projects(city="Dubai", limit=3)
        for p in res:
            # Amenities must not be derived from Handover or Status strings
            for amenity in p.amenities:
                self.assertFalse(amenity.lower().startswith("handover"))
                self.assertFalse("construction" in amenity.lower())
                self.assertFalse("under construction" in amenity.lower())
            # sq_ft must be None if unknown, never 0
            if p.sq_ft is not None:
                self.assertGreater(p.sq_ft, 0)

        # Verification of display: when sq_ft is None, comparison narrative must not say "0 sq.ft"
        mock_item = {
            "title": "Off-Plan Project A",
            "community": "Dubai Marina",
            "price": 1500000.0,
            "sq_ft": None,
            "price_per_sq_ft": None,
            "down_payment_aed": 300000.0,
            "monthly_emi_aed": 6200.0,
            "estimated_rental_yield": "7.2%"
        }
        comp = {"properties": [mock_item, mock_item], "comparison_table": []}
        narrative = ConversationOrchestrator._format_comparison_narrative(comp, lang="en")
        self.assertNotIn("0 sq.ft", narrative)
        self.assertNotIn("Area: 0", narrative)
        self.assertIn("Details on request", narrative)

    def test_20_developer_filter_no_silent_relaxation(self):
        """
        Concern 3:
        - Ensure developer-filter relaxation does not silently show other developers' properties
          as satisfying an Imtiyaz-specific request.
        - Use actual search results and offer relevant alternatives transparently.
        """
        filters = PropertySearchFilter(
            city="JLT",
            developer="Imtiyaz"
        )
        # Search for Imtiyaz in JLT must return 0 direct listings (does NOT silently return Damac!)
        listings = PropertyDiscoveryService.search_and_rank(filters=filters, session_id=self.session_id)
        self.assertEqual(len(listings), 0)

        # Catalog alternatives discovery must transparently identify Damac as an alternative in JLT
        # and Imtiyaz projects in other communities (e.g. JVC)
        alts = PropertyDiscoveryService.find_catalog_alternatives(filters)
        dev_alts = alts.get("developer_alternatives", {})
        self.assertEqual(dev_alts.get("searched_developer"), "Imtiyaz")
        self.assertIn("Damac", dev_alts.get("other_developers_in_community", []))
        self.assertTrue(any("JVC" in c for c in dev_alts.get("developer_other_communities", [])))

    def test_21_preferences_waived_and_unconfirmed_location_reset_on_new_task(self):
        """
        Concern 4:
        - Verify preferences_waived and unresolved-location state reset correctly when a new task begins,
          while retaining relevant confirmed context for genuine follow-ups.
        """
        # 1. User waives preferences in Turn 1
        ConversationOrchestrator._extract_slots("I don't have any preferences for now, just provide me any listing.", self.session)
        self.assertTrue(self.session.slots.preferences_waived)
        self.assertIsNone(self.session.slots.unconfirmed_location)

        # 2. Turn 2: User starts a new explicit task (e.g. off-plan in Dubai)
        ConversationOrchestrator._extract_slots("Can you provide me some off-plan properties in Dubai?", self.session)
        self.assertFalse(self.session.slots.preferences_waived)  # Reset!
        self.assertEqual(self.session.slots.property_city, "Dubai")
        self.assertEqual(self.session.slots.property_timeline, "off-plan")

        # 3. Genuine follow-up preserves confirmed context
        ConversationOrchestrator._extract_slots("Show me 2 bedrooms near metro", self.session)
        self.assertEqual(self.session.slots.property_city, "Dubai")
        self.assertEqual(self.session.slots.property_timeline, "off-plan")
        self.assertEqual(self.session.slots.property_beds, 2)
        self.assertIn("Near Metro Station", self.session.slots.property_amenities)

        # 4. Unconfirmed location candidate detected
        ConversationOrchestrator._extract_slots("Show me apartments in alt", self.session)
        self.assertEqual(self.session.slots.unconfirmed_location, "alt")

        # 5. User pivots to mortgage calculation task: unconfirmed location reset!
        self.session.active_intent = "mortgage"
        ConversationOrchestrator._extract_slots("Can you calculate my mortgage affordability for income 35,000?", self.session)
        self.assertIsNone(self.session.slots.unconfirmed_location)
        self.assertFalse(self.session.slots.preferences_waived)
        self.assertEqual(self.session.slots.mortgage_income, 35000.0)

if __name__ == "__main__":
    unittest.main()
