"""The configuration items an admin can edit, version and publish (PRD FR-25, FR-27, FR-29).

Each item has a seed (the built-in file, also the fallback), the permission needed to change it (FR-30) and a
validator. A version that fails validation is never published, and an invalid published version is ignored at
start-up in favour of the seed, so a bad edit cannot stop XO from working."""
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Tuple

from app.admin import permissions as P
from app.core.config import builtin_config
from app.services import escalation, prompt_profile

Number = (int, float)


@dataclass(frozen=True)
class ConfigItem:
    name: str
    label: str
    permission: str
    seed: Callable[[], Any]
    validate: Callable[[Any], List[str]]


def _get(data: Any, path: str) -> Any:
    for part in path.split("."):
        if not isinstance(data, dict) or part not in data:
            raise KeyError(path)
        data = data[part]
    return data


def _check_numbers(data: Any, bounds: List[Tuple[str, str, float, float]]) -> List[str]:
    errors = []
    for path, label, low, high in bounds:
        try:
            value = _get(data, path)
        except KeyError:
            errors.append(f"{label} is missing.")
            continue
        if isinstance(value, bool) or not isinstance(value, Number):
            errors.append(f"{label} must be a number.")
        elif not low <= value <= high:
            errors.append(f"{label} must be between {low:g} and {high:g} (it is {value:g}).")
    return errors


# ---------------------------------------------------------------------------------------------------------------------
# Lending rules (mortgage_rules.json): the approved build logic's settings. Conditions of the loan-to-value table are
# part of that logic and stay fixed; its percentages can change.
# ---------------------------------------------------------------------------------------------------------------------

RULE_BOUNDS = [
    ("bank_settings.min_age", "Minimum age", 18, 30),
    ("bank_settings.min_monthly_income_aed", "Minimum monthly income (AED)", 0, 1_000_000),
    ("bank_settings.max_age_at_last_repayment.salaried", "Maximum age at last repayment, salaried", 50, 80),
    ("bank_settings.max_age_at_last_repayment.self_employed", "Maximum age at last repayment, self-employed", 50, 80),
    ("bank_settings.stress_test_addon_pct", "Stress-test add-on (percentage points)", 0, 10),
    ("bank_settings.credit_card_debt_pct_of_limit", "Card debt counted as share of the limit", 0, 0.2),
    ("bank_settings.non_resident_ltv", "Non-resident loan-to-value", 0, 1),
    ("central_bank.debt_burden_max_ratio", "Maximum debt burden", 0.1, 0.9),
    ("central_bank.max_term_years", "Maximum term (years)", 1, 35),
    ("central_bank.income_multiple.uae_national", "Income multiple, UAE national", 1, 20),
    ("central_bank.income_multiple.expat", "Income multiple, expat", 1, 20),
    ("central_bank.rent_vacancy_months", "Rent vacancy (months)", 0, 12),
    ("property_value_threshold_aed", "Property value threshold (AED)", 100_000, 100_000_000),
    ("interest.benchmark_rate_pct", "Benchmark interest rate (%)", 0, 20),
    ("interest.min_rate_pct", "Lowest accepted rate (%)", 0, 20),
    ("interest.max_rate_pct", "Highest accepted rate (%)", 1, 50),
    ("tenure.default_years", "Default term (years)", 1, 35),
    ("tenure.min_years", "Shortest term (years)", 1, 35),
    ("tenure.max_years", "Longest term (years)", 1, 35),
    ("upfront_costs.arrangement_fee_max_pct_of_loan", "Bank arrangement fee, share of the loan", 0, 0.05),
    ("input_limits.min_monthly_income_aed", "Lowest income XO accepts (AED)", 0, 1_000_000),
    ("input_limits.max_monthly_income_aed", "Highest income XO accepts (AED)", 1_000, 1_000_000_000),
]
LTV_CONDITION_KEYS = ("order", "property_status", "residency", "home", "value", "ltv_setting")


