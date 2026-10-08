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
    TTS_MODEL: str = Field(default_factory=lambda: os.getenv("TTS_MODEL", "gpt-4o-mini-tts"))
    EMBEDDING_MODEL: str = Field(default_factory=lambda: os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"))
    OPENAI_API_KEY: str = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))

    # Compliance & Retention Policy
    COMPANY_RETENTION_POLICY_REF: str = "XOTO-CORP-RETENTION-POL-2024-V3"
    REGULATORY_SCOPE: str = "UAE / Dubai / DIFC"
    MAX_DBR_RATIO: float = 0.50  # UAE Central Bank 50% Debt Burden Ratio cap

    # Launch Languages
    LAUNCH_LANGUAGES: List[str] = ["en", "ar", "hi", "ur"]

    # Latency Targets (PRD Section 7)
    PERCEIVED_LATENCY_TARGET_SEC: float = 2.0
    FULL_ANSWER_LATENCY_TARGET_SEC: float = 6.0

    # Availability Target
    AVAILABILITY_TARGET_PCT: float = 99.9

settings = AppSettings()
