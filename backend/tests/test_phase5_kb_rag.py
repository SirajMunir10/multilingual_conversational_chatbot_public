import unittest
import os
import sys
import asyncio

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from app.main import app
from app.services.rag_service import RAGService
from app.orchestrator.orchestrator import ConversationOrchestrator
from app.orchestrator.session_store import SessionStore

class TestPhase5KnowledgeBaseAndRAG(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        RAGService.load_kb(force_reload=True)
        cls.client = TestClient(app)

    def test_01_master_kb_integrity(self):
        """Validates that all 48 articles and 28 glossary terms are loaded with correct activation boundaries."""
        kb = RAGService._kb_data
        self.assertIsNotNone(kb, "KB data must be loaded")
        self.assertEqual(kb["metadata"]["total_articles"], 48, f"Expected 48 articles, got {kb['metadata']['total_articles']}")
        self.assertEqual(kb["metadata"]["total_glossary_terms"], 28, f"Expected 28 glossary terms, got {kb['metadata']['total_glossary_terms']}")

        # Verify status distributions
        articles = kb["articles"]
        active = [a for a in articles if a["status"] == "ACTIVE"]
        partial = [a for a in articles if a["status"] == "PARTIALLY_ACTIVE"]
        excluded = [a for a in articles if a["status"] == "EXCLUDED"]

        self.assertEqual(len(active), 40, f"Expected 40 active articles, got {len(active)}")
        self.assertEqual(len(partial), 4, f"Expected 4 partially active articles, got {len(partial)}")
        self.assertEqual(len(excluded), 4, f"Expected 4 excluded articles, got {len(excluded)}")

        # Verify excluded articles are strictly 25, 26, 27, 28
        excluded_ids = sorted([a["article_number"] for a in excluded])
        self.assertEqual(excluded_ids, [25, 26, 27, 28], f"Excluded IDs must be [25, 26, 27, 28], got {excluded_ids}")

        # Verify partial articles are strictly 9, 10, 11, 12
        partial_ids = sorted([a["article_number"] for a in partial])
        self.assertEqual(partial_ids, [9, 10, 11, 12], f"Partial IDs must be [9, 10, 11, 12], got {partial_ids}")

    def test_02_active_article_retrieval_buying_fees(self):
        """Article 2 (buying_fees_breakdown) retrieval test."""
        res = RAGService.retrieve_kb("What are the fees for buying property in Dubai?")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["article_number"], 2)
        self.assertEqual(res["intent_name"], "buying_fees_breakdown")
        self.assertTrue("4% of purchase price" in res["detail"] or "DLD Transfer Fee" in res["detail"])
        self.assertGreaterEqual(res["confidence"], 0.70)

    def test_03_active_article_retrieval_expat_eligibility(self):
        """Article 1 (expat_buy_property_eligibility) retrieval test."""
        res = RAGService.retrieve_kb("Can foreigners buy property in the UAE?")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["article_number"], 1)
        self.assertEqual(res["intent_name"], "expat_buy_property_eligibility")
        self.assertTrue("freehold" in res["short_answer"].lower())

    def test_04_active_article_retrieval_golden_visa_with_disclaimer(self):
        """Article 16 (golden_visa_property_eligibility) retrieval test with mandatory legal disclaimer."""
        res = RAGService.retrieve_kb("Can I get a UAE Golden Visa with an AED 2 million property investment?")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["article_number"], 16)
        self.assertEqual(res["intent_name"], "golden_visa_property_eligibility")
        self.assertTrue("2,000,000" in res["detail"])
        self.assertNotEqual(res["disclaimer"], "", "Golden visa must include statutory legal disclaimer")
        self.assertTrue("licensed property professional" in res["disclaimer"])

    def test_05_active_article_retrieval_area_guides(self):
        """Domain 7 Area Guides retrieval test."""
        res_palm = RAGService.retrieve_kb("Tell me about Palm Jumeirah luxury property prices")
        self.assertEqual(res_palm["status"], "success")
        self.assertEqual(res_palm["article_number"], 17)
        self.assertTrue("Palm Jumeirah" in res_palm["title"])

        res_jvc = RAGService.retrieve_kb("What is the rental yield and price per sqft in JVC?")
        self.assertEqual(res_jvc["status"], "success")
        self.assertEqual(res_jvc["article_number"], 20)
        self.assertTrue("JVC" in res_jvc["title"])

        res_auh = RAGService.retrieve_kb("Is Al Reem Island in Abu Dhabi a good investment?")
        self.assertEqual(res_auh["status"], "success")
        self.assertEqual(res_auh["article_number"], 30)
        self.assertTrue("Al Reem Island" in res_auh["title"])

    def test_06_active_article_retrieval_tenant_journey_and_trust(self):
        """Articles 51-53 (Tenant Journey, Eviction Rights, XOTO Verification) retrieval test."""
        res_tenant = RAGService.retrieve_kb("What is the step by step tenant rental process in UAE?")
        self.assertEqual(res_tenant["status"], "success")
        self.assertEqual(res_tenant["article_number"], 51)
        self.assertEqual(res_tenant["intent_name"], "tenant_rental_journey")

        res_eviction = RAGService.retrieve_kb("Can my landlord evict me in Dubai?")
        self.assertEqual(res_eviction["status"], "success")
        self.assertEqual(res_eviction["article_number"], 52)
        self.assertTrue("12 months" in res_eviction["detail"] or "12 months" in res_eviction["short_answer"])
        self.assertNotEqual(res_eviction["disclaimer"], "", "Eviction rights must include legal disclaimer")

        res_trust = RAGService.retrieve_kb("How does XOTO verify listings and protect buyers from fraud?")
        self.assertEqual(res_trust["status"], "success")
        self.assertEqual(res_trust["article_number"], 53)
        self.assertTrue("title deed" in res_trust["detail"].lower())

    def test_07_glossary_definitions(self):
        """Domain 12 Glossary lookup test."""
        res_dld = RAGService.retrieve_kb("What is DLD?")
        self.assertEqual(res_dld["status"], "success")
        self.assertTrue("Dubai Land Department" in (res_dld.get("definition") or res_dld.get("detail", "")))

        res_ejari = RAGService.retrieve_kb("What is Ejari?")
        self.assertEqual(res_ejari["status"], "success")
        self.assertTrue("Ejari" in res_ejari["title"] or "Ejari" in res_ejari.get("term", ""))

    def test_08_partially_active_articles_educational_allowed(self):
        """Articles 9-12 Educational queries must be successfully retrieved."""
        res_islamic = RAGService.retrieve_kb("What is the difference between Islamic and conventional mortgage?")
        self.assertEqual(res_islamic["status"], "success")
        self.assertEqual(res_islamic["article_number"], 12)
        self.assertTrue("Ijara" in res_islamic["detail"] or "Murabaha" in res_islamic["detail"])

        res_proc = RAGService.retrieve_kb("What is the mortgage application process steps in UAE?")
        self.assertEqual(res_proc["status"], "success")
        self.assertEqual(res_proc["article_number"], 11)
        self.assertTrue("pre-approval" in res_proc["detail"].lower())

    def test_09_partially_active_articles_conventional_calculations_blocked(self):
        """Articles 9-12 Conventional calculation / loan application requests must be blocked from calculation flows."""
        blocked_query = "Calculate my mortgage with conventional interest rate and start my loan application"
        res = RAGService.retrieve_kb(blocked_query)
        self.assertEqual(res["status"], "scope_restricted")
        self.assertTrue(res.get("is_educational_only"))
        self.assertTrue("outside our current conversational scope" in res["message"])

    def test_10_excluded_articles_never_retrieved(self):
        """Articles 25-28 (Calculators) are EXCLUDED and must never be retrieved as active KB articles."""
        calculator_queries = [
            "Affordability Calculator formula",
            "calculator_mortgage_emi monthly emi factor",
            "Rent vs Buy Calculator buy scenario",
            "Remortgage Refinance Calculator"
        ]
        for cq in calculator_queries:
            res = RAGService.retrieve_kb(cq)
            art_num = res.get("article_number")
            self.assertNotIn(art_num, [25, 26, 27, 28], f"Query '{cq}' leaked excluded article {art_num}")

    def test_11_low_confidence_fallback(self):
        """Queries with no matching knowledge return Domain 11.4 Fallback."""
        res = RAGService.retrieve_kb("How to bake chocolate cake in outer space")
        self.assertEqual(res["status"], "fallback")
        self.assertEqual(res["intent_name"], "fallback_unrecognised_intent")
        self.assertTrue("outside of my knowledge base" in res["message"])
        self.assertTrue(res.get("handoff_offered"))

    def test_12_orchestrator_integration_grounded_answer(self):
        """Validates that ConversationOrchestrator grounds knowledge inquiries via RAG."""
        session_id = "test-phase5-grounding"
        response = self.client.post("/api/chat/message", json={
            "session_id": session_id,
            "message": "What fees do I pay when buying property in Dubai?"
        })
        self.assertEqual(response.status_code, 200)
        res = response.json()
        self.assertIsNotNone(res)
        self.assertTrue("4%" in res["text"] or "DLD" in res["text"] or "Trustee" in res["text"])
        tool_calls = res.get("tool_calls", [])
        if tool_calls:
            self.assertTrue(any(tc["function"] == "retrieve_kb" for tc in tool_calls))

    def test_13_gateway_api_endpoint(self):
        """Validates PRD FN-6 API endpoint GET /api/gateways/kb?query=..."""
        response = self.client.get("/api/gateways/kb?query=What are the fees for buying property in Dubai?")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["article_number"], 2)

    def test_14_phase4_regression_property_search_still_functional(self):
        """Regression test ensuring Phase 4 property discovery remains intact."""
        session_id = "test-phase5-regression"
        response = self.client.post("/api/chat/message", json={
            "session_id": session_id,
            "message": "Show me 1 BHK apartments in Dubai Marina"
        })
        self.assertEqual(response.status_code, 200)
        res = response.json()
        self.assertIsNotNone(res)
        props = res.get("property_results", [])
        self.assertTrue(any("Dubai Marina" in (p.get("community") or p.get("location") or p.get("title", "")) for p in props))

if __name__ == "__main__":
    unittest.main()