def validate_rules(data: Any) -> List[str]:
    if not isinstance(data, dict):
        return ["The lending rules are not in the expected format."]
    errors = _check_numbers(data, RULE_BOUNDS)
    if errors:
        return errors
    interest, tenure = data["interest"], data["tenure"]
    if not interest["min_rate_pct"] <= interest["benchmark_rate_pct"] <= interest["max_rate_pct"]:
        errors.append("The benchmark rate must lie between the lowest and highest accepted rates.")
    if not tenure["min_years"] <= tenure["default_years"] <= tenure["max_years"]:
        errors.append("The default term must lie between the shortest and longest terms.")
    if tenure["max_years"] > data["central_bank"]["max_term_years"]:
        errors.append("The longest term cannot exceed the Central Bank maximum term.")
    if data["input_limits"]["min_monthly_income_aed"] >= data["input_limits"]["max_monthly_income_aed"]:
        errors.append("The lowest accepted income must be below the highest.")
    seed_rows = builtin_config("mortgage_rules")["ltv_table"]
    rows = data.get("ltv_table")
    if not isinstance(rows, list) or len(rows) != len(seed_rows):
        return errors + ["The loan-to-value table must keep its rows (they come from the approved build logic)."]
    for row, base in zip(rows, seed_rows):
        if any(row.get(k) != base.get(k) for k in LTV_CONDITION_KEYS):
            errors.append(f"Row {base['order']} of the loan-to-value table: only the percentage and description can change.")
        elif "ltv" in base:
            ltv = row.get("ltv")
            if isinstance(ltv, bool) or not isinstance(ltv, Number) or not 0 < ltv <= 1:
                errors.append(f"Row {base['order']} of the loan-to-value table needs a value above 0% and at most 100%.")
        if not str(row.get("case") or "").strip():
            errors.append(f"Row {base['order']} of the loan-to-value table needs a description.")
    return errors


# ---------------------------------------------------------------------------------------------------------------------
# Fees (fees.json)
# ---------------------------------------------------------------------------------------------------------------------

def validate_fees(data: Any) -> List[str]:
    if not isinstance(data, dict):
        return ["The fees are not in the expected format."]
    errors = _check_numbers(data, [
        ("vat_rate", "VAT rate", 0, 0.2),
        ("agent_commission_pct", "Agent commission", 0, 0.1),
        ("mortgage.registration_fee_pct_of_loan", "Mortgage registration fee, share of the loan", 0, 0.02),
        ("mortgage.valuation_fee_aed.min", "Valuation fee, lowest (AED)", 0, 50_000),
        ("mortgage.valuation_fee_aed.max", "Valuation fee, highest (AED)", 0, 50_000),
        ("resale_only.developer_noc_aed.min", "Developer NOC, lowest (AED)", 0, 100_000),
        ("resale_only.developer_noc_aed.max", "Developer NOC, highest (AED)", 0, 100_000),
        ("early_settlement_fee_pct.min", "Early settlement fee, lowest", 0, 0.1),
        ("early_settlement_fee_pct.max", "Early settlement fee, highest", 0, 0.1),
    ])
    if errors:
        return errors
    for key, label in (("mortgage.valuation_fee_aed", "Valuation fee"), ("resale_only.developer_noc_aed", "Developer NOC"),
                       ("early_settlement_fee_pct", "Early settlement fee")):
        band = _get(data, key)
        if band["min"] > band["max"]:
            errors.append(f"{label}: the lowest value cannot be above the highest.")
    seed = builtin_config("fees")
    emirates = data.get("emirates")
    if not isinstance(emirates, dict) or set(emirates) != set(seed["emirates"]):
        return errors + ["Every emirate in the fee table must stay (emirates cannot be added or removed here)."]
    if data.get("default_emirate") not in emirates:
        errors.append("The default emirate must be one of the emirates.")
    for code, fee in emirates.items():
        label = seed["emirates"][code]["label"]
        errors += _check_numbers(fee, [
            ("registration_fee_pct", f"{label}: registration fee", 0, 0.1),
            ("admin_fee_aed", f"{label}: admin fee (AED)", 0, 50_000),
            ("title_deed_fee_aed", f"{label}: title deed fee (AED)", 0, 50_000),
        ])
        if fee.get("trustee_fee") is not None:
            errors += _check_numbers(fee["trustee_fee"], [
                ("threshold_aed", f"{label}: trustee fee threshold (AED)", 0, 100_000_000),
                ("above_aed", f"{label}: trustee fee above the threshold (AED)", 0, 50_000),
                ("at_or_below_aed", f"{label}: trustee fee at or below the threshold (AED)", 0, 50_000),
            ])
    return errors


