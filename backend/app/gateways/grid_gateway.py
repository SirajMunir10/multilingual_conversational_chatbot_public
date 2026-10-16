"""GRID gateways (PRD §6, §6.1): live off-plan feed (read-only) and real-estate lead writes."""
import asyncio
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel

from app.core.audit import AuditService
from app.core.config import settings
from app.gateways.inventory_gateway import Listing
from app.services.location_service import canonical_community, emirate_label

logger = logging.getLogger("xo.gateways.grid")

_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_DEVELOPER_IN_TEXT = re.compile(r"\bby ([A-Z][\w&'.-]*(?: [A-Z][\w&'.-]*){0,3})")


def _bed_range(raw: Any):
    nums = [float(n) for n in _NUMBER.findall(str(raw or ""))]
    if not nums:
        return None, None
    return min(nums), max(nums)


def _positive(value: Any) -> Optional[float]:
    try:
        v = float(value)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def _developer(item: Dict[str, Any]) -> Optional[str]:
    """Upstream developer field when present, otherwise the 'by <Developer>' phrase in the name or description."""
    explicit = item.get("developer")
    if isinstance(explicit, dict):
        explicit = explicit.get("name")
    if explicit:
        return str(explicit).strip()
    for text in (item.get("name"), item.get("description")):
        m = _DEVELOPER_IN_TEXT.search(str(text or ""))
        if m:
            return m.group(1).strip()
    return None


def _property_type(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    raw = raw.lower().strip()
    return raw[:-1] if raw.endswith("s") else raw


def normalise_project(item: Dict[str, Any]) -> Listing:
    loc = item.get("location") or {}
    district = loc.get("district") or item.get("address") or ""
    community, emirate = canonical_community(district)
    city = loc.get("city") or ""
    if not emirate:
        emirate = canonical_community(city)[1]
    beds_min, beds_max = _bed_range(item.get("bedrooms"))
    price_from, price_to = _positive(item.get("min_price")), _positive(item.get("max_price"))
    status = "ready" if item.get("construction_status") == "completed" else "off-plan"
    template = settings.OFFPLAN_LISTING_URL_TEMPLATE
    return Listing(
        id=f"offplan-{item.get('id') or item.get('_id')}",
        source="live_offplan",
        title=str(item.get("name") or "").strip(),
        developer=_developer(item),
        city=emirate_label(emirate) or city.replace(" Emirate", "").strip(),
        emirate=emirate,
        community=community,
        property_type=_property_type(item.get("property_type")),
        status=status,
        beds_min=beds_min, beds_max=beds_max,
        baths=_positive(item.get("bathrooms")),
        size_sqft=None,
        price_from=price_from, price_to=price_to or price_from,
        completion=item.get("completion_date"),
        sale_status=item.get("sale_status"),
        image_url=item.get("cover_image") or ((item.get("images") or [None])[0]),
        listing_url=template.format(slug=item["slug"], id=item.get("id")) if template and item.get("slug") else None,
        amenities=[str(a).strip() for a in (item.get("amenities") or item.get("facilities") or []) if str(a).strip()],
    )


class GridOffPlanGateway:
    """Live off-plan projects. The full catalogue is fetched page by page and cached briefly
    so filtering is consistent and the upstream API is not called on every message."""

    _cache: List[Listing] = []
    _fetched_at: float = 0.0
    _lock = asyncio.Lock()

    @classmethod
    async def all(cls, session_id: Optional[str] = None) -> List[Listing]:
        if cls._cache and time.time() - cls._fetched_at < settings.GRID_OFFPLAN_CACHE_SEC:
            return cls._cache
        async with cls._lock:
            if cls._cache and time.time() - cls._fetched_at < settings.GRID_OFFPLAN_CACHE_SEC:
                return cls._cache
            items: List[Dict[str, Any]] = []
            try:
                async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT_SEC) as client:
                    page, total_pages = 1, 1
                    while page <= total_pages:
                        resp = await client.get(settings.GRID_OFFPLAN_API_URL, params={"limit": settings.GRID_OFFPLAN_PAGE_SIZE, "page": page})
                        resp.raise_for_status()
                        data = resp.json()
                        items.extend(data.get("data") or [])
                        total_pages = int(data.get("totalPages") or 1)
                        page += 1
                listings = [normalise_project(i) for i in items if i.get("name") and i.get("sale_status", "on_sale") != "out_of_stock"]
                cls._cache, cls._fetched_at = listings, time.time()
                AuditService.log_event("grid_offplan_query", "refresh_catalogue", "grid_offplan_api", session_id=session_id,
                                       details={"projects": len(listings)})
            except Exception as exc:
                logger.warning("GRID off-plan feed unavailable: %s", exc)
                if not cls._cache:
                    raise
        return cls._cache

    @classmethod
    def clear_cache(cls) -> None:
        cls._cache, cls._fetched_at = [], 0.0


class GridLeadPayload(BaseModel):
    contact_name: str
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    property_reference: Optional[str] = None
    inquiry_type: str = "advisor_callback"
    preferred_language: Optional[str] = None
    budget_max: Optional[float] = None
    notes: Optional[str] = None


class GridLeadGateway:
    """Narrow write endpoint for real-estate leads (PRD §6.1). Every write is audit-logged."""

    @classmethod
    async def create_lead(cls, payload: GridLeadPayload, session_id: Optional[str] = None) -> Dict[str, Any]:
        result = {"crm": "GRID", "synced": False, "lead_id": None, "created_at": datetime.now(timezone.utc).isoformat()}
        if settings.GRID_API_URL:
            try:
                headers = {"Authorization": f"Bearer {settings.GRID_API_KEY}"} if settings.GRID_API_KEY else {}
                async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT_SEC) as client:
                    resp = await client.post(f"{settings.GRID_API_URL.rstrip('/')}/leads", json=payload.model_dump(), headers=headers)
                    resp.raise_for_status()
                    body = resp.json() if resp.content else {}
                    result.update(synced=True, lead_id=body.get("lead_id") or body.get("id"))
            except Exception as exc:
                logger.warning("GRID lead sync failed: %s", exc)
        AuditService.log_event("business_write", "create_lead_grid", "grid_crm", session_id=session_id,
                               status="success" if result["synced"] else "not_synced",
                               details={"contact_name": payload.contact_name, "contact_phone": payload.contact_phone, "synced": result["synced"]})
        return result
