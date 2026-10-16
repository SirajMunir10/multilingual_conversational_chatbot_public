"""Test configuration: deterministic, offline settings applied before the app is imported."""
import os

os.environ.update({
    "OPENAI_API_KEY": os.environ.get("XO_LIVE_OPENAI_API_KEY", "test-key"),
    "ELEVENLABS_API_KEY": "",
    "ADMIN_API_KEY": "test-admin-key",
    "JWT_SECRET": "test-jwt-secret",
    "DATABASE_URL": "",
    "RATE_LIMIT_ENABLED": "false",
    "ALLOWED_ORIGINS": "http://localhost:3000",
    "LLM_MODEL": "gpt-6-luna",
    "ENVIRONMENT": "test",
})
