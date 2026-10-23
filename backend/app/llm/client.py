"""Shared OpenAI client and system-prompt rendering."""
from datetime import datetime, timezone
from typing import Optional

from openai import AsyncOpenAI

from app.core.config import load_config, settings
from app.services import prompt_profile


class LLMService:
    _client: Optional[AsyncOpenAI] = None

    @classmethod
    def client(cls) -> AsyncOpenAI:
        """One pooled async client for the whole process (connection reuse lowers latency)."""
        if cls._client is None:
            if not settings.OPENAI_API_KEY:
                raise RuntimeError("OPENAI_API_KEY is not configured")
            cls._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY, timeout=settings.LLM_TIMEOUT_SEC, max_retries=1)
        return cls._client

    @classmethod
    def reset(cls) -> None:
        cls._client = None

    @classmethod
    def system_prompt(cls, language: str, language_locked: bool) -> str:
        locales = load_config("locales")["locales"]
        info = locales.get(language, locales[load_config("locales")["default"]])
        rules = load_config("mortgage_rules")
        mode = ("chosen by the user in the language menu; keep using it unless they write in or ask for another language"
                if language_locked else "detected from the conversation")
        # The instructions published in the admin module (FR-25), or the built-in file when none is published.
        return prompt_profile.fill(prompt_profile.render_template(prompt_profile.current_profile(), language), {
            "language_name": info["name"],
            "language_native": info["native"],
            "language_mode": mode,
            "supported_languages": ", ".join(f"{v['name']}" for v in locales.values()),
            "default_tenure": rules["tenure"]["default_years"],
            "benchmark_rate": rules["interest"]["benchmark_rate_pct"],
            "today": datetime.now(timezone.utc).strftime("%d %B %Y"),
        })
