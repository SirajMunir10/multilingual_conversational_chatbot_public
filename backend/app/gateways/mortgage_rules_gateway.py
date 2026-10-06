from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from app.core.audit import AuditService

class ScopedMortgageProduct(BaseModel):
    product_id: str
    bank_name: str
    rate_type: str  # Fixed 3-Year, Fixed 5-Year, Variable, Islamic Murabaha, Islamic Ijarah
    interest_rate: float  # Percentage / Profit Rate, e.g. 4.49
    max_ltv_national: float  # E.g. 80.0
    max_ltv_expat: float  # E.g. 75.0
    min_salary_aed: float
    max_tenure_years: int
    processing_fee_pct: float
    valuation_fee_aed: float
    early_settlement_fee_pct: float
    finance_type: str = "conventional"  # "conventional" or "islamic"
    version: str = "v1.2.0"

class MortgageRulesGateway:
    """
    Internal Admin-Managed Rate & Rule Gateway.
    In v1, eligibility rules and interest rates are sourced from internal admin-managed
    versioned tables, NOT third-party lender APIs (Rule 5 & Decision 2).
    """

    _version = "v1.2.0"
    _products: List[ScopedMortgageProduct] = [
        # --- Conventional Banking Products ---
        ScopedMortgageProduct(
            product_id="prod_enb_fixed3",
            bank_name="Emirates NBD",
            rate_type="Fixed 3-Year",
            interest_rate=4.49,
            max_ltv_national=80.0,
            max_ltv_expat=75.0,
            min_salary_aed=15000.0,
            max_tenure_years=25,
            processing_fee_pct=0.5,
            valuation_fee_aed=2625.0,
            early_settlement_fee_pct=1.0,
            finance_type="conventional",
            version="v1.2.0"
        ),
        ScopedMortgageProduct(
            product_id="prod_fab_fixed5",
            bank_name="First Abu Dhabi Bank (FAB)",
            rate_type="Fixed 5-Year",
            interest_rate=4.75,
            max_ltv_national=80.0,
            max_ltv_expat=75.0,
            min_salary_aed=15000.0,
            max_tenure_years=25,
            processing_fee_pct=0.5,
            valuation_fee_aed=2500.0,
            early_settlement_fee_pct=1.0,
            finance_type="conventional",
            version="v1.2.0"
        ),
        ScopedMortgageProduct(
            product_id="prod_adcb_var",
            bank_name="ADCB",
            rate_type="Variable",
            interest_rate=6.20,  # 3M EIBOR + margin
            max_ltv_national=80.0,
            max_ltv_expat=75.0,
            min_salary_aed=12000.0,
            max_tenure_years=25,
            processing_fee_pct=0.25,
            valuation_fee_aed=2625.0,
            early_settlement_fee_pct=1.0,
            finance_type="conventional",
            version="v1.2.0"
        ),

        # --- Islamic Banking Products (Sharia Compliant) ---
        ScopedMortgageProduct(
            product_id="prod_dib_fixed3",
            bank_name="Dubai Islamic Bank (DIB)",
            rate_type="Islamic Fixed 3-Year (Murabaha)",
            interest_rate=4.29,
            max_ltv_national=80.0,
            max_ltv_expat=75.0,
            min_salary_aed=15000.0,
            max_tenure_years=25,
            processing_fee_pct=0.5,
            valuation_fee_aed=2500.0,
            early_settlement_fee_pct=1.0,
            finance_type="islamic",
            version="v1.2.0"
        ),
        ScopedMortgageProduct(
            product_id="prod_dib_var_ijarah",
            bank_name="Dubai Islamic Bank (DIB)",
            rate_type="Islamic Variable (Ijarah)",
            interest_rate=5.95,
            max_ltv_national=80.0,
            max_ltv_expat=75.0,
            min_salary_aed=15000.0,
            max_tenure_years=25,
            processing_fee_pct=0.5,
            valuation_fee_aed=2500.0,
            early_settlement_fee_pct=1.0,
            finance_type="islamic",
            version="v1.2.0"
        ),
        ScopedMortgageProduct(
            product_id="prod_adib_fixed3",
            bank_name="Abu Dhabi Islamic Bank (ADIB)",
            rate_type="Islamic Fixed 3-Year (Baiti Home Finance)",
            interest_rate=4.39,
            max_ltv_national=80.0,
            max_ltv_expat=75.0,
            min_salary_aed=15000.0,
            max_tenure_years=25,
            processing_fee_pct=0.5,
            valuation_fee_aed=2625.0,
            early_settlement_fee_pct=1.0,
            finance_type="islamic",
            version="v1.2.0"
        ),
        ScopedMortgageProduct(
            product_id="prod_adib_fixed5",
            bank_name="Abu Dhabi Islamic Bank (ADIB)",
            rate_type="Islamic Fixed 5-Year (Baiti Home Finance)",
            interest_rate=4.69,
            max_ltv_national=80.0,
            max_ltv_expat=75.0,
            min_salary_aed=15000.0,
            max_tenure_years=25,
            processing_fee_pct=0.5,
            valuation_fee_aed=2625.0,
            early_settlement_fee_pct=1.0,
            finance_type="islamic",
            version="v1.2.0"
        ),
        ScopedMortgageProduct(
            product_id="prod_ei_fixed3",
            bank_name="Emirates Islamic",
            rate_type="Islamic Fixed 3-Year (Manzili)",
            interest_rate=4.35,
            max_ltv_national=80.0,
            max_ltv_expat=75.0,
            min_salary_aed=12000.0,
            max_tenure_years=25,
            processing_fee_pct=0.5,
            valuation_fee_aed=2625.0,
            early_settlement_fee_pct=1.0,
            finance_type="islamic",
            version="v1.2.0"
        ),
        ScopedMortgageProduct(
            product_id="prod_ei_var",
            bank_name="Emirates Islamic",
            rate_type="Islamic Variable (Manzili)",
            interest_rate=6.10,
            max_ltv_national=80.0,
            max_ltv_expat=75.0,
            min_salary_aed=12000.0,
            max_tenure_years=25,
            processing_fee_pct=0.25,
            valuation_fee_aed=2625.0,
            early_settlement_fee_pct=1.0,
            finance_type="islamic",
            version="v1.2.0"
        ),
        ScopedMortgageProduct(
            product_id="prod_sib_fixed3",
            bank_name="Sharjah Islamic Bank (SIB)",
            rate_type="Islamic Fixed 3-Year (Murabaha)",
            interest_rate=4.45,
            max_ltv_national=80.0,
            max_ltv_expat=75.0,
            min_salary_aed=12000.0,
            max_tenure_years=25,
            processing_fee_pct=0.5,
            valuation_fee_aed=2500.0,
            early_settlement_fee_pct=1.0,
            finance_type="islamic",
            version="v1.2.0"
        ),
        ScopedMortgageProduct(
            product_id="prod_ajman_fixed3",
            bank_name="Ajman Bank",
            rate_type="Islamic Fixed 3-Year (Murabaha Land/Home)",
            interest_rate=4.49,
            max_ltv_national=80.0,
            max_ltv_expat=75.0,
            min_salary_aed=10000.0,
            max_tenure_years=25,
            processing_fee_pct=0.5,
            valuation_fee_aed=2500.0,
            early_settlement_fee_pct=1.0,
            finance_type="islamic",
            version="v1.2.0"
        ),
        ScopedMortgageProduct(
            product_id="prod_alhilal_fixed3",
            bank_name="Al Hilal Bank",
            rate_type="Islamic Fixed 3-Year",
            interest_rate=4.40,
            max_ltv_national=80.0,
            max_ltv_expat=75.0,
            min_salary_aed=12000.0,
            max_tenure_years=25,
            processing_fee_pct=0.35,
            valuation_fee_aed=2625.0,
            early_settlement_fee_pct=1.0,
            finance_type="islamic",
            version="v1.2.0"
        ),
        ScopedMortgageProduct(
            product_id="prod_mashreq_islami_fixed5",
            bank_name="Mashreq Al Islami",
            rate_type="Islamic Fixed 5-Year (Ijarah)",
            interest_rate=4.75,
            max_ltv_national=80.0,
            max_ltv_expat=75.0,
            min_salary_aed=15000.0,
            max_tenure_years=25,
            processing_fee_pct=0.5,
            valuation_fee_aed=2500.0,
            early_settlement_fee_pct=1.0,
            finance_type="islamic",
            version="v1.2.0"
        ),
        ScopedMortgageProduct(
            product_id="prod_rakbank_amal_var",
            bank_name="RAKBANK Islamic (Amal)",
            rate_type="Islamic Variable (Amal Home Finance)",
            interest_rate=6.25,
            max_ltv_national=80.0,
            max_ltv_expat=75.0,
            min_salary_aed=15000.0,
            max_tenure_years=25,
            processing_fee_pct=0.5,
            valuation_fee_aed=2625.0,
            early_settlement_fee_pct=1.0,
            finance_type="islamic",
            version="v1.2.0"
        )
    ]

    @classmethod
    def get_mortgage_products(
        cls,
        bank: Optional[str] = None,
        rate_type: Optional[str] = None,
        salary: Optional[float] = None,
        nationality: Optional[str] = None,
        finance_type: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> List[ScopedMortgageProduct]:
        """
        PRD Architecture Function: get_mortgage_products(bank, rate_type, salary, nationality, finance_type)
        """
        results = cls._products

        if bank:
            results = [p for p in results if bank.lower() in p.bank_name.lower()]
        if rate_type:
            results = [p for p in results if rate_type.lower() in p.rate_type.lower()]
        if salary is not None:
            results = [p for p in results if salary >= p.min_salary_aed]
        if finance_type:
            results = [p for p in results if finance_type.lower() in p.finance_type.lower()]

        # Audit log rule retrieval
        AuditService.log_event(
            event_type="mortgage_rules_query",
            action="get_mortgage_products",
            resource="mortgage_rate_rules",
            session_id=session_id,
            details={
                "bank": bank,
                "rate_type": rate_type,
                "salary": salary,
                "nationality": nationality,
                "finance_type": finance_type,
                "version": cls._version,
                "results_count": len(results)
            }
        )

        return results

    @classmethod
    def update_product_rate(cls, product_id: str, new_rate: float, user_role: str) -> bool:
        """
        Admin-controlled rate modification (FR-27). Updates rules in memory and logs version change.
        """
        for p in cls._products:
            if p.product_id == product_id:
                old_rate = p.interest_rate
                p.interest_rate = new_rate
                AuditService.log_event(
                    event_type="business_write",
                    action="update_rate_rule",
                    resource="mortgage_rate_rules",
                    details={
                        "product_id": product_id,
                        "old_rate": old_rate,
                        "new_rate": new_rate,
                        "updated_by": user_role
                    }
                )
                return True
        return False
