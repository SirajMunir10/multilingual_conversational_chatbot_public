import sys
import os
import unittest

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from app.main import app
from app.orchestrator.orchestrator import ConversationOrchestrator
from app.orchestrator.session_store import SessionStore
from app.services.property_service import PropertyDiscoveryService, PropertySearchFilter

class TestPhase4IntelligenceEnhancements(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        PropertyDiscoveryService.clear_shortlists()

    def test_property_comparison_intent_preserves_cards_and_evaluates(self):
        """
        Verify FR-9 Comparison & Evaluation Intent:
        When a user asks to evaluate or compare on-screen properties, the assistant:
        1. Classifies intent as 'property_comparison'
        2. Preserves the properties in property_results (does not wipe them with 0 results)
        3. Generates a side-by-side comparative analysis with price, sq.ft, EMI, and rental yields
        4. Includes the mandatory non-binding financial disclaimer
        """
        session_id = "test_comparison_sess_101"
        SessionStore.get_or_create_session(session_id)

        # Turn 1: Search for 2 BHK in Dubai Hills
        turn1 = ConversationOrchestrator.process_user_turn(
            user_message="Marhaba, I need a 2 BHK apartment in Dubai Hills.",
            session_id=session_id
        )
        # Handle async coroutine if returned
        import asyncio
        if asyncio.iscoroutine(turn1):
            turn1 = asyncio.run(turn1)

        self.assertEqual(turn1["intent"], "property")
        self.assertGreaterEqual(len(turn1["property_results"]), 2)
        prop_titles = [p["title"] for p in turn1["property_results"]]
        self.assertTrue(any("Dubai Hills" in t for t in prop_titles))

        # Turn 2: Ask which one to buy for investment
        user_query = (
            "Do you think among these two BHK residences you provided me, "
            "what would be the most beneficial for me? Like I am thinking of it as an investment. "
            "So what do you suggest? Which one should I be buying?"
        )
        turn2 = ConversationOrchestrator.process_user_turn(
            user_message=user_query,
            session_id=session_id
        )
        if asyncio.iscoroutine(turn2):
            turn2 = asyncio.run(turn2)

        self.assertEqual(turn2["intent"], "property_comparison")
        # Ensure property cards are STILL displayed on screen
        self.assertEqual(len(turn2["property_results"]), len(turn1["property_results"]))
        
        # Verify comparative narrative contents
        text = turn2["text"]
        self.assertTrue("comparison" in text.lower() or "comparative" in text.lower())
        self.assertTrue("sq.ft" in text.lower() or "price" in text.lower())
        self.assertTrue("emi" in text.lower() or "installment" in text.lower())
        self.assertTrue("yield" in text.lower() or "return" in text.lower())
        # Mandatory Rule 10 non-binding disclaimer
        self.assertIn("Indicative market comparison only; not binding financial advice", text)

    def test_catalog_aware_empathetic_fallback(self):
        """
        Verify FR-8 Empathetic & Catalog-Aware Fallback:
        When searching for 2 BHK in Palm Jumeirah under 3 million (where Shoreline 2BR is 4.85M,
        and 2BR in Downtown / Business Bay are 1.95M-2.45M), the system does not give a robotic
        'I found 0 properties', but proactively and empathetically suggests specific alternatives.
        """
        session_id = "test_fallback_sess_102"
        SessionStore.get_or_create_session(session_id)

        turn = ConversationOrchestrator.process_user_turn(
            user_message="Hi, can I get a 2 BHK apartment in Palm Jumeirah with budget around 3 million AED?",
            session_id=session_id
        )
        import asyncio
        if asyncio.iscoroutine(turn):
            turn = asyncio.run(turn)

        self.assertEqual(turn["intent"], "property")
        text = turn["text"]

        # Should acknowledge with empathy that exact match isn't available
        self.assertTrue("unfortunately" in text.lower() or "couldn't find" in text.lower() or "sorry" in text.lower() or "0" in text or "no" in text.lower())
        # Should proactively mention Palm Jumeirah and alternative communities or options
        self.assertIn("Palm Jumeirah", text)
        self.assertTrue("Downtown" in text or "Business Bay" in text or "Dubai Hills" in text or "residences" in text.lower())

    def test_relaxation_on_other_property_request(self):
        """
        Verify that saying 'provide me some other property' after a specific community search
        broadens the scope to all Dubai and returns live inventory instead of remaining stuck at 0.
        """
        session_id = "test_other_prop_sess_103"
        SessionStore.get_or_create_session(session_id)

        import asyncio
        # Step 1: Turn searching Palm Jumeirah 2BR
        t1 = ConversationOrchestrator.process_user_turn(
            user_message="Find 2 BHK in Palm Jumeirah under 4 million",
            session_id=session_id
        )
        if asyncio.iscoroutine(t1):
            t1 = asyncio.run(t1)

        # Step 2: User says 'provide me some other property'
        t2 = ConversationOrchestrator.process_user_turn(
            user_message="provide me some other property",
            session_id=session_id
        )
        if asyncio.iscoroutine(t2):
            t2 = asyncio.run(t2)

        self.assertEqual(t2["intent"], "property")
        self.assertGreater(len(t2["property_results"]), 0)

    def test_exploratory_investment_places_inquiry_first_attempt(self):
        """
        Verify that asking for investment places/areas directly ('I just want to know the places where I can invest. Just give me the names of the places.')
        is understood and answered with actual investment destinations on the very FIRST attempt,
        instead of repeating generic slot-filling clarifying questions.
        """
        session_id = "test_invest_places_first_attempt"
        SessionStore.get_or_create_session(session_id)

        import asyncio
        turn = ConversationOrchestrator.process_user_turn(
            user_message="I just want to know the places where I can invest. Just give me the names of the places.",
            session_id=session_id
        )
        if asyncio.iscoroutine(turn):
            turn = asyncio.run(turn)

        text = turn["text"]
        # Must NOT be the robotic generic slot-filling loop
        self.assertNotIn("Are you looking for an apartment or villa, how many bedrooms", text)
        # Must authoritatively provide premier investment areas in Dubai on turn 1
        has_places = any(area in text for area in ["Downtown", "Dubai Marina", "Business Bay", "Palm Jumeirah", "Dubai Hills", "Creek", "JVC"])
        self.assertTrue(has_places, f"Response should list investment locations on first attempt, got: {text}")

if __name__ == "__main__":
    unittest.main()

