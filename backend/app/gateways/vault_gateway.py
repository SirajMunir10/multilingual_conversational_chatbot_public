"""Vault gateway (PRD §6, FR-16): narrow write endpoint for mortgage leads with affordability data."""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx
from pydantic import BaseModel

from app.core.audit import AuditService
from app.core.config import settings

logger = logging.getLogger("xo.gateways.vault")


class VaultMortgageLeadPayload(BaseModel):
    applicant_name: str
    applicant_phone: Optional[str] = None
    preferred_language: Optional[str] = None
    consent_given: bool = False
    monthly_income: Optional[float] = None
    monthly_debts: Optional[float] = None
    calculated_max_loan: Optional[float] = None
    calculated_max_price: Optional[float] = None
    notes: Optional[str] = None


class VaultGateway:

    @classmethod
    async def create_lead(cls, payload: VaultMortgageLeadPayload, session_id: Optional[str] = None) -> Dict[str, Any]:
        if not payload.consent_given:
            raise ValueError("Explicit customer consent is required before sending a mortgage lead to Vault.")
        result = {"crm": "Vault", "synced": False, "application_id": None, "created_at": datetime.now(timezone.utc).isoformat()}
        if settings.VAULT_API_URL:
            try:
                headers = {"Authorization": f"Bearer {settings.VAULT_API_KEY}"} if settings.VAULT_API_KEY else {}
                async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT_SEC) as client:
                    resp = await client.post(f"{settings.VAULT_API_URL.rstrip('/')}/applications", json=payload.model_dump(), headers=headers)
                    resp.raise_for_status()
                    body = resp.json() if resp.content else {}
                    result.update(synced=True, application_id=body.get("application_id") or body.get("id"))
            except Exception as exc:
                logger.warning("Vault lead sync failed: %s", exc)
        AuditService.log_event("business_write", "create_lead_vault", "vault_crm", session_id=session_id,
                               status="success" if result["synced"] else "not_synced",
                               details={"applicant_name": payload.applicant_name, "applicant_phone": payload.applicant_phone,
                                        "synced": result["synced"], "consent_given": True})
        return result
