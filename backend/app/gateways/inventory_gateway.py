from typing import List, Optional
from pydantic import BaseModel, Field
from app.core.audit import AuditService

class ScopedPropertyListing(BaseModel):
    id: str
    title: str
    city: str
    community: str
    type: str  # apartment, villa, townhouse, penthouse
    beds: int
    baths: int
    sq_ft: int
    price: float  # AED
    purpose: str  # buy, rent, invest
    developer: str
    status: str  # ready, off-plan
    image_url: str
    listing_url: str
    amenities: List[str] = Field(default_factory=list)

# Alias for standard naming
PropertyListing = ScopedPropertyListing

class PropertyInventoryGateway:
    """
    Live Property Inventory Gateway.
    Strictly read-only, returning scoped fields only.
    No direct database connection from LLM/bot layer (Rule 4 / PRD Sec 6.1).
    """

    # High-quality mock inventory representative of prime UAE/Dubai market
    _inventory: List[ScopedPropertyListing] = [
        ScopedPropertyListing(
            id="prop-dxb-001",
            title="Luxury 2BR Apartment in Downtown Dubai",
            city="Dubai",
            community="Downtown Dubai",
            type="apartment",
            beds=2,
            baths=2,
            sq_ft=1250,
            price=2450000.0,
            purpose="buy",
            developer="Emaar",
            status="ready",
            image_url="https://images.unsplash.com/photo-1512917774080-9991f1c4c750?auto=format&fit=crop&w=800&q=80",
            listing_url="https://xoto.ae/properties/prop-dxb-001",
            amenities=["Burj Khalifa View", "Swimming Pool", "Gym", "Concierge"]
        ),
        ScopedPropertyListing(
            id="prop-dxb-002",
            title="Modern 2BR Residence with Canal View",
            city="Dubai",
            community="Business Bay",
            type="apartment",
            beds=2,
            baths=3,
            sq_ft=1400,
            price=1950000.0,
            purpose="buy",
            developer="Damac",
            status="ready",
            image_url="https://images.unsplash.com/photo-1545324418-cc1a3fa10c00?auto=format&fit=crop&w=800&q=80",
            listing_url="https://xoto.ae/properties/prop-dxb-002",
            amenities=["Canal View", "Covered Parking", "Balcony", "Security"]
        ),
        ScopedPropertyListing(
            id="prop-dxb-003",
            title="Contemporary 1BR Apartment near Metro",
            city="Dubai",
            community="Dubai Marina",
            type="apartment",
            beds=1,
            baths=2,
            sq_ft=850,
            price=1350000.0,
            purpose="buy",
            developer="Select Group",
            status="ready",
            image_url="https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?auto=format&fit=crop&w=800&q=80",
            listing_url="https://xoto.ae/properties/prop-dxb-003",
            amenities=["Marina Walk Access", "Infinity Pool", "Fitness Club"]
        ),
        ScopedPropertyListing(
            id="prop-dxb-004",
            title="Spacious 3BR Townhouse with Garden",
            city="Dubai",
            community="Dubai Hills Estate",
            type="townhouse",
            beds=3,
            baths=4,
            sq_ft=2800,
            price=3850000.0,
            purpose="buy",
            developer="Emaar",
            status="ready",
            image_url="https://images.unsplash.com/photo-1600585154340-be6161a56a0c?auto=format&fit=crop&w=800&q=80",
            listing_url="https://xoto.ae/properties/prop-dxb-004",
            amenities=["Private Garden", "Golf Course Access", "Parks", "Maid's Room"]
        ),
        ScopedPropertyListing(
            id="prop-dxb-005",
            title="Premium 4BR Luxury Villa",
            city="Dubai",
            community="Palm Jumeirah",
            type="villa",
            beds=4,
            baths=5,
            sq_ft=5200,
            price=14500000.0,
            purpose="buy",
            developer="Nakheel",
            status="ready",
            image_url="https://images.unsplash.com/photo-1613977257363-707ba9348227?auto=format&fit=crop&w=800&q=80",
            listing_url="https://xoto.ae/properties/prop-dxb-005",
            amenities=["Private Beach Access", "Private Pool", "Smart Home System"]
        ),
        ScopedPropertyListing(
            id="prop-dxb-006",
            title="Affordable 1BR Apartment in JVC",
            city="Dubai",
            community="Jumeirah Village Circle",
            type="apartment",
            beds=1,
            baths=1,
            sq_ft=720,
            price=780000.0,
            purpose="buy",
            developer="Ellington",
            status="ready",
            image_url="https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?auto=format&fit=crop&w=800&q=80",
            listing_url="https://xoto.ae/properties/prop-dxb-006",
            amenities=["Community Park", "Gym", "Kid's Play Area"]
        ),
        ScopedPropertyListing(
            id="prop-dxb-007",
            title="Waterfront 2BR at Dubai Creek Harbour",
            city="Dubai",
            community="Dubai Creek Harbour",
            type="apartment",
            beds=2,
            baths=2,
            sq_ft=1150,
            price=2150000.0,
            purpose="buy",
            developer="Emaar",
            status="off-plan",
            image_url="https://images.unsplash.com/photo-1545324418-cc1a3fa10c00?auto=format&fit=crop&w=800&q=80",
            listing_url="https://xoto.ae/properties/prop-dxb-007",
            amenities=["Creek Beach Access", "Marina Promenade", "Sunset Views", "Infinity Pool"]
        ),
        ScopedPropertyListing(
            id="prop-dxb-008",
            title="Ultra-Luxury 5BR Signature Villa in Palm Jumeirah",
            city="Dubai",
            community="Palm Jumeirah",
            type="villa",
            beds=5,
            baths=6,
            sq_ft=7200,
            price=28000000.0,
            purpose="buy",
            developer="Nakheel",
            status="ready",
            image_url="https://images.unsplash.com/photo-1613977257363-707ba9348227?auto=format&fit=crop&w=800&q=80",
            listing_url="https://xoto.ae/properties/prop-dxb-008",
            amenities=["Private Beachfront", "Infinity Pool", "Private Elevator", "Atlantis Views"]
        ),
        ScopedPropertyListing(
            id="prop-dxb-009",
            title="High-ROI 1BR in Business Bay (Investment Asset)",
            city="Dubai",
            community="Business Bay",
            type="apartment",
            beds=1,
            baths=2,
            sq_ft=820,
            price=1280000.0,
            purpose="invest",
            developer="Omniyat",
            status="ready",
            image_url="https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?auto=format&fit=crop&w=800&q=80",
            listing_url="https://xoto.ae/properties/prop-dxb-009",
            amenities=["High Rental Yield", "Fully Furnished", "Canal Promenade", "Metro Nearby"]
        ),
        ScopedPropertyListing(
            id="prop-dxb-010",
            title="Family 4BR Villa in Arabian Ranches III",
            city="Dubai",
            community="Arabian Ranches III",
            type="villa",
            beds=4,
            baths=5,
            sq_ft=3450,
            price=4950000.0,
            purpose="buy",
            developer="Emaar",
            status="ready",
            image_url="https://images.unsplash.com/photo-1600585154340-be6161a56a0c?auto=format&fit=crop&w=800&q=80",
            listing_url="https://xoto.ae/properties/prop-dxb-010",
            amenities=["Gated Community", "Private Garden", "Clubhouse", "Sports Courts"]
        ),
        ScopedPropertyListing(
            id="prop-dxb-011",
            title="Sky Collection 3BR Penthouse in JBR",
            city="Dubai",
            community="Jumeirah Beach Residence",
            type="penthouse",
            beds=3,
            baths=4,
            sq_ft=3900,
            price=9200000.0,
            purpose="buy",
            developer="Dubai Properties",
            status="ready",
            image_url="https://images.unsplash.com/photo-1512917774080-9991f1c4c750?auto=format&fit=crop&w=800&q=80",
            listing_url="https://xoto.ae/properties/prop-dxb-011",
            amenities=["Panoramic Sea View", "Private Rooftop Terrace", "Ain Dubai View", "Beach Access"]
        ),
        ScopedPropertyListing(
            id="prop-auh-012",
            title="Modern 2BR Sea-View Apartment on Yas Island",
            city="Abu Dhabi",
            community="Yas Island",
            type="apartment",
            beds=2,
            baths=2,
            sq_ft=1300,
            price=1750000.0,
            purpose="buy",
            developer="Aldar",
            status="off-plan",
            image_url="https://images.unsplash.com/photo-1545324418-cc1a3fa10c00?auto=format&fit=crop&w=800&q=80",
            listing_url="https://xoto.ae/properties/prop-auh-012",
            amenities=["Sea View", "Yas Marina Access", "Theme Parks Nearby", "Pool & Gym"]
        ),
        ScopedPropertyListing(
            id="prop-dxb-013",
            title="Contemporary 2BR Apartment in Downtown Views",
            city="Dubai",
            community="Downtown Dubai",
            type="apartment",
            beds=2,
            baths=2,
            sq_ft=1180,
            price=1950000.0,
            purpose="buy",
            developer="Emaar",
            status="ready",
            image_url="https://images.unsplash.com/photo-1545324418-cc1a3fa10c00?auto=format&fit=crop&w=800&q=80",
            listing_url="https://xoto.ae/properties/prop-dxb-013",
            amenities=["Boulevard View", "Direct Mall Access", "Infinity Pool", "Modern Gym"]
        ),
        ScopedPropertyListing(
            id="prop-dxb-014",
            title="Luxury 2BR Seafront Apartment in Shoreline, Palm Jumeirah",
            city="Dubai",
            community="Palm Jumeirah",
            type="apartment",
            beds=2,
            baths=3,
            sq_ft=1650,
            price=4850000.0,
            purpose="buy",
            developer="Nakheel",
            status="ready",
            image_url="https://images.unsplash.com/photo-1512917774080-9991f1c4c750?auto=format&fit=crop&w=800&q=80",
            listing_url="https://xoto.ae/properties/prop-dxb-014",
            amenities=["Private Beach Club", "Burj Al Arab View", "Swimming Pool & Gym", "Concierge Service"]
        ),
        ScopedPropertyListing(
            id="prop-dxb-015",
            title="Ultra-Luxury 3BR Waterfront Residence at Palm Views",
            city="Dubai",
            community="Palm Jumeirah",
            type="apartment",
            beds=3,
            baths=4,
            sq_ft=2200,
            price=7950000.0,
            purpose="buy",
            developer="Omniyat",
            status="ready",
            image_url="https://images.unsplash.com/photo-1545324418-cc1a3fa10c00?auto=format&fit=crop&w=800&q=80",
            listing_url="https://xoto.ae/properties/prop-dxb-015",
            amenities=["Panoramic Marina Views", "Beach Access", "Valet Parking", "Infinity Pool"]
        ),
        ScopedPropertyListing(
            id="prop-dxb-016",
            title="Park View 2BR Luxury Residence in Dubai Hills Estate",
            city="Dubai",
            community="Dubai Hills Estate",
            type="apartment",
            beds=2,
            baths=2,
            sq_ft=1320,
            price=2650000.0,
            purpose="buy",
            developer="Emaar",
            status="ready",
            image_url="https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?auto=format&fit=crop&w=800&q=80",
            listing_url="https://xoto.ae/properties/prop-dxb-016",
            amenities=["Golf Course View", "Central Park Access", "Infinity Pool", "Kids Club"]
        ),
        ScopedPropertyListing(
            id="prop-dxb-017",
            title="Executive 2BR Golf Suite at Golf Gate, Dubai Hills",
            city="Dubai",
            community="Dubai Hills Estate",
            type="apartment",
            beds=2,
            baths=3,
            sq_ft=1480,
            price=3450000.0,
            purpose="buy",
            developer="Emaar",
            status="ready",
            image_url="https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?auto=format&fit=crop&w=800&q=80",
            listing_url="https://xoto.ae/properties/prop-dxb-017",
            amenities=["Championship Golf View", "Private Balcony", "Smart Home", "Fitness Center"]
        ),
        ScopedPropertyListing(
            id="prop-dxb-018",
            title="High-Floor 2BR Marina View Apartment in Marina Gate",
            city="Dubai",
            community="Dubai Marina",
            type="apartment",
            beds=2,
            baths=3,
            sq_ft=1420,
            price=3200000.0,
            purpose="buy",
            developer="Select Group",
            status="ready",
            image_url="https://images.unsplash.com/photo-1545324418-cc1a3fa10c00?auto=format&fit=crop&w=800&q=80",
            listing_url="https://xoto.ae/properties/prop-dxb-018",
            amenities=["Full Marina View", "Marina Promenade Direct Access", "Infinity Pool", "Squash Courts"]
        )
    ]

    @classmethod
    def search_properties(
        cls,
        city: Optional[str] = None,
        type: Optional[str] = None,
        budget_min: Optional[float] = None,
        budget_max: Optional[float] = None,
        beds: Optional[int] = None,
        purpose: Optional[str] = None,
        status: Optional[str] = None,
        developer: Optional[str] = None,
        limit: Optional[int] = 5,
        session_id: Optional[str] = None
    ) -> List[ScopedPropertyListing]:
        """
        PRD Architecture Function: search_properties(city, type, budget_min, budget_max, beds)
        """
        results = cls._inventory

        if city:
            c_low = city.lower().strip()
            # If user searches "UAE" or "all UAE", return all UAE properties without filtering out Dubai/Abu Dhabi
            if c_low in ["uae", "all", "any", "united arab emirates", "all uae", "all of uae", "anywhere in uae", "anywhere"]:
                pass
            elif c_low in ["dubai", "all dubai", "anywhere in dubai", "dxb"]:
                results = [p for p in results if "dubai" in p.city.lower()]
            elif c_low in ["abu dhabi", "all abu dhabi", "auh"]:
                results = [p for p in results if "abu dhabi" in p.city.lower()]
            else:
                results = [p for p in results if c_low in p.city.lower() or c_low in p.community.lower()]
        if type:
            results = [p for p in results if type.lower() in p.type.lower()]
        if budget_min is not None:
            results = [p for p in results if p.price >= budget_min]
        if budget_max is not None:
            results = [p for p in results if p.price <= budget_max]
        if beds is not None:
            results = [p for p in results if p.beds == beds]
        if purpose:
            p_low = purpose.lower().strip()
            if p_low in ["invest", "investment"]:
                results = [p for p in results if p.purpose.lower() in ["buy", "invest"]]
            else:
                results = [p for p in results if p_low in p.purpose.lower()]
        if status:
            results = [p for p in results if status.lower() in p.status.lower()]
        if developer:
            results = [p for p in results if developer.lower() in p.developer.lower()]

        # Audit log the property search query
        AuditService.log_event(
            event_type="property_inventory_query",
            action="search_properties",
            resource="property_inventory",
            session_id=session_id,
            details={
                "city": city,
                "type": type,
                "budget_min": budget_min,
                "budget_max": budget_max,
                "beds": beds,
                "purpose": purpose,
                "status": status,
                "developer": developer,
                "results_count": len(results)
            }
        )

        if limit is not None:
            return results[:limit]
        return results

    @classmethod
    def get_all_properties(cls) -> List[ScopedPropertyListing]:
        """Return all catalog inventory listings."""
        return list(cls._inventory)

    @classmethod
    def get_property_by_id(cls, property_id: str, session_id: Optional[str] = None) -> Optional[ScopedPropertyListing]:
        """
        Retrieve a single property listing by ID.
        """
        for p in cls._inventory:
            if p.id.lower() == property_id.lower():
                AuditService.log_event(
                    event_type="property_inventory_query",
                    action="get_property_by_id",
                    resource="property_inventory",
                    session_id=session_id,
                    details={"property_id": property_id, "found": True}
                )
                return p
        return None

    @classmethod
    def get_similar_properties(cls, property_id: str, limit: int = 3, session_id: Optional[str] = None) -> List[ScopedPropertyListing]:
        """
        FR-9 Conversational Refinement: Find properties similar to a referenced property.
        Matches by same property type, community or nearby price range (+/- 25%).
        """
        target = cls.get_property_by_id(property_id, session_id=session_id)
        if not target:
            return []

        candidates = [p for p in cls._inventory if p.id != target.id]

        def similarity_score(prop: ScopedPropertyListing) -> int:
            score = 0
            if prop.type == target.type:
                score += 3
            if prop.community == target.community or prop.city == target.city:
                score += 2
            if abs(prop.price - target.price) / target.price <= 0.25:
                score += 3
            if prop.beds == target.beds:
                score += 1
            return score

        candidates.sort(key=similarity_score, reverse=True)
        results = candidates[:limit]

        AuditService.log_event(
            event_type="property_inventory_query",
            action="get_similar_properties",
            resource="property_inventory",
            session_id=session_id,
            details={"reference_property_id": property_id, "results_count": len(results)}
        )
        return results

# Method alias
PropertyInventoryGateway.search = PropertyInventoryGateway.search_properties

