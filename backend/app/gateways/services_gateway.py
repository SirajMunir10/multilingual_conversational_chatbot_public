"""Services & quotations gateway (PRD §6.1 getServicePricing). Rates come from data/config/services_pricing.json."""
from typing import Any, Dict, Optional

from app.core.audit import AuditService
from app.core.config import load_config


class ServicesGateway:

    @classmethod
    def available_categories(cls) -> list:
        return list(load_config("services_pricing")["services"].keys())

    @classmethod
    def get_service_pricing(cls, category: str, area_sq_ft: float, session_id: Optional[str] = None) -> Dict[str, Any]:
        table = load_config("services_pricing")
        key = (category or "").strip().lower().replace(" ", "_").replace("-", "_")
        if key not in table["services"]:
            return {"status": "unknown_category", "available_categories": cls.available_categories()}
        if area_sq_ft <= 0:
            return {"status": "invalid_area", "message": "Area must be greater than zero."}
        cfg = table["services"][key]
        estimate = {
            "status": "success",
            "category": key,
            "area_sq_ft": area_sq_ft,
            "rate_per_sqft_aed": cfg["rate_per_sqft"],
            "estimated_total_aed": round(area_sq_ft * cfg["rate_per_sqft"], 2),
            "timeline_weeks": max(cfg["min_weeks"], int(area_sq_ft / cfg["sqft_per_week"])),
            "inclusions": cfg["inclusions"],
            "table_status": table["note"],
            "disclaimer": "indicative quotation only, subject to on-site assessment",
        }
        AuditService.log_event("service_pricing_query", "get_service_pricing", "service_quotations", session_id=session_id,
                               details={"category": key, "area": area_sq_ft})
        return estimate
