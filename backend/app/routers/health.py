from fastapi import APIRouter
from app.core.config import settings

router = APIRouter(prefix="/api", tags=["Health & Diagnostics"])

@router.get("/health")
def get_system_health():
    """
    Core system health and architectural diagnostics endpoint.
    Verifies availability targets and operational readiness.
    """
    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "environment": settings.ENVIRONMENT,
        "availability_target_pct": settings.AVAILABILITY_TARGET_PCT,
        "models": {
            "llm": settings.LLM_MODEL,
            "stt": settings.STT_MODEL,
            "tts": settings.TTS_MODEL,
            "voice": settings.ELEVENLABS_VOICE_NAME,
            "voice_id": settings.ELEVENLABS_VOICE_ID,
            "v2v_pipeline": f"{settings.STT_MODEL} -> {settings.LLM_MODEL} -> {settings.TTS_MODEL}"
        },
        "gateways": {
            "property_inventory": "operational_read_scoped",
            "mortgage_rules": "operational_versioned_internal",
            "grid_crm": "operational_narrow_write",
            "vault_crm": "operational_narrow_write"
        },
        "compliance": {
            "regulatory_scope": settings.REGULATORY_SCOPE,
            "retention_policy_ref": settings.COMPANY_RETENTION_POLICY_REF,
            "max_dbr_ratio": settings.MAX_DBR_RATIO
        },
        "launch_languages": settings.LAUNCH_LANGUAGES
    }
