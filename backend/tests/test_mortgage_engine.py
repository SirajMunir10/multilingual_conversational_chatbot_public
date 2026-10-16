"""Deterministic mortgage engine (PRD FR-12–FR-14).

Eligibility and affordability are checked against the 15 test cases of the approved build logic
("Mortgage Eligibility Calculations"); results must match to the nearest dirham. EMI, fees and rule
tables are checked against the KB worked examples."""
import json
import unittest
from unittest import mock

from pydantic import ValidationError

from app.core import config
from app.services.mortgage_service import (AffordabilityInput, EligibilityInput, EMIInput, MortgageCalculationService as M,
                                           MortgageInputError)

# Baseline from the worked example: expat, 35, salaried, AED 35,000 income, AED 2,000 instalments,
# AED 20,000 card limits, AED 1.8M ready first home, AED 360,000 down, 4.5%, 25 years.
BASE = dict(residency="uae_resident", age=35, employment_type="salaried", monthly_income=35_000, monthly_debts=2_000,
            credit_card_limits=20_000, interest_rate=4.5, tenure_years=25, property_price=1_800_000, down_payment=360_000,
            has_outstanding_mortgage=False, property_status="ready", purpose="home")


def check(**changes):
    args = {k: v for k, v in {**BASE, **changes}.items() if v is not None}
    return M.check_eligibility(EligibilityInput(**args))


class TestApprovedEligibilityCases(unittest.TestCase):

    def assertDirham(self, value, expected):
        self.assertEqual(round(value), expected)

    def test_01_worked_example(self):
        r = check()
        self.assertEqual(r["verdict"], "eligible")
        self.assertEqual(r["term_years"], 25)
        self.assertEqual(r["existing_debts_aed"], 3_000)
        self.assertDirham(r["ceilings_aed"]["debt_burden"], 2_147_489)
        self.assertEqual(r["ceilings_aed"]["income_multiple"], 2_940_000)
        self.assertEqual(r["ceilings_aed"]["ltv"], 1_440_000)
        self.assertEqual(r["eligible_loan_aed"], 1_440_000)
        self.assertEqual(r["requested_loan_aed"], 1_440_000)
        self.assertDirham(r["instalment_aed"], 8_004)
        self.assertDirham(r["stress_instalment_aed"], 9_723)
        self.assertAlmostEqual(r["debt_burden"]["after_loan_pct"], 31.4, places=1)

    def test_02_age_19_fails_applicant_gate(self):
        r = check(age=19)
        self.assertEqual((r["verdict"], r["failed_gate"]), ("not_eligible", "applicant"))

    def test_03_income_12000_fails_applicant_gate(self):
        r = check(monthly_income=12_000)
        self.assertEqual((r["verdict"], r["failed_gate"]), ("not_eligible", "applicant"))

    def test_04_age_66_fails_term_gate(self):
        r = check(age=66)
        self.assertEqual((r["verdict"], r["failed_gate"]), ("not_eligible", "term"))

    def test_05_age_62_term_three_years(self):
        r = check(age=62)
        self.assertEqual(r["verdict"], "eligible_lower")
        self.assertEqual(r["term_years"], 3)
        self.assertDirham(r["eligible_loan_aed"], 473_099)
        self.assertEqual(r["tightest_limit"], "debt_burden")
        self.assertEqual(next(g for g in r["gates"] if g["gate"] == "term")["result"], "review")

    def test_06_age_62_self_employed(self):
        r = check(age=62, employment_type="self_employed")
        self.assertEqual((r["verdict"], r["term_years"]), ("eligible_lower", 8))
        self.assertDirham(r["eligible_loan_aed"], 1_083_202)

    def test_07_off_plan(self):
        r = check(property_status="off_plan")
        self.assertEqual((r["verdict"], r["ltv_applied_pct"], r["eligible_loan_aed"]), ("eligible_lower", 50, 900_000))

    def test_08_requested_above_ltv(self):
        r = check(property_price=2_500_000, down_payment=250_000)
        self.assertEqual(r["verdict"], "eligible_lower")
        self.assertEqual((r["eligible_loan_aed"], r["shortfall_aed"], r["tightest_limit"]), (2_000_000, 250_000, "ltv"))

    def test_09_no_room_for_an_instalment(self):
        r = check(monthly_income=20_000, monthly_debts=10_000, credit_card_limits=0)
        self.assertEqual((r["verdict"], r["failed_gate"]), ("not_eligible", "debt_burden"))

    def test_10_non_resident_with_note(self):
        r = check(residency="non_resident")
        self.assertEqual((r["verdict"], r["ltv_applied_pct"], r["eligible_loan_aed"]), ("eligible_lower", 50, 900_000))
        self.assertTrue(any("65%" in n for n in r["notes"]))

    def test_11_no_property_can_borrow(self):
        r = check(property_price=None, down_payment=None, has_outstanding_mortgage=None)
        self.assertEqual(r["verdict"], "can_borrow")
        self.assertDirham(r["eligible_loan_aed"], 2_147_489)
        self.assertDirham(r["implied_property_price_aed"], 2_684_361)

    def test_12_investment_with_rent(self):
        r = check(purpose="investment", property_price=2_000_000, down_payment=800_000, expected_annual_rent=120_000)
        self.assertEqual((r["verdict"], r["ltv_applied_pct"], r["eligible_loan_aed"]), ("eligible", 60, 1_200_000))
        self.assertDirham(r["income"]["recognised_rent_aed"], 8_333)

    def test_13_uae_national_above_5m(self):
        r = check(residency="uae_national", monthly_income=80_000, monthly_debts=0, credit_card_limits=0,
                  property_price=6_000_000, down_payment=1_500_000)
        self.assertEqual((r["verdict"], r["ltv_applied_pct"], r["eligible_loan_aed"]), ("eligible", 75, 4_500_000))
        self.assertEqual(r["ceilings_aed"]["income_multiple"], 7_680_000)

    def test_14_expat_exactly_5m_gets_lower_ltv(self):
        r = check(property_price=5_000_000, down_payment=1_500_000, monthly_income=100_000, monthly_debts=0, credit_card_limits=0)
        self.assertEqual((r["verdict"], r["ltv_applied_pct"], r["eligible_loan_aed"]), ("eligible", 70, 3_500_000))

    def test_15_outstanding_mortgage_uses_second_home_ltv(self):
        r = check(has_outstanding_mortgage=True)
        self.assertEqual((r["verdict"], r["ltv_applied_pct"], r["eligible_loan_aed"]), ("eligible_lower", 60, 1_080_000))


