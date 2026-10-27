import re
import secrets
import time
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.core.config import settings

_SESSION_ID_PATTERN = re.compile(r"^sess_[A-Za-z0-9_-]{16,64}$")


def new_session_id() -> str:
    return f"sess_{secrets.token_urlsafe(18)}"


def is_valid_session_id(session_id: Optional[str]) -> bool:
    return bool(session_id and _SESSION_ID_PATTERN.match(session_id))


class TranscriptEntry(BaseModel):
    role: str
    content: str
    language: str = "en"
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SessionContext(BaseModel):
    session_id: str
    user_id: Optional[str] = None
    language: str = "en"
    language_locked: bool = False
    # LLM-format conversation history (user/assistant/tool messages) — the bot's memory (PRD FR-2)
    history: List[Dict[str, Any]] = Field(default_factory=list)
    # Human-readable transcript for handoff (PRD FR-5)
    transcript: List[TranscriptEntry] = Field(default_factory=list)
    # Listings currently shown to the user, referenced by number (#1, #2…) (PRD FR-9)
    displayed_listings: List[Dict[str, Any]] = Field(default_factory=list)
    last_calculation: Optional[Dict[str, Any]] = None
    shortlisted: List[str] = Field(default_factory=list)
    handoff_ticket: Optional[str] = None
    # Callback details awaiting the user's confirmation on the review card
    handoff_draft: Optional[Dict[str, Any]] = None
    current_user_text: str = ""
    # Ids of this session's XO replies, so visitor thumbs are only accepted for real replies (FR-26).
    turn_ids: List[str] = Field(default_factory=list)
    # Characters of XO's own replies not yet spoken; the voice endpoints spend from it (no free text-to-speech).
    speech_allowance: int = 0
    # Escalation rules already offered in this conversation, and knowledge-base questions XO could not answer (FR-29).
    escalations_offered: List[str] = Field(default_factory=list)
    kb_misses: int = 0
    # An admin's test chat (FR-25): runs like a visitor's, but is never saved for review or analytics.
    preview: bool = False
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)


class SessionStore:
    """In-memory session store with expiry and size bounds.
    Session IDs are issued by the server; client-invented IDs are rejected."""

    _sessions: "OrderedDict[str, SessionContext]" = OrderedDict()

    @classmethod
    def _evict(cls) -> None:
        cutoff = time.time() - settings.SESSION_TTL_MIN * 60
        for sid in [s for s, ctx in cls._sessions.items() if ctx.updated_at < cutoff]:
            cls._sessions.pop(sid, None)
        while len(cls._sessions) > settings.SESSION_MAX_COUNT:
            cls._sessions.popitem(last=False)

    @classmethod
    def get_or_create(cls, session_id: Optional[str], user_id: Optional[str] = None, language: Optional[str] = None) -> SessionContext:
        cls._evict()
        session = cls._sessions.get(session_id) if is_valid_session_id(session_id) else None
        if session is None:
            session = SessionContext(session_id=new_session_id(), user_id=user_id, language=language or "en")
            cls._sessions[session.session_id] = session
        elif user_id and session.user_id != user_id:
            # A different signed-in identity never inherits another user's session.
            session = SessionContext(session_id=new_session_id(), user_id=user_id, language=session.language)
            cls._sessions[session.session_id] = session
        session.updated_at = time.time()
        cls._sessions.move_to_end(session.session_id)
        return session

    @classmethod
    def get(cls, session_id: str) -> Optional[SessionContext]:
        return cls._sessions.get(session_id)

    @classmethod
    def append_history(cls, session: SessionContext, messages: List[Dict[str, Any]]) -> None:
        session.history.extend(messages)
        limit = settings.HISTORY_MAX_MESSAGES
        if len(session.history) > limit:
            trimmed = session.history[-limit:]
            # Never start history with an orphan tool result or assistant tool-call fragment.
            while trimmed and (trimmed[0].get("role") == "tool" or (trimmed[0].get("role") == "assistant" and trimmed[0].get("tool_calls"))):
                trimmed = trimmed[1:]
            session.history = trimmed

    @classmethod
    def add_transcript(cls, session: SessionContext, role: str, content: str) -> None:
        session.transcript.append(TranscriptEntry(role=role, content=content, language=session.language))

    @classmethod
    def list_sessions(cls, limit: int = 50) -> List[Dict[str, Any]]:
        return [{"session_id": s.session_id, "language": s.language, "turns": len(s.transcript), "updated_at": s.updated_at}
                for s in list(cls._sessions.values())[-limit:]]

    @classmethod
    def clear_all(cls) -> None:
        cls._sessions.clear()
