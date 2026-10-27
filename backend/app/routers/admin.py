"""Back-office endpoints (PRD §5.6). Every endpoint requires a signed-in admin whose role grants the permission
it declares (FR-30), or the X-Admin-Key header for scripts."""
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.admin import permissions as P
from app.admin.activity import ActivityLog
from app.admin.auth import Actor, clear_session_cookie, current_actor, require, start_session
from app.admin.users import DUMMY_HASH, AdminUserError, AdminUserStore, public, verify_password
from app.core.audit import AuditService
from app.core.config import reload_config, settings
from app.core.security import client_ip, rate_limiter
from app.core.usage_tracker import UsageTracker
from app.db.database import Database
from app.db.lead_store import LeadDatabaseService
from app.gateways.grid_gateway import GridOffPlanGateway
from app.orchestrator.session_store import SessionStore
from app.services.handoff_service import HandoffService
from app.services.rag_service import RAGService

router = APIRouter(prefix="/api/admin", tags=["Admin"])

_LOGIN_WINDOW_SEC = 15 * 60


def _bad_request(exc: AdminUserError) -> HTTPException:
    code = str(exc)
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND if code == "not_found" else status.HTTP_400_BAD_REQUEST, detail=code)


def _me(actor: Actor) -> Dict[str, Any]:
    return {"user": {k: actor[k] for k in ("id", "email", "name", "role")}, "role_label": P.ROLE_LABELS.get(actor["role"], actor["role"]),
            "permissions": actor["permissions"], "storage": Database.mode()}


# --------------------------------------------------------------------------------------------------------------------
# Sign-in
# --------------------------------------------------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: str = Field(..., max_length=255)
    password: str = Field(..., max_length=256)


@router.post("/auth/login")
async def login(payload: LoginRequest, request: Request, response: Response):
    if not settings.JWT_SECRET:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="admin_login_unavailable")
    email = payload.email.strip().lower()
    # Only failed attempts count, per address and per account, so colleagues behind one office IP never block each other.
    keys = (f"admin-login-fail-ip:{client_ip(request)}", f"admin-login-fail-email:{email}")
    if any(rate_limiter.blocked(k, settings.ADMIN_LOGIN_ATTEMPTS_PER_15_MIN, _LOGIN_WINDOW_SEC) for k in keys):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="too_many_attempts")

    user = await AdminUserStore.get_by_email(email)
    password_ok = verify_password(payload.password, user["password_hash"] if user else DUMMY_HASH)
    if not user or not password_ok or not user["active"]:
        for k in keys:
            rate_limiter.record(k)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_credentials")

    await AdminUserStore.record_login(user["id"])
    await start_session(request, response, user)
    actor = {**public(user), "permissions": sorted(P.permissions_for(user["role"]))}
    await ActivityLog.record(actor, "signed_in", f"user:{user['email']}")
    return _me(actor)


@router.post("/auth/logout")
async def logout(response: Response, actor: Actor = Depends(current_actor)):
    if actor["via"] == "session":
        await AdminUserStore.revoke_session(actor["session_id"])
        await ActivityLog.record(actor, "signed_out", f"user:{actor['email']}")
    clear_session_cookie(response)
    return {"status": "signed_out"}


@router.get("/auth/me")
async def me(actor: Actor = Depends(current_actor)):
    return _me(actor)


class PasswordChange(BaseModel):
    current_password: str = Field(..., max_length=256)
    new_password: str = Field(..., max_length=256)


@router.post("/auth/password")
async def change_own_password(payload: PasswordChange, request: Request, response: Response, actor: Actor = Depends(current_actor)):
    if actor["via"] != "session":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="sign_in_required")
    user = await AdminUserStore.get(actor["id"])
    if not user or not verify_password(payload.current_password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="wrong_current_password")
    try:
        await AdminUserStore.set_password(actor["id"], payload.new_password)
    except AdminUserError as exc:
        raise _bad_request(exc)
    # The change signs out every other session; this browser gets a fresh one.
    await start_session(request, response, await AdminUserStore.get(actor["id"]))
    await ActivityLog.record(actor, "password_changed", f"user:{actor['email']}")
    return {"status": "password_changed"}


@router.get("/roles")
async def roles(actor: Actor = Depends(current_actor)):
    return [{"role": r, "label": P.ROLE_LABELS[r], "permissions": sorted(P.permissions_for(r))} for r in P.ROLES]


# --------------------------------------------------------------------------------------------------------------------
# Users (Admin role)
# --------------------------------------------------------------------------------------------------------------------

class NewUser(BaseModel):
    email: str = Field(..., max_length=255)
    name: str = Field(..., max_length=100)
    role: str
    password: str = Field(..., max_length=256)


