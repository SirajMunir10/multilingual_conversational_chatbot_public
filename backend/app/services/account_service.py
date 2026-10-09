from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
import logging
from pydantic import BaseModel, Field

from app.core.audit import AuditService
from app.gateways.inventory_gateway import PropertyInventoryGateway
from app.gateways.vault_gateway import VaultGateway
from app.gateways.grid_gateway import GridGateway

logger = logging.getLogger("xo.account_service")

class UserAccountProfile(BaseModel):
    user_id: str
    full_name: str
    email: str
    phone: Optional[str] = None
    account_tier: str = "VIP"  # VIP, Standard, Investor
    saved_property_ids: List[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class AccountService:
    """
    PRD Architecture Component: Account Awareness & Data Boundary Layer (Rule 4, Rule 9, FR-21, FR-22).
    
    Principles:
    1. USER-SCOPED DATA ACCESS ONLY (FR-21):
       An authenticated user can query and manipulate ONLY their own account data.
    2. REJECT CROSS-USER INQUIRIES (FR-22):
       Never accept target user_id parameters from client input; the user_id is strictly
       derived from the authenticated session context.
    3. ZERO PAYMENT HANDLING (FR-23b):
       No credit cards, IBANs, or payment collections.
    4. NO DIRECT DB ACCESS (FR-23a):
       All interactions go through scoped service methods.
    5. AUDIT LOGGING (FR-22):
       Every read and write to user-scoped data writes a tamper-evident audit record.
    """

    # In-memory user profiles store
    _user_profiles: Dict[str, UserAccountProfile] = {}
    _initialized: bool = False

    @classmethod
    def _ensure_seed_data(cls):
        """Seed realistic user profiles for authenticated prototype testing."""
        if cls._initialized:
            return

        # 1. VIP Client Siraj Munir
        cls._user_profiles["user_siraj_vip"] = UserAccountProfile(
            user_id="user_siraj_vip",
            full_name="Siraj Munir",
            email="siraj@xoto.ae",
            phone="+971 50 789 1234",
            account_tier="VIP Premier",
            saved_property_ids=["prop-dxb-001", "prop-dxb-002"]
        )

        # 2. Investor Layla Al-Hashimi
        cls._user_profiles["user_layla_investor"] = UserAccountProfile(
            user_id="user_layla_investor",
            full_name="Layla Al-Hashimi",
            email="layla@alhashimi-invest.ae",
            phone="+971 52 345 6789",
            account_tier="High-Yield Investor",
            saved_property_ids=["prop-dxb-003", "prop-dxb-006"]
        )

        cls._initialized = True
        logger.info("AccountService seed profiles initialized.")

    @classmethod
    def get_or_create_profile(cls, user_id: str, full_name: Optional[str] = None) -> UserAccountProfile:
        cls._ensure_seed_data()
        if user_id not in cls._user_profiles:
            cls._user_profiles[user_id] = UserAccountProfile(
                user_id=user_id,
                full_name=full_name or f"User {user_id}",
                email=f"{user_id}@client.xoto.ae",
                account_tier="Standard"
            )
        return cls._user_profiles[user_id]

    @classmethod
    def get_my_saved_properties(
        cls,
        user_id: Optional[str],
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        PRD Function: get_my_saved_properties()
        Retrieves shortlisted/saved residences strictly for the authenticated user.
        If user_id is None, returns an auth_required prompt without leaking data.
        """
        cls._ensure_seed_data()

        # Unauthenticated Guard (FR-21, FR-22)
        if not user_id:
            AuditService.log_event(
                event_type="security_boundary",
                action="get_my_saved_properties",
                resource="user_account",
                session_id=session_id,
                status="auth_required",
                details={"reason": "Unauthenticated user attempted to access saved properties"}
            )
            return {
                "status": "auth_required",
                "authenticated": False,
                "message": "Authentication required. Please sign in to view your saved properties.",
                "saved_properties": []
            }

        profile = cls.get_or_create_profile(user_id)
        
        # Hydrate properties from Inventory Gateway
        saved_items = []
        for pid in profile.saved_property_ids:
            prop = PropertyInventoryGateway.get_property_by_id(pid)
            if prop:
                prop_data = prop.model_dump()
                prop_data["is_shortlisted"] = True
                saved_items.append(prop_data)

        # Mandatory Audit Logging for Customer Data Access (FR-22)
        AuditService.log_event(
            event_type="customer_data_access",
            action="get_my_saved_properties",
            resource="user_account",
            session_id=session_id,
            user_id=user_id,
            status="success",
            details={
                "retrieved_count": len(saved_items),
                "property_ids": profile.saved_property_ids
            }
        )

        return {
            "status": "success",
            "authenticated": True,
            "user_id": user_id,
            "user_name": profile.full_name,
            "account_tier": profile.account_tier,
            "count": len(saved_items),
            "saved_properties": saved_items
        }

    @classmethod
    def get_my_application_status(
        cls,
        user_id: Optional[str],
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        PRD Function: get_my_application_status()
        Retrieves active mortgage pre-approvals (Vault) and property viewings (GRID)
        strictly for the authenticated user.
        """
        cls._ensure_seed_data()

        # Unauthenticated Guard (FR-21, FR-22)
        if not user_id:
            AuditService.log_event(
                event_type="security_boundary",
                action="get_my_application_status",
                resource="user_account",
                session_id=session_id,
                status="auth_required",
                details={"reason": "Unauthenticated user attempted to access application status"}
            )
            return {
                "status": "auth_required",
                "authenticated": False,
                "message": "Authentication required. Please sign in to view your application status.",
                "applications": []
            }

        profile = cls.get_or_create_profile(user_id)

        # 1. Fetch user-scoped mortgage applications from Vault CRM
        vault_apps = VaultGateway.get_user_applications(user_id)

        # Provide pre-seeded application for user_siraj_vip if empty
        if user_id == "user_siraj_vip" and not vault_apps:
            vault_apps = [{
                "application_id": "VAULT-MORT-9021",
                "crm": "Vault",
                "type": "Mortgage Pre-Approval",
                "lender_partner": "Emirates NBD",
                "requested_loan_aed": 3500000.0,
                "calculated_affordability_max": 4200000.0,
                "monthly_income": 45000.0,
                "status": "under_review",
                "status_label": "Under Review (Credit Assessment)",
                "assigned_officer": "Sarah Al-Maktoum (Mortgage Specialist)",
                "created_at": "2026-10-08T14:30:00Z",
                "last_update": "Document verification in progress"
            }]

        # 2. Fetch user-scoped property inquiries from GRID CRM
        grid_leads = GridGateway.get_user_leads(user_id)
        if user_id == "user_siraj_vip" and not grid_leads:
            grid_leads = [{
                "lead_id": "GRID-LEAD-4821",
                "crm": "GRID",
                "type": "VIP Property Viewing",
                "property_id": "prop-dxb-001",
                "property_title": "Palm Jumeirah Luxury Penthouse",
                "status": "scheduled",
                "status_label": "Viewing Scheduled",
                "scheduled_date": "2026-10-12T11:00:00+04:00",
                "assigned_agent": "Omar Farooq (Prime Consultant)",
                "created_at": "2026-10-07T09:15:00Z"
            }]

        all_applications = vault_apps + grid_leads

        # Mandatory Audit Logging for Customer Data Access (FR-22)
        AuditService.log_event(
            event_type="customer_data_access",
            action="get_my_application_status",
            resource="user_account",
            session_id=session_id,
            user_id=user_id,
            status="success",
            details={
                "vault_applications_count": len(vault_apps),
                "grid_inquiries_count": len(grid_leads),
                "total_records": len(all_applications)
            }
        )

        return {
            "status": "success",
            "authenticated": True,
            "user_id": user_id,
            "user_name": profile.full_name,
            "total_count": len(all_applications),
            "applications": all_applications,
            "vault_mortgage_applications": vault_apps,
            "grid_property_inquiries": grid_leads
        }

    @classmethod
    def save_property(
        cls,
        user_id: str,
        property_id: str,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Save a property to the user's shortlisted residences."""
        cls._ensure_seed_data()
        profile = cls.get_or_create_profile(user_id)
        if property_id not in profile.saved_property_ids:
            profile.saved_property_ids.append(property_id)

        AuditService.log_event(
            event_type="business_write",
            action="save_property_to_account",
            resource="user_account",
            session_id=session_id,
            user_id=user_id,
            details={"property_id": property_id}
        )

        return {
            "status": "saved",
            "user_id": user_id,
            "property_id": property_id,
            "saved_count": len(profile.saved_property_ids)
        }

    @classmethod
    def remove_saved_property(
        cls,
        user_id: str,
        property_id: str,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Remove a property from the user's shortlisted residences."""
        cls._ensure_seed_data()
        profile = cls.get_or_create_profile(user_id)
        if property_id in profile.saved_property_ids:
            profile.saved_property_ids.remove(property_id)

        AuditService.log_event(
            event_type="business_write",
            action="remove_saved_property",
            resource="user_account",
            session_id=session_id,
            user_id=user_id,
            details={"property_id": property_id}
        )

        return {
            "status": "removed",
            "user_id": user_id,
            "property_id": property_id,
            "saved_count": len(profile.saved_property_ids)
        }
