import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

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
    RATE_LIMIT_PER_MINUTE: int = Field(default_factory=lambda: _env_int("RATE_LIMIT_PER_MINUTE", 30))
    RATE_LIMIT_ENABLED: bool = Field(default_factory=lambda: _env_bool("RATE_LIMIT_ENABLED", True))
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


def load_config(name: str) -> Dict[str, Any]:
    """Loads a versioned business configuration table from data/config (admin-editable, PRD FR-27)."""
    return _load_json(name)


def load_prompt(name: str) -> str:
    with open(CONFIG_DIR / "prompts" / f"{name}.md", "r", encoding="utf-8") as f:
        return f.read()


def reload_config() -> None:
    """Clears cached configuration so updated rule/rate tables apply without a redeploy."""
    _load_json.cache_clear()


settings = AppSettings()
