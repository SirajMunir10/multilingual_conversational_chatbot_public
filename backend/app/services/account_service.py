"""Account-aware answers (PRD FR-21–FR-23a): only for a verified signed-in user, via narrow functions.

No customer data is seeded in code. Saved properties come from XOTO's account API once it is
integrated; until then a signed-in user's in-session saves are returned."""
from typing import Any, Dict, List, Optional

from app.core.audit import AuditService
from app.gateways.inventory_gateway import SampleInventoryGateway


class AccountService:
    _saved: Dict[str, List[str]] = {}

    @classmethod
    def _auth_required(cls, action: str, session_id: Optional[str]) -> Dict[str, Any]:
        AuditService.log_event("security_boundary", action, "user_account", session_id=session_id, status="auth_required")
        return {"status": "auth_required", "authenticated": False,
                "instruction": "Tell the user to sign in to their XOTO account to see this. Do not show any account data."}

    @classmethod
    def get_my_saved_properties(cls, user_id: Optional[str], session_id: Optional[str] = None) -> Dict[str, Any]:
        if not user_id:
            return cls._auth_required("get_my_saved_properties", session_id)
        ids = cls._saved.get(user_id, [])
        items = [l.summary() for l in (SampleInventoryGateway.get(i) for i in ids) if l]
        AuditService.log_event("customer_data_access", "get_my_saved_properties", "user_account", session_id=session_id,
                               user_id=user_id, details={"count": len(items)})
        return {"status": "success", "authenticated": True, "count": len(items), "saved_properties": items}

    @classmethod
    def get_my_application_status(cls, user_id: Optional[str], session_id: Optional[str] = None) -> Dict[str, Any]:
        if not user_id:
            return cls._auth_required("get_my_application_status", session_id)
        AuditService.log_event("customer_data_access", "get_my_application_status", "user_account", session_id=session_id, user_id=user_id)
        return {"status": "not_connected", "authenticated": True,
                "instruction": "Application status is not connected to XO yet. Say so and offer an advisor."}

    @classmethod
    def save_property(cls, user_id: str, listing_id: str, session_id: Optional[str] = None) -> int:
        saved = cls._saved.setdefault(user_id, [])
        if listing_id not in saved:
            saved.append(listing_id)
        AuditService.log_event("business_write", "save_property", "user_account", session_id=session_id, user_id=user_id,
                               details={"listing": listing_id})
        return len(saved)
