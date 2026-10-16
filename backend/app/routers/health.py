from fastapi import APIRouter

from app.core.config import load_config, settings

router = APIRouter(prefix="/api", tags=["Health & client config"])


@router.get("/health")
def health():
    """Liveness only — no model names, keys or internal details are exposed publicly."""
    return {"status": "ok"}


@router.get("/config")
def client_config():
    """Public, non-sensitive settings the widget needs (languages, voice timing)."""
    locales = load_config("locales")
    return {
        "default_language": locales["default"],
        "languages": [{"code": code, "name": v["name"], "native": v["native"], "dir": v["dir"]} for code, v in locales["locales"].items()],
        "voice": {"sample_rate": settings.STT_SAMPLE_RATE, "silence_submit_ms": settings.VOICE_SILENCE_SUBMIT_MS,
                  "max_session_sec": settings.STT_MAX_SESSION_SEC},
    }
