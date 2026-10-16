"""Speech-to-text relay for gpt-live-transcribe (OpenAI Realtime transcription session).

The browser streams 24 kHz PCM16 audio to /api/voice/stt over a WebSocket; this relay forwards it to
OpenAI (the API key never reaches the browser) and returns transcript deltas and the final transcript.
gpt-live-transcribe has no server VAD, so the browser decides when the user stopped speaking and sends
a commit (PRD voice requirement; silence auto-submit is configurable)."""
import asyncio
import base64
import json
import logging
import socket
import time
from typing import Any, Dict, Optional

import websockets
from fastapi import WebSocket, WebSocketDisconnect

from app.core.config import load_config, settings
from app.core.usage_tracker import UsageTracker

logger = logging.getLogger("xo.stt")


async def _connect_upstream():
    """Opens the Realtime session. IPv4 is tried first with a short timeout: Python (and uvloop) do not
    fall back between address families the way browsers do, so a host with a broken IPv6 route would
    otherwise hang for the full timeout. The default resolver order is the fallback (IPv6-only hosts)."""
    options = {"additional_headers": {"Authorization": f"Bearer {settings.OPENAI_API_KEY}"}, "max_size": 2 ** 22}
    try:
        return await websockets.connect(settings.STT_REALTIME_URL, family=socket.AF_INET, open_timeout=5, **options)
    except (OSError, asyncio.TimeoutError) as exc:
        logger.info("IPv4 connection to the STT provider failed (%s); retrying with the default route", exc)
        return await websockets.connect(settings.STT_REALTIME_URL, open_timeout=10, **options)

_KEYWORDS_LIMIT = 40


def _session_update(language: Optional[str]) -> Dict[str, Any]:
    transcription: Dict[str, Any] = {"model": settings.STT_MODEL, "delay": settings.STT_DELAY,
                                     "prompt": "A customer talking to XOTO's UAE real estate and mortgage assistant."}
    locales = load_config("locales")["locales"]
    stt_lang = (locales.get(language or "") or {}).get("stt_language")
    if stt_lang:
        transcription["languages"] = [stt_lang]
    communities = load_config("communities")["communities"]
    keywords = ["XOTO", "AED", "EMI", "DLD", "Ejari", "off-plan", "Golden Visa"] + [c["name"] for c in communities]
    transcription["keywords"] = keywords[:_KEYWORDS_LIMIT]
    return {"type": "session.update", "session": {"type": "transcription", "audio": {"input": {
        "format": {"type": "audio/pcm", "rate": settings.STT_SAMPLE_RATE}, "transcription": transcription, "turn_detection": None}}}}


async def relay(client_ws: WebSocket, language: Optional[str], session_id: Optional[str]) -> None:
    await client_ws.accept()
    if not settings.OPENAI_API_KEY:
        await client_ws.send_json({"type": "error", "code": "stt_unavailable"})
        await client_ws.close()
        return
    audio_bytes = 0
    started = time.monotonic()
    try:
        async with await _connect_upstream() as upstream:
            await upstream.send(json.dumps(_session_update(language)))

            async def from_client() -> None:
                nonlocal audio_bytes
                while True:
                    msg = await client_ws.receive()
                    if msg.get("type") == "websocket.disconnect":
                        return
                    if msg.get("bytes"):
                        chunk = msg["bytes"]
                        audio_bytes += len(chunk)
                        if time.monotonic() - started > settings.STT_MAX_SESSION_SEC:
                            await client_ws.send_json({"type": "error", "code": "session_too_long"})
                            return
                        await upstream.send(json.dumps({"type": "input_audio_buffer.append", "audio": base64.b64encode(chunk).decode()}))
                    elif msg.get("text"):
                        data = json.loads(msg["text"])
                        if data.get("type") == "commit":
                            await upstream.send(json.dumps({"type": "input_audio_buffer.commit"}))
                        elif data.get("type") == "language":
                            await upstream.send(json.dumps(_session_update(data.get("language"))))

            async def from_upstream() -> None:
                async for raw in upstream:
                    ev = json.loads(raw)
                    kind = ev.get("type", "")
                    if kind == "conversation.item.input_audio_transcription.delta":
                        await client_ws.send_json({"type": "delta", "text": ev.get("delta", "")})
                    elif kind == "conversation.item.input_audio_transcription.completed":
                        await client_ws.send_json({"type": "final", "text": ev.get("transcript", "")})
                    elif kind == "session.updated":
                        await client_ws.send_json({"type": "ready"})
                    elif kind == "error":
                        logger.warning("Realtime transcription error: %s", ev.get("error"))
                        await client_ws.send_json({"type": "error", "code": "stt_error"})

            tasks = [asyncio.create_task(from_client()), asyncio.create_task(from_upstream())]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in pending:
                t.cancel()
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("STT relay failed: %s", exc)
        try:
            await client_ws.send_json({"type": "error", "code": "stt_unavailable"})
        except Exception:
            pass
    finally:
        seconds = audio_bytes / (2 * settings.STT_SAMPLE_RATE)
        if seconds > 0:
            UsageTracker.record_stt(session_id, settings.STT_MODEL, seconds)
        try:
            await client_ws.close()
        except Exception:
            pass
