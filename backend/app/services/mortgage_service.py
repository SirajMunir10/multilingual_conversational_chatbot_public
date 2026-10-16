"""Deterministic mortgage calculation service (PRD FR-12–FR-14, §6.2).

Eligibility and affordability follow the approved build logic in "Mortgage Eligibility Calculations"
(CBUAE Rulebook Article 3): two gates, three loan ceilings, one verdict.

All rules, thresholds, rates and fees are read from versioned tables in data/config
(mortgage_rules.json, fees.json, bank_products.json). The LLM never performs this math.
"""
import math
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, field_validator

from app.core.audit import AuditService
from app.core.config import load_config


def _rules() -> Dict[str, Any]:
    return load_config("mortgage_rules")


def _fees() -> Dict[str, Any]:
    return load_config("fees")


def _r(value: float) -> float:
    return round(float(value), 2)


class MortgageInputError(ValueError):
    """Raised for inputs that cannot be calculated; the message is shown to the user by the LLM."""


def _validate_rate(rate: Optional[float]) -> Optional[float]:
    if rate is None:
        return None
    cfg = _rules()["interest"]
    if not (cfg["min_rate_pct"] <= rate <= cfg["max_rate_pct"]):
        raise MortgageInputError(f"Interest rate must be between {cfg['min_rate_pct']}% and {cfg['max_rate_pct']}%.")
    return rate


def _validate_tenure(years: Optional[int]) -> Optional[int]:
    if years is None:
        return None
    cfg = _rules()["tenure"]
    if not (cfg["min_years"] <= years <= cfg["max_years"]):
        raise MortgageInputError(f"Tenure must be between {cfg['min_years']} and {cfg['max_years']} years.")
    return years


