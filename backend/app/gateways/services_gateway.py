from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from app.core.audit import AuditService

class ServicePricingEstimate(BaseModel):
    category: str
    area_sq_ft: float
    base_rate_per_sq_ft: float
    estimated_total_aed: float
    timeline_weeks: int
    package_inclusions: list[str] = Field(default_factory=list)
    disclaimer: str = "indicative quotation only, subject to on-site engineering assessment"

class ServicesGateway:
    """
    Live Services & Quotations Gateway.
    PRD Architecture Function: get_service_pricing(category, area_sq_ft)
    """

    _pricing_matrix = {
        "interior_design": {
            "rate_per_sqft": 140.0,
            "min_weeks": 4,
            "inclusions": ["3D Visualizations", "Material Sourcing", "FF&E Schedule", "Site Supervision"]
        },
        "landscaping": {
            "rate_per_sqft": 85.0,
            "min_weeks": 3,
            "inclusions": ["Automated Irrigation", "Softscape & Flora", "Hardscape Paving", "Outdoor Lighting"]
        },
        "smart_home": {
            "rate_per_sqft": 45.0,
            "min_weeks": 2,
            "inclusions": ["Lighting Automation", "HVAC Control", "Security Sensors", "Mobile Integration"]
        }
    }

    @classmethod
    def get_service_pricing(
        cls,
        category: str,
        area_sq_ft: float,
        session_id: Optional[str] = None
    ) -> ServicePricingEstimate:
        norm_cat = category.lower().replace(" ", "_")
        config = cls._pricing_matrix.get(norm_cat, cls._pricing_matrix["interior_design"])
        
        total = round(area_sq_ft * config["rate_per_sqft"], 2)
        timeline = max(config["min_weeks"], int(area_sq_ft / 500))

        estimate = ServicePricingEstimate(
            category=category,
            area_sq_ft=area_sq_ft,
            base_rate_per_sq_ft=config["rate_per_sqft"],
            estimated_total_aed=total,
            timeline_weeks=timeline,
            package_inclusions=config["inclusions"]
        )

        AuditService.log_event(
            event_type="service_pricing_query",
            action="get_service_pricing",
            resource="service_quotations",
            session_id=session_id,
            details=estimate.model_dump()
        )

        return estimate
