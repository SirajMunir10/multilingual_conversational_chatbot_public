from typing import Optional, List
from fastapi import APIRouter, Query, Header
from app.gateways.inventory_gateway import PropertyInventoryGateway, ScopedPropertyListing
from app.gateways.mortgage_rules_gateway import MortgageRulesGateway, ScopedMortgageProduct
from app.gateways.services_gateway import ServicesGateway, ServicePricingEstimate
from app.gateways.grid_gateway import GridGateway, GridLeadPayload, GridLeadResponse
from app.gateways.vault_gateway import VaultGateway, VaultMortgageLeadPayload, VaultMortgageLeadResponse

router = APIRouter(prefix="/api/gateways", tags=["Scoped Production Gateways"])

@router.get("/properties", response_model=List[ScopedPropertyListing])
def search_properties_endpoint(
    city: Optional[str] = Query(None, description="City or community filter"),
    type: Optional[str] = Query(None, description="Property type"),
    budget_min: Optional[float] = Query(None, description="Minimum price AED"),
    budget_max: Optional[float] = Query(None, description="Maximum price AED"),
    beds: Optional[int] = Query(None, description="Number of bedrooms"),
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """
    PRD Architecture Function: search_properties(city, type, budget_min, budget_max, beds)
    Read-only scoped property inventory query.
    """
    return PropertyInventoryGateway.search_properties(
        city=city,
        type=type,
        budget_min=budget_min,
        budget_max=budget_max,
        beds=beds,
        session_id=x_session_id
    )

@router.get("/mortgage-products", response_model=List[ScopedMortgageProduct])
def get_mortgage_products_endpoint(
    bank: Optional[str] = Query(None),
    rate_type: Optional[str] = Query(None),
    salary: Optional[float] = Query(None),
    nationality: Optional[str] = Query(None),
    finance_type: Optional[str] = Query(None, description="conventional or islamic"),
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """
    PRD Architecture Function: get_mortgage_products(bank, rate_type, salary, nationality)
    Read-only scoped rate/rule product query from internal versioned tables.
    """
    return MortgageRulesGateway.get_mortgage_products(
        bank=bank,
        rate_type=rate_type,
        salary=salary,
        nationality=nationality,
        finance_type=finance_type,
        session_id=x_session_id
    )

@router.get("/service-pricing", response_model=ServicePricingEstimate)
def get_service_pricing_endpoint(
    category: str = Query(..., description="Service category e.g. interior_design, landscaping"),
    area_sq_ft: float = Query(..., description="Total area in square feet"),
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """
    PRD Architecture Function: get_service_pricing(category, area_sq_ft)
    """
    return ServicesGateway.get_service_pricing(
        category=category,
        area_sq_ft=area_sq_ft,
        session_id=x_session_id
    )

@router.post("/grid/leads", response_model=GridLeadResponse)
def create_grid_lead_endpoint(
    payload: GridLeadPayload,
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """
    GRID CRM write endpoint for real estate leads and shortlisted properties.
    Narrow, explicitly defined write endpoint.
    """
    return GridGateway.create_lead(payload, session_id=x_session_id)

@router.post("/vault/leads", response_model=VaultMortgageLeadResponse)
def create_vault_lead_endpoint(
    payload: VaultMortgageLeadPayload,
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """
    Vault CRM write endpoint for mortgage leads and applications with calculated affordability.
    Narrow, explicitly defined write endpoint.
    """
    return VaultGateway.create_lead(payload, session_id=x_session_id)
