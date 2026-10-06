import sys
import os
import unittest

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from app.main import app
from app.gateways.inventory_gateway import PropertyInventoryGateway, PropertyListing
from app.services.property_service import PropertyDiscoveryService, PropertySearchFilter
from app.gateways.grid_gateway import GridGateway

class TestPhase4PropertyDiscoveryAndRecommendation(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        PropertyDiscoveryService.clear_shortlists()

    def test_live_inventory_gateway_count_and_types(self):
        """Verify the inventory gateway holds diverse luxury & investment properties across UAE."""
        all_props = PropertyInventoryGateway.get_all_properties()
        self.assertGreaterEqual(len(all_props), 12)
        
        # Verify communities represented
        communities = {p.community for p in all_props}
        self.assertIn("Downtown Dubai", communities)
        self.assertIn("Palm Jumeirah", communities)
        self.assertIn("Dubai Hills Estate", communities)
        self.assertIn("Business Bay", communities)
        self.assertIn("Yas Island", communities)

        # Verify property types
        types = {p.type for p in all_props}
        self.assertIn("apartment", types)
        self.assertIn("villa", types)
        self.assertIn("townhouse", types)
        self.assertIn("penthouse", types)

    def test_property_search_with_filters(self):
        """FR-7 & FR-8: Test filtering by bedrooms, budget, and location."""
        filt = PropertySearchFilter(
            location="Downtown",
            beds=2,
            budget_max=3000000.0,
            purpose="buy"
        )
        results = PropertyDiscoveryService.search_and_rank(filt)
        self.assertGreaterEqual(len(results), 1)
        
        prop = results[0]
        self.assertEqual(prop["beds"], 2)
        self.assertLessEqual(prop["price"], 3000000.0)
        self.assertIn("Downtown", prop["community"])

    def test_mortgage_cross_sell_math_enrichment(self):
        """
        FR-11: Verify bidirectional property/mortgage cross-sell calculations.
        For a property <= 5M AED (e.g. 2,450,000 AED):
        Down payment = 20% = 490,000 AED
        Loan amount = 80% = 1,960,000 AED
        """
        filt = PropertySearchFilter(location="Downtown Dubai", beds=2)
        results = PropertyDiscoveryService.search_and_rank(filt)
        self.assertGreaterEqual(len(results), 1)
        
        prop = results[0]
        self.assertIn("mortgage_cross_sell", prop)
        cross_sell = prop["mortgage_cross_sell"]
        
        expected_down_payment = round(prop["price"] * 0.20, 2)
        self.assertEqual(cross_sell["down_payment_aed"], expected_down_payment)
        self.assertEqual(cross_sell["loan_amount_aed"], round(prop["price"] - expected_down_payment, 2))
        self.assertGreater(cross_sell["estimated_monthly_emi_aed"], 0)
        self.assertIn("Dubai Islamic Bank", cross_sell["recommended_product"]["bank_name"])
        self.assertEqual(cross_sell["disclaimer"], "estimate only, subject to lender approval")

    def test_mortgage_cross_sell_luxury_over_5m(self):
        """
        FR-11: For luxury villas over 5M AED (e.g. 14,500,000 AED):
        Expat down payment rule specifies 25% down payment.
        """
        prop_villa = PropertyInventoryGateway.get_property_by_id("prop-dxb-005")
        self.assertIsNotNone(prop_villa)
        self.assertEqual(prop_villa.price, 14500000.0)

        cross_sell = PropertyDiscoveryService.compute_mortgage_cross_sell(prop_villa)
        expected_down_payment = round(14500000.0 * 0.25, 2)
        self.assertEqual(cross_sell["down_payment_aed"], expected_down_payment)
        self.assertEqual(cross_sell["loan_amount_aed"], 14500000.0 - expected_down_payment)
        self.assertGreater(cross_sell["estimated_monthly_emi_aed"], 40000)

    def test_conversational_refinement_cheaper(self):
        """FR-9: Test relative conversational refinement: 'cheaper'."""
        initial_filter = PropertySearchFilter(location="Dubai", budget_max=3000000.0)
        refined_filter = PropertyDiscoveryService.refine_search(initial_filter, "Can you show me something cheaper?")
        
        self.assertLess(refined_filter.budget_max, 3000000.0)
        results = PropertyDiscoveryService.search_and_rank(refined_filter)
        for p in results:
            self.assertLessEqual(p["price"], refined_filter.budget_max)

    def test_conversational_refinement_more_bedrooms(self):
        """FR-9: Test relative conversational refinement: 'need more bedrooms'."""
        initial_filter = PropertySearchFilter(beds=2)
        refined_filter = PropertyDiscoveryService.refine_search(initial_filter, "I need more bedrooms for my family")
        self.assertEqual(refined_filter.beds, 3)

    def test_conversational_refinement_closer_to_downtown(self):
        """FR-9: Test relative conversational refinement: 'closer to downtown'."""
        initial_filter = PropertySearchFilter(location="JVC")
        refined_filter = PropertyDiscoveryService.refine_search(initial_filter, "Something closer to downtown")
        self.assertEqual(refined_filter.location, "Downtown Dubai")

    def test_conversational_refinement_similar_to_property(self):
        """FR-9: Test 'show more like #1' / similar properties."""
        similar = PropertyInventoryGateway.get_similar_properties("prop-dxb-001", limit=3)
        self.assertGreaterEqual(len(similar), 1)
        for s in similar:
            self.assertNotEqual(s.id, "prop-dxb-001")
            # Should have similar specs (apartment / 2 beds or nearby community)
            self.assertTrue(s.beds in [1, 2, 3] or s.community in ["Downtown Dubai", "Business Bay"])

    def test_anonymous_shortlist_and_lead_capture(self):
        """FR-10: Test saving/shortlisting properties from chat and capturing anonymous leads."""
        session_id = "test_user_session_42"
        prop_id = "prop-dxb-001"

        # 1. Anonymous user shortlists property
        result = PropertyDiscoveryService.shortlist_property(prop_id, session_id=session_id)
        self.assertTrue(result["is_shortlisted"])
        self.assertTrue(result["requires_lead_capture"])

        # 2. Check active shortlist
        shortlisted = PropertyDiscoveryService.get_user_shortlist(session_id=session_id)
        self.assertEqual(len(shortlisted), 1)
        self.assertEqual(shortlisted[0]["id"], prop_id)

        # 3. Anonymous user submits lead capture details
        lead_res = PropertyDiscoveryService.capture_anonymous_lead(
            property_id=prop_id,
            full_name="Sarah Al-Mansoor",
            email="sarah.mansoor@example.com",
            phone="+971501234567",
            session_id=session_id
        )
        self.assertEqual(lead_res["status"], "success")
        self.assertIn("lead_id", lead_res)
        self.assertEqual(lead_res["property_id"], prop_id)

        # 4. Verify lead exists in GridGateway CRM
        lead = GridGateway.get_lead(lead_res["lead_id"])
        self.assertIsNotNone(lead)
        self.assertEqual(lead["contact_name"], "Sarah Al-Mansoor")
        self.assertIn("prop-dxb-001", lead["notes"])

        # 5. Toggle off shortlist
        result_untoggle = PropertyDiscoveryService.shortlist_property(prop_id, session_id=session_id)
        self.assertFalse(result_untoggle["is_shortlisted"])
        self.assertEqual(len(PropertyDiscoveryService.get_user_shortlist(session_id=session_id)), 0)

    def test_fastapi_properties_endpoints(self):
        """Verify REST API router endpoints for search, shortlist, and lead capture."""
        # 1. Search
        res = self.client.get("/api/properties/search?beds=2&budget_max=2500000")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("properties", data)
        self.assertGreater(data["count"], 0)

        # 2. Get by ID
        res_id = self.client.get("/api/properties/prop-dxb-001")
        self.assertEqual(res_id.status_code, 200)
        self.assertEqual(res_id.json()["id"], "prop-dxb-001")

        # 3. Similar
        res_sim = self.client.get("/api/properties/prop-dxb-001/similar")
        self.assertEqual(res_sim.status_code, 200)
        self.assertIn("similar_properties", res_sim.json())

        # 4. Shortlist endpoint
        res_shortlist = self.client.post("/api/properties/prop-dxb-002/shortlist", json={
            "session_id": "api_test_session"
        })
        self.assertEqual(res_shortlist.status_code, 200)
        self.assertTrue(res_shortlist.json()["is_shortlisted"])

        # 5. Lead capture endpoint
        res_lead = self.client.post("/api/properties/shortlist/lead", json={
            "property_id": "prop-dxb-002",
            "full_name": "Tariq Malik",
            "email": "tariq.malik@example.com",
            "phone": "+971559876543",
            "session_id": "api_test_session"
        })
        self.assertEqual(res_lead.status_code, 200)
        self.assertEqual(res_lead.json()["status"], "success")

        # 6. Refinement endpoint
        res_refine = self.client.post("/api/properties/refine", json={
            "current_filter": {"beds": 2, "budget_max": 2500000},
            "refinement_instruction": "show me cheaper options"
        })
        self.assertEqual(res_refine.status_code, 200)
        self.assertIn("refined_filter", res_refine.json())
        self.assertLess(res_refine.json()["refined_filter"]["budget_max"], 2500000)

if __name__ == "__main__":
    unittest.main()
