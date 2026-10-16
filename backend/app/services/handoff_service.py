"""Human handoff (PRD FR-5, FR-16, FR-29): consent-gated callback requests with the full transcript.

Flow: the assistant collects name, phone and language, then `prepare_callback` validates them and stores a
draft on the session. The widget shows the draft as a review card (Confirm / Edit). Nothing is saved until
the user confirms the card, which calls `confirm_callback` and writes the lead to the lead store."""
import secrets
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional

import phonenumbers

from app.core.audit import AuditService
from app.core.config import load_config, settings
from app.db.lead_store import LeadDatabaseService
from app.gateways.grid_gateway import GridLeadGateway, GridLeadPayload
from app.gateways.vault_gateway import VaultGateway, VaultMortgageLeadPayload
from app.orchestrator.session_store import SessionContext, SessionStore

TEAMS = {"mortgage": "Mortgage Advisory", "sales": "Property Advisory", "support": "Client Support"}
PHONE_EXAMPLE = "+971 50 123 4567"
MAX_NAME = 120


def normalise_phone(raw: Optional[str]) -> Optional[str]:
    """Returns the number in E.164 (+971501234567) when it is a real, dialable number, else None.
    Numbers without a country code are read as PHONE_DEFAULT_REGION numbers (UAE: 050 123 4567)."""
    if not raw or not raw.strip():
        return None
    text = raw.strip()
    if text.startswith("00"):
        text = "+" + text[2:]
    try:
        number = phonenumbers.parse(text, None if text.startswith("+") else settings.PHONE_DEFAULT_REGION)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(number):
        return None
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)


def display_phone(e164: str) -> str:
    return phonenumbers.format_number(phonenumbers.parse(e164, None), phonenumbers.PhoneNumberFormat.INTERNATIONAL)


def valid_phone(phone: Optional[str]) -> bool:
    return normalise_phone(phone) is not None


def resolve_language(value: Optional[str], fallback: str) -> str:
    """Maps 'hi', 'Hindi' or 'हिन्दी' to a supported language code."""
    locales = load_config("locales")["locales"]
    wanted = (value or "").strip().casefold()
    if wanted in locales:
        return wanted
    for code, loc in locales.items():
        names = {str(loc.get(k, "")).casefold() for k in ("name", "native", "english_name")}
        if wanted and wanted in names:
            return code
    return fallback if fallback in locales else load_config("locales")["default"]


def language_name(code: str) -> str:
    loc = load_config("locales")["locales"].get(code) or {}
    return loc.get("name") or code


