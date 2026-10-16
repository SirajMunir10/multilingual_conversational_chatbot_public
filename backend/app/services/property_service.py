"""Property discovery and recommendation (PRD FR-7–FR-11)."""
import difflib
import logging
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from app.core.audit import AuditService
from app.core.config import settings
from app.gateways.grid_gateway import GridOffPlanGateway
from app.gateways.inventory_gateway import Listing, SampleInventoryGateway
from app.services import location_service
from app.services.mortgage_service import EMIInput, MortgageCalculationService

logger = logging.getLogger("xo.property")


class SearchFilters(BaseModel):
    location: Optional[str] = None
    property_type: Optional[str] = None
    bedrooms: Optional[float] = None
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    purpose: Optional[str] = None          # buy | rent | invest
    status: Optional[str] = None           # ready | off-plan | any
    developer: Optional[str] = None
    amenities: Optional[List[str]] = None


def _norm(text: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", (text or "").lower()).strip()


def _developer_matches(wanted: str, actual: Optional[str], title: str) -> bool:
    if not actual and not title:
        return False
    wanted_n = _norm(wanted)
    for candidate in (actual or "", title):
        cand_n = _norm(candidate)
        if not cand_n:
            continue
        if wanted_n in cand_n or difflib.SequenceMatcher(None, wanted_n, cand_n).ratio() >= 0.8:
            return True
        for token in cand_n.split():
            if difflib.SequenceMatcher(None, wanted_n, token).ratio() >= 0.8:
                return True
    return False


def _type_matches(wanted: str, actual: Optional[str]) -> bool:
    if not actual:
        return False
    w, a = _norm(wanted).rstrip("s"), _norm(actual).rstrip("s")
    return w == a or w in a or a in w


def _beds_match(wanted: float, listing: Listing) -> bool:
    if listing.beds_min is None:
        return False
    low, high = listing.beds_min, listing.beds_max if listing.beds_max is not None else listing.beds_min
    return low - 0.5 <= wanted <= high + 0.5 if low != high else abs(low - wanted) < 0.5


def _amenity_match(wanted: str, listing: Listing) -> bool:
    w = _norm(wanted)
    return any(w in _norm(a) or _norm(a) in w for a in listing.amenities)


class PropertyDiscoveryService:

    @classmethod
    async def _inventory(cls, status: Optional[str], session_id: Optional[str]) -> Dict[str, Any]:
        """Off-plan from the live GRID feed, ready from the sample catalogue."""
        sources: List[Listing] = []
        offplan_available = True
        want = (status or "any").lower()
        if want in ("any", "off-plan", "offplan", "off plan"):
            try:
                sources.extend(await GridOffPlanGateway.all(session_id))
            except Exception:
                offplan_available = False
        if want in ("any", "ready"):
            sources.extend(SampleInventoryGateway.all())
        return {"listings": sources, "offplan_feed_available": offplan_available}

    @classmethod
    def _apply(cls, listings: List[Listing], f: SearchFilters, location: Optional[Dict[str, Any]], skip: str = "") -> List[Listing]:
        out = []
        for l in listings:
            if skip != "location" and location and location["kind"] != "unknown" and not location_service.matches(location, l.community, l.city):
                continue
            if skip != "type" and f.property_type and not _type_matches(f.property_type, l.property_type):
                continue
            if skip != "bedrooms" and f.bedrooms is not None and not _beds_match(f.bedrooms, l):
                continue
            if skip != "budget" and f.budget_max is not None and (l.price_on_request or l.price_from > f.budget_max):
                continue
            if skip != "budget" and f.budget_min is not None and (l.price_on_request or (l.price_to or l.price_from) < f.budget_min):
                continue
            if skip != "developer" and f.developer and not _developer_matches(f.developer, l.developer, l.title):
                continue
            if skip != "amenities" and f.amenities and not all(_amenity_match(a, l) for a in f.amenities):
                continue
            out.append(l)
        return out

    @staticmethod
    def _rank(listings: List[Listing], f: SearchFilters) -> List[Listing]:
        def score(l: Listing):
            exact_beds = 0 if (f.bedrooms is None or (l.beds_min == l.beds_max == f.bedrooms)) else 1
            price = l.price_from if l.price_from else float("inf")
            budget_gap = abs((f.budget_max or 0) - price) if f.budget_max else price
            live_first = 0 if l.source == "live_offplan" else 1
            return (exact_beds, 1 if l.price_on_request else 0, budget_gap, live_first)
        return sorted(listings, key=score)

    @classmethod
    def to_card(cls, listing: Listing, ref: int, residency: Optional[str] = None) -> Dict[str, Any]:
        card = listing.model_dump()
        card["ref"] = ref
        card["price_on_request"] = listing.price_on_request
        if listing.price_from:
            try:
                emi = MortgageCalculationService.calc_emi(EMIInput(property_price=listing.price_from, residency=residency, property_status=listing.status))
                card["mortgage_estimate"] = {"monthly_payment_aed": emi["instalment_aed"], "down_payment_aed": emi["down_payment_aed"],
                                             "interest_rate_pct": emi["interest_rate_pct"], "tenure_years": emi["tenure_years"],
                                             "basis": "from price" if listing.price_to and listing.price_to != listing.price_from else "price",
                                             "disclaimer": emi["disclaimer"]}
            except Exception:
                card["mortgage_estimate"] = None
        return card

    @classmethod
    async def search(cls, f: SearchFilters, session_id: Optional[str] = None, limit: Optional[int] = None) -> Dict[str, Any]:
        limit = min(limit or settings.SEARCH_MAX_RESULTS, settings.SEARCH_MAX_RESULTS)
        location = location_service.resolve(f.location)
        if (f.purpose or "").lower() == "rent":
            return {"status": "no_rental_inventory", "results": [], "total_matches": 0, "offplan_feed_available": True,
                    "instruction": ("XO lists properties for sale only — there are no rental listings in XO (this is not an outage). "
                                    "Say this plainly in one sentence, then offer rental help from the knowledge base "
                                    "(typical rents in the area, Ejari, cheques, tenant rights) or properties for sale.")}
        inv = await cls._inventory(f.status, session_id)
        matches = cls._rank(cls._apply(inv["listings"], f, location), f)
        result: Dict[str, Any] = {
            "status": "ok" if matches else "no_exact_matches",
            "applied_filters": {k: v for k, v in f.model_dump().items() if v not in (None, [], "")},
            "total_matches": len(matches),
            "results": matches[:limit],
            "offplan_feed_available": inv["offplan_feed_available"],
        }
        if location and location["kind"] == "unknown":
            result["status"] = "unknown_location"
            result["unknown_location"] = location["name"]
            result["results"] = []
            result["total_matches"] = 0
            result["known_communities_sample"] = location_service.known_communities()[:12]
        elif not matches:
            result["alternatives"] = cls._alternatives(inv["listings"], f, location, limit)
        AuditService.log_event("property_inventory_query", "search_properties", "property_inventory", session_id=session_id,
                               details={"filters": result["applied_filters"], "results": result["total_matches"]})
        return result

    @classmethod
    def _alternatives(cls, listings: List[Listing], f: SearchFilters, location: Optional[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
        """Relax one filter at a time and report exactly which one was relaxed (never silent)."""
        alternatives = []
        for relaxed in ("budget", "bedrooms", "type", "developer", "amenities", "location"):
            active = {"budget": f.budget_max or f.budget_min, "bedrooms": f.bedrooms, "type": f.property_type, "developer": f.developer,
                      "amenities": f.amenities, "location": location}.get(relaxed)
            if not active:
                continue
            found = cls._rank(cls._apply(listings, f, location, skip=relaxed), f)
            if found:
                alternatives.append({"relaxed_filter": relaxed, "count": len(found), "listings": found[:min(limit, 3)]})
            if len(alternatives) == 2:
                break
        return alternatives

    @classmethod
    def similar(cls, reference: Listing, pool: List[Listing], limit: int = 3) -> List[Listing]:
        def score(l: Listing):
            same_comm = 0 if l.community == reference.community else 1
            same_type = 0 if l.property_type == reference.property_type else 1
            ref_price = reference.price_from or 0
            gap = abs((l.price_from or 0) - ref_price) / ref_price if ref_price else 1
            beds_gap = abs((l.beds_min or 0) - (reference.beds_min or 0))
            return (same_type, round(gap, 1), same_comm, beds_gap)
        return sorted([l for l in pool if l.id != reference.id and not l.price_on_request], key=score)[:limit]

    @classmethod
    async def all_listings(cls, session_id: Optional[str] = None) -> List[Listing]:
        return (await cls._inventory("any", session_id))["listings"]

    @classmethod
    def compare(cls, listings: List[Listing], residency: Optional[str] = None) -> Dict[str, Any]:
        rows = []
        for i, l in enumerate(listings, 1):
            row: Dict[str, Any] = {"listing": l.title, "community": l.community, "status": l.status, **l.summary()}
            if l.price_from and l.size_sqft:
                row["price_per_sqft_aed"] = round(l.price_from / l.size_sqft)
            if l.price_from:
                emi = MortgageCalculationService.calc_emi(EMIInput(property_price=l.price_from, residency=residency, property_status=l.status))
                row["monthly_payment_aed"] = round(emi["instalment_aed"])
                row["down_payment_aed"] = round(emi["down_payment_aed"])
                row["mortgage_assumptions"] = emi["assumptions"]
            rows.append(row)
        return {"compared": rows, "note": "Rental yields are not part of listing data; ask about an area to get the KB yield range."}
