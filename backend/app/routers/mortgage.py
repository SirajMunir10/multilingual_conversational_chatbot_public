from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
from app.services.mortgage_service import (
    MortgageCalculationService,
    AffordabilityInput,
    EMIInput,
    EligibilityInput
)
from app.gateways.mortgage_rules_gateway import MortgageRulesGateway

router = APIRouter(prefix="/api/mortgage", tags=["Mortgage & Financial Tools"])

@router.post("/affordability")
def calculate_affordability(payload: AffordabilityInput, session_id: Optional[str] = None):
    """
    Calculate maximum borrowing capacity and property affordability based on UAE Central Bank 50% DBR cap.
    """
    try:
        return MortgageCalculationService.calc_affordability(payload, session_id=session_id)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Affordability calculation error: {str(e)}")

@router.post("/emi")
def calculate_emi(payload: EMIInput, session_id: Optional[str] = None):
    """
    Calculate exact monthly EMI payment and amortization breakdown.
    """
    try:
        return MortgageCalculationService.calc_emi(payload, session_id=session_id)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"EMI calculation error: {str(e)}")

@router.post("/eligibility")
def check_eligibility(payload: EligibilityInput, session_id: Optional[str] = None):
    """
    Evaluate applicant eligibility against UAE lending criteria and DBR limits.
    """
    try:
        return MortgageCalculationService.check_eligibility(payload, session_id=session_id)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Eligibility check error: {str(e)}")

@router.post("/offers")
def get_indicative_offers(
    loan_amount: float = Query(..., gt=0),
    salary: float = Query(..., gt=0),
    nationality: str = Query("expat"),
    tenure: int = Query(25, ge=1, le=25),
    finance_type: Optional[str] = Query(None, description="conventional or islamic"),
    session_id: Optional[str] = None
):
    """
    Retrieve top tailored indicative offers from partner bank rate sheets (conventional or Islamic).
    """
    try:
        return MortgageCalculationService.get_indicative_offers(
            loan_amount=loan_amount,
            salary=salary,
            nationality=nationality,
            tenure=tenure,
            finance_type=finance_type,
            session_id=session_id
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Offer estimation error: {str(e)}")

@router.get("/products")
def get_products(
    bank: Optional[str] = None,
    rate_type: Optional[str] = None,
    salary: Optional[float] = None,
    nationality: Optional[str] = None,
    finance_type: Optional[str] = Query(None, description="conventional or islamic")
):
    """
    Query internal admin-managed versioned rate/rule tables for UAE mortgage products (conventional and Islamic).
    """
    products = MortgageRulesGateway.get_mortgage_products(
        bank=bank,
        rate_type=rate_type,
        salary=salary,
        nationality=nationality,
        finance_type=finance_type
    )
    return {
        "count": len(products),
        "version": MortgageRulesGateway._version,
        "products": [p.model_dump() for p in products]
    }
