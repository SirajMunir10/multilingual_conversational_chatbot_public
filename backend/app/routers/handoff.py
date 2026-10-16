"""Advisor callback review card (PRD FR-5, FR-16): the user confirms or edits the details, then they are saved."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.security import enforce_rate_limit
from app.orchestrator.session_store import SessionStore
from app.services.handoff_service import HandoffService

router = APIRouter(prefix="/api/handoff", tags=["Advisor handoff"], dependencies=[Depends(enforce_rate_limit)])


class ConfirmRequest(BaseModel):
    session_id: str = Field(..., max_length=128)
    draft_id: str = Field(..., max_length=64)
    full_name: str = Field("", max_length=200)
    phone: str = Field("", max_length=40)
    preferred_language: str = Field("", max_length=16)
    team: str = Field("", max_length=16)


@router.post("/confirm")
async def confirm(payload: ConfirmRequest):
    session = SessionStore.get(payload.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session_expired")
    return await HandoffService.confirm_callback(session, payload.draft_id, payload.full_name, payload.phone,
                                                 payload.preferred_language, payload.team)