class TestEligibilityInputsAndOutputs(unittest.TestCase):

    def test_required_fields_are_asked_together(self):
        with self.assertRaises(MortgageInputError) as ctx:
            M.check_eligibility(EligibilityInput(monthly_income=30_000))
        message = str(ctx.exception)
        for field in ("residency", "age", "employment type"):
            self.assertIn(field, message)

    def test_property_needs_first_home_confirmation(self):
        with self.assertRaises(MortgageInputError) as ctx:
            check(has_outstanding_mortgage=None)
        self.assertIn("outstanding mortgage", str(ctx.exception))

    def test_uae_national_exactly_5m_keeps_higher_ltv(self):
        self.assertEqual(M.ltv_for("uae_national", "first", "ready", 5_000_000)[0], 0.85)
        self.assertEqual(M.ltv_for("uae_resident", "first", "ready", 5_000_000)[0], 0.70)

    def test_defaults_are_reported_as_assumptions(self):
        r = M.calc_affordability(AffordabilityInput(residency="uae_resident", age=30, employment_type="salaried", monthly_income=30_000))
        self.assertEqual(r["calculation_type"], "affordability")
        self.assertEqual(r["verdict"], "can_borrow")
        joined = " ".join(r["assumptions"])
        for text in ("benchmark", "no existing loan instalments", "no credit card limits"):
            self.assertIn(text, joined)

    def test_cash_upfront_lists_each_item(self):
        r = check()
        items = {i["item"]: i for i in r["cash_upfront"]["items"]}
        self.assertEqual(items["down_payment"]["amount_aed"], 360_000)
        self.assertEqual(items["transfer_fee"]["amount_aed"], 72_000)            # 4% of AED 1.8M (Dubai)
        self.assertEqual(items["mortgage_registration"]["amount_aed"], 3_600)    # 0.25% of the loan
        self.assertEqual(items["bank_arrangement_fee"]["max_aed"], 14_400)       # up to 1% of the loan
        self.assertIn("agent_commission", items)

    def test_valuation_below_price_is_used(self):
        r = check(valuation=1_700_000, down_payment=None)
        self.assertEqual(r["property_value_aed"], 1_700_000)
        self.assertEqual(r["eligible_loan_aed"], 1_360_000)

    def test_result_is_json_serialisable(self):
        json.dumps(check())


