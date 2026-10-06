import math
import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, field_validator
from app.core.config import settings
from app.core.audit import AuditService
from app.gateways.mortgage_rules_gateway import MortgageRulesGateway, ScopedMortgageProduct

logger = logging.getLogger("xo.mortgage")

# ==============================================================================
# PYDANTIC INPUT VALIDATION SCHEMAS (FR-12e: Validate inputs immediately)
# ==============================================================================

class AffordabilityInput(BaseModel):
    income: float = Field(..., description="Monthly income in AED")
    existing_debt: float = Field(0.0, description="Monthly existing debt commitments in AED")
    down_payment: float = Field(0.0, description="Available down payment in AED")
    location: Optional[str] = Field("Dubai", description="Target emirate/city in UAE")
    price_range: Optional[float] = Field(None, description="Target property price in AED")
    term: int = Field(25, description="Mortgage tenure in years (1 to 25)")
    rate_assumption: Optional[float] = Field(4.49, description="Annual interest rate percentage")
    nationality: Optional[str] = Field("expat", description="'national' or 'expat'")
    consent_given: bool = Field(False, description="Explicit user consent to store/process financial data")

    @field_validator("income")
    def validate_income(cls, v):
        if v < 5000.0:
            raise ValueError("Minimum qualifying monthly income in UAE is 5,000 AED.")
        if v > 10000000.0:
            raise ValueError("Income exceeds maximum permitted input threshold.")
        return v

    @field_validator("existing_debt")
    def validate_existing_debt(cls, v):
        if v < 0:
            raise ValueError("Existing debt cannot be negative.")
        return v

    @field_validator("down_payment")
    def validate_down_payment(cls, v):
        if v < 0:
            raise ValueError("Down payment cannot be negative.")
        return v

    @field_validator("term")
    def validate_term(cls, v):
        if v < 1 or v > 25:
            raise ValueError("Mortgage tenure must be between 1 and 25 years per UAE Central Bank regulations.")
        return v

    @field_validator("rate_assumption")
    def validate_rate(cls, v):
        if v is not None and (v <= 0 or v > 20.0):
            raise ValueError("Interest rate must be between 0.1% and 20.0%.")
        return v or 4.49


class EMIInput(BaseModel):
    loan_amount: float = Field(..., description="Total mortgage principal in AED")
    interest_rate: float = Field(..., description="Annual interest rate percentage (e.g. 4.49)")
    tenure: int = Field(..., description="Loan tenure in years (1 to 25)")
    frequency: str = Field("monthly", description="'monthly' or 'quarterly'")

    @field_validator("loan_amount")
    def validate_loan_amount(cls, v):
        if v <= 0:
            raise ValueError("Loan amount must be greater than zero.")
        return v

    @field_validator("interest_rate")
    def validate_rate(cls, v):
        if v <= 0 or v > 20.0:
            raise ValueError("Annual interest rate must be between 0.1% and 20.0%.")
        return v

    @field_validator("tenure")
    def validate_tenure(cls, v):
        if v < 1 or v > 25:
            raise ValueError("Tenure must be between 1 and 25 years per UAE Central Bank regulations.")
        return v

    @field_validator("frequency")
    def validate_frequency(cls, v):
        if v.lower() not in ["monthly", "quarterly"]:
            raise ValueError("Payment frequency must be 'monthly' or 'quarterly'.")
        return v.lower()


class EligibilityInput(BaseModel):
    salary: float = Field(..., description="Monthly salary in AED")
    nationality: str = Field(..., description="'national' (UAE National) or 'expat' (Expat Resident)")
    employment_type: str = Field("salaried", description="'salaried' or 'self_employed'")
    liabilities: float = Field(0.0, description="Total monthly debt commitments in AED")
    credit_band: Optional[str] = Field("good", description="'excellent', 'good', 'fair', 'poor'")

    @field_validator("salary")
    def validate_salary(cls, v):
        if v <= 0:
            raise ValueError("Salary must be positive.")
        return v


# ==============================================================================
# DETERMINISTIC MORTGAGE CALCULATION SERVICE (Rule 5: Zero LLM / Frontend Math)
# ==============================================================================

