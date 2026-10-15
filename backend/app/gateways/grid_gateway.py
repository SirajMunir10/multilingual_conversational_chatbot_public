from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from app.core.audit import AuditService

class GridLeadPayload(BaseModel):
    contact_name: str
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    property_id: Optional[str] = None
    inquiry_type: str = "property_inquiry"  # property_inquiry, shortlist_save, viewing_request
    preferred_timeline: Optional[str] = None
    budget_max: Optional[float] = None
    notes: Optional[str] = None

class GridLeadResponse(BaseModel):
    lead_id: str
    crm: str = "GRID"
    status: str = "created"
    created_at: str

class GridGateway:
    """
    GRID — In-house Real Estate CRM Gateway.
    Accessed strictly through this scoped API gateway.
    No direct database connection from LLM/bot layer (Rule 4 / PRD Sec 6.1).
    All writes are strictly logged.
    """
    _leads_store: List[Dict[str, Any]] = []

    @classmethod
    def create_lead(
        cls,
        payload: GridLeadPayload,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> GridLeadResponse:
        lead_id = f"grid_lead_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        record = {
            "lead_id": lead_id,
            "crm": "GRID",
            "payload": payload.model_dump(),
            "session_id": session_id,
            "user_id": user_id,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        # Live external API integration if endpoint configured
        from app.core.config import settings
        if settings.GRID_API_URL:
            try:
                import httpx
                headers = {"Content-Type": "application/json"}
                if settings.GRID_API_KEY:
                    headers["Authorization"] = f"Bearer {settings.GRID_API_KEY}"
                with httpx.Client(timeout=5.0) as client:
                    resp = client.post(
                        f"{settings.GRID_API_URL.rstrip('/')}/leads",
                        json=record["payload"],
                        headers=headers
                    )
                    if resp.is_success:
                        resp_data = resp.json()
                        lead_id = resp_data.get("lead_id") or resp_data.get("id") or lead_id
                        record["lead_id"] = lead_id
            except Exception as e:
                import logging
                logging.getLogger("xo.gateways.grid").warning(f"Could not sync with live GRID API: {e}")

        cls._leads_store.append(record)

        # Mandatory audit logging for business write action
        AuditService.log_event(
            event_type="business_write",
            action="create_lead_grid",
            resource="grid_crm",
            session_id=session_id,
            user_id=user_id,
            details={
                "lead_id": lead_id,
                "property_id": payload.property_id,
                "inquiry_type": payload.inquiry_type,
                "live_api_synced": bool(settings.GRID_API_URL)
            }
        )

        return GridLeadResponse(
            lead_id=lead_id,
            status="created",
            created_at=record["created_at"]
        )

    @classmethod
    def get_lead(cls, lead_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve lead by ID for audit and verification."""
        for item in cls._leads_store:
            if item["lead_id"] == lead_id:
                data = dict(item["payload"])
                data["lead_id"] = item["lead_id"]
                data["created_at"] = item["created_at"]
                return data
        return None

    @classmethod
    def get_user_leads(cls, user_id: str) -> List[Dict[str, Any]]:
        """Retrieve leads scoped strictly to the authenticated user ID."""
        results = []
        for item in cls._leads_store:
            if item.get("user_id") == user_id:
                data = dict(item["payload"])
                data["lead_id"] = item["lead_id"]
                data["crm"] = "GRID"
                data["type"] = f"GRID {item['payload'].get('inquiry_type', 'Property Inquiry').replace('_', ' ').title()}"
                data["status"] = "in_progress"
                data["status_label"] = "Agent Review In Progress"
                data["created_at"] = item["created_at"]
                results.append(data)
        return results

    @classmethod
    def search_offplan_projects(
        cls,
        search: Optional[str] = None,
        city: Optional[str] = None,
        district: Optional[str] = None,
        property_type: Optional[str] = None,
        bedrooms: Optional[int] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        limit: int = 20,
        page: int = 1,
        session_id: Optional[str] = None
    ) -> List[Any]:
        """
        Phase 6 / Master AI: Query live GRID Off-Plan API endpoint.
        Returns ScopedPropertyListing items for live off-plan catalog projects.
        Data classification: External Off-Plan Aggregator (Non-PII, Public Off-Plan Inventory).
        """
        import re
        import logging
        from app.core.config import settings
        from app.gateways.inventory_gateway import ScopedPropertyListing

        url = settings.GRID_OFFPLAN_API_URL or "https://xoto.ae/api/gridoffplan/website"
        raw_items = []

        # Ensure city-wide Dubai searches use provider's city parameter, not district parameter
        if district and district.lower().strip() in ["dubai", "all dubai", "uae", "all uae", "dxb"]:
            city = "Dubai"
            district = None

        params = {"limit": str(limit), "page": str(page)}
        if city:
            params["city"] = city
        if district:
            clean_dist = district.replace("\xa0", " ").strip()
            params["district"] = clean_dist
        if search:
            s_low = search.lower().strip()
            # Handle Imtiaz / Imtiyaz spelling alignment for provider query
            if s_low in ["imtiaz", "imtiyaz"]:
                params["search"] = "Imtiaz"
            else:
                params["search"] = search
        if property_type:
            pt_low = property_type.lower().strip()
            if "villa" in pt_low:
                params["propertyType"] = "villas"
            elif "townhouse" in pt_low:
                params["propertyType"] = "townhouses"
            elif "apartment" in pt_low:
                params["propertyType"] = "apartments"
        if bedrooms is not None:
            params["bedrooms"] = str(bedrooms)
        if min_price is not None:
            params["min_price"] = str(min_price)
        if max_price is not None:
            params["max_price"] = str(max_price)

        upstream_success = False
        try:
            import httpx
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(url, params=params)
                if resp.is_success:
                    upstream_success = True
                    data = resp.json()
                    raw_items = data.get("data", [])
                else:
                    logging.getLogger("xo.gateways.grid").warning(
                        f"GRID offplan API returned HTTP {resp.status_code}: {resp.text[:200]}"
                    )
        except Exception as e:
            logging.getLogger("xo.gateways.grid").warning(f"GRID offplan API query failed: {e}")

        # In-memory normalization and filtering
        normalized: List[ScopedPropertyListing] = []
        for item in raw_items:
            name = item.get("name", "Off-Plan Project")
            loc = item.get("location") or {}
            raw_district = (loc.get("district") or item.get("address") or "Dubai").replace("\xa0", " ").strip()
            item_city = loc.get("city") or "Dubai"

            # Parse bedrooms integer
            beds_str = item.get("bedrooms", "1")
            bed_m = re.search(r'(\d+)', str(beds_str))
            beds = int(bed_m.group(1)) if bed_m else 1

            # Extract developer truthfully without inventing names
            if " by " in name:
                dev = name.split(" by ")[-1].strip()
            elif "pearl house" in name.lower() or "imtiaz" in name.lower() or "imtiyaz" in name.lower():
                dev = "Imtiaz"
            else:
                dev = "Developer TBA"

            p_min = float(item.get("min_price") or 0.0)
            p_max = float(item.get("max_price") or p_min or 1000000.0)
            price = p_min if p_min > 0 else p_max

            # Price filters
            if min_price and price < min_price:
                continue
            if max_price and price > max_price:
                continue

            # District filter match if passed
            if district:
                dist_clean = district.lower().replace("\xa0", " ").strip()
                if dist_clean not in raw_district.lower() and dist_clean not in item_city.lower():
                    continue

            # Developer / search filter match if passed
            if search:
                s_low = search.lower().strip()
                if s_low in ["imtiaz", "imtiyaz"]:
                    if "imtiaz" not in name.lower() and "imtiyaz" not in name.lower() and "pearl house" not in name.lower() and "imtiaz" not in dev.lower():
                        continue
                elif s_low not in name.lower() and s_low not in dev.lower() and s_low not in raw_district.lower():
                    continue

            p_type = "apartment"
            raw_type = (item.get("property_type") or "").lower()
            if "villa" in raw_type:
                p_type = "villa"
            elif "townhouse" in raw_type:
                p_type = "townhouse"

            # Preserve missing property fields as unknown; do not infer amenities from construction status or completion dates
            raw_amenities = item.get("amenities") or item.get("facilities") or []
            if isinstance(raw_amenities, list):
                genuine_amenities = [str(a).strip() for a in raw_amenities if str(a).strip()]
            else:
                genuine_amenities = []

            # Preserve missing sq_ft and baths as unknown (None) rather than inventing false values
            raw_sqft = item.get("sq_ft") or item.get("sqft") or item.get("area") or item.get("size")
            parsed_sqft = None
            if raw_sqft is not None:
                try:
                    val = float(str(raw_sqft).replace(",", "").strip())
                    if val > 0:
                        parsed_sqft = int(val)
                except (ValueError, TypeError):
                    parsed_sqft = None

            raw_baths = item.get("bathrooms") or item.get("baths")
            parsed_baths = None
            if raw_baths is not None:
                try:
                    b_val = int(raw_baths)
                    if b_val > 0:
                        parsed_baths = b_val
                except (ValueError, TypeError):
                    parsed_baths = None

            listing = ScopedPropertyListing(
                id=f"grid-offplan-{item.get('id', item.get('_id', '0'))}",
                title=name,
                city=item_city,
                community=raw_district,
                type=p_type,
                beds=beds,
                baths=parsed_baths,
                sq_ft=parsed_sqft,
                price=price,
                purpose="buy",
                developer=dev,
                status="off-plan",
                image_url=item.get("cover_image") or (item.get("images")[0] if item.get("images") else ""),
                listing_url=f"https://xoto.ae/properties/off-plan/{item.get('slug', item.get('id', ''))}",
                amenities=genuine_amenities
            )
            normalized.append(listing)
            if len(normalized) >= limit:
                break

        # Audit query
        AuditService.log_event(
            event_type="grid_offplan_query",
            action="search_offplan_projects",
            resource="grid_offplan_api",
            session_id=session_id,
            details={
                "search": search,
                "city": city,
                "district": district,
                "min_price": min_price,
                "max_price": max_price,
                "upstream_success": upstream_success,
                "results_count": len(normalized)
            }
        )

        return normalized

# Alias for backward-compatible service imports
LeadCreationRequest = GridLeadPayload

