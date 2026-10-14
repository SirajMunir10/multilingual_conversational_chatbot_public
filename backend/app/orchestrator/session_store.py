from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime, timezone
import uuid

class ChatMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    role: str  # "user", "assistant", "system"
    content: str
    language: str = "en"
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_results: Optional[List[Dict[str, Any]]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class SlotState(BaseModel):
    # Property discovery slots
    property_city: Optional[str] = None
    property_type: Optional[str] = None
    property_budget_min: Optional[float] = None
    property_budget_max: Optional[float] = None
    property_beds: Optional[int] = None
    property_purpose: Optional[str] = None  # buy, rent, invest
    property_timeline: Optional[str] = None
    property_amenities: List[str] = Field(default_factory=list)
    property_developer: Optional[str] = None
    unconfirmed_location: Optional[str] = None
    inferred_location_note: Optional[str] = None

    # Mortgage calculation slots
    mortgage_income: Optional[float] = None
    mortgage_existing_debt: Optional[float] = None
    mortgage_down_payment: Optional[float] = None
    mortgage_location: Optional[str] = None
    mortgage_price_range: Optional[float] = None
    mortgage_term_years: Optional[int] = None
    mortgage_interest_rate: Optional[float] = None
    mortgage_loan_amount: Optional[float] = None
    mortgage_frequency: str = "monthly"
    mortgage_employment_type: Optional[str] = None
    mortgage_nationality: Optional[str] = None

    # Customer contact & advisor callback slots
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_preferred_language: Optional[str] = None
    customer_consent_given: bool = False
    advisor_consent_pending: bool = False

class SessionContext(BaseModel):
    session_id: str
    user_id: Optional[str] = None  # Populated when authenticated
    language: str = "en"
    language_manually_overridden: bool = False
    active_intent: str = "general"  # property, mortgage, general, account
    slots: SlotState = Field(default_factory=SlotState)
    messages: List[ChatMessage] = Field(default_factory=list)
    shortlisted_properties: List[str] = Field(default_factory=list)
    last_recommended_properties: List[Dict[str, Any]] = Field(default_factory=list)
    last_mortgage_result: Optional[Dict[str, Any]] = None
    handoff_requested: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class SessionStore:
    """
    Central in-memory session and context store.
    Maintains dialogue state, slot memory, and conversation history across turns.
    """
    _sessions: Dict[str, SessionContext] = {}

    @classmethod
    def get_or_create_session(
        cls,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        initial_language: str = "en"
    ) -> SessionContext:
        if not session_id:
            session_id = f"sess_{uuid.uuid4().hex[:12]}"

        if session_id not in cls._sessions:
            cls._sessions[session_id] = SessionContext(
                session_id=session_id,
                user_id=user_id,
                language=initial_language
            )
        else:
            if user_id and not cls._sessions[session_id].user_id:
                cls._sessions[session_id].user_id = user_id

        return cls._sessions[session_id]

    @classmethod
    def update_session(cls, session: SessionContext) -> None:
        session.updated_at = datetime.now(timezone.utc).isoformat()
        cls._sessions[session.session_id] = session

    @classmethod
    def add_message(
        cls,
        session_id: str,
        role: str,
        content: str,
        language: str = "en",
        metadata: Optional[Dict[str, Any]] = None
    ) -> ChatMessage:
        session = cls.get_or_create_session(session_id)
        msg = ChatMessage(
            role=role,
            content=content,
            language=language,
            metadata=metadata or {}
        )
        session.messages.append(msg)
        cls.update_session(session)
        return msg

    @classmethod
    def set_language_override(cls, session_id: str, language: str) -> None:
        session = cls.get_or_create_session(session_id)
        session.language = language
        session.language_manually_overridden = True
        cls.update_session(session)

    @classmethod
    def get_full_transcript(cls, session_id: str) -> List[Dict[str, Any]]:
        session = cls.get_or_create_session(session_id)
        return [msg.model_dump() for msg in session.messages]

    @classmethod
    def get_session(cls, session_id: str) -> Optional[SessionContext]:
        """Retrieve existing session context if present without creating."""
        return cls._sessions.get(session_id)

    @classmethod
    def clear_all(cls) -> None:
        """Clear all active sessions (used in test setups)."""
        cls._sessions.clear()

