from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Header, Depends
from fastapi.responses import StreamingResponse
from app.core.config import settings
from app.orchestrator.orchestrator import ConversationOrchestrator
from app.orchestrator.session_store import SessionStore

router = APIRouter(prefix="/api/chat", tags=["Conversational Chat Core"])

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User message text")
    session_id: Optional[str] = None
    language: Optional[str] = Field(None, description="Optional manual language override across all supported launch languages")

class LanguageOverrideRequest(BaseModel):
    language: str = Field(..., description="Target language code from supported launch languages")

@router.post("/message")
async def send_chat_message(
    payload: ChatRequest,
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    x_user_id: Optional[str] = Header(None, alias="X-User-ID")
):
    """
    Standard conversational turn endpoint.
    Unified orchestrator managing language auto-detection, intent routing,
    slot memory, and guardrails.
    """
    active_session_id = payload.session_id or x_session_id
    try:
        response = await ConversationOrchestrator.process_user_turn(
            user_message=payload.message,
            session_id=active_session_id,
            user_id=x_user_id,
            manual_language=payload.language
        )
        return response
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stream")
async def stream_chat_message(
    payload: ChatRequest,
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    x_user_id: Optional[str] = Header(None, alias="X-User-ID")
):
    """
    Server-Sent Events (SSE) streaming endpoint.
    Perceived latency target < 2.0s (PRD Sec 7).
    """
    active_session_id = payload.session_id or x_session_id
    generator = ConversationOrchestrator.stream_user_turn(
        user_message=payload.message,
        session_id=active_session_id,
        user_id=x_user_id,
        manual_language=payload.language
    )
    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no"
    }
    return StreamingResponse(generator, media_type="text/event-stream", headers=headers)

@router.get("/session/{session_id}")
def get_session_details(session_id: str):
    """
    Retrieve full conversation transcript and state for a session.
    """
    session = SessionStore.get_or_create_session(session_id)
    return {
        "session_id": session.session_id,
        "language": session.language,
        "active_intent": session.active_intent,
        "messages_count": len(session.messages),
        "transcript": SessionStore.get_full_transcript(session_id)
    }

@router.post("/session/{session_id}/language")
def set_session_language(session_id: str, payload: LanguageOverrideRequest):
    """
    Manual language override toggle (FR-1c).
    Persists for the remainder of the session.
    """
    if payload.language not in settings.LAUNCH_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported language '{payload.language}'. Supported languages: {', '.join(settings.LAUNCH_LANGUAGES)}."
        )
    SessionStore.set_language_override(session_id, payload.language)
    return {"status": "updated", "session_id": session_id, "language": payload.language}
