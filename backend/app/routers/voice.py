import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.config import load_config, settings
from app.core.security import allow_paid_call, client_ip, enforce_paid_limit
from app.core.usage_tracker import UsageTracker
from app.db.conversation_store import ConversationStore
from app.orchestrator.session_store import SessionStore, is_valid_session_id
from app.voice import stt_service
from app.voice.tts_service import TTSService, TTSUnavailable

router = APIRouter(prefix="/api/voice", tags=["Voice"])


def _record_speech_cost(session_id: Optional[str]) -> None:
    """Speech is produced after the reply is saved; adds its cost to the conversation (PRD FR-31 cost per conversation)."""
    if session_id:
        total = UsageTracker.summary(session_id).get("cost_usd", {}).get("total")
        if total:
            ConversationStore.save_in_background(ConversationStore.update_cost(session_id, total))


class SpeakRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)
    language: str = Field("en", max_length=16)
    session_id: Optional[str] = Field(None, max_length=128)


def _spend_speech(payload: SpeakRequest) -> None:
    """Speech is only for what XO said in this live conversation (its speech allowance), never arbitrary text."""
    session = SessionStore.get(payload.session_id) if is_valid_session_id(payload.session_id) else None
    if session is None:
        raise HTTPException(status_code=403, detail="no_conversation")
    if len(payload.text) > session.speech_allowance:
        raise HTTPException(status_code=429, detail="speech_limit")
    session.speech_allowance -= len(payload.text)


@router.post("/speak", dependencies=[Depends(enforce_paid_limit)])
async def speak(payload: SpeakRequest):
    """TTS for an XO reply (eleven_v4_turbo, Horatius). Streams MP3 as it is generated."""
    _spend_speech(payload)
    stream = TTSService.stream(payload.text, payload.language, payload.session_id)
    try:
        first = await stream.__anext__()
    except (TTSUnavailable, StopAsyncIteration):
        raise HTTPException(status_code=503, detail="voice_unavailable")

    async def body():
        yield first
        async for chunk in stream:
            yield chunk
        _record_speech_cost(payload.session_id)
    return StreamingResponse(body(), media_type="audio/mpeg")


@router.post("/speak-timed", dependencies=[Depends(enforce_paid_limit)])
async def speak_timed(payload: SpeakRequest):
    """TTS with word timing: newline-delimited JSON, one line per audio chunk
    ({"audio": base64 MP3, "chars", "start", "end"}). Lets the widget mark the word being spoken."""
    _spend_speech(payload)
    stream = TTSService.stream_timed(payload.text, payload.language, payload.session_id)
    try:
        first = await stream.__anext__()
    except (TTSUnavailable, StopAsyncIteration):
        raise HTTPException(status_code=503, detail="voice_unavailable")

    async def body():
        yield json.dumps(first, ensure_ascii=False) + "\n"
        async for chunk in stream:
            yield json.dumps(chunk, ensure_ascii=False) + "\n"
        _record_speech_cost(payload.session_id)
    return StreamingResponse(body(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store"})


@router.websocket("/stt")
async def speech_to_text(websocket: WebSocket, language: Optional[str] = None, session_id: Optional[str] = None):
    """Live transcription with gpt-live-transcribe. Send binary PCM16 (24 kHz mono) frames, then {"type":"commit"}.

    CORS does not cover WebSockets, so the allowed sites are checked here. To use voice from another site,
    add it to that server's ALLOWED_ORIGINS instead of removing this check."""
    origin = websocket.headers.get("origin")
    if origin and settings.ALLOWED_ORIGINS and origin not in settings.ALLOWED_ORIGINS:
        await websocket.close(code=1008)
        return
    # Every session spends transcription credit, so it shares the per-visitor limit with the other paid endpoints.
    # Only a known language and a well-formed conversation id are passed on; anything else is dropped.
    language = language if language in load_config("locales")["locales"] else None
    session_id = session_id if is_valid_session_id(session_id) else None
    if not allow_paid_call(f"stt:{client_ip(websocket, direct=True)}"):
        await websocket.close(code=1013)
        return
    await stt_service.relay(websocket, language, session_id)
