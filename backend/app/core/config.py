import json
import os
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CONFIG_DIR = DATA_DIR / "config"


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def _env_int(name: str, default: int) -> int:
    return int(_env(name, str(default)))


def _env_float(name: str, default: float) -> float:
    return float(_env(name, str(default)))


def _env_bool(name: str, default: bool) -> bool:
    return str(_env(name, str(default))).lower() in ("1", "true", "yes", "on")


def _env_list(name: str, default: str = "") -> List[str]:
    return [v.strip() for v in str(_env(name, default)).split(",") if v.strip()]


class AppSettings(BaseModel):
    APP_NAME: str = Field(default_factory=lambda: _env("APP_NAME", "XO — Conversational AI Assistant"))
    ENVIRONMENT: str = Field(default_factory=lambda: _env("ENVIRONMENT", "development"))
    PORT: int = Field(default_factory=lambda: _env_int("PORT", 8000))
    ALLOWED_ORIGINS: List[str] = Field(default_factory=lambda: _env_list(
        "ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173"))

    # Provider keys
    OPENAI_API_KEY: str = Field(default_factory=lambda: _env("OPENAI_API_KEY", ""))
    ELEVENLABS_API_KEY: str = Field(default_factory=lambda: _env("ELEVENLABS_API_KEY", ""))

    # Models (confirmed by the business, override PRD §6.2)
    LLM_MODEL: str = Field(default_factory=lambda: _env("LLM_MODEL", "gpt-6-luna"))
    LLM_REASONING_EFFORT: str = Field(default_factory=lambda: _env("LLM_REASONING_EFFORT", "none"))
    LLM_MAX_OUTPUT_TOKENS: int = Field(default_factory=lambda: _env_int("LLM_MAX_OUTPUT_TOKENS", 700))
    LLM_TIMEOUT_SEC: float = Field(default_factory=lambda: _env_float("LLM_TIMEOUT_SEC", 30.0))
    LLM_MAX_TOOL_STEPS: int = Field(default_factory=lambda: _env_int("LLM_MAX_TOOL_STEPS", 4))
    STT_MODEL: str = Field(default_factory=lambda: _env("STT_MODEL", "gpt-live-transcribe"))
    STT_REALTIME_URL: str = Field(default_factory=lambda: _env("STT_REALTIME_URL", "wss://api.openai.com/v1/realtime?intent=transcription"))
    STT_DELAY: str = Field(default_factory=lambda: _env("STT_DELAY", "medium"))
    STT_SAMPLE_RATE: int = Field(default_factory=lambda: _env_int("STT_SAMPLE_RATE", 24000))
    STT_MAX_SESSION_SEC: int = Field(default_factory=lambda: _env_int("STT_MAX_SESSION_SEC", 120))
    # Pause after the visitor stops talking before the turn is sent. 1 s feels immediate yet leaves room for a short breath.
    VOICE_SILENCE_SUBMIT_MS: int = Field(default_factory=lambda: _env_int("VOICE_SILENCE_SUBMIT_MS", 1000))
    # Turns down background sound before transcription ("near_field" for a phone or laptop mic, "far_field", or "" for off).
    STT_NOISE_REDUCTION: str = Field(default_factory=lambda: _env("STT_NOISE_REDUCTION", "near_field"))
    TTS_MODEL: str = Field(default_factory=lambda: _env("TTS_MODEL", "eleven_v4_turbo"))
    ELEVENLABS_VOICE_ID: str = Field(default_factory=lambda: _env("ELEVENLABS_VOICE_ID", "qXpMhyvQqiRxWQs4qSSB"))
    ELEVENLABS_VOICE_NAME: str = Field(default_factory=lambda: _env("ELEVENLABS_VOICE_NAME", "Horatius - Energetic Character voice"))
    TTS_STABILITY: float = Field(default_factory=lambda: _env_float("TTS_STABILITY", 0.5))
    TTS_SIMILARITY_BOOST: float = Field(default_factory=lambda: _env_float("TTS_SIMILARITY_BOOST", 0.75))
    TTS_OUTPUT_FORMAT: str = Field(default_factory=lambda: _env("TTS_OUTPUT_FORMAT", "mp3_44100_128"))
    TTS_MAX_CHARS: int = Field(default_factory=lambda: _env_int("TTS_MAX_CHARS", 1200))
    EMBEDDING_MODEL: str = Field(default_factory=lambda: _env("EMBEDDING_MODEL", "text-embedding-3-small"))

    # Conversation behaviour
    HISTORY_MAX_MESSAGES: int = Field(default_factory=lambda: _env_int("HISTORY_MAX_MESSAGES", 24))
    SESSION_TTL_MIN: int = Field(default_factory=lambda: _env_int("SESSION_TTL_MIN", 120))
    SESSION_MAX_COUNT: int = Field(default_factory=lambda: _env_int("SESSION_MAX_COUNT", 5000))
    MAX_MESSAGE_CHARS: int = Field(default_factory=lambda: _env_int("MAX_MESSAGE_CHARS", 2000))
    SEARCH_MAX_RESULTS: int = Field(default_factory=lambda: _env_int("SEARCH_MAX_RESULTS", 5))

    # RAG
    RAG_TOP_K: int = Field(default_factory=lambda: _env_int("RAG_TOP_K", 3))
    RAG_MIN_SIMILARITY: float = Field(default_factory=lambda: _env_float("RAG_MIN_SIMILARITY", 0.35))
    RAG_CACHE_SIZE: int = Field(default_factory=lambda: _env_int("RAG_CACHE_SIZE", 512))

    # Security
    ADMIN_API_KEY: str = Field(default_factory=lambda: _env("ADMIN_API_KEY", ""))
    JWT_SECRET: str = Field(default_factory=lambda: _env("JWT_SECRET", ""))
    # Admin module (PRD FR-30). The first Admin account is created from these when no admin user exists yet.
    ADMIN_BOOTSTRAP_EMAIL: str = Field(default_factory=lambda: _env("ADMIN_BOOTSTRAP_EMAIL", ""))
    ADMIN_BOOTSTRAP_PASSWORD: str = Field(default_factory=lambda: _env("ADMIN_BOOTSTRAP_PASSWORD", ""))
    ADMIN_SESSION_HOURS: int = Field(default_factory=lambda: _env_int("ADMIN_SESSION_HOURS", 12))
    ADMIN_LOGIN_ATTEMPTS_PER_15_MIN: int = Field(default_factory=lambda: _env_int("ADMIN_LOGIN_ATTEMPTS_PER_15_MIN", 8))
    RATE_LIMIT_PER_MINUTE: int = Field(default_factory=lambda: _env_int("RATE_LIMIT_PER_MINUTE", 30))
    RATE_LIMIT_ENABLED: bool = Field(default_factory=lambda: _env_bool("RATE_LIMIT_ENABLED", True))
    # Proxies in front of the API that append to X-Forwarded-For (the site's /api rewrite on Vercel, then Render).
    # The visitor's address is read this many entries from the right, so a value the visitor typed in is never used.
    TRUSTED_PROXY_HOPS: int = Field(default_factory=lambda: _env_int("TRUSTED_PROXY_HOPS", 2))
    # Ceiling on paid calls (AI, speech) across all visitors together, per minute. It holds even if someone spreads
    # requests over many addresses, so a flood can never run up an unbounded bill.
    GLOBAL_PAID_CALLS_PER_MINUTE: int = Field(default_factory=lambda: _env_int("GLOBAL_PAID_CALLS_PER_MINUTE", 600))
    # Speech is only produced for what XO says in a live conversation: characters of reply text plus this allowance
    # per turn (the short "let me check" phrases).
    TTS_ALLOWANCE_PER_TURN: int = Field(default_factory=lambda: _env_int("TTS_ALLOWANCE_PER_TURN", 160))
    ENABLE_API_DOCS: bool = Field(default_factory=lambda: _env_bool("ENABLE_API_DOCS", False))
    # Phone numbers typed without a country code are read as numbers from this region (ISO 3166 code).
    PHONE_DEFAULT_REGION: str = Field(default_factory=lambda: _env("PHONE_DEFAULT_REGION", "AE"))

    # Integrations
    GRID_API_URL: str = Field(default_factory=lambda: _env("GRID_API_URL", ""))
    GRID_API_KEY: str = Field(default_factory=lambda: _env("GRID_API_KEY", ""))
    GRID_OFFPLAN_API_URL: str = Field(default_factory=lambda: _env("GRID_OFFPLAN_API_URL", "https://xoto.ae/api/gridoffplan/website"))
    GRID_OFFPLAN_PAGE_SIZE: int = Field(default_factory=lambda: _env_int("GRID_OFFPLAN_PAGE_SIZE", 50))
    GRID_OFFPLAN_CACHE_SEC: int = Field(default_factory=lambda: _env_int("GRID_OFFPLAN_CACHE_SEC", 600))
    OFFPLAN_LISTING_URL_TEMPLATE: str = Field(default_factory=lambda: _env("OFFPLAN_LISTING_URL_TEMPLATE", ""))
    VAULT_API_URL: str = Field(default_factory=lambda: _env("VAULT_API_URL", ""))
    VAULT_API_KEY: str = Field(default_factory=lambda: _env("VAULT_API_KEY", ""))
    HTTP_TIMEOUT_SEC: float = Field(default_factory=lambda: _env_float("HTTP_TIMEOUT_SEC", 8.0))
    DATABASE_URL: str = Field(default_factory=lambda: _env("DATABASE_URL", ""))

    # Compliance
    COMPANY_RETENTION_POLICY_REF: str = Field(default_factory=lambda: _env("COMPANY_RETENTION_POLICY_REF", "XOTO-CORP-RETENTION-POL-2024-V3"))
    REGULATORY_SCOPE: str = Field(default_factory=lambda: _env("REGULATORY_SCOPE", "UAE / Dubai / DIFC"))

    # Latency targets (PRD §7) — used for monitoring only
    PERCEIVED_LATENCY_TARGET_SEC: float = Field(default_factory=lambda: _env_float("PERCEIVED_LATENCY_TARGET_SEC", 2.0))
    FULL_ANSWER_LATENCY_TARGET_SEC: float = Field(default_factory=lambda: _env_float("FULL_ANSWER_LATENCY_TARGET_SEC", 6.0))

    @property
    def LAUNCH_LANGUAGES(self) -> List[str]:
        return list(load_config("locales")["locales"].keys())


