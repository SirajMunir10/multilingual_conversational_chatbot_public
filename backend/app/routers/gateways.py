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

@router.get("/kb")
def retrieve_kb_endpoint(
    query: str = Query(..., description="Natural language question or search query"),
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """
    PRD Architecture Function: retrieve_kb(query)
    RAG retriever with access scoping and Phase 5 activation boundary enforcement.
    """
    from app.services.rag_service import RAGService
    return RAGService.retrieve_kb(query, session_id=x_session_id)

@router.get("/account/saved-properties")
def get_my_saved_properties_endpoint(
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """
    PRD Architecture Function: get_my_saved_properties()
    User-scoped read API (FR-21, FR-23a).
    """
    from app.services.account_service import AccountService
    return AccountService.get_my_saved_properties(user_id=x_user_id, session_id=x_session_id)

@router.get("/account/applications")
def get_my_application_status_endpoint(
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """
    PRD Architecture Function: get_my_application_status()
    User-scoped read API for Vault & GRID status (FR-21, FR-23a).
    """
    from app.services.account_service import AccountService
    return AccountService.get_my_application_status(user_id=x_user_id, session_id=x_session_id)

@router.post("/account/saved-properties/{property_id}")
def save_property_to_account_endpoint(
    property_id: str,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """Save property to authenticated user account (FR-10, FR-21)."""
    from app.services.account_service import AccountService
    if not x_user_id:
        return {"status": "auth_required", "message": "Sign in required to bookmark properties"}
    return AccountService.save_property(user_id=x_user_id, property_id=property_id, session_id=x_session_id)

@router.delete("/account/saved-properties/{property_id}")
def remove_saved_property_endpoint(
    property_id: str,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """Remove property from authenticated user account."""
    from app.services.account_service import AccountService
    if not x_user_id:
        return {"status": "auth_required", "message": "Sign in required"}
    return AccountService.remove_saved_property(user_id=x_user_id, property_id=property_id, session_id=x_session_id)

@router.post("/handoff")
def initiate_human_handoff_endpoint(
    reason: str = Query("explicit_request"),
    preferred_team: Optional[str] = Query(None),
    notes: Optional[str] = Query(None),
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    x_user_id: Optional[str] = Header(None, alias="X-User-ID")
):
    """
    Initiates warm human handoff with full serialized transcript (FR-5, FR-20).
    """
    from app.services.handoff_service import HandoffService
    active_session_id = x_session_id or "sess_direct_handoff"
    return HandoffService.initiate_handoff(
        session_id=active_session_id,
        reason=reason,
        preferred_team=preferred_team,
        notes=notes,
        user_id=x_user_id
    )

@router.get("/handoff/queue")
def get_handoff_queue_endpoint(
    queue: Optional[str] = Query(None, description="Optional filter by queue: sales, mortgage, support")
):
    """Inspect active human handoff queue for back-office review (Phase 7)."""
    from app.services.handoff_service import HandoffService
    return HandoffService.get_queue(queue=queue)

