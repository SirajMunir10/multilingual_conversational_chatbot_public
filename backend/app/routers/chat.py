from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.security import enforce_rate_limit, optional_user
from app.orchestrator.orchestrator import ConversationOrchestrator, sse

router = APIRouter(prefix="/api/chat", tags=["Conversation"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=settings.MAX_MESSAGE_CHARS)
    session_id: Optional[str] = None
    selected_language: Optional[str] = Field(None, description="Set only when the user picked a language in the menu (manual override, FR-1).")
    ui_language: Optional[str] = Field(None, description="Current UI language; used to start a new session.")
    channel: str = Field("text", pattern="^(text|voice)$")


@router.post("/stream", dependencies=[Depends(enforce_rate_limit)])
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


@router.post("/message", dependencies=[Depends(enforce_rate_limit)])
async def chat_message(payload: ChatRequest, user_id: Optional[str] = Depends(optional_user)):
    """Non-streaming variant returning the final event."""
    return await ConversationOrchestrator.process_turn(payload.message, session_id=payload.session_id, user_id=user_id,
                                                       selected_language=payload.selected_language, ui_language=payload.ui_language,
                                                       channel=payload.channel)
