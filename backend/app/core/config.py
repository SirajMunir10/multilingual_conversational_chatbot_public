import os
from typing import List
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load .env file if available
load_dotenv()

class AppSettings(BaseModel):
    APP_NAME: str = "XO — Conversational AI Assistant"
    ENVIRONMENT: str = Field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    PORT: int = Field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173"
    ]
    
    # Authoritative Model Selections (PRD Confirmed Decisions)
    LLM_MODEL: str = Field(default_factory=lambda: os.getenv("LLM_MODEL", "gpt-5-mini"))
    STT_MODEL: str = Field(default_factory=lambda: os.getenv("STT_MODEL", "gpt-live-transcribe"))
    TTS_MODEL: str = Field(default_factory=lambda: os.getenv("TTS_MODEL", "eleven_flash_v2_5"))
    ELEVENLABS_API_KEY: str = Field(default_factory=lambda: os.getenv("ELEVENLABS_API_KEY", ""))
    ELEVENLABS_VOICE_ID: str = Field(default_factory=lambda: os.getenv("ELEVENLABS_VOICE_ID", "qXpMhyvQqiRxWQs4qSSB"))
    ELEVENLABS_VOICE_NAME: str = Field(default_factory=lambda: os.getenv("ELEVENLABS_VOICE_NAME", "Horatius - Energetic Character voice"))
    EMBEDDING_MODEL: str = Field(default_factory=lambda: os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"))
    OPENAI_API_KEY: str = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))

    # Compliance & Retention Policy
    COMPANY_RETENTION_POLICY_REF: str = "XOTO-CORP-RETENTION-POL-2024-V3"
    REGULATORY_SCOPE: str = "UAE / Dubai / DIFC"
    MAX_DBR_RATIO: float = 0.50  # UAE Central Bank 50% Debt Burden Ratio cap

    # CRM Gateways Configuration (GRID & Vault)
    GRID_API_URL: str = Field(default_factory=lambda: os.getenv("GRID_API_URL", ""))
    GRID_API_KEY: str = Field(default_factory=lambda: os.getenv("GRID_API_KEY", ""))
    GRID_OFFPLAN_API_URL: str = Field(default_factory=lambda: os.getenv("GRID_OFFPLAN_API_URL", "https://xoto.ae/api/gridoffplan/website"))
    VAULT_API_URL: str = Field(default_factory=lambda: os.getenv("VAULT_API_URL", ""))
    VAULT_API_KEY: str = Field(default_factory=lambda: os.getenv("VAULT_API_KEY", ""))

    # Company PostgreSQL Database Configuration (Private Advisor Lead Storage)
    DATABASE_URL: str = Field(default_factory=lambda: os.getenv("DATABASE_URL", ""))

    # Launch Languages (Expanded 15 Locales)
    LAUNCH_LANGUAGES: List[str] = [
        "en", "ar", "hi", "ur",
        "bn", "ml", "tl", "fa", "ta", "pa", "or",
        "fr", "es", "de", "zh"
    ]

    # Latency Targets (PRD Section 7)
    PERCEIVED_LATENCY_TARGET_SEC: float = 2.0
    FULL_ANSWER_LATENCY_TARGET_SEC: float = 6.0

    # Availability Target
    AVAILABILITY_TARGET_PCT: float = 99.9

settings = AppSettings()
