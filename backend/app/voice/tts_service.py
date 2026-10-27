"""Text-to-speech via ElevenLabs (confirmed model eleven_v4_turbo, Horatius voice)."""
import json
import logging
import re
from typing import Any, AsyncGenerator, Dict, Optional, Tuple

import httpx

from app.core.config import load_config, settings
from app.core.usage_tracker import UsageTracker
from app.services.brand_terms import spoken_text

logger = logging.getLogger("xo.tts")


class TTSUnavailable(RuntimeError):
    pass


def speech_text(text: str) -> str:
    """Removes markdown, links and symbols that should not be read aloud."""
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text or "")
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"https?://\S+", "", t)
    t = re.sub(r"^\s{0,3}#{1,6}\s*", "", t, flags=re.MULTILINE)
    t = re.sub(r"^\s*[-*•]\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"^\s*(\d+)\.\s+", r"\1, ", t, flags=re.MULTILINE)
    t = re.sub(r"[*_`|>#]", "", t)
    t = re.sub(r"\n{2,}", ". ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[: settings.TTS_MAX_CHARS]


class TTSService:
    # One keep-alive connection pool: repeat requests skip the TLS handshake (~0.9 s faster first audio).
    _client: Optional[httpx.AsyncClient] = None

    @classmethod
    def _http(cls) -> httpx.AsyncClient:
        if cls._client is None or cls._client.is_closed:
            cls._client = httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT_SEC * 3,
                                            limits=httpx.Limits(max_keepalive_connections=10, keepalive_expiry=120))
        return cls._client

    @classmethod
    async def close(cls) -> None:
        if cls._client is not None:
            await cls._client.aclose()
            cls._client = None

    @classmethod
    def _request(cls, text: str, language: str) -> Tuple[str, Dict[str, Any]]:
        if not settings.ELEVENLABS_API_KEY:
            raise TTSUnavailable("ELEVENLABS_API_KEY not configured")
        spoken = spoken_text(speech_text(text), language)  # XOTO is said "X-oto", never "Zoto"
        if not spoken:
            raise TTSUnavailable("Nothing to speak")
        locales = load_config("locales")["locales"]
        payload: Dict[str, Any] = {
            "text": spoken,
            "model_id": settings.TTS_MODEL,
            "voice_settings": {"stability": settings.TTS_STABILITY, "similarity_boost": settings.TTS_SIMILARITY_BOOST},
        }
        lang_code = (locales.get(language) or {}).get("tts_language_code")
        if lang_code:
            payload["language_code"] = lang_code
        return spoken, payload

    @classmethod
    async def _open(cls, path: str, payload: Dict[str, Any], accept: str):
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{settings.ELEVENLABS_VOICE_ID}/{path}"
        headers = {"xi-api-key": settings.ELEVENLABS_API_KEY, "Accept": accept}
        request = cls._http().build_request("POST", url, headers=headers, params={"output_format": settings.TTS_OUTPUT_FORMAT}, json=payload)
        try:
            resp = await cls._http().send(request, stream=True)
        except httpx.HTTPError as exc:
            raise TTSUnavailable(f"TTS provider unreachable: {exc}") from exc
        if resp.status_code != 200:
            body = (await resp.aread())[:300]
            await resp.aclose()
            logger.warning("ElevenLabs TTS error %s: %s", resp.status_code, body)
            raise TTSUnavailable(f"TTS provider returned {resp.status_code}")
        return resp

    @classmethod
    async def stream(cls, text: str, language: str = "en", session_id: Optional[str] = None) -> AsyncGenerator[bytes, None]:
        """MP3 bytes as they are generated."""
        spoken, payload = cls._request(text, language)
        resp = await cls._open("stream", payload, "audio/mpeg")
        UsageTracker.record_tts(session_id, settings.TTS_MODEL, len(spoken))
        try:
            async for chunk in resp.aiter_bytes():
                yield chunk
        finally:
            await resp.aclose()

    @classmethod
    async def stream_timed(cls, text: str, language: str = "en", session_id: Optional[str] = None) -> AsyncGenerator[Dict[str, Any], None]:
        """Audio chunks with character timings (seconds from the start of this clip), used to
        highlight the word XO is saying. Yields {"audio": base64 mp3, "chars": [...], "start": [...], "end": [...]}."""
        spoken, payload = cls._request(text, language)
        resp = await cls._open("stream/with-timestamps", payload, "application/json")
        UsageTracker.record_tts(session_id, settings.TTS_MODEL, len(spoken))
        try:
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                data = json.loads(line)
                align = data.get("alignment") or {}
                yield {
                    "audio": data.get("audio_base64") or "",
                    "chars": align.get("characters") or [],
                    "start": align.get("character_start_times_seconds") or [],
                    "end": align.get("character_end_times_seconds") or [],
                }
        finally:
            await resp.aclose()
