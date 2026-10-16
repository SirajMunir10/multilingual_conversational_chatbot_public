"""Property inventory gateways (PRD FR-8, §6.1): read-only, scoped fields only.

- Ready properties: sample listings from data/config/inventory_sample.json (prototype; not live).
- Off-plan projects: live GRID off-plan feed (see grid_gateway.GridOffPlanGateway).
"""
from typing import List, Optional

from pydantic import BaseModel, Field

from app.core.config import load_config
from app.services.location_service import canonical_community


class Listing(BaseModel):
    id: str
    source: str                      # "live_offplan" | "sample"
    title: str
    developer: Optional[str] = None
    city: str
    emirate: Optional[str] = None
    community: str
    property_type: Optional[str] = None
    status: str                      # "off-plan" | "ready"
    beds_min: Optional[float] = None
    beds_max: Optional[float] = None
    baths: Optional[float] = None
    size_sqft: Optional[int] = None
    price_from: Optional[float] = None
    price_to: Optional[float] = None
    completion: Optional[str] = None
    sale_status: Optional[str] = None
    image_url: Optional[str] = None
    listing_url: Optional[str] = None
    amenities: List[str] = Field(default_factory=list)

    @property
    def price_on_request(self) -> bool:
        return not self.price_from

    def summary(self) -> dict:
        """Compact fields for the LLM (no URLs or internal IDs)."""
        beds = None
        if self.beds_min is not None:
            beds = f"{self.beds_min:g}" if self.beds_max in (None, self.beds_min) else f"{self.beds_min:g}-{self.beds_max:g}"
        price = None
        if self.price_from:
            price = f"AED {self.price_from:,.0f}" if self.price_to in (None, self.price_from) else f"from AED {self.price_from:,.0f}"
        return {k: v for k, v in {
            "title": self.title, "developer": self.developer, "community": self.community, "city": self.city,
            "type": self.property_type, "status": self.status, "bedrooms": beds, "price": price or "price on request",
            "size_sqft": self.size_sqft, "completion": self.completion, "amenities": self.amenities or None,
            "source": "live off-plan feed" if self.source == "live_offplan" else "sample listing",
        }.items() if v not in (None, [], "")}


class SampleInventoryGateway:
    """Sample ready-property listings for the prototype (not live inventory)."""

    @classmethod
    def all(cls) -> List[Listing]:
        rows = load_config("inventory_sample")["listings"]
        listings = []
        for r in rows:
            community, emirate = canonical_community(r["community"])
            listings.append(Listing(
                id=r["id"], source="sample", title=r["title"], developer=r.get("developer"), city=r["city"], emirate=emirate,
                community=community, property_type=r.get("type"), status=r.get("status", "ready"),
                beds_min=r.get("beds"), beds_max=r.get("beds"), baths=r.get("baths"), size_sqft=r.get("sq_ft"),
                price_from=r.get("price"), price_to=r.get("price"), image_url=r.get("image_url"),
                listing_url=r.get("listing_url"), amenities=r.get("amenities") or []))
        return listings

    @classmethod
    def get(cls, listing_id: str) -> Optional[Listing]:
        return next((l for l in cls.all() if l.id == listing_id), None)
