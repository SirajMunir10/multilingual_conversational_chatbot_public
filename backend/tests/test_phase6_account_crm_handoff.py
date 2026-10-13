import unittest
import os
import sys

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from app.main import app
from app.services.account_service import AccountService
from app.gateways.grid_gateway import GridGateway, GridLeadPayload
from app.gateways.vault_gateway import VaultGateway, VaultMortgageLeadPayload
from app.services.handoff_service import HandoffService
from app.orchestrator.session_store import SessionStore
from app.core.audit import AuditService

class TestPhase6AccountCRMAndHandoff(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    # =========================================================================
    # 1. ACCOUNT AWARENESS & DATA ACCESS BOUNDARIES (FR-21, FR-22, FR-23a, FR-23b)
    # =========================================================================

    def test_01_authenticated_user_retrieves_saved_properties(self):
        """FR-21: Authenticated user can query their own saved properties."""
        res = AccountService.get_my_saved_properties("user_siraj_vip", session_id="test_sess_01")
        self.assertEqual(res["status"], "success")
        self.assertTrue(res["authenticated"])
        self.assertEqual(res["user_id"], "user_siraj_vip")
        self.assertGreaterEqual(res["count"], 2)
        prop_ids = [p["id"] for p in res["saved_properties"]]
        self.assertIn("prop-dxb-001", prop_ids)
        self.assertIn("prop-dxb-002", prop_ids)

    def test_02_unauthenticated_user_access_rejected_cleanly(self):
        """FR-21 & FR-22: Unauthenticated user is prompted to sign in with zero data leakage."""
        res = AccountService.get_my_saved_properties(None, session_id="test_sess_guest")
        self.assertEqual(res["status"], "auth_required")
        self.assertFalse(res["authenticated"])
        self.assertEqual(len(res["saved_properties"]), 0)
        self.assertTrue("sign in" in res["message"].lower() or "authentication" in res["message"].lower())

    def test_03_user_data_isolation(self):
        """FR-22: Strict data boundary prevents cross-user exposure."""
        siraj_res = AccountService.get_my_saved_properties("user_siraj_vip")
        layla_res = AccountService.get_my_saved_properties("user_layla_investor")

        siraj_ids = [p["id"] for p in siraj_res["saved_properties"]]
        layla_ids = [p["id"] for p in layla_res["saved_properties"]]

        # Verify no cross-pollution of user bookmarks
        self.assertIn("prop-dxb-001", siraj_ids)
        self.assertNotIn("prop-dxb-001", layla_ids)
        self.assertIn("prop-dxb-003", layla_ids)
        self.assertNotIn("prop-dxb-003", siraj_ids)

    def test_04_authenticated_user_retrieves_application_status(self):
        """FR-21: Authenticated user can query their own applications across Vault & GRID."""
        res = AccountService.get_my_application_status("user_siraj_vip", session_id="test_sess_02")
        self.assertEqual(res["status"], "success")
        self.assertTrue(res["authenticated"])
        self.assertGreaterEqual(res["total_count"], 2)
        self.assertGreaterEqual(len(res["vault_mortgage_applications"]), 1)
        self.assertGreaterEqual(len(res["grid_property_inquiries"]), 1)
        self.assertEqual(res["vault_mortgage_applications"][0]["crm"], "Vault")
        self.assertEqual(res["grid_property_inquiries"][0]["crm"], "GRID")

    def test_05_save_and_remove_property_from_account(self):
        """FR-10, FR-21: User can add and remove bookmarks with audit logs."""
        add_res = AccountService.save_property("user_siraj_vip", "prop-dxb-005")
        self.assertEqual(add_res["status"], "saved")

        rem_res = AccountService.remove_saved_property("user_siraj_vip", "prop-dxb-005")
        self.assertEqual(rem_res["status"], "removed")

    def test_06_customer_data_access_audit_logging(self):
        """FR-22: Every customer data access is recorded in tamper-evident audit ledger."""
        AccountService.get_my_saved_properties("user_siraj_vip", session_id="audit_test_sess")
        logs = AuditService.get_recent_logs(limit=10, event_type="customer_data_access")
        self.assertGreater(len(logs), 0)
        latest = logs[-1]
        self.assertEqual(latest.user_id, "user_siraj_vip")
        self.assertIn(latest.action, ["get_my_saved_properties", "get_my_application_status"])

    # =========================================================================
    # 2. CRM GATEWAYS: GRID & VAULT (Section 20, FR-16, WRT-BND)
    # =========================================================================

    def test_07_grid_lead_creation_and_audit(self):
        """Section 20 & WRT-BND: Narrow lead capture write endpoint for GRID CRM."""
        payload = GridLeadPayload(
            contact_name="Ahmad Al-Mansoor",
            contact_phone="+971 50 111 2233",
            contact_email="ahmad@domain.ae",
            property_id="prop-dxb-001",
            inquiry_type="viewing_request",
            budget_max=12500000.0,
            notes="Interested in private terrace viewing"
        )
        res = GridGateway.create_lead(payload, session_id="sess_grid_test", user_id="user_siraj_vip")
        self.assertEqual(res.crm, "GRID")
        self.assertEqual(res.status, "created")
        self.assertTrue(res.lead_id.startswith("grid_lead_"))

        # Verify retrieval scoped by user
        user_leads = GridGateway.get_user_leads("user_siraj_vip")
        self.assertTrue(any(l["lead_id"] == res.lead_id for l in user_leads))

    def test_08_vault_mortgage_lead_creation_and_audit(self):
        """FR-16 & SEC-CONS: Qualified mortgage lead handoff with calculated affordability into Vault CRM."""
        payload = VaultMortgageLeadPayload(
            applicant_name="Rashid Al-Falasi",
            applicant_phone="+971 55 999 8888",
            applicant_email="rashid@finance.ae",
            monthly_income=50000.0,
            existing_debt=5000.0,
            calculated_affordability_max=4500000.0,
            estimated_emi=18500.0,
            nationality_status="uae_national",
            consent_given=True,
            notes="Pre-qualification approved for DIB Islamic Murabaha"
        )
        res = VaultGateway.create_lead(payload, session_id="sess_vault_test", user_id="user_siraj_vip")
        self.assertEqual(res.crm, "Vault")
        self.assertEqual(res.status, "submitted")
        self.assertTrue(res.application_id.startswith("vault_app_"))

        # Verify retrieval scoped by user
        user_apps = VaultGateway.get_user_applications("user_siraj_vip")
        self.assertTrue(any(a["application_id"] == res.application_id for a in user_apps))

    # =========================================================================
    # 3. HUMAN HANDOFF ORCHESTRATION (FR-5, FR-20)
    # =========================================================================

    def test_09_explicit_human_request_trigger(self):
        """FR-5: Explicit user request triggers warm human handoff."""
        session = SessionStore.get_or_create_session("sess_handoff_01", user_id="user_siraj_vip")
        trigger = HandoffService.evaluate_handoff_trigger("Can I speak with a human advisor please?", session)
        self.assertIsNotNone(trigger)
        self.assertTrue(trigger["triggered"])
        self.assertEqual(trigger["reason"], "explicit_request")

    def test_10_negative_sentiment_frustration_trigger(self):
        """FR-5: Frustrated sentiment triggers high-priority handoff to human support."""
        session = SessionStore.get_or_create_session("sess_handoff_02")
        trigger = HandoffService.evaluate_handoff_trigger("This bot is useless and frustrating!", session)
        self.assertIsNotNone(trigger)
        self.assertTrue(trigger["triggered"])
        self.assertEqual(trigger["reason"], "negative_sentiment")
        self.assertEqual(trigger["priority"], "high")

    def test_11_handoff_queue_routing_mortgage(self):
        """Section 10: User with mortgage context routes to Mortgage desk."""
        session = SessionStore.get_or_create_session("sess_handoff_mortgage")
        session.active_intent = "mortgage"
        session.slots.mortgage_income = 40000.0
        queue = HandoffService.determine_target_queue(session)
        self.assertEqual(queue, "mortgage")

    def test_12_handoff_queue_routing_sales(self):
        """Section 10: User with property search context routes to Sales desk."""
        session = SessionStore.get_or_create_session("sess_handoff_sales")
        session.active_intent = "property"
        session.slots.property_city = "Downtown Dubai"
        queue = HandoffService.determine_target_queue(session)
        self.assertEqual(queue, "sales")

    def test_13_handoff_execution_with_full_transcript_serialization(self):
        """FR-5: Handoff creates ticket with serialized transcript turns and assigned specialist."""
        sess_id = "sess_full_transcript_test"
        session = SessionStore.get_or_create_session(sess_id, user_id="user_siraj_vip")

        # Add a couple of conversation turns
        SessionStore.add_message(sess_id, role="user", content="Looking for penthouses in Palm Jumeirah under 20M AED")
        SessionStore.add_message(sess_id, role="assistant", content="We have luxury 3-bed penthouses available.")
        SessionStore.add_message(sess_id, role="user", content="Connect me to an advisor please")

        handoff_res = HandoffService.initiate_handoff(
            session_id=sess_id,
            reason="explicit_request",
            user_id="user_siraj_vip"
        )

        self.assertEqual(handoff_res["status"], "handoff_initiated")
        self.assertTrue(handoff_res["ticket_id"].startswith("XO-HD-"))
        self.assertIsNotNone(handoff_res["assigned_advisor"]["name"])
        self.assertEqual(handoff_res["priority"], "vip")

        # Verify ticket details in queue
        ticket = HandoffService.get_ticket(handoff_res["ticket_id"])
        self.assertIsNotNone(ticket)
        self.assertGreaterEqual(ticket["transcript_turns_count"], 3)
        self.assertGreaterEqual(len(ticket["full_transcript"]), 3)
        self.assertEqual(ticket["customer_summary"]["user_id"], "user_siraj_vip")

    # =========================================================================
    # 4. END-TO-END CHAT & GATEWAY API INTEGRATION
    # =========================================================================

    def test_14_e2e_authenticated_account_query_via_chat(self):
        """End-to-end: Authenticated user asking about saved properties via /api/chat/message."""
        resp = self.client.post(
            "/api/chat/message",
            json={"message": "Show my saved properties"},
            headers={"X-User-ID": "user_siraj_vip", "X-Session-ID": "sess_e2e_acc"}
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn(data["intent"], ["account", "general"])
        self.assertGreaterEqual(len(data.get("saved_properties", [])), 2)
        self.assertTrue("Siraj" in data["text"] or "portfolio" in data["text"] or "saved" in data["text"] or "properties" in data["text"])

    def test_15_e2e_unauthenticated_account_query_via_chat(self):
        """End-to-end: Unauthenticated user asking about saved properties gets auth prompt."""
        resp = self.client.post(
            "/api/chat/message",
            json={"message": "Show my saved properties"},
            headers={"X-Session-ID": "sess_e2e_guest"}
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data.get("saved_properties", [])), 0)
        self.assertTrue("sign in" in data["text"].lower() or "log in" in data["text"].lower() or "protected" in data["text"].lower())

    def test_16_e2e_human_handoff_via_chat(self):
        """End-to-end: User asking to speak with an advisor requests permission/details in turn 1, registers callback in turn 2."""
        # Turn 1: User asks for advisor without contact details -> bot asks for permission and contact info
        resp1 = self.client.post(
            "/api/chat/message",
            json={"message": "Speak with advisor"},
            headers={"X-User-ID": "user_siraj_vip", "X-Session-ID": "sess_e2e_handoff"}
        )
        self.assertEqual(resp1.status_code, 200)
        data1 = resp1.json()
        self.assertFalse(data1.get("handoff_offered"))
        self.assertIn("reach out", data1["text"].lower())

        # Turn 2: User provides name, phone number, and preferred language -> bot registers callback and creates ticket
        resp2 = self.client.post(
            "/api/chat/message",
            json={"message": "Yes, my name is Siraj Munir, phone +971501234567, language English"},
            headers={"X-User-ID": "user_siraj_vip", "X-Session-ID": "sess_e2e_handoff"}
        )
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json()
        self.assertTrue(data2.get("handoff_offered"))
        self.assertIsNotNone(data2.get("handoff_data"))
        self.assertTrue(data2["handoff_data"]["ticket_id"].startswith("XO-HD-"))
        self.assertEqual(data2["handoff_data"]["applicant_phone"], "+971501234567")

    def test_17_http_gateway_account_endpoints(self):
        """HTTP API test for GET /api/gateways/account/saved-properties and /applications."""
        res_props = self.client.get("/api/gateways/account/saved-properties", headers={"X-User-ID": "user_siraj_vip"})
        self.assertEqual(res_props.status_code, 200)
        self.assertTrue(res_props.json()["authenticated"])

        res_apps = self.client.get("/api/gateways/account/applications", headers={"X-User-ID": "user_siraj_vip"})
        self.assertEqual(res_apps.status_code, 200)
        self.assertTrue(res_apps.json()["authenticated"])

    def test_18_http_gateway_handoff_queue_inspection(self):
        """HTTP API test for GET /api/gateways/handoff/queue."""
        res_queue = self.client.get("/api/gateways/handoff/queue")
        self.assertEqual(res_queue.status_code, 200)
        self.assertIsInstance(res_queue.json(), list)

if __name__ == "__main__":
    unittest.main(verbosity=2)