class TestEMI(unittest.TestCase):

    def test_kb_article_26_example(self):
        # KB Art. 26: AED 1.5M, 20% down, 3.8%, 25 years -> AED 6,202 / month
        r = M.calc_emi(EMIInput(property_price=1_500_000, residency="uae_resident"))
        self.assertEqual(r["down_payment_aed"], 300_000)
        self.assertEqual(r["loan_amount_aed"], 1_200_000)
        self.assertAlmostEqual(r["instalment_aed"], 6202.28, places=2)
        self.assertIn("3.8% interest rate (benchmark)", r["assumptions"])
        self.assertEqual(r["stress_rate_pct"], 5.8)

    def test_kb_formula_reference_example(self):
        r = M.calc_emi(EMIInput(loan_amount=800_000, interest_rate=3.8, tenure_years=25))
        self.assertAlmostEqual(r["instalment_aed"], 4134.85, places=2)

    def test_off_plan_and_non_resident_need_half_down(self):
        self.assertEqual(M.calc_emi(EMIInput(property_price=2_000_000, property_status="off-plan"))["down_payment_aed"], 1_000_000)
        self.assertEqual(M.calc_emi(EMIInput(property_price=2_000_000, residency="non_resident"))["down_payment_aed"], 1_000_000)

    def test_quarterly_frequency_and_schedule(self):
        r = M.calc_emi(EMIInput(loan_amount=1_000_000, interest_rate=4, tenure_years=20, frequency="quarterly"))
        self.assertEqual(len(r["amortization_schedule"]), 5)
        self.assertAlmostEqual(r["principal_share_pct"] + r["interest_share_pct"], 100, places=0)

    def test_down_payment_below_minimum_is_explained(self):
        with self.assertRaises(MortgageInputError) as ctx:
            M.calc_emi(EMIInput(property_price=2_000_000, down_payment=100_000, residency="uae_resident"))
        self.assertIn("20%", str(ctx.exception))

    def test_invalid_tenure_rejected(self):
        with self.assertRaises((MortgageInputError, ValidationError)):
            EMIInput(loan_amount=1_000_000, tenure_years=30)


class TestFeesProductsRules(unittest.TestCase):

    def test_dubai_purchase_costs_match_kb_article_2(self):
        r = M.calc_purchase_costs(2_000_000, "dubai")
        items = {i["item"]: i["amount_aed"] for i in r["items"]}
        self.assertEqual(items["DLD transfer fee"], 80_000)
        self.assertEqual(items["Trustee office fee"], 4_000)
        self.assertEqual(items["Title deed fee"], 250)
        self.assertEqual(r["total_fixed_aed"], 126_830)

    def test_mortgage_adds_arrangement_fee_range(self):
        r = M.calc_purchase_costs(2_000_000, "dubai", loan_amount=1_600_000)
        ranges = {i["item"]: i for i in r["variable_items"]}
        self.assertEqual(ranges["Bank arrangement fee (up to 1% of the loan)"]["max_aed"], 16_000)

    def test_abu_dhabi_uses_its_own_fees(self):
        r = M.calc_purchase_costs(2_000_000, "Abu Dhabi")
        self.assertEqual(r["emirate"], "Abu Dhabi")
        self.assertEqual(r["total_fixed_aed"], 82_000)

    def test_products_are_json_and_marked_unconfirmed(self):
        r = M.get_products(finance_type="islamic")
        json.dumps(r)
        self.assertGreater(r["count"], 0)
        self.assertEqual(r["status"], "pending_mortgage_team_confirmation")

    def test_offers_sorted_by_rate(self):
        r = M.estimate_offers(2_000_000)
        rates = [o["indicative_rate_pct"] for o in r["offers"]]
        self.assertEqual(rates, sorted(rates))

    def test_lending_rules_table(self):
        r = M.lending_rules("uae_national")
        cases = {row["case"]: row["max_ltv_pct"] for row in r["ltv_table_first_match_wins"]}
        self.assertEqual(cases["UAE national, first home, value above AED 5 million"], 75)
        self.assertEqual(cases["Off-plan property, any buyer"], 50)
        self.assertEqual(r["debt_burden_limit_pct"], 50)

    def test_rule_table_drives_calculation(self):
        """Changing the versioned rule table changes results without code changes (PRD FR-27)."""
        original = config.load_config("mortgage_rules")
        patched = json.loads(json.dumps(original))
        patched["bank_settings"]["stress_test_addon_pct"] = 3.0
        with mock.patch("app.services.mortgage_service.load_config", side_effect=lambda n: patched if n == "mortgage_rules" else config.load_config(n)):
            r = check()
        self.assertEqual(r["stress_rate_pct"], 7.5)


if __name__ == "__main__":
    unittest.main()
