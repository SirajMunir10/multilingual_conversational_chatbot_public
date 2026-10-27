from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.security import enforce_paid_limit, enforce_rate_limit, optional_user
from app.db.conversation_store import ConversationStore
from app.orchestrator.orchestrator import ConversationOrchestrator, sse
from app.orchestrator.session_store import SessionStore, is_valid_session_id

router = APIRouter(prefix="/api/chat", tags=["Conversation"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=settings.MAX_MESSAGE_CHARS)
    session_id: Optional[str] = None
    selected_language: Optional[str] = Field(None, description="Set only when the user picked a language in the menu (manual override, FR-1).")
    ui_language: Optional[str] = Field(None, description="Current UI language; used to start a new session.")
    channel: str = Field("text", pattern="^(text|voice)$")


@router.post("/stream", dependencies=[Depends(enforce_paid_limit)])
async def stream_chat(payload: ChatRequest, request: Request, user_id: Optional[str] = Depends(optional_user)):
    """Server-Sent Events: session → status/token… → final (PRD §7 streaming)."""
    async def events():
        async for event in ConversationOrchestrator.stream_turn(
                payload.message, session_id=payload.session_id, user_id=user_id, selected_language=payload.selected_language,
                ui_language=payload.ui_language, channel=payload.channel):
            if await request.is_disconnected():
                break
            yield sse(event)
    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


class FeedbackRequest(BaseModel):
    session_id: str = Field(..., max_length=128)
    turn_id: str = Field(..., pattern="^[0-9a-f]{16}$")
    rating: Optional[str] = Field(None, pattern="^(up|down)$", description="None removes the rating.")


@router.post("/feedback", dependencies=[Depends(enforce_rate_limit)])
async def feedback(payload: FeedbackRequest):
    """Visitor thumbs up/down on one XO reply (PRD FR-26). Accepted only for a reply of a live session."""
    session = SessionStore.get(payload.session_id) if is_valid_session_id(payload.session_id) else None
    if not session or payload.turn_id not in session.turn_ids:
        raise HTTPException(status_code=404, detail="reply_not_found")
    rating = {"up": 1, "down": -1}.get(payload.rating)
    await ConversationStore.set_feedback(payload.session_id, payload.turn_id, rating)
    return {"status": "saved", "rating": payload.rating}


@router.post("/message", dependencies=[Depends(enforce_paid_limit)])
async def chat_message(payload: ChatRequest, user_id: Optional[str] = Depends(optional_user)):
    """Non-streaming variant returning the final event."""
    return await ConversationOrchestrator.process_turn(payload.message, session_id=payload.session_id, user_id=user_id,
                                                       selected_language=payload.selected_language, ui_language=payload.ui_language,
                                                       channel=payload.channel)