class HandoffService:
    _queue: Deque[Dict[str, Any]] = deque(maxlen=2000)

    @classmethod
    def _team(cls, session: SessionContext, requested: Optional[str]) -> str:
        if requested in TEAMS:
            return requested
        if session.last_calculation:
            return "mortgage"
        if session.displayed_listings:
            return "sales"
        return "support"

    @classmethod
    def _draft_view(cls, draft: Dict[str, Any]) -> Dict[str, Any]:
        return {"draft_id": draft["draft_id"], "name": draft["name"], "phone": draft["phone_display"],
                "preferred_language": draft["language"], "team": draft["team"], "status": "review"}

    @classmethod
    def prepare_callback(cls, session: SessionContext, name: str, phone: str, preferred_language: str,
                         consent_confirmed: bool, team: Optional[str] = None, summary: Optional[str] = None) -> Dict[str, Any]:
        """Validates the details and stores them as a draft for the user to review. Saves nothing."""
        if not consent_confirmed:
            return {"status": "consent_missing", "instruction": "Ask the user whether they agree to be contacted before collecting details."}
        missing = [k for k, v in (("full_name", name), ("phone", phone)) if not (v or "").strip()]
        if missing:
            return {"status": "missing_details", "missing": missing,
                    "instruction": f"Nothing failed. Ask only for the missing details in one short message. For the phone, show the format: {PHONE_EXAMPLE} (with country code)."}
        e164 = normalise_phone(phone)
        if not e164:
            return {"status": "invalid_phone",
                    "instruction": f"The phone number is not valid. Ask for the mobile number with the country code, for example {PHONE_EXAMPLE}."}
        draft = {
            "draft_id": secrets.token_urlsafe(8), "name": " ".join(name.split())[:MAX_NAME], "phone": e164,
            "phone_display": display_phone(e164), "language": resolve_language(preferred_language, session.language),
            "team": cls._team(session, team), "summary": summary,
        }
        session.handoff_draft = draft
        messages = (load_config("locales")["locales"].get(session.language) or {}).get("messages", {})
        confirm, edit = messages.get("button_confirm", "Confirm"), messages.get("button_edit", "Edit")
        return {"status": "awaiting_confirmation", "details": cls._draft_view(draft),
                "instruction": f"A review card with the buttons \"{confirm}\" and \"{edit}\" is now shown under your message. In one short sentence, "
                               f"ask the user to check the details and tap \"{confirm}\", or \"{edit}\" to change them (use these exact button names). "
                               "Do NOT say the request is saved or registered."}

    @classmethod
    async def confirm_callback(cls, session: SessionContext, draft_id: str, name: str, phone: str,
                               preferred_language: str, team: str) -> Dict[str, Any]:
        """Saves the reviewed (and possibly edited) details. Confirming the card is the user's explicit consent."""
        draft = getattr(session, "handoff_draft", None)
        if not draft or draft.get("draft_id") != draft_id:
            return {"lead_saved": False, "error": "draft_expired"}
        clean_name = " ".join((name or "").split())[:MAX_NAME]
        if not clean_name:
            return {"lead_saved": False, "error": "invalid_name", "field": "name"}
        e164 = normalise_phone(phone)
        if not e164:
            return {"lead_saved": False, "error": "invalid_phone", "field": "phone"}
        locales = load_config("locales")["locales"]
        language = preferred_language if preferred_language in locales else draft["language"]
        team_key = team if team in TEAMS else draft["team"]

        calc = session.last_calculation or {}
        ticket_id = f"XO-{datetime.now(timezone.utc).strftime('%y%m%d')}-{secrets.token_hex(3).upper()}"
        context = {
            "ticket_id": ticket_id,
            "summary": draft.get("summary"),
            "reason": "explicit_request",
            "conversation_language": session.language,
            "edited_on_card": {k: True for k, old, new in (("name", draft["name"], clean_name), ("phone", draft["phone"], e164),
                                                           ("preferred_language", draft["language"], language), ("team", draft["team"], team_key)) if old != new},
            "shown_listings": [l.get("listing", {}).get("title") for l in session.displayed_listings][:10],
            "last_calculation": {k: calc.get(k) for k in ("calculation_type", "max_loan_aed", "max_property_price_aed",
                                                           "instalment_aed", "loan_amount_aed") if calc.get(k) is not None},
            "transcript": [t.model_dump() for t in session.transcript],
        }
        storage = await LeadDatabaseService.save_advisor_lead(session.session_id, clean_name, e164, language_name(language),
                                                             TEAMS[team_key], context, ticket_id=ticket_id)
        crm: Dict[str, Any] = {}
        if storage["saved"]:
            if team_key == "mortgage":
                crm = await VaultGateway.create_lead(VaultMortgageLeadPayload(
                    applicant_name=clean_name, applicant_phone=e164, preferred_language=language_name(language), consent_given=True,
                    calculated_max_loan=calc.get("max_loan_aed"), calculated_max_price=calc.get("max_property_price_aed"),
                    monthly_income=(calc.get("inputs") or {}).get("monthly_income_aed"), notes=draft.get("summary")), session.session_id)
            else:
                crm = await GridLeadGateway.create_lead(GridLeadPayload(
                    contact_name=clean_name, contact_phone=e164, preferred_language=language_name(language), notes=draft.get("summary")),
                    session.session_id)
            session.handoff_draft = None
            session.handoff_ticket = ticket_id
            cls._queue.append({"ticket_id": ticket_id, "session_id": session.session_id, "team": TEAMS[team_key], "name": clean_name,
                               "phone": e164, "preferred_language": language_name(language), "storage": storage["storage"],
                               "crm_synced": crm.get("synced", False), "created_at": datetime.now(timezone.utc).isoformat(), "context": context})
            # Lets the assistant know the request went through if the user asks about it later.
            note = f"[The user confirmed the advisor callback card. Saved: ticket {ticket_id}, {TEAMS[team_key]}, {display_phone(e164)}, {language_name(language)}.]"
            SessionStore.append_history(session, [{"role": "assistant", "content": note}])
            SessionStore.add_transcript(session, "assistant", note)
        AuditService.log_event("business_write", "human_handoff", "handoff_queue", session_id=session.session_id,
                               status="success" if storage["saved"] else "failed",
                               details={"ticket_id": ticket_id, "team": team_key, "name": clean_name, "phone": e164, "storage": storage["storage"]})
        if not storage["saved"]:
            return {"lead_saved": False, "error": "save_failed"}
        return {"lead_saved": True, "ticket_id": ticket_id, "team": team_key, "name": clean_name, "phone": display_phone(e164),
                "preferred_language": language, "status": "saved"}

    @classmethod
    def queue(cls, team: Optional[str] = None) -> List[Dict[str, Any]]:
        return [t for t in cls._queue if not team or t["team"] == TEAMS.get(team, team)]
