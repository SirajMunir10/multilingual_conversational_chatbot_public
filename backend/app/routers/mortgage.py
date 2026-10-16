"""Deterministic calculator API (PRD FR-13): the same service the assistant's tools call."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import enforce_rate_limit
from app.services.mortgage_service import (AffordabilityInput, EligibilityInput, EMIInput, MortgageCalculationService,
                                           MortgageInputError)

router = APIRouter(prefix="/api/mortgage", tags=["Mortgage calculators"], dependencies=[Depends(enforce_rate_limit)])


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except MortgageInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/affordability")
def affordability(payload: AffordabilityInput):
    return _run(MortgageCalculationService.calc_affordability, payload)


@router.post("/emi")
def emi(payload: EMIInput):
    return _run(MortgageCalculationService.calc_emi, payload)


@router.post("/eligibility")
def eligibility(payload: EligibilityInput):
    return _run(MortgageCalculationService.check_eligibility, payload)


@router.get("/purchase-costs")
def purchase_costs(property_price: float, emirate: Optional[str] = None, loan_amount: Optional[float] = None):
    return _run(MortgageCalculationService.calc_purchase_costs, property_price, emirate, loan_amount)


@router.get("/products")
def products(bank: Optional[str] = None, finance_type: Optional[str] = None, rate_type: Optional[str] = None, salary: Optional[float] = None):
    return MortgageCalculationService.get_products(bank, finance_type, rate_type, salary)


@router.get("/offers")
def offers(loan_amount: float, monthly_income: Optional[float] = None, residency: Optional[str] = None,
           tenure_years: Optional[int] = None, finance_type: Optional[str] = None):
    return _run(MortgageCalculationService.estimate_offers, loan_amount, monthly_income, residency, tenure_years, finance_type)