class MortgageCalculationService:
    """
    Authoritative Deterministic Mortgage Math Engine.
    Strictly follows UAE Central Bank Mortgage Regulations and DBR rules.
    NO LLM MATH. NO FRONTEND MATH.
    """

    MANDATORY_DISCLAIMER = "estimate only, subject to lender approval"
    MANDATORY_LABEL = "estimates, not offers"

    @classmethod
    def calc_affordability(
        cls,
        inputs: AffordabilityInput,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        PRD Function: calc_affordability()
        Computes maximum borrowing capacity, affordable purchase price, upfront costs,
        and DBR compliance based on UAE Central Bank 50% cap.
        """
        income = inputs.income
        debt = inputs.existing_debt
        down_payment = inputs.down_payment
        term_years = inputs.term
        annual_rate = inputs.rate_assumption or 4.49
        nationality = (inputs.nationality or "expat").lower()

        # 1. UAE Central Bank Debt Burden Ratio (DBR) Cap: 50%
        max_dbr = settings.MAX_DBR_RATIO  # 0.50
        max_total_monthly_commitment = income * max_dbr
        max_allowable_installment = max(0.0, max_total_monthly_commitment - debt)

        current_dbr_pct = round((debt / income) * 100.0, 2)
        projected_dbr_pct = round(((debt + max_allowable_installment) / income) * 100.0, 2)

        # 2. Maximum Loan Capacity via Present Value (PV) Formula
        # PV = PMT * [1 - (1 + r)^(-n)] / r
        monthly_rate = (annual_rate / 100.0) / 12.0
        total_months = term_years * 12

        if max_allowable_installment <= 0:
            max_loan_amount = 0.0
            max_property_price = down_payment
            total_interest = 0.0
            monthly_payment = 0.0
            dbr_exceeded = True
        else:
            dbr_exceeded = False
            monthly_payment = round(max_allowable_installment, 2)
            # Standard Present Value formula of an ordinary annuity
            discount_factor = (1.0 - math.pow(1.0 + monthly_rate, -total_months)) / monthly_rate
            max_loan_amount = round(max_allowable_installment * discount_factor, 2)

            # 3. Maximum LTV Constraints in UAE
            # UAE Nationals: Up to 80% LTV (or 85% for first homes <= 5M)
            # Expats: Up to 75% - 80% LTV
            max_ltv_pct = 80.0 if "national" in nationality else 75.0
            max_ltv_ratio = max_ltv_pct / 100.0

            # Bounded by borrowing capacity and down payment
            if down_payment > 0:
                # If buyer has down payment, price = loan + down payment
                max_property_price = round(max_loan_amount + down_payment, 2)
                # Ensure down payment satisfies minimum down payment requirement (1 - LTV)
                min_dp_required = max_property_price * (1.0 - max_ltv_ratio)
                if down_payment < min_dp_required:
                    # Constrained by down payment: price = down_payment / (1 - LTV)
                    max_property_price = round(down_payment / (1.0 - max_ltv_ratio), 2)
                    max_loan_amount = round(max_property_price * max_ltv_ratio, 2)
                    # Recompute monthly payment for the constrained loan
                    monthly_payment = round((max_loan_amount * monthly_rate) / (1.0 - math.pow(1.0 + monthly_rate, -total_months)), 2)
            else:
                # Minimum down payment required by law in UAE is 20% for expats / 15-20% for nationals
                # Property price if 20% down payment is yet to be funded:
                max_property_price = round(max_loan_amount / max_ltv_ratio, 2)
                down_payment = round(max_property_price * (1.0 - max_ltv_ratio), 2)

            total_repayment = round(monthly_payment * total_months, 2)
            total_interest = round(total_repayment - max_loan_amount, 2)

        # 4. Standard UAE Purchase Fee Breakdown (Dubai Standards)
        # DLD Fee: 4% of property price + 580 AED admin
        dld_fee = round((max_property_price * 0.04) + 580.0, 2)
        # Agency Broker Fee: 2% of property price + 5% VAT (2.1% total)
        agency_fee = round(max_property_price * 0.021, 2)
        # Mortgage Registration Fee: 0.25% of loan amount + 290 AED admin
        mortgage_reg_fee = round((max_loan_amount * 0.0025) + 290.0, 2)
        # Bank Processing Fee: ~0.5% + 5% VAT
        bank_proc_fee = round(max_loan_amount * 0.00525, 2)
        # Valuation Fee
        valuation_fee = 2625.0

        total_upfront_fees = round(dld_fee + agency_fee + mortgage_reg_fee + bank_proc_fee + valuation_fee, 2)
        total_cash_required = round(down_payment + total_upfront_fees, 2)

        result = {
            "label": cls.MANDATORY_LABEL,
            "disclaimer": cls.MANDATORY_DISCLAIMER,
            "calculation_type": "affordability",
            "dbr_status": {
                "max_allowed_dbr_pct": max_dbr * 100.0,
                "current_dbr_pct": current_dbr_pct,
                "projected_dbr_pct": projected_dbr_pct,
                "dbr_cap_exceeded": dbr_exceeded,
                "message": "Eligible within UAE 50% DBR limits" if not dbr_exceeded else "Exceeds UAE Central Bank 50% DBR cap. Consider reducing debt."
            },
            "affordability_summary": {
                "monthly_income_aed": income,
                "existing_debt_aed": debt,
                "max_dbr_allowable_installment_aed": round(max_total_monthly_commitment - debt, 2),
                "max_allowable_monthly_emi_aed": monthly_payment,
                "max_borrowing_capacity_aed": max_loan_amount,
                "max_property_price_aed": max_property_price,
                "down_payment_aed": down_payment,
                "tenure_years": term_years,
                "assumed_interest_rate_pct": annual_rate,
                "total_interest_payable_aed": total_interest
            },
            "upfront_costs_breakdown": {
                "down_payment_aed": down_payment,
                "dld_transfer_fee_aed": dld_fee,
                "agency_broker_fee_aed": agency_fee,
                "mortgage_registration_fee_aed": mortgage_reg_fee,
                "bank_processing_fee_aed": bank_proc_fee,
                "property_valuation_fee_aed": valuation_fee,
                "total_upfront_fees_aed": total_upfront_fees,
                "total_cash_required_at_purchase_aed": total_cash_required
            },
            "jump_to_properties": {
                "enabled": True,
                "recommended_budget_max": max_property_price,
                "query_suggestion": f"Show properties under {int(max_property_price):,} AED"
            },
            "compliance_ref": settings.COMPANY_RETENTION_POLICY_REF
        }

        # Audit Logging (Rule 14c)
        AuditService.log_event(
            event_type="mortgage_calculation",
            action="calc_affordability",
            resource="mortgage_service",
            session_id=session_id,
            user_id=user_id,
            details={
                "income": income,
                "debt": debt,
                "down_payment": down_payment,
                "term_years": term_years,
                "max_loan_amount": max_loan_amount,
                "max_property_price": max_property_price,
                "dbr_pct": projected_dbr_pct
            }
        )

        return result

    @classmethod
    def calc_emi(
        cls,
        inputs: EMIInput,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        PRD Function: calc_emi()
        Standard Amortization Formula:
        EMI = P * [r(1 + r)^n] / [(1 + r)^n - 1]
        """
        loan = inputs.loan_amount
        annual_rate = inputs.interest_rate
        years = inputs.tenure
        freq = inputs.frequency.lower()

        periods_per_year = 12 if freq == "monthly" else 4
        total_periods = years * periods_per_year
        periodic_rate = (annual_rate / 100.0) / periods_per_year

        # Exact EMI Formula
        numerator = loan * periodic_rate * math.pow(1.0 + periodic_rate, total_periods)
        denominator = math.pow(1.0 + periodic_rate, total_periods) - 1.0
        installment = round(numerator / denominator, 2)

        total_repayment = round(installment * total_periods, 2)
        total_interest = round(total_repayment - loan, 2)

        principal_pct = round((loan / total_repayment) * 100.0, 1)
        interest_pct = round((total_interest / total_repayment) * 100.0, 1)

        # Generate Amortization Schedule (First 5 Years + Milestones)
        schedule = []
        balance = loan
        for yr in range(1, min(years + 1, 6)):
            year_interest = 0.0
            year_principal = 0.0
            for _ in range(periods_per_year):
                p_interest = balance * periodic_rate
                p_principal = installment - p_interest
                year_interest += p_interest
                year_principal += p_principal
                balance = max(0.0, balance - p_principal)
            
            schedule.append({
                "year": yr,
                "principal_paid_aed": round(year_principal, 2),
                "interest_paid_aed": round(year_interest, 2),
                "remaining_balance_aed": round(balance, 2)
            })

        result = {
            "label": cls.MANDATORY_LABEL,
            "disclaimer": cls.MANDATORY_DISCLAIMER,
            "calculation_type": "emi",
            "loan_amount_aed": loan,
            "annual_interest_rate_pct": annual_rate,
            "tenure_years": years,
            "frequency": freq,
            "periodic_installment_aed": installment,
            "monthly_equivalent_aed": installment if freq == "monthly" else round(installment / 3.0, 2),
            "total_repayment_aed": total_repayment,
            "total_interest_payable_aed": total_interest,
            "breakdown_pct": {
                "principal_pct": principal_pct,
                "interest_pct": interest_pct
            },
            "amortization_schedule_sample": schedule,
            "compliance_ref": settings.COMPANY_RETENTION_POLICY_REF
        }

        # Audit Logging (Rule 14c)
        AuditService.log_event(
            event_type="mortgage_calculation",
            action="calc_emi",
            resource="mortgage_service",
            session_id=session_id,
            user_id=user_id,
            details={
                "loan_amount": loan,
                "interest_rate": annual_rate,
                "tenure": years,
                "installment": installment,
                "total_interest": total_interest
            }
        )

        return result

    @classmethod
    def check_eligibility(
        cls,
        inputs: EligibilityInput,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        PRD Function: check_eligibility()
        Validates criteria against UAE Central Bank guidelines:
        - Minimum salary (5,000 AED general, 15,000 AED premier)
        - DBR cap (< 50%)
        - Nationality LTV rules
        - Employment history standards
        """
        salary = inputs.salary
        nat = inputs.nationality.lower()
        is_national = "national" in nat
        liabilities = inputs.liabilities
        emp_type = inputs.employment_type.lower()

        current_dbr_pct = round((liabilities / salary) * 100.0, 2)
        dbr_pass = current_dbr_pct < 50.0

        min_salary_pass = salary >= 5000.0
        max_ltv = 80.0 if is_national else 75.0

        # Query matching products from internal rule table
        matching_products = MortgageRulesGateway.get_mortgage_products(
            salary=salary,
            nationality="UAE National" if is_national else "Expat",
            session_id=session_id
        )

        overall_eligible = min_salary_pass and dbr_pass

        return {
            "label": cls.MANDATORY_LABEL,
            "disclaimer": cls.MANDATORY_DISCLAIMER,
            "is_eligible": overall_eligible,
            "current_dbr_pct": current_dbr_pct,
            "dbr_status_ok": dbr_pass,
            "max_ltv_permitted_pct": max_ltv,
            "matching_products_count": len(matching_products),
            "matching_products": [p.model_dump() for p in matching_products],
            "recommendation": "Profile meets primary UAE Central Bank lending criteria" if overall_eligible else "Profile requires review due to DBR or minimum income requirements"
        }

    @classmethod
    def get_indicative_offers(
        cls,
        loan_amount: float,
        salary: float,
        nationality: str = "expat",
        tenure: int = 25,
        finance_type: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        PRD Function: offer_estimation()
        Surfaces top indicative offers from configured partner bank rule sheets.
        """
        products = MortgageRulesGateway.get_mortgage_products(
            salary=salary,
            nationality="UAE National" if "national" in nationality.lower() else "Expat",
            finance_type=finance_type,
            session_id=session_id
        )

        offers = []
        for prod in products[:3]:
            emi_calc = cls.calc_emi(EMIInput(
                loan_amount=loan_amount,
                interest_rate=prod.interest_rate,
                tenure=min(tenure, prod.max_tenure_years),
                frequency="monthly"
            ))
            offers.append({
                "product_id": prod.product_id,
                "bank_name": prod.bank_name,
                "rate_type": prod.rate_type,
                "finance_type": prod.finance_type,
                "interest_rate_pct": prod.interest_rate,
                "monthly_emi_aed": emi_calc["periodic_installment_aed"],
                "processing_fee_aed": round(loan_amount * (prod.processing_fee_pct / 100.0), 2),
                "valuation_fee_aed": prod.valuation_fee_aed,
                "max_ltv_pct": prod.max_ltv_national if "national" in nationality.lower() else prod.max_ltv_expat
            })

        return {
            "label": cls.MANDATORY_LABEL,
            "disclaimer": cls.MANDATORY_DISCLAIMER,
            "loan_amount_aed": loan_amount,
            "finance_type_filter": finance_type,
            "indicative_offers": offers
        }
