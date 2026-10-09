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
                "inquiry_type": payload.inquiry_type
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

# Alias for backward-compatible service imports
LeadCreationRequest = GridLeadPayload
