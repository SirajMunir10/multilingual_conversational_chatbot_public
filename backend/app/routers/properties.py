from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Query, Header, HTTPException, Body
from pydantic import BaseModel
from app.gateways.inventory_gateway import ScopedPropertyListing, PropertyInventoryGateway
from app.services.property_service import PropertyDiscoveryService, PropertySearchFilter

router = APIRouter(prefix="/api/properties", tags=["Properties"])

class AnonymousLeadPayload(BaseModel):
    name: Optional[str] = None
    full_name: Optional[str] = None
    email: str
    phone: str
    property_id: Optional[str] = None
    session_id: Optional[str] = None
    notes: Optional[str] = None

class RefinementPayload(BaseModel):
    refinement_text: Optional[str] = None
    refinement_instruction: Optional[str] = None
    current_filter: Optional[Dict[str, Any]] = None
    nationality: Optional[str] = "expat"

@router.get("/search")
def search_properties_endpoint(
    city: Optional[str] = Query(None, description="City or community"),
    type: Optional[str] = Query(None, description="apartment, villa, townhouse, penthouse"),
    budget_min: Optional[float] = Query(None, ge=0),
    budget_max: Optional[float] = Query(None, ge=0),
    beds: Optional[int] = Query(None, ge=1),
    purpose: Optional[str] = Query(None, description="buy, rent, invest"),
    status: Optional[str] = Query(None, description="ready, off-plan"),
    developer: Optional[str] = Query(None),
    nationality: str = Query("expat", description="national or expat for mortgage calculations"),
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """
    FR-8: Live Property Inventory Query returning ranked matches enriched with mortgage cross-sell math.
    """
    filters = PropertySearchFilter(
        city=city,
        type=type,
        budget_min=budget_min,
        budget_max=budget_max,
        beds=beds,
        purpose=purpose,
        status=status,
        developer=developer
    )
    results = PropertyDiscoveryService.search_and_rank(
        filters=filters,
        nationality=nationality,
        session_id=x_session_id
    )
    return {
        "count": len(results),
        "results": results,
        "properties": results
    }

@router.get("/{property_id}")
def get_property_details(
    property_id: str,
    nationality: str = Query("expat"),
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """
    Retrieve single property listing with calculated mortgage breakdown (FR-11).
    """
    prop = PropertyInventoryGateway.get_property_by_id(property_id, session_id=x_session_id)
    if not prop:
        raise HTTPException(status_code=404, detail=f"Property '{property_id}' not found.")

    data = prop.model_dump()
    data["mortgage_cross_sell"] = PropertyDiscoveryService.compute_mortgage_cross_sell(
        prop, nationality=nationality, session_id=x_session_id
    )
    return data

@router.get("/{property_id}/similar")
def get_similar_properties(
    property_id: str,
    limit: int = Query(3, ge=1, le=10),
    nationality: str = Query("expat"),
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """
    FR-9: Retrieve properties similar to a referenced property.
    """
    similar = PropertyInventoryGateway.get_similar_properties(property_id, limit=limit, session_id=x_session_id)
    enriched = []
    for p in similar:
        d = p.model_dump()
        d["mortgage_cross_sell"] = PropertyDiscoveryService.compute_mortgage_cross_sell(
            p, nationality=nationality, session_id=x_session_id
        )
        enriched.append(d)
    return {
        "reference_property_id": property_id,
        "count": len(enriched),
        "similar_properties": enriched
    }

@router.post("/{property_id}/shortlist")
def toggle_shortlist_property(
    property_id: str,
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    x_user_id: Optional[str] = Header(None, alias="X-User-ID")
):
    """
    FR-10: Save / shortlist property from chat.
    """
    if not x_session_id:
        x_session_id = "default_session"
    result = PropertyDiscoveryService.shortlist_property(
        session_id=x_session_id,
        property_id=property_id,
        user_id=x_user_id
    )
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error"))
    return result

@router.get("/user/shortlist")
def get_user_shortlist(
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    x_user_id: Optional[str] = Header(None, alias="X-User-ID")
):
    """
    FR-10: Retrieve all currently shortlisted properties in session.
    """
    if not x_session_id:
        return {"count": 0, "shortlist": []}
    shortlist = PropertyDiscoveryService.get_shortlist(session_id=x_session_id, user_id=x_user_id)
    return {
        "count": len(shortlist),
        "shortlist": shortlist
    }

@router.post("/shortlist/lead")
def capture_shortlist_lead(
    payload: AnonymousLeadPayload,
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """
    FR-10: Anonymous lead capture to preserve shortlisted portfolio into CRM.
    """
    sess_id = payload.session_id or x_session_id or "default_session"
    c_name = payload.full_name or payload.name or "Interested Client"
    return PropertyDiscoveryService.capture_anonymous_lead(
        session_id=sess_id,
        name=c_name,
        email=payload.email,
        phone=payload.phone,
        property_id=payload.property_id,
        notes=payload.notes
    )

@router.post("/refine")
def refine_search_endpoint(
    payload: RefinementPayload,
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """
    FR-9: Conversational Refinement API for relative shifts ("cheaper", "more bedrooms", "like #2").
    """
    text = payload.refinement_instruction or payload.refinement_text or ""
    if payload.current_filter:
        filt = PropertySearchFilter(**payload.current_filter)
        refined = PropertyDiscoveryService.refine_search(filt, text)
        return {
            "status": "success",
            "refined_filter": refined.model_dump(),
            "properties": PropertyDiscoveryService.search_and_rank(refined)
        }
    else:
        sess_id = x_session_id or "default_session"
        return PropertyDiscoveryService.refine_search(
            session_id=sess_id,
            refinement_text=text,
            nationality=payload.nationality or "expat"
        )