def normalise_residency(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = value.strip().lower().replace("-", "_").replace(" ", "_")
    if v in _rules()["residency_labels"]:
        return v
    if "non" in v and "resident" in v:
        return "non_resident"
    if "national" in v or "emirati" in v or "citizen" in v:
        return "uae_national"
    return "uae_resident"


def _employment(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return "self_employed" if value.lower().replace("-", "_").replace(" ", "_").startswith("self") else "salaried"


def _status(value: Optional[str]) -> str:
    return "off_plan" if value and "off" in value.lower() else "ready"


def _purpose(value: Optional[str]) -> str:
    return "investment" if value and "invest" in value.lower() else "home"


class EligibilityInput(BaseModel):
    """Inputs of the approved eligibility check (Mortgage Eligibility Calculations, 'Inputs to collect').
    Residency, age, employment type and income are always needed; everything else has a default that is
    reported back as an assumption. Property fields are used when the buyer has chosen a property."""
    residency: Optional[str] = None
    age: Optional[int] = Field(None, ge=0, le=120)
    employment_type: Optional[str] = None
    monthly_income: Optional[float] = Field(None, gt=0)
    monthly_debts: Optional[float] = Field(None, ge=0)
    credit_card_limits: Optional[float] = Field(None, ge=0)
    interest_rate: Optional[float] = None
    tenure_years: Optional[int] = None
    property_price: Optional[float] = Field(None, gt=0)
    valuation: Optional[float] = Field(None, gt=0)
    down_payment: Optional[float] = Field(None, ge=0)
    has_outstanding_mortgage: Optional[bool] = None
    property_status: Optional[str] = None
    purpose: Optional[str] = None
    expected_annual_rent: Optional[float] = Field(None, ge=0)
    emirate: Optional[str] = None
    agent_used: Optional[bool] = None
    # Older argument names, still accepted
    target_price: Optional[float] = Field(None, gt=0)
    first_property: Optional[bool] = None

    @field_validator("interest_rate")
    @classmethod
    def _rate(cls, v):
        return _validate_rate(v)

    @field_validator("tenure_years")
    @classmethod
    def _tenure(cls, v):
        return _validate_tenure(v)


AffordabilityInput = EligibilityInput


class EMIInput(BaseModel):
    loan_amount: Optional[float] = Field(None, gt=0)
    property_price: Optional[float] = Field(None, gt=0)
    down_payment: Optional[float] = Field(None, ge=0)
    residency: Optional[str] = None
    interest_rate: Optional[float] = None
    tenure_years: Optional[int] = None
    frequency: str = "monthly"
    has_outstanding_mortgage: Optional[bool] = None
    property_status: Optional[str] = None
    purpose: Optional[str] = None
    first_property: Optional[bool] = None

    @field_validator("interest_rate")
    @classmethod
    def _rate(cls, v):
        return _validate_rate(v)

    @field_validator("tenure_years")
    @classmethod
    def _tenure(cls, v):
        return _validate_tenure(v)

    @field_validator("frequency")
    @classmethod
    def _freq(cls, v):
        v = (v or "monthly").lower()
        if v not in ("monthly", "quarterly"):
            raise MortgageInputError("Payment frequency must be monthly or quarterly.")
        return v


class MortgageCalculationService:

    # ---------- shared rules ----------
    @classmethod
    def ltv_for(cls, residency: str, home: str = "first", property_status: str = "ready",
                value: Optional[float] = None) -> Tuple[float, str]:
        """First matching row of the LTV cap table (CBUAE Article 3). Returns (ltv, case)."""
        rules = _rules()
        threshold = rules["property_value_threshold_aed"]
        v = value if value is not None else 0.0
        tests = {"at_or_below": v <= threshold, "above": v > threshold, "below": v < threshold, "at_or_above": v >= threshold}
        for row in rules["ltv_table"]:
            if "property_status" in row and row["property_status"] != property_status:
                continue
            if "residency" in row and row["residency"] != residency:
                continue
            if "home" in row and row["home"] != home:
                continue
            if "value" in row and not tests[row["value"]]:
                continue
            ltv = row["ltv"] if "ltv" in row else rules["bank_settings"][row["ltv_setting"]]
            return ltv, row["case"]
        raise MortgageInputError("No lending rule matches this profile.")

    @staticmethod
    def instalment(principal: float, annual_rate_pct: float, years: int, periods_per_year: int = 12) -> float:
        r = annual_rate_pct / 100.0 / periods_per_year
        n = years * periods_per_year
        if r == 0:
            return principal / n
        return principal * r / (1 - (1 + r) ** -n)

    @staticmethod
    def present_value(payment: float, annual_rate_pct: float, years: int) -> float:
        r = annual_rate_pct / 100.0 / 12
        n = years * 12
        if r == 0:
            return payment * n
        return payment * (1 - (1 + r) ** -n) / r

    @classmethod
    def _check_income(cls, income: float) -> None:
        limits = _rules().get("input_limits", {})
        low, high = limits.get("min_monthly_income_aed"), limits.get("max_monthly_income_aed")
        if (low is not None and income < low) or (high is not None and income > high):
            raise MortgageInputError("The monthly income looks missing or implausible. Ask the user for their gross monthly income in AED.")

    @classmethod
    def _disclaimers(cls) -> Dict[str, str]:
        return _rules()["disclaimers"]

    # ---------- eligibility check (FR-12a/b; approved build logic: 2 gates, 3 ceilings) ----------
    @classmethod
    def assess(cls, inputs: EligibilityInput, calculation_type: str = "eligibility") -> Dict[str, Any]:
        rules = _rules()
        bank, cb = rules["bank_settings"], rules["central_bank"]
        residency = normalise_residency(inputs.residency)
        employment = _employment(inputs.employment_type)
        price = inputs.property_price or inputs.target_price
        has_mortgage = inputs.has_outstanding_mortgage
        if has_mortgage is None and inputs.first_property is not None:
            has_mortgage = not inputs.first_property

        missing = [name for name, val in (("residency (UAE national, expat resident or non-resident)", residency), ("age", inputs.age),
                                          ("employment type (salaried or self-employed)", employment),
                                          ("gross monthly income", inputs.monthly_income)) if val is None]
        if price is not None and has_mortgage is None:
            missing.append("whether they have an outstanding mortgage on another property")
        if missing:
            raise MortgageInputError("Missing: " + "; ".join(missing) + ". Ask the user for all of these in one short message.")
        cls._check_income(inputs.monthly_income)

        assumptions: List[str] = []
        rate = inputs.interest_rate if inputs.interest_rate is not None else rules["interest"]["benchmark_rate_pct"]
        if inputs.interest_rate is None:
            assumptions.append(f"{rate}% interest rate (benchmark)")
        stress_rate = rate + bank["stress_test_addon_pct"]
        requested_term = inputs.tenure_years or rules["tenure"]["default_years"]
        if inputs.tenure_years is None:
            assumptions.append(f"{requested_term}-year term requested")
        instalments = inputs.monthly_debts or 0.0
        cards = inputs.credit_card_limits or 0.0
        if inputs.monthly_debts is None:
            assumptions.append("no existing loan instalments")
        if inputs.credit_card_limits is None:
            assumptions.append("no credit card limits")
        status, purpose = _status(inputs.property_status), _purpose(inputs.purpose)
        if price is not None:
            if inputs.property_status is None:
                assumptions.append("ready property")
            if inputs.purpose is None:
                assumptions.append("home to live in")

        # Income counted for the debt limit: salary plus rent (investment only, after the vacancy deduction)
        salary = inputs.monthly_income
        rent = 0.0
        if purpose == "investment" and inputs.expected_annual_rent:
            rent = inputs.expected_annual_rent * (12 - cb["rent_vacancy_months"]) / 12 / 12
        income = salary + rent
        debts = instalments + bank["credit_card_debt_pct_of_limit"] * cards

        gates: List[Dict[str, Any]] = []
        notes: List[str] = []
        # 1. Applicant gate
        applicant_ok = inputs.age >= bank["min_age"] and salary >= bank["min_monthly_income_aed"]
        gates.append({"gate": "applicant", "result": "pass" if applicant_ok else "fail",
                      "rule": f"Age {bank['min_age']} or over and gross monthly income at least AED {bank['min_monthly_income_aed']:,} "
                              f"(banks range from AED {bank['min_monthly_income_range_aed'][0]:,} to {bank['min_monthly_income_range_aed'][1]:,})"})
        if residency == "non_resident":
            notes.append(bank["non_resident_note"])
        # 2. Term gate
        max_age = bank["max_age_at_last_repayment"][employment]
        years_left = max_age - inputs.age
        term = int(math.floor(min(requested_term, cb["max_term_years"], years_left)))
        shortened = years_left < min(requested_term, cb["max_term_years"])
        term_result = "fail" if term < 1 else ("review" if shortened else "pass")
        gates.append({"gate": "term", "result": term_result, "term_years": max(term, 0),
                      "rule": f"Loan must end by age {max_age} ({employment.replace('_', '-')}); maximum {cb['max_term_years']} years"})
        # 3. Debt-burden room
        room = max(0.0, cb["debt_burden_max_ratio"] * income - debts)
        gates.append({"gate": "debt_burden", "result": "pass" if room > 0 else "fail",
                      "rule": f"All monthly debts including the new instalment within {round(cb['debt_burden_max_ratio'] * 100)}% of income"})

        result: Dict[str, Any] = {
            "calculation_type": calculation_type,
            "label": cls._disclaimers()["label"],
            "disclaimer": cls._disclaimers()["calculator"],
            "rule_version": rules["version"],
            "inputs": {"residency": rules["residency_labels"][residency], "age": inputs.age, "employment_type": employment,
                       "monthly_income_aed": salary, "monthly_loan_instalments_aed": instalments, "credit_card_limits_aed": cards,
                       "interest_rate_pct": rate, "tenure_years": requested_term, "property_price_aed": price,
                       "property_status": status, "purpose": purpose, "has_outstanding_mortgage": has_mortgage},
            "gates": gates,
            "notes": notes,
            "assumptions": assumptions,
            "interest_rate_pct": rate,
            "stress_rate_pct": stress_rate,
            "term_years": max(term, 0),
            "income": {"salary_aed": _r(salary), "recognised_rent_aed": _r(rent), "total_aed": _r(income)},
            "existing_debts_aed": _r(debts),
        }

        failed = next((g for g in gates if g["result"] == "fail"), None)
        if failed:
            reasons = {
                "applicant": f"Age must be at least {bank['min_age']} and gross monthly income at least AED {bank['min_monthly_income_aed']:,}.",
                "term": f"No full year is left before the maximum age of {max_age} at the last repayment.",
                "debt_burden": "Existing debts already use the 50% debt-burden limit, so there is no room for a mortgage instalment.",
            }
            result.update({"verdict": "not_eligible", "failed_gate": failed["gate"],
                           "reason": reasons[failed["gate"]] + " No loan amount can pass until this is fixed.",
                           "eligible_loan_aed": 0.0, "max_loan_aed": 0.0, "max_property_price_aed": 0.0})
            return result

        # Ceilings
        ceilings = {
            "debt_burden": cls.present_value(room, stress_rate, term),
            "income_multiple": 12 * salary * cb["income_multiple"]["uae_national" if residency == "uae_national" else "expat"],
        }
        ltv = ltv_case = value = None
        if price is not None:
            value = min(price, inputs.valuation) if inputs.valuation else price
            home = "second" if (has_mortgage or purpose == "investment") else "first"
            ltv, ltv_case = cls.ltv_for(residency, home, status, value)
            ceilings["ltv"] = value * ltv
        tightest = min(ceilings, key=ceilings.get)
        eligible = ceilings[tightest]

        if price is not None:
            if inputs.down_payment is None:
                down = value * (1 - ltv)
                assumptions.append(f"minimum down payment ({round((1 - ltv) * 100)}%)")
            else:
                down = inputs.down_payment
                if down >= value:
                    raise MortgageInputError("The down payment must be below the property value.")
            requested = value - down
            loan = min(requested, eligible)
            if requested <= eligible + 0.5:
                verdict = "eligible"
                reason = "The requested loan passes every gate."
                if term_result == "review":
                    reason += " The term was shortened by the maximum age, so an underwriter should review."
            else:
                verdict = "eligible_lower"
                reason = (f"The requested loan is above the eligible loan by AED {round(requested - eligible):,}. "
                          f"The tightest limit is the {tightest.replace('_', ' ')}.")
            result.update({"requested_loan_aed": _r(requested), "shortfall_aed": _r(max(0.0, requested - eligible)),
                           "property_value_aed": _r(value), "down_payment_aed": _r(down),
                           "ltv_applied_pct": _r(ltv * 100), "ltv_case": ltv_case, "max_property_price_aed": _r(value)})
            cash_price, cash_down = value, down
        else:
            loan = eligible
            verdict, reason = "can_borrow", f"The buyer can borrow up to AED {round(eligible):,}."
            implied = cls.implied_price(eligible, residency)
            result.update({"implied_property_price_aed": _r(implied), "max_property_price_aed": _r(implied)})
            cash_price, cash_down = implied, max(0.0, implied - eligible)

        instalment = cls.instalment(loan, rate, term) if loan > 0 else 0.0
        stress_instalment = cls.instalment(loan, stress_rate, term) if loan > 0 else 0.0
        result.update({
            "verdict": verdict, "reason": reason,
            "eligible_loan_aed": _r(eligible), "max_loan_aed": _r(eligible), "loan_amount_aed": _r(loan),
            "ceilings_aed": {k: _r(v) for k, v in ceilings.items()}, "tightest_limit": tightest,
            "instalment_aed": _r(instalment), "stress_instalment_aed": _r(stress_instalment),
            "debt_burden": {"max_ratio_pct": cb["debt_burden_max_ratio"] * 100,
                            "after_loan_pct": _r((debts + instalment) / income * 100) if income else None,
                            "within_cap": (debts + instalment) <= cb["debt_burden_max_ratio"] * income + 0.5},
            "cash_upfront": cls.cash_upfront(cash_price, cash_down, loan, inputs.emirate, inputs.agent_used),
        })
        if inputs.agent_used is None:
            assumptions.append("an agent is used")
        return result

    @classmethod
    def implied_price(cls, loan: float, residency: str) -> float:
        """Price the eligible loan supports: loan ÷ first-home LTV; above AED 5M use the higher-value LTV,
        and if that falls below AED 5M show AED 5M (approved build logic)."""
        threshold = _rules()["property_value_threshold_aed"]
        low, _ = cls.ltv_for(residency, "first", "ready", 0.0)
        price = loan / low
        if price > threshold:
            high, _ = cls.ltv_for(residency, "first", "ready", threshold * 10)
            price = max(loan / high, threshold)
        return price

    @classmethod
    def cash_upfront(cls, price: float, down_payment: float, loan: float, emirate: Optional[str] = None,
                     agent_used: Optional[bool] = None) -> Dict[str, Any]:
        """Cash needed upfront, each item with how it is worked out (approved build logic; fee rates from fees.json)."""
        fees, rules = _fees(), _rules()
        em = cls._emirate(emirate)
        commission = 0.0
        if agent_used is not False:
            commission = price * fees["agent_commission_pct"] * ((1 + fees["vat_rate"]) if fees.get("agent_commission_vat_applies") else 1)
        arrangement_max = loan * rules["upfront_costs"]["arrangement_fee_max_pct_of_loan"]
        items = [
            {"item": "down_payment", "amount_aed": _r(down_payment), "how": "The amount the buyer pays"},
            {"item": "transfer_fee", "amount_aed": _r(price * em["registration_fee_pct"]), "how": f"{em['registration_fee_pct'] * 100:g}% of the property price ({em['label']})"},
            {"item": "mortgage_registration", "amount_aed": _r(loan * fees["mortgage"]["registration_fee_pct_of_loan"]), "how": f"{fees['mortgage']['registration_fee_pct_of_loan'] * 100:g}% of the loan"},
            {"item": "bank_arrangement_fee", "min_aed": 0.0, "max_aed": _r(arrangement_max), "how": "Up to 1% of the loan"},
        ]
        if agent_used is not False:
            items.append({"item": "agent_commission", "amount_aed": _r(commission), "how": f"{fees['agent_commission_pct'] * 100:g}% of the price + VAT, if an agent is used"})
        fixed = sum(i.get("amount_aed", 0.0) for i in items)
        return {"items": items, "total_min_aed": _r(fixed), "total_max_aed": _r(fixed + arrangement_max),
                "note": rules["upfront_costs"]["note"]}

    @classmethod
    def calc_affordability(cls, inputs: EligibilityInput, session_id: Optional[str] = None, user_id: Optional[str] = None) -> Dict[str, Any]:
        """How much can I borrow / afford: the eligibility check without a property ('Can borrow up to X'),
        or against a target price when the user has one."""
        result = cls.assess(inputs, "affordability")
        AuditService.log_event("mortgage_calculation", "calc_affordability", "mortgage_service", session_id=session_id, user_id=user_id,
                               details={"inputs": result["inputs"], "verdict": result["verdict"], "eligible_loan": result.get("eligible_loan_aed"),
                                        "rule_version": result["rule_version"]})
        return result

    @classmethod
    def check_eligibility(cls, inputs: EligibilityInput, session_id: Optional[str] = None, user_id: Optional[str] = None) -> Dict[str, Any]:
        result = cls.assess(inputs, "eligibility")
        AuditService.log_event("mortgage_calculation", "check_eligibility", "mortgage_service", session_id=session_id, user_id=user_id,
                               details={"inputs": result["inputs"], "verdict": result["verdict"], "eligible_loan": result.get("eligible_loan_aed"),
                                        "tightest_limit": result.get("tightest_limit"), "rule_version": result["rule_version"]})
        return result

    # ---------- EMI (FR-12c) ----------
    @classmethod
    def calc_emi(cls, inputs: EMIInput, session_id: Optional[str] = None, user_id: Optional[str] = None) -> Dict[str, Any]:
        rules = _rules()
        residency = normalise_residency(inputs.residency) or "uae_resident"
        rate = inputs.interest_rate if inputs.interest_rate is not None else rules["interest"]["benchmark_rate_pct"]
        years = inputs.tenure_years or rules["tenure"]["default_years"]
        assumptions: List[str] = []
        if inputs.interest_rate is None:
            assumptions.append(f"{rate}% interest rate (benchmark)")
        if inputs.tenure_years is None:
            assumptions.append(f"{years}-year term")

        down_payment = inputs.down_payment
        ltv_applied = None
        if inputs.loan_amount is not None:
            loan = inputs.loan_amount
        elif inputs.property_price is not None:
            if inputs.residency is None:
                assumptions.append(rules["residency_labels"][residency])
            has_mortgage = inputs.has_outstanding_mortgage
            if has_mortgage is None and inputs.first_property is not None:
                has_mortgage = not inputs.first_property
            home = "second" if (has_mortgage or _purpose(inputs.purpose) == "investment") else "first"
            ltv_applied, _ = cls.ltv_for(residency, home, _status(inputs.property_status), inputs.property_price)
            min_down = inputs.property_price * (1 - ltv_applied)
            if down_payment is None:
                down_payment = min_down
                assumptions.append(f"minimum {round((1 - ltv_applied) * 100)}% down payment")
            elif down_payment < min_down - 0.5:
                raise MortgageInputError(
                    f"The minimum down payment for this profile is {round((1 - ltv_applied) * 100)}% (AED {round(min_down):,}).")
            loan = inputs.property_price - down_payment
        else:
            raise MortgageInputError("Please provide a loan amount or a property price.")
        if loan <= 0:
            raise MortgageInputError("The loan amount must be greater than zero.")

        periods = 12 if inputs.frequency == "monthly" else 4
        payment = cls.instalment(loan, rate, years, periods)
        total = payment * years * periods
        interest = total - loan
        schedule, balance = [], loan
        r = rate / 100.0 / periods
        for year in range(1, min(years, 5) + 1):
            paid_interest = paid_principal = 0.0
            for _ in range(periods):
                i = balance * r
                p = payment - i
                paid_interest += i
                paid_principal += p
                balance = max(0.0, balance - p)
            schedule.append({"year": year, "principal_paid_aed": _r(paid_principal), "interest_paid_aed": _r(paid_interest),
                             "remaining_balance_aed": _r(balance)})

        stress_rate = rate + rules["bank_settings"]["stress_test_addon_pct"]
        result = {
            "calculation_type": "emi",
            "label": cls._disclaimers()["label"],
            "disclaimer": cls._disclaimers()["calculator"],
            "rule_version": rules["version"],
            "property_price_aed": inputs.property_price,
            "down_payment_aed": _r(down_payment) if down_payment is not None else None,
            "ltv_applied_pct": _r(ltv_applied * 100) if ltv_applied is not None else None,
            "loan_amount_aed": _r(loan),
            "interest_rate_pct": rate,
            "tenure_years": years,
            "frequency": inputs.frequency,
            "instalment_aed": _r(payment),
            "monthly_equivalent_aed": _r(payment if periods == 12 else payment / 3),
            "stress_rate_pct": stress_rate,
            "stress_instalment_aed": _r(cls.instalment(loan, stress_rate, years)),
            "total_repayment_aed": _r(total),
            "total_interest_aed": _r(interest),
            "principal_share_pct": _r(loan / total * 100),
            "interest_share_pct": _r(interest / total * 100),
            "amortization_schedule": schedule,
            "assumptions": assumptions,
        }
        AuditService.log_event("mortgage_calculation", "calc_emi", "mortgage_service", session_id=session_id, user_id=user_id,
                               details={"loan": result["loan_amount_aed"], "rate": rate, "years": years, "instalment": result["instalment_aed"]})
        return result

    @classmethod
    def _emirate(cls, emirate: Optional[str]) -> Dict[str, Any]:
        fees = _fees()
        key = (emirate or fees["default_emirate"]).strip().lower().replace(" ", "_")
        if key not in fees["emirates"]:
            matches = [k for k, v in fees["emirates"].items() if v["label"].lower() == (emirate or "").strip().lower()]
            key = matches[0] if matches else fees["default_emirate"]
        return fees["emirates"][key]

    # ---------- purchase costs (KB Art. 2) ----------
    @classmethod
    def calc_purchase_costs(cls, property_price: float, emirate: Optional[str] = None, loan_amount: Optional[float] = None,
                            resale: bool = True, session_id: Optional[str] = None, audit: bool = True) -> Dict[str, Any]:
        if property_price <= 0:
            raise MortgageInputError("Property price must be greater than zero.")
        fees = _fees()
        em = cls._emirate(emirate)
        items: List[Dict[str, Any]] = [{"item": em["registration_label"], "amount_aed": _r(property_price * em["registration_fee_pct"])}]
        if em.get("admin_fee_aed"):
            items.append({"item": "Admin fee", "amount_aed": em["admin_fee_aed"]})
        if em.get("trustee_fee"):
            t = em["trustee_fee"]
            items.append({"item": "Trustee office fee", "amount_aed": t["above_aed"] if property_price > t["threshold_aed"] else t["at_or_below_aed"]})
        if em.get("title_deed_fee_aed"):
            items.append({"item": "Title deed fee", "amount_aed": em["title_deed_fee_aed"]})
        commission = property_price * fees["agent_commission_pct"]
        if fees.get("agent_commission_vat_applies"):
            commission *= 1 + fees["vat_rate"]
        items.append({"item": "Agent commission (incl. VAT)", "amount_aed": _r(commission)})
        ranges: List[Dict[str, Any]] = []
        if loan_amount:
            items.append({"item": "Mortgage registration", "amount_aed": _r(loan_amount * fees["mortgage"]["registration_fee_pct_of_loan"])})
            v = fees["mortgage"]["valuation_fee_aed"]
            ranges.append({"item": "Bank valuation", "min_aed": v["min"], "max_aed": v["max"]})
            ranges.append({"item": "Bank arrangement fee (up to 1% of the loan)", "min_aed": 0.0,
                           "max_aed": _r(loan_amount * _rules()["upfront_costs"]["arrangement_fee_max_pct_of_loan"])})
        if resale and fees.get("resale_only"):
            n = fees["resale_only"]["developer_noc_aed"]
            ranges.append({"item": "Developer NOC (resale)", "min_aed": n["min"], "max_aed": n["max"]})
        fixed_total = sum(i["amount_aed"] for i in items)
        result = {
            "calculation_type": "purchase_costs",
            "emirate": em["label"],
            "property_price_aed": property_price,
            "items": items,
            "variable_items": ranges,
            "total_fixed_aed": _r(fixed_total),
            "total_range_aed": {"min": _r(fixed_total + sum(r["min_aed"] for r in ranges)), "max": _r(fixed_total + sum(r["max_aed"] for r in ranges))},
            "total_pct_of_price": _r(fixed_total / property_price * 100),
            "fee_table_version": fees["version"],
            "note": "Fees per XOTO knowledge base; verify with the land department.",
        }
        if audit:
            AuditService.log_event("mortgage_calculation", "calc_purchase_costs", "mortgage_service", session_id=session_id,
                                   details={"price": property_price, "emirate": em["label"], "total": result["total_fixed_aed"]})
        return result

    # ---------- rule table (FR-13 internal rule tables) ----------
    @classmethod
    def lending_rules(cls, residency: Optional[str] = None) -> Dict[str, Any]:
        rules = _rules()
        bank, cb = rules["bank_settings"], rules["central_bank"]
        key = normalise_residency(residency)
        table = [{"case": row["case"], "max_ltv_pct": round((row["ltv"] if "ltv" in row else bank[row["ltv_setting"]]) * 100),
                  "min_down_payment_pct": round((1 - (row["ltv"] if "ltv" in row else bank[row["ltv_setting"]])) * 100)}
                 for row in rules["ltv_table"] if not key or row.get("residency") in (None, key)]
        return {"rule_version": rules["version"], "status": rules["status"], "source": rules["sources"],
                "ltv_table_first_match_wins": table, "threshold_note": rules["threshold_note"], "first_home_note": rules["first_home_note"],
                "non_resident_note": bank["non_resident_note"],
                "debt_burden_limit_pct": cb["debt_burden_max_ratio"] * 100,
                "debt_burden_rule": "All monthly debts (loan instalments + 5% of credit card limits) plus the new instalment must stay within 50% of gross income.",
                "stress_test": f"Maximum loan is worked out at the rate + {bank['stress_test_addon_pct']:g} percentage points (allowed range 2-4).",
                "income_multiple": f"Loan at most {cb['income_multiple']['uae_national']}x annual income for UAE nationals, {cb['income_multiple']['expat']}x for expats.",
                "investment_rent": f"For an investment property, rent counts as income after removing {cb['rent_vacancy_months']} months a year for vacancy.",
                "min_age": bank["min_age"], "min_monthly_income_aed": bank["min_monthly_income_aed"],
                "min_monthly_income_range_aed": bank["min_monthly_income_range_aed"],
                "max_age_at_last_repayment": bank["max_age_at_last_repayment"], "max_term_years": cb["max_term_years"],
                "benchmark_rate_pct": rules["interest"]["benchmark_rate_pct"], "application_documents": rules["application_documents"]}

    # ---------- products and offers (FR-12d, PRD §6.1 getMortgageProducts) ----------
    @classmethod
    def get_products(cls, bank: Optional[str] = None, finance_type: Optional[str] = None, rate_type: Optional[str] = None,
                     salary: Optional[float] = None, session_id: Optional[str] = None) -> Dict[str, Any]:
        table = load_config("bank_products")
        products = table["products"]
        if bank:
            products = [p for p in products if bank.lower() in p["bank_name"].lower()]
        if finance_type:
            products = [p for p in products if finance_type.lower() in p["finance_type"].lower()]
        if rate_type:
            products = [p for p in products if rate_type.lower() in p["rate_type"].lower()]
        if salary is not None:
            products = [p for p in products if salary >= p["min_salary_aed"]]
        products = sorted(products, key=lambda p: p["interest_rate"])
        AuditService.log_event("mortgage_rules_query", "get_mortgage_products", "bank_products", session_id=session_id,
                               details={"bank": bank, "finance_type": finance_type, "rate_type": rate_type, "count": len(products)})
        return {"status": table["status"], "table_version": table["version"], "note": table["note"], "count": len(products),
                "products": [{k: p[k] for k in ("bank_name", "rate_type", "finance_type", "interest_rate", "max_ltv_national", "max_ltv_expat",
                                                "min_salary_aed", "max_tenure_years", "processing_fee_pct")} for p in products]}

    @classmethod
    def estimate_offers(cls, loan_amount: float, monthly_income: Optional[float] = None, residency: Optional[str] = None,
                        tenure_years: Optional[int] = None, finance_type: Optional[str] = None, limit: int = 3,
                        session_id: Optional[str] = None) -> Dict[str, Any]:
        if loan_amount <= 0:
            raise MortgageInputError("Loan amount must be greater than zero.")
        rules = _rules()
        years = _validate_tenure(tenure_years) or rules["tenure"]["default_years"]
        residency_key = normalise_residency(residency)
        products = cls.get_products(finance_type=finance_type, salary=monthly_income, session_id=session_id)
        offers = []
        for p in products["products"][:limit]:
            term = min(years, p["max_tenure_years"])
            payment = cls.instalment(loan_amount, p["interest_rate"], term)
            offers.append({"bank_name": p["bank_name"], "product": p["rate_type"], "finance_type": p["finance_type"],
                           "indicative_rate_pct": p["interest_rate"], "monthly_payment_aed": _r(payment), "tenure_years": term,
                           "processing_fee_aed": _r(loan_amount * p["processing_fee_pct"] / 100)})
        rates = [o["indicative_rate_pct"] for o in offers]
        result = {"calculation_type": "offers", "label": cls._disclaimers()["label"], "disclaimer": cls._disclaimers()["calculator"],
                  "loan_amount_aed": loan_amount, "rate_table_status": products["status"], "offers": offers,
                  "indicative_rate_range_pct": [min(rates), max(rates)] if rates else None,
                  "residency": rules["residency_labels"][residency_key] if residency_key else None}
        AuditService.log_event("mortgage_calculation", "estimate_offers", "mortgage_service", session_id=session_id,
                               details={"loan": loan_amount, "offers": len(offers)})
        return result
