"""What a calculator-rules draft would change (PRD FR-27), before it is published.

The 15 cases of the approved build logic ("Mortgage Eligibility Calculations"), a monthly-payment example and a
purchase-cost example are calculated twice: with the published rules and with the draft. The draft applies to this
request only (config.preview), so visitors never see it, and nothing is written to the audit log."""
from typing import Any, Dict, List, Optional

from app.core.config import preview
from app.services.mortgage_service import EligibilityInput, MortgageCalculationService as M, MortgageInputError

# The approved worked example: expat, 35, salaried, AED 35,000 income, AED 2,000 instalments, AED 20,000 card limits,
# AED 1.8M ready first home, AED 360,000 down, 4.5%, 25 years. Each case changes only what it names
# (the same 15 cases as tests/test_mortgage_engine.py).
BASE = dict(residency="uae_resident", age=35, employment_type="salaried", monthly_income=35_000, monthly_debts=2_000,
            credit_card_limits=20_000, interest_rate=4.5, tenure_years=25, property_price=1_800_000, down_payment=360_000,
            has_outstanding_mortgage=False, property_status="ready", purpose="home")

CASES = [
    ("1", "Worked example", {}),
    ("2", "Applicant aged 19", {"age": 19}),
    ("3", "Income AED 12,000", {"monthly_income": 12_000}),
    ("4", "Applicant aged 66", {"age": 66}),
    ("5", "Applicant aged 62", {"age": 62}),
    ("6", "Aged 62, self-employed", {"age": 62, "employment_type": "self_employed"}),
    ("7", "Off-plan property", {"property_status": "off_plan"}),
    ("8", "AED 2.5M with AED 250,000 down", {"property_price": 2_500_000, "down_payment": 250_000}),
    ("9", "No room for an instalment", {"monthly_income": 20_000, "monthly_debts": 10_000, "credit_card_limits": 0}),
    ("10", "Non-resident", {"residency": "non_resident"}),
    ("11", "No property yet (how much can I borrow)", {"property_price": None, "down_payment": None, "has_outstanding_mortgage": None}),
    ("12", "Investment with rent", {"purpose": "investment", "property_price": 2_000_000, "down_payment": 800_000,
                                    "expected_annual_rent": 120_000}),
    ("13", "UAE national, AED 6M", {"residency": "uae_national", "monthly_income": 80_000, "monthly_debts": 0,
                                     "credit_card_limits": 0, "property_price": 6_000_000, "down_payment": 1_500_000}),
    ("14", "Expat, exactly AED 5M", {"property_price": 5_000_000, "down_payment": 1_500_000, "monthly_income": 100_000,
                                      "monthly_debts": 0, "credit_card_limits": 0}),
    ("15", "Outstanding mortgage elsewhere", {"has_outstanding_mortgage": True}),
]

VERDICTS = {"eligible": "Eligible", "eligible_lower": "Eligible for less", "not_eligible": "Not eligible",
            "can_borrow": "Can borrow"}


def _case_figures(changes: Dict[str, Any]) -> Dict[str, Any]:
    args = {k: v for k, v in {**BASE, **changes}.items() if v is not None}
    try:
        r = M.assess(EligibilityInput(**args), "eligibility")
    except (MortgageInputError, ValueError) as exc:
        return {"Result": f"Error: {exc}"}
    out: Dict[str, Any] = {"Result": VERDICTS.get(r["verdict"], r["verdict"])}
    if r.get("failed_gate"):
        out["Failed check"] = r["failed_gate"].replace("_", " ")
    for key, label in (("eligible_loan_aed", "Loan (AED)"), ("instalment_aed", "Monthly payment (AED)"),
                       ("stress_instalment_aed", "Payment at stress rate (AED)"), ("ltv_applied_pct", "Loan-to-value (%)"),
                       ("term_years", "Term (years)"), ("implied_property_price_aed", "Property price (AED)")):
        if r.get(key) is not None:
            out[label] = round(r[key])
    # The three limits, so a change shows its effect even when another limit is the tightest.
    for key, label in (("debt_burden", "Limit from debt burden (AED)"), ("income_multiple", "Limit from income multiple (AED)"),
                       ("ltv", "Limit from loan-to-value (AED)")):
        if (r.get("ceilings_aed") or {}).get(key) is not None:
            out[label] = round(r["ceilings_aed"][key])
    if r.get("tightest_limit"):
        out["Tightest limit"] = r["tightest_limit"].replace("_", " ")
    return out


def _examples() -> List[Dict[str, Any]]:
    rows = []
    try:
        rules_ltv, _ = M.ltv_for("uae_resident", value=1_500_000)
        from app.core.config import load_config
        rules = load_config("mortgage_rules")
        loan = 1_500_000 * rules_ltv
        payment = M.instalment(loan, rules["interest"]["benchmark_rate_pct"], rules["tenure"]["default_years"])
        rows.append({"id": "emi", "label": "Monthly payment on an AED 1.5M home (expat, benchmark rate, default term)",
                     "figures": {"Loan (AED)": round(loan), "Monthly payment (AED)": round(payment)}})
    except (MortgageInputError, KeyError) as exc:
        rows.append({"id": "emi", "label": "Monthly payment on an AED 1.5M home", "figures": {"Result": f"Error: {exc}"}})
    try:
        costs = M.calc_purchase_costs(2_000_000, "dubai", 1_600_000, audit=False)
        rows.append({"id": "costs", "label": "Buying costs, AED 2M home in Dubai with an AED 1.6M loan",
                     "figures": {"Fixed costs (AED)": round(costs["total_fixed_aed"]),
                                 "With variable costs, up to (AED)": round(costs["total_range_aed"]["max"])}})
    except (MortgageInputError, KeyError) as exc:
        rows.append({"id": "costs", "label": "Buying costs, AED 2M home in Dubai", "figures": {"Result": f"Error: {exc}"}})
    return rows


def _snapshot() -> List[Dict[str, Any]]:
    rows = [{"id": f"case_{cid}", "label": f"Case {cid}: {label}", "figures": _case_figures(changes)} for cid, label, changes in CASES]
    return rows + _examples()


def impact(draft: Dict[str, Any], published: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """`draft` maps item name → draft data (e.g. {"mortgage_rules": {...}}). Returns each scenario's figures before and
    after, with the figures that change."""
    with preview(published or {}):
        before = _snapshot()
    with preview(draft):
        after = _snapshot()
    rows = []
    for b, a in zip(before, after):
        changed = sorted(k for k in set(b["figures"]) | set(a["figures"]) if b["figures"].get(k) != a["figures"].get(k))
        rows.append({"id": b["id"], "label": b["label"], "before": b["figures"], "after": a["figures"], "changed": changed})
    return {"scenarios": rows, "changed_count": sum(1 for r in rows if r["changed"])}
