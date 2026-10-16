"""Read-only property search API (PRD FR-8, §6.1 searchProperties) and KB lookup (retrieve_kb)."""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from app.core.security import enforce_rate_limit
from app.services.property_service import PropertyDiscoveryService, SearchFilters
from app.services.rag_service import RAGService

router = APIRouter(prefix="/api", tags=["Properties & knowledge"], dependencies=[Depends(enforce_rate_limit)])


@router.get("/properties/search")
async def search(location: Optional[str] = None, property_type: Optional[str] = None, bedrooms: Optional[float] = None,
                 budget_min: Optional[float] = None, budget_max: Optional[float] = None, status: Optional[str] = None,
                 developer: Optional[str] = None, amenities: Optional[List[str]] = Query(None)):
    filters = SearchFilters(location=location, property_type=property_type, bedrooms=bedrooms, budget_min=budget_min,
                            budget_max=budget_max, status=status, developer=developer, amenities=amenities)
    res = await PropertyDiscoveryService.search(filters)
    return {"status": res["status"], "total_matches": res["total_matches"],
            "results": [PropertyDiscoveryService.to_card(l, i) for i, l in enumerate(res["results"], 1)]}


@router.get("/kb")
async def knowledge(query: str = Query(..., min_length=2, max_length=500)):
    return await RAGService.retrieve(query)
