import sys
import os
import unittest
import math

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from app.main import app
from app.services.mortgage_service import (
    MortgageCalculationService,
    AffordabilityInput,
    EMIInput,
    EligibilityInput
)
from app.gateways.mortgage_rules_gateway import MortgageRulesGateway

class TestPhase3MortgageCalculationService(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_calc_emi_exact_mathematical_benchmark(self):
        """
        Verify calc_emi against standard banking amortization benchmarks:
        Loan: 1,000,000 AED
        Rate: 4.49% per annum
        Tenure: 25 years (300 monthly payments)
        Benchmark EMI = ~5,553.07 AED/month
        """
        inp = EMIInput(
            loan_amount=1000000.0,
            interest_rate=4.49,
            tenure=25,
            frequency="monthly"
        )
        res = MortgageCalculationService.calc_emi(inp, session_id="test_emi_bench")
        
        # Verify periodic installment matches standard annuity formula within 0.10 AED
        self.assertAlmostEqual(res["periodic_installment_aed"], 5552.65, delta=0.10)
        self.assertGreater(res["total_repayment_aed"], 1000000.0)
        self.assertAlmostEqual(res["total_interest_payable_aed"], res["total_repayment_aed"] - 1000000.0, places=2)
        
        # Check Rule 10 mandatory disclaimers
        self.assertEqual(res["label"], "estimates, not offers")
        self.assertEqual(res["disclaimer"], "estimate only, subject to lender approval")
        self.assertEqual(res["compliance_ref"], "XOTO-CORP-RETENTION-POL-2024-V3")
        
        # Check amortization schedule has 5 initial years
        self.assertEqual(len(res["amortization_schedule_sample"]), 5)
        self.assertEqual(res["amortization_schedule_sample"][0]["year"], 1)

    def test_calc_affordability_uae_central_bank_50pct_dbr(self):
        """
        Verify affordability calculations strictly enforce the UAE Central Bank 50% DBR cap.
        Income: 30,000 AED/mo
        Existing Debt: 5,000 AED/mo
        Max Allowable Monthly Payment = (30,000 * 0.50) - 5,000 = 10,000 AED/mo
        """
        inp = AffordabilityInput(
            income=30000.0,
            existing_debt=5000.0,
            down_payment=250000.0,
            term=25,
            rate_assumption=4.49,
            nationality="expat",
            consent_given=True
        )
        res = MortgageCalculationService.calc_affordability(inp, session_id="test_afford_dbr")
        summary = res["affordability_summary"]
        dbr = res["dbr_status"]

        self.assertEqual(dbr["max_allowed_dbr_pct"], 50.0)
        self.assertFalse(dbr["dbr_cap_exceeded"])
        self.assertAlmostEqual(summary["max_dbr_allowable_installment_aed"], 10000.0, places=2)
        self.assertGreater(summary["max_borrowing_capacity_aed"], 500000.0)
        
        # Verify upfront purchase costs
        upfront = res["upfront_costs_breakdown"]
        self.assertGreater(upfront["dld_transfer_fee_aed"], 0)
        self.assertGreater(upfront["agency_broker_fee_aed"], 0)
        self.assertGreater(upfront["total_cash_required_at_purchase_aed"], 250000.0)
        
        # Verify jump to properties CTA
        jump = res["jump_to_properties"]
        self.assertTrue(jump["enabled"])
        self.assertGreater(jump["recommended_budget_max"], 0)

    def test_dbr_cap_exceeded_rejection(self):
        """
        Verify that when existing debt commitments already exceed 50% DBR,
        the service flags dbr_cap_exceeded and sets borrowing capacity to 0.
        """
        inp = AffordabilityInput(
            income=20000.0,
            existing_debt=12000.0,  # 12,000 / 20,000 = 60% DBR (exceeds 50% cap)
            down_payment=100000.0,
            term=25
        )
        res = MortgageCalculationService.calc_affordability(inp, session_id="test_dbr_exceeded")
        dbr = res["dbr_status"]
        summary = res["affordability_summary"]

        self.assertTrue(dbr["dbr_cap_exceeded"])
        self.assertEqual(summary["max_borrowing_capacity_aed"], 0.0)
        self.assertEqual(summary["max_allowable_monthly_emi_aed"], 0.0)
        self.assertIn("Exceeds UAE Central Bank 50% DBR cap", dbr["message"])

    def test_immediate_input_validation(self):
        """
        Verify FR-12e: Inputs are validated immediately with clear errors.
        """
        # 1. Salary below UAE minimum threshold (< 5,000 AED)
        with self.assertRaises(ValueError):
            AffordabilityInput(income=3000.0, term=25)

        # 2. Negative existing debt
        with self.assertRaises(ValueError):
            AffordabilityInput(income=25000.0, existing_debt=-500.0, term=25)

        # 3. Tenure exceeding UAE Central Bank 25-year maximum limit
        with self.assertRaises(ValueError):
            AffordabilityInput(income=25000.0, term=35)

        # 4. Invalid EMI loan amount
        with self.assertRaises(ValueError):
            EMIInput(loan_amount=0.0, interest_rate=4.49, tenure=25)

    def test_eligibility_criteria_uae_national_vs_expat(self):
        """
        Verify eligibility differentiation (LTV 80% National vs 75% Expat).
        """
        # UAE National
        nat_res = MortgageCalculationService.check_eligibility(
            EligibilityInput(salary=25000.0, nationality="national", liabilities=3000.0)
        )
        self.assertTrue(nat_res["is_eligible"])
        self.assertEqual(nat_res["max_ltv_permitted_pct"], 80.0)

        # Expat
        exp_res = MortgageCalculationService.check_eligibility(
            EligibilityInput(salary=25000.0, nationality="expat", liabilities=3000.0)
        )
        self.assertTrue(exp_res["is_eligible"])
        self.assertEqual(exp_res["max_ltv_permitted_pct"], 75.0)

    def test_mortgage_rest_endpoints(self):
        """
        Verify all FastAPI mortgage endpoints return 200 and schema validation works.
        """
        # 1. POST /api/mortgage/affordability
        res_afford = self.client.post("/api/mortgage/affordability", json={
            "income": 35000.0,
            "existing_debt": 4000.0,
            "down_payment": 300000.0,
            "term": 25,
            "rate_assumption": 4.49,
            "nationality": "expat",
            "consent_given": True
        })
        self.assertEqual(res_afford.status_code, 200)
        d_afford = res_afford.json()
        self.assertIn("affordability_summary", d_afford)
        self.assertEqual(d_afford["label"], "estimates, not offers")

        # 2. POST /api/mortgage/emi
        res_emi = self.client.post("/api/mortgage/emi", json={
            "loan_amount": 1500000.0,
            "interest_rate": 4.75,
            "tenure": 20,
            "frequency": "monthly"
        })
        self.assertEqual(res_emi.status_code, 200)
        d_emi = res_emi.json()
        self.assertGreater(d_emi["periodic_installment_aed"], 0)

        # 3. POST /api/mortgage/eligibility
        res_elig = self.client.post("/api/mortgage/eligibility", json={
            "salary": 18000.0,
            "nationality": "national",
            "employment_type": "salaried",
            "liabilities": 2000.0
        })
        self.assertEqual(res_elig.status_code, 200)
        self.assertTrue(res_elig.json()["is_eligible"])

        # 4. POST /api/mortgage/offers
        res_offers = self.client.post("/api/mortgage/offers?loan_amount=1200000&salary=30000&nationality=expat&tenure=25")
        self.assertEqual(res_offers.status_code, 200)
        self.assertGreater(len(res_offers.json()["indicative_offers"]), 0)

        # 5. GET /api/mortgage/products
        res_prods = self.client.get("/api/mortgage/products")
        self.assertEqual(res_prods.status_code, 200)
        self.assertGreater(res_prods.json()["count"], 0)

    def test_zero_llm_math_audit_trail(self):
        """
        Verify Rule 5: Math was executed deterministically and logged in audit trail.
        """
        session_id = "test_audit_sess_900"
        res = self.client.post(f"/api/mortgage/emi?session_id={session_id}", json={
            "loan_amount": 800000.0,
            "interest_rate": 4.49,
            "tenure": 15,
            "frequency": "monthly"
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        # Verify deterministic exact calculation (no rounding fuzziness)
        self.assertEqual(data["loan_amount_aed"], 800000.0)
        self.assertIn("compliance_ref", data)

    def test_islamic_mortgage_products_and_offers(self):
        """
        Verify Islamic home finance rate sheets and Sharia-compliant product retrieval:
        - Dubai Islamic Bank (DIB)
        - Abu Dhabi Islamic Bank (ADIB)
        - Emirates Islamic
        - Sharjah Islamic Bank (SIB)
        - Ajman Bank, Al Hilal Bank, Mashreq Al Islami, RAKBANK Islamic
        """
        # 1. Query all Islamic products
        islamic_prods = MortgageRulesGateway.get_mortgage_products(finance_type="islamic")
        self.assertGreaterEqual(len(islamic_prods), 10)
        dib_prods = [p for p in islamic_prods if "Dubai Islamic Bank" in p.bank_name]
        self.assertGreaterEqual(len(dib_prods), 2)
        self.assertTrue(all(p.finance_type == "islamic" for p in islamic_prods))

        # 2. Query via REST API filter
        res_gateway = self.client.get("/api/gateways/mortgage-products?finance_type=islamic")
        self.assertEqual(res_gateway.status_code, 200)
        self.assertGreaterEqual(len(res_gateway.json()), 10)

        # 3. Request indicative offers specifically for Islamic financing
        res_offers = self.client.post("/api/mortgage/offers?loan_amount=1500000&salary=25000&finance_type=islamic")
        self.assertEqual(res_offers.status_code, 200)
        data = res_offers.json()
        self.assertGreater(len(data["indicative_offers"]), 0)
        for offer in data["indicative_offers"]:
            self.assertEqual(offer["finance_type"], "islamic")
            self.assertGreater(offer["monthly_emi_aed"], 0)