# ---------------------------------------------------------------------------------------------------------------------
# Bank products (bank_products.json): indicative products, rows can be added and removed.
# ---------------------------------------------------------------------------------------------------------------------

PRODUCT_TEXT = ("product_id", "bank_name", "rate_type", "finance_type")
PRODUCT_NUMBERS = [
    ("interest_rate", "interest rate (%)", 0, 20),
    ("max_ltv_national", "maximum loan-to-value, UAE national (%)", 0, 100),
    ("max_ltv_expat", "maximum loan-to-value, expat (%)", 0, 100),
    ("min_salary_aed", "minimum salary (AED)", 0, 1_000_000),
    ("max_tenure_years", "maximum term (years)", 1, 35),
    ("processing_fee_pct", "processing fee (%)", 0, 5),
    ("valuation_fee_aed", "valuation fee (AED)", 0, 50_000),
    ("early_settlement_fee_pct", "early settlement fee (%)", 0, 10),
]


def validate_products(data: Any) -> List[str]:
    if not isinstance(data, dict) or not isinstance(data.get("products"), list):
        return ["The bank products are not in the expected format."]
    errors: List[str] = []
    ids = set()
    for i, product in enumerate(data["products"], 1):
        name = str(product.get("bank_name") or f"Product {i}")
        for key in PRODUCT_TEXT:
            if not str(product.get(key) or "").strip():
                errors.append(f"{name}: {key.replace('_', ' ')} is required.")
        if product.get("finance_type") not in (None, "conventional", "islamic"):
            errors.append(f"{name}: finance type must be conventional or islamic.")
        if product.get("product_id") in ids:
            errors.append(f"{name}: the product id {product.get('product_id')} is used twice.")
        ids.add(product.get("product_id"))
        errors += _check_numbers(product, [(k, f"{name}: {label}", lo, hi) for k, label, lo, hi in PRODUCT_NUMBERS])
    return errors


# ---------------------------------------------------------------------------------------------------------------------
# Canned replies (the "messages" of locales.json) for every language.
# ---------------------------------------------------------------------------------------------------------------------

def seed_messages() -> Dict[str, Dict[str, str]]:
    return {code: dict(loc["messages"]) for code, loc in builtin_config("locales")["locales"].items()}


def validate_messages(data: Any) -> List[str]:
    if not isinstance(data, dict):
        return ["The canned replies are not in the expected format."]
    seed = seed_messages()
    errors = []
    for code, messages in seed.items():
        mine = data.get(code)
        if not isinstance(mine, dict) or set(mine) != set(messages):
            errors.append(f"The {code} replies must keep the same set of messages.")
            continue
        for key, text in mine.items():
            if not str(text or "").strip():
                errors.append(f"The {code} reply “{key}” cannot be empty.")
            elif len(str(text)) > 500:
                errors.append(f"The {code} reply “{key}” is longer than 500 characters.")
    if set(data) - set(seed):
        errors.append("Only the supported languages can have replies.")
    return errors


ITEMS: Dict[str, ConfigItem] = {item.name: item for item in (
    ConfigItem("mortgage_rules", "Lending rules", P.RULES_EDIT, lambda: builtin_config("mortgage_rules"), validate_rules),
    ConfigItem("fees", "Fees", P.RULES_EDIT, lambda: builtin_config("fees"), validate_fees),
    ConfigItem("bank_products", "Bank products", P.RULES_EDIT, lambda: builtin_config("bank_products"), validate_products),
    ConfigItem(prompt_profile.PROFILE_ITEM, "XO's instructions", P.PROMPTS_EDIT, prompt_profile.builtin_profile, prompt_profile.validate),
    ConfigItem("messages", "Canned replies", P.PROMPTS_EDIT, seed_messages, validate_messages),
    ConfigItem(escalation.ITEM, "Escalation rules", P.ESCALATION_EDIT, escalation.builtin_rules, escalation.validate),
)}
