"""Keeps the first reply fast (PRD §7 latency): opens the connections to the model and voice providers before a
visitor needs them. A cold connection adds roughly a second to the first answer and the first spoken words.

Uses free, read-only requests (model lists) and runs at most once a minute, whoever asks."""
import asyncio
import logging
import time

from app.core.config import settings

logger = logging.getLogger("xo.warmup")

_EVERY_SEC = 60.0
_last = 0.0
_running = False


async def _openai() -> None:
    from app.llm.client import LLMService
    if settings.OPENAI_API_KEY:
        await LLMService.client().models.list()


async def _elevenlabs() -> None:
    from app.voice.tts_service import TTSService
    if settings.ELEVENLABS_API_KEY:
        await TTSService._http().get("https://api.elevenlabs.io/v1/models", headers={"xi-api-key": settings.ELEVENLABS_API_KEY})


async def warm() -> bool:
    """Warms both providers; returns False when skipped because it ran less than a minute ago."""
    global _last, _running
    if _running or time.monotonic() - _last < _EVERY_SEC:
        return False
    _running, _last = True, time.monotonic()
    try:
        results = await asyncio.gather(_openai(), _elevenlabs(), return_exceptions=True)
        for name, result in zip(("OpenAI", "ElevenLabs"), results):
            if isinstance(result, Exception):
                logger.info("Warm-up of %s failed: %s", name, result)
        return True
    finally:
        _running = False


def warm_in_background() -> None:
    """Starts a warm-up without waiting for it (the request that asked for it returns at once)."""
    try:
        asyncio.get_running_loop().create_task(warm())
    except RuntimeError:
        pass
