from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
import re
import logging
from pydantic import BaseModel, Field

from app.core.audit import AuditService
from app.orchestrator.session_store import SessionContext, SessionStore

logger = logging.getLogger("xo.handoff_service")

class HandoffTicket(BaseModel):
    ticket_id: str
    session_id: str
    user_id: Optional[str] = None
    applicant_name: Optional[str] = None
    applicant_phone: Optional[str] = None
    preferred_language: Optional[str] = None
    target_queue: str  # "sales", "mortgage", "support"
    priority: str = "normal"  # "vip", "high", "normal"
    reason: str  # "explicit_request", "high_value_lead", "negative_sentiment", "low_confidence_fallback"
    assigned_advisor: Dict[str, Any]
    customer_summary: Dict[str, Any]
    transcript_turns_count: int
    full_transcript: List[Dict[str, Any]]
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "queued"  # "queued", "accepted", "resolved"

class HandoffService:
    """
    PRD Architecture Component: Human Handoff Orchestration (Rule 4, FR-5, FR-20).
    
    Responsibilities:
    1. Multi-trigger detection (explicit request, high-value lead, negative sentiment, fallback).
    2. Intelligent queue routing (sales, mortgage, support).
    3. Complete transcript serialization with full context snapshot.
    4. Generation of a compliance-logged handoff ticket with assigned specialist advisor.
    5. In-memory queue store for inspection by back-office and admin modules (Phase 7).
    """

    _handoff_queue: List[Dict[str, Any]] = []

    # Neutral Advisory Department Roster (No personal names, numbers, or WhatsApp links)
    ADVISORS = {
        "mortgage": {
            "name": "Mortgage Advisory Specialist",
            "title": "Senior UAE Mortgage Specialist",
            "department": "Mortgage Advisory"
        },
        "sales": {
            "name": "Property Advisory Specialist",
            "title": "Prime & Ultra-Luxury Property Consultant",
            "department": "Prime & Ultra-Luxury Sales"
        },
        "support": {
            "name": "Client Concierge Manager",
            "title": "Client Concierge & Advisory Manager",
            "department": "Client Concierge & Advisory"
        }
    }

    # Trigger patterns
    EXPLICIT_TRIGGERS = [
        r"\b(human|agent|advisor|broker|specialist|representative|person|consultant)\b",
        r"\b(speak|talk|chat|connect|transfer)\s+(to|with)\s+(a\s+)?(human|agent|person|advisor|broker|team)\b",
        r"\b(speak with advisor|talk to human|connect me|transfer me|human please)\b",
        r"\b(call me|callback|phone me|reach out)\b"
    ]

    NEGATIVE_SENTIMENT_TRIGGERS = [
        r"\b(frustrated|frustrating|useless|terrible|horrible|annoyed|stupid|awful|waste of time)\b",
        r"\b(not helpful|unhelpful|stop bot|hate this|complaint|manager)\b"
    ]

    @classmethod
    def evaluate_handoff_trigger(cls, text: str, session: SessionContext) -> Optional[Dict[str, Any]]:
        """
        Evaluates incoming text and session state to detect if a handoff should trigger.
        Returns trigger metadata or None.
        """
        text_lower = text.lower().strip()

        # 1. Explicit user request (FR-5)
        for pattern in cls.EXPLICIT_TRIGGERS:
            if re.search(pattern, text_lower):
                return {
                    "triggered": True,
                    "reason": "explicit_request",
                    "priority": "high" if (session.user_id and "vip" in session.user_id.lower()) else "normal"
                }

        # 2. Negative sentiment / Frustration
        for pattern in cls.NEGATIVE_SENTIMENT_TRIGGERS:
            if re.search(pattern, text_lower):
                return {
                    "triggered": True,
                    "reason": "negative_sentiment",
                    "priority": "high"
                }

        # 3. High-Value Lead Detection (PRD Lead Qualification)
        slots = session.slots
        is_high_budget = (slots.property_budget_max and slots.property_budget_max >= 10_000_000)
        is_high_income = (slots.mortgage_income and slots.mortgage_income >= 80_000)
        if is_high_budget or is_high_income:
            # Trigger high-value proactive handoff recommendation
            return {
                "triggered": False,  # Available for proactive suggestion
                "high_value_lead": True,
                "priority": "vip"
            }

        return None

    @classmethod
    def determine_target_queue(cls, session: SessionContext, user_reason: Optional[str] = None) -> str:
        """Determines whether the inquiry belongs to Sales, Mortgage, or Support."""
        intent = session.active_intent
        slots = session.slots

        # Mortgage queue
        if intent == "mortgage" or slots.mortgage_income or slots.mortgage_loan_amount or session.last_mortgage_result:
            return "mortgage"

        # Sales queue
        if intent == "property" or slots.property_city or slots.property_budget_max or session.shortlisted_properties:
            return "sales"

        return "support"

    @classmethod
    def initiate_handoff(
        cls,
        session_id: str,
        applicant_name: Optional[str] = None,
        applicant_phone: Optional[str] = None,
        preferred_language: Optional[str] = None,
        reason: str = "explicit_request",
        preferred_team: Optional[str] = None,
        notes: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes a persistent, low-friction warm human handoff callback registration (FR-5, FR-20).
        Serializes full transcript, logs compliance audit record, and schedules advisor contact.
        """
        session = SessionStore.get_or_create_session(session_id, user_id=user_id)
        session.handoff_requested = True

        # Save details on session slots if provided
        if applicant_name:
            session.slots.customer_name = applicant_name
        if applicant_phone:
            session.slots.customer_phone = applicant_phone
        if preferred_language:
            session.slots.customer_preferred_language = preferred_language

        client_name = applicant_name or session.slots.customer_name or "Valued Client"
        client_phone = applicant_phone or session.slots.customer_phone or ""
        contact_lang = preferred_language or session.slots.customer_preferred_language or session.language

        queue = preferred_team if preferred_team in ["sales", "mortgage", "support"] else cls.determine_target_queue(session)
        advisor = cls.ADVISORS.get(queue, cls.ADVISORS["support"])

        # Determine priority
        priority = "normal"
        if (session.user_id and "vip" in session.user_id.lower()) or (session.slots.property_budget_max and session.slots.property_budget_max >= 10_000_000):
            priority = "vip"
        elif reason == "negative_sentiment":
            priority = "high"

        # Generate unique ticket
        ticket_id = f"XO-HD-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

        # Serialize full conversation transcript (FR-5)
        transcript = SessionStore.get_full_transcript(session_id)

        # Extract customer context summary
        customer_summary = {
            "session_id": session_id,
            "user_id": session.user_id,
            "applicant_name": client_name,
            "applicant_phone": client_phone,
            "preferred_language": contact_lang,
            "language": session.language,
            "active_intent": session.active_intent,
            "property_criteria": {
                "city": session.slots.property_city,
                "type": session.slots.property_type,
                "budget_max": session.slots.property_budget_max,
                "beds": session.slots.property_beds,
                "shortlisted_count": len(session.shortlisted_properties)
            },
            "mortgage_criteria": {
                "income": session.slots.mortgage_income,
                "existing_debt": session.slots.mortgage_existing_debt,
                "down_payment": session.slots.mortgage_down_payment,
                "calculated_affordability": session.last_mortgage_result.get("affordability_summary", {}).get("max_borrowing_capacity_aed") if session.last_mortgage_result else None
            },
            "notes": notes
        }

        ticket = HandoffTicket(
            ticket_id=ticket_id,
            session_id=session_id,
            user_id=session.user_id,
            applicant_name=client_name,
            applicant_phone=client_phone,
            preferred_language=contact_lang,
            target_queue=queue,
            priority=priority,
            reason=reason,
            assigned_advisor=advisor,
            customer_summary=customer_summary,
            transcript_turns_count=len(transcript),
            full_transcript=transcript,
            status="queued"
        )

        cls._handoff_queue.append(ticket.model_dump())

        # Mandatory Audit Logging for Handoff (FR-22)
        AuditService.log_event(
            event_type="business_write",
            action="human_handoff_created",
            resource="handoff_queue",
            session_id=session_id,
            user_id=session.user_id,
            status="success",
            details={
                "ticket_id": ticket_id,
                "queue": queue,
                "priority": priority,
                "reason": reason,
                "applicant_name": client_name,
                "applicant_phone": client_phone,
                "preferred_language": contact_lang,
                "advisor": advisor["name"],
                "transcript_turns": len(transcript)
            }
        )

        # Persist lead to private company PostgreSQL database with deduplication
        lead_saved = False
        if client_phone and client_name and client_name != "Valued Client":
            import asyncio
            from app.db.lead_store import LeadDatabaseService
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(LeadDatabaseService.save_advisor_lead(
                    session_id=session_id,
                    full_name=client_name,
                    phone_number=client_phone,
                    preferred_language=contact_lang,
                    advisor_type=advisor.get("department", queue),
                    conversation_context=customer_summary
                ))
                lead_saved = True
            except RuntimeError:
                try:
                    asyncio.run(LeadDatabaseService.save_advisor_lead(
                        session_id=session_id,
                        full_name=client_name,
                        phone_number=client_phone,
                        preferred_language=contact_lang,
                        advisor_type=advisor.get("department", queue),
                        conversation_context=customer_summary
                    ))
                    lead_saved = True
                except Exception as ex:
                    logger.warning(f"Error running sync lead save: {ex}")

        logger.info(f"Handoff ticket created: {ticket_id} for queue {queue} (client: {client_name}, lead_saved: {lead_saved})")

        dept_title = advisor.get("department", "Advisory")
        if lead_saved:
            confirm_msg = f"Thank you, {client_name}! Your request has been registered. An advisor from our {dept_title} team will contact you directly at {client_phone} in {contact_lang}."
        else:
            confirm_msg = f"We have recorded your inquiry ({ticket_id}). Please ensure your contact phone number is provided to receive an advisor callback."

        return {
            "status": "handoff_initiated",
            "ticket_id": ticket_id,
            "queue": queue,
            "priority": priority,
            "estimated_wait_minutes": 1 if priority == "vip" else 2,
            "applicant_name": client_name,
            "applicant_phone": client_phone,
            "preferred_language": contact_lang,
            "assigned_advisor": advisor,
            "lead_saved": lead_saved,
            "customer_summary": customer_summary,
            "created_at": ticket.created_at,
            "message": confirm_msg
        }

    @classmethod
    def get_queue(cls, queue: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve active handoff queue for back-office review (Phase 7)."""
        if queue:
            return [t for t in cls._handoff_queue if t.get("target_queue") == queue]
        return cls._handoff_queue

    @classmethod
    def get_ticket(cls, ticket_id: str) -> Optional[Dict[str, Any]]:
        for t in cls._handoff_queue:
            if t.get("ticket_id") == ticket_id:
                return t
        return None
