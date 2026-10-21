import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.security import client_ip, enforce_rate_limit, rate_limiter
from app.voice import stt_service
from app.voice.tts_service import TTSService, TTSUnavailable

router = APIRouter(prefix="/api/voice", tags=["Voice"])


class SpeakRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)
    language: str = "en"
    session_id: Optional[str] = None


@router.post("/speak", dependencies=[Depends(enforce_rate_limit)])
async def speak(payload: SpeakRequest):
    """TTS for an XO reply (eleven_v4_turbo, Horatius). Streams MP3 as it is generated."""
    stream = TTSService.stream(payload.text, payload.language, payload.session_id)
    try:
        first = await stream.__anext__()
    except (TTSUnavailable, StopAsyncIteration):
        raise HTTPException(status_code=503, detail="voice_unavailable")

    async def body():
        yield first
        async for chunk in stream:
            yield chunk
    return StreamingResponse(body(), media_type="audio/mpeg")


@router.post("/speak-timed", dependencies=[Depends(enforce_rate_limit)])
async def speak_timed(payload: SpeakRequest):
    """TTS with word timing: newline-delimited JSON, one line per audio chunk
    ({"audio": base64 MP3, "chars", "start", "end"}). Lets the widget mark the word being spoken."""
    stream = TTSService.stream_timed(payload.text, payload.language, payload.session_id)
    try:
        first = await stream.__anext__()
    except (TTSUnavailable, StopAsyncIteration):
        raise HTTPException(status_code=503, detail="voice_unavailable")

    async def body():
        yield json.dumps(first, ensure_ascii=False) + "\n"
        async for chunk in stream:
            yield json.dumps(chunk, ensure_ascii=False) + "\n"
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
    if settings.RATE_LIMIT_ENABLED and not rate_limiter.allow(f"stt:{client_ip(websocket)}", settings.RATE_LIMIT_PER_MINUTE):
        await websocket.close(code=1013)
        return
    await stt_service.relay(websocket, language, session_id)
