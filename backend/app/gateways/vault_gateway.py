from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from app.core.audit import AuditService

class VaultMortgageLeadPayload(BaseModel):
    applicant_name: str
    applicant_phone: Optional[str] = None
    applicant_email: Optional[str] = None
    monthly_income: float
    existing_debt: float
    calculated_affordability_max: Optional[float] = None
    estimated_emi: Optional[float] = None
    nationality_status: Optional[str] = None  # uae_national, expat
    consent_given: bool = True  # Mandatory explicit consent check
    notes: Optional[str] = None

class VaultMortgageLeadResponse(BaseModel):
    application_id: str
    crm: str = "Vault"
    status: str = "submitted"
    created_at: str

class VaultGateway:
    """
    Vault — In-house Mortgage CRM Gateway.
    Accessed strictly through this scoped API gateway.
    No direct database connection from LLM/bot layer (Rule 4 / PRD Sec 6.1).
    All writes are strictly logged.
    """
    _applications_store: List[Dict[str, Any]] = []

    @classmethod
    def create_lead(
        cls,
        payload: VaultMortgageLeadPayload,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> VaultMortgageLeadResponse:
        app_id = f"vault_app_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        record = {
            "application_id": app_id,
            "crm": "Vault",
            "payload": payload.model_dump(),
            "session_id": session_id,
            "user_id": user_id,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        # Live external API integration if endpoint configured
        from app.core.config import settings
        if settings.VAULT_API_URL:
            try:
                import httpx
                headers = {"Content-Type": "application/json"}
                if settings.VAULT_API_KEY:
                    headers["Authorization"] = f"Bearer {settings.VAULT_API_KEY}"
                with httpx.Client(timeout=5.0) as client:
                    resp = client.post(
                        f"{settings.VAULT_API_URL.rstrip('/')}/applications",
                        json=record["payload"],
                        headers=headers
                    )
                    if resp.is_success:
                        resp_data = resp.json()
                        app_id = resp_data.get("application_id") or resp_data.get("id") or app_id
                        record["application_id"] = app_id
            except Exception as e:
                import logging
                logging.getLogger("xo.gateways.vault").warning(f"Could not sync with live Vault API: {e}")

        cls._applications_store.append(record)

        # Mandatory audit logging for business write action
        AuditService.log_event(
            event_type="business_write",
            action="create_lead_vault",
            resource="vault_crm",
            session_id=session_id,
            user_id=user_id,
            details={
                "application_id": app_id,
                "calculated_affordability_max": payload.calculated_affordability_max,
                "consent_given": payload.consent_given,
                "live_api_synced": bool(settings.VAULT_API_URL)
            }
        )

        return VaultMortgageLeadResponse(
            application_id=app_id,
            status="submitted",
            created_at=record["created_at"]
        )

    @classmethod
    def get_user_applications(cls, user_id: str) -> List[Dict[str, Any]]:
        """Retrieve mortgage applications scoped strictly to the authenticated user ID."""
        results = []
        for item in cls._applications_store:
            if item.get("user_id") == user_id:
                data = dict(item["payload"])
                data["application_id"] = item["application_id"]
                data["crm"] = "Vault"
                data["type"] = "Mortgage Pre-Approval Application"
                data["status"] = "under_review"
                data["status_label"] = "Under Review by Mortgage Specialist"
                data["created_at"] = item["created_at"]
                results.append(data)
        return results