class UserChange(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    role: Optional[str] = None
    active: Optional[bool] = None


class PasswordReset(BaseModel):
    password: str = Field(..., max_length=256)


@router.get("/users")
async def list_users(actor: Actor = Depends(require(P.USERS_MANAGE))):
    return [public(u) for u in await AdminUserStore.list()]


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(payload: NewUser, actor: Actor = Depends(require(P.USERS_MANAGE))):
    try:
        user = await AdminUserStore.create(payload.email, payload.name, payload.role, payload.password)
    except AdminUserError as exc:
        raise _bad_request(exc)
    await ActivityLog.record(actor, "user_created", f"user:{user['email']}", {"role": user["role"]})
    return public(user)


@router.patch("/users/{user_id}")
async def update_user(user_id: int, payload: UserChange, actor: Actor = Depends(require(P.USERS_MANAGE))):
    if user_id == actor["id"] and (payload.role is not None or payload.active is not None):
        # Prevents locking yourself out; another admin can make these changes.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="cannot_change_own_access")
    before = await AdminUserStore.get(user_id)
    try:
        user = await AdminUserStore.update(user_id, name=payload.name, role=payload.role, active=payload.active)
    except AdminUserError as exc:
        raise _bad_request(exc)
    changes = {k: {"from": before[k], "to": user[k]} for k in ("name", "role", "active") if before[k] != user[k]}
    if changes:
        await ActivityLog.record(actor, "user_updated", f"user:{user['email']}", changes)
    return public(user)


@router.post("/users/{user_id}/password")
async def reset_password(user_id: int, payload: PasswordReset, actor: Actor = Depends(require(P.USERS_MANAGE))):
    user = await AdminUserStore.get(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    try:
        await AdminUserStore.set_password(user_id, payload.password)
    except AdminUserError as exc:
        raise _bad_request(exc)
    await ActivityLog.record(actor, "password_reset", f"user:{user['email']}")
    return {"status": "password_reset"}


@router.get("/activity")
async def activity(limit: int = 100, actor_email: Optional[str] = None, action: Optional[str] = None,
                   actor: Actor = Depends(require(P.ACTIVITY_VIEW))):
    return await ActivityLog.recent(limit, actor_email=actor_email, action=action)


# --------------------------------------------------------------------------------------------------------------------
# Operations
# --------------------------------------------------------------------------------------------------------------------

@router.get("/status")
def system_status(actor: Actor = Depends(current_actor)):
    return {"environment": settings.ENVIRONMENT, "models": {"llm": settings.LLM_MODEL, "stt": settings.STT_MODEL, "tts": settings.TTS_MODEL,
            "voice": settings.ELEVENLABS_VOICE_NAME}, "lead_storage": LeadDatabaseService.storage_mode(), "storage": Database.mode()}


@router.get("/sessions")
def sessions(limit: int = 50, actor: Actor = Depends(require(P.CONVERSATIONS_VIEW))):
    return SessionStore.list_sessions(limit)


@router.get("/sessions/{session_id}/transcript")
def transcript(session_id: str, actor: Actor = Depends(require(P.CONVERSATIONS_VIEW))):
    session = SessionStore.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session_id": session_id, "language": session.language, "transcript": [t.model_dump() for t in session.transcript]}


@router.get("/usage")
def usage(limit: int = 50, actor: Actor = Depends(require(P.ANALYTICS_VIEW))):
    return UsageTracker.recent_sessions(limit)


@router.get("/usage/{session_id}")
def usage_for(session_id: str, actor: Actor = Depends(require(P.ANALYTICS_VIEW))):
    return UsageTracker.summary(session_id)


@router.get("/handoffs")
def handoffs(team: Optional[str] = None, actor: Actor = Depends(require(P.LEADS_VIEW))):
    return HandoffService.queue(team)


@router.get("/leads")
async def leads(limit: int = 100, actor: Actor = Depends(require(P.LEADS_VIEW))):
    return await LeadDatabaseService.list_leads(limit)


@router.get("/audit")
def audit(limit: int = 100, event_type: Optional[str] = None, actor: Actor = Depends(require(P.ACTIVITY_VIEW))):
    return [r.model_dump() for r in AuditService.get_recent_logs(limit, event_type)]


@router.post("/reload-config")
async def reload(actor: Actor = Depends(require(P.CONFIG_RELOAD))):
    """Applies edited rule/rate/fee tables without a redeploy (PRD FR-27)."""
    reload_config()
    RAGService.clear_cache()
    GridOffPlanGateway.clear_cache()
    await ActivityLog.record(actor, "config_reloaded", "config")
    return {"status": "reloaded"}
