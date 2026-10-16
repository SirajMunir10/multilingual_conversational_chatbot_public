"""Back-office endpoints (PRD §5.6). All require the X-Admin-Key header."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.core.audit import AuditService
from app.core.config import reload_config, settings
from app.core.security import require_admin
from app.core.usage_tracker import UsageTracker
from app.db.lead_store import LeadDatabaseService
from app.gateways.grid_gateway import GridOffPlanGateway
from app.orchestrator.session_store import SessionStore
from app.services.handoff_service import HandoffService
from app.services.rag_service import RAGService

router = APIRouter(prefix="/api/admin", tags=["Admin"], dependencies=[Depends(require_admin)])


@router.get("/status")
def status():
    return {"environment": settings.ENVIRONMENT, "models": {"llm": settings.LLM_MODEL, "stt": settings.STT_MODEL, "tts": settings.TTS_MODEL,
            "voice": settings.ELEVENLABS_VOICE_NAME}, "lead_storage": LeadDatabaseService.storage_mode()}


@router.get("/sessions")
def sessions(limit: int = 50):
    return SessionStore.list_sessions(limit)


@router.get("/sessions/{session_id}/transcript")
def transcript(session_id: str):
    session = SessionStore.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session_id": session_id, "language": session.language, "transcript": [t.model_dump() for t in session.transcript]}


@router.get("/usage")
def usage(limit: int = 50):
    return UsageTracker.recent_sessions(limit)


@router.get("/usage/{session_id}")
def usage_for(session_id: str):
    return UsageTracker.summary(session_id)


@router.get("/handoffs")
def handoffs(team: Optional[str] = None):
    return HandoffService.queue(team)


@router.get("/leads")
async def leads(limit: int = 100):
    return await LeadDatabaseService.list_leads(limit)


@router.get("/audit")
def audit(limit: int = 100, event_type: Optional[str] = None):
    return [r.model_dump() for r in AuditService.get_recent_logs(limit, event_type)]


@router.post("/reload-config")
def reload():
    """Applies edited rule/rate/fee tables without a redeploy (PRD FR-27)."""
    reload_config()
    RAGService.clear_cache()
    GridOffPlanGateway.clear_cache()
    return {"status": "reloaded"}