@lru_cache(maxsize=None)
def _load_json(name: str) -> Dict[str, Any]:
    with open(CONFIG_DIR / f"{name}.json", "r", encoding="utf-8") as f:
        return json.load(f)


# Versions published in the admin module (PRD FR-25, FR-27, FR-29) replace the built-in files above; they are set by
# app.admin.config_store. A preview applies a draft to one request only (a ContextVar), so visitors never see drafts.
_published: Dict[str, Any] = {}
_preview: ContextVar[Optional[Dict[str, Any]]] = ContextVar("config_preview", default=None)
_merged_locales: Dict[str, Any] = {}


def override(name: str) -> Optional[Any]:
    """The admin's draft (in a preview) or published version of `name`, or None to use the built-in file."""
    previewing = _preview.get()
    if previewing and name in previewing:
        return previewing[name]
    return _published.get(name)


def set_published(name: str, data: Optional[Any]) -> None:
    if data is None:
        _published.pop(name, None)
    else:
        _published[name] = data
    _merged_locales.clear()


@contextmanager
def preview(overrides: Dict[str, Any]) -> Iterator[None]:
    """Uses the given drafts instead of the published versions until the block ends (this request only)."""
    token = _preview.set({**(_preview.get() or {}), **overrides})
    try:
        yield
    finally:
        _preview.reset(token)


def _with_messages(locales: Dict[str, Any], messages: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
    key = f"{id(locales)}:{id(messages)}"
    if key not in _merged_locales:
        merged = {**locales, "locales": {code: {**loc, "messages": {**loc.get("messages", {}), **messages.get(code, {})}}
                                         for code, loc in locales["locales"].items()}}
        _merged_locales.clear()
        _merged_locales[key] = merged
    return _merged_locales[key]


def load_config(name: str) -> Dict[str, Any]:
    """A business configuration table (PRD FR-27): the version published in the admin module, else the built-in file.
    Canned replies edited in the admin ("messages") are merged into the locales table."""
    data = override(name)
    if data is None:
        data = _load_json(name)
    if name == "locales":
        messages = override("messages")
        if messages:
            data = _with_messages(data, messages)
    return data


def builtin_config(name: str) -> Dict[str, Any]:
    """The built-in file, ignoring any admin version (the seed and the fallback)."""
    return _load_json(name)


def load_prompt(name: str) -> str:
    with open(CONFIG_DIR / "prompts" / f"{name}.md", "r", encoding="utf-8") as f:
        return f.read()


def reload_config() -> None:
    """Clears cached configuration so updated rule/rate tables apply without a redeploy."""
    _load_json.cache_clear()


settings = AppSettings()
