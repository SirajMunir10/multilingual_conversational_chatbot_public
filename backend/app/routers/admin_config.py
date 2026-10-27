"""Editing XO from the admin module (PRD FR-25 bot tuning, FR-27 calculator rules, FR-29 escalation rules).

Every item follows draft → preview → publish. Publishing adds a numbered version and applies it at once; rollback
re-publishes an older version as a new one. Each item needs its own permission (FR-30) and every change is recorded
in the activity log."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.admin import permissions as P
from app.admin.activity import ActivityLog
from app.admin.auth import Actor, current_actor, require
from app.admin.config_items import ITEMS
from app.admin.config_store import ConfigError, ConfigStore
from app.admin.rules_impact import impact
from app.core.config import preview
from app.orchestrator.orchestrator import ConversationOrchestrator
from app.orchestrator.session_store import SessionStore
from app.services import prompt_profile

router = APIRouter(prefix="/api/admin/config", tags=["Admin configuration"])

RULE_ITEMS = ("mortgage_rules", "fees", "bank_products")


def _error(exc: ConfigError) -> HTTPException:
    codes = {"not_found": 404, "version_not_found": 404, "stale_draft": 409, "no_draft": 400, "invalid": 422, "too_large": 413}
    return HTTPException(status_code=codes.get(exc.code, 400), detail={"code": exc.code, "errors": exc.errors})


def _allowed(name: str, actor: Actor) -> None:
    spec = ITEMS.get(name)
    if not spec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "not_found", "errors": []})
    if spec.permission not in actor["permissions"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your role does not allow this.")


@router.get("/{name}")
async def get_item(name: str, actor: Actor = Depends(current_actor)):
    """The published version, the working draft (if any) and the draft's problems."""
    _allowed(name, actor)
    draft = await ConfigStore.draft(name)
    published = await ConfigStore.published(name)
    return {"item": name, "label": ITEMS[name].label, "published": published, "draft": draft,
            "draft_errors": ITEMS[name].validate(draft["data"]) if draft else [],
            "stale": bool(draft and draft["base_version"] != published["version"])}


class DraftBody(BaseModel):
    data: Any
    base_version: int = Field(..., ge=0)


@router.put("/{name}/draft")
async def save_draft(name: str, body: DraftBody, actor: Actor = Depends(current_actor)):
    _allowed(name, actor)
    try:
        draft = await ConfigStore.save_draft(name, body.data, body.base_version, actor)
    except ConfigError as exc:
        raise _error(exc)
    return {"draft": draft, "draft_errors": ITEMS[name].validate(body.data)}


@router.delete("/{name}/draft")
async def discard_draft(name: str, actor: Actor = Depends(current_actor)):
    _allowed(name, actor)
    await ConfigStore.discard_draft(name)
    return {"status": "discarded"}


class PublishBody(BaseModel):
    note: str = Field("", max_length=500)


@router.post("/{name}/publish")
async def publish(name: str, body: PublishBody, actor: Actor = Depends(current_actor)):
    _allowed(name, actor)
    try:
        version = await ConfigStore.publish(name, body.note, actor)
    except ConfigError as exc:
        raise _error(exc)
    await ActivityLog.record(actor, "config_published", f"config:{name}", {"version": version, "note": body.note})
    return {"version": version}


@router.get("/{name}/versions")
async def versions(name: str, actor: Actor = Depends(current_actor)) -> List[Dict[str, Any]]:
    _allowed(name, actor)
    return await ConfigStore.versions(name)


@router.get("/{name}/versions/{number}")
async def version(name: str, number: int, actor: Actor = Depends(current_actor)):
    _allowed(name, actor)
    try:
        return await ConfigStore.version(name, number)
    except ConfigError as exc:
        raise _error(exc)


class RollbackBody(BaseModel):
    version: int = Field(..., ge=0)
    note: str = Field("", max_length=500)


@router.post("/{name}/rollback")
async def rollback(name: str, body: RollbackBody, actor: Actor = Depends(current_actor)):
    _allowed(name, actor)
    try:
        version_number = await ConfigStore.rollback(name, body.version, body.note, actor)
    except ConfigError as exc:
        raise _error(exc)
    await ActivityLog.record(actor, "config_rolled_back", f"config:{name}", {"to": body.version, "version": version_number})
    return {"version": version_number}


# --------------------------------------------------------------------------------------------------------------------
# Previews
# --------------------------------------------------------------------------------------------------------------------

class ImpactBody(BaseModel):
    mortgage_rules: Optional[Dict[str, Any]] = None
    fees: Optional[Dict[str, Any]] = None
    bank_products: Optional[Dict[str, Any]] = None


@router.post("/rules/impact")
async def rules_impact(body: ImpactBody, actor: Actor = Depends(require(P.RULES_EDIT))):
    """The 15 approved cases and two examples with the published rules and with the drafts (FR-27)."""
    drafts = {k: v for k, v in body.model_dump().items() if v is not None}
    problems = {k: ITEMS[k].validate(v) for k, v in drafts.items()}
    if any(problems.values()):
        raise HTTPException(status_code=422, detail={"code": "invalid", "errors": [e for errs in problems.values() for e in errs]})
    published = {k: (await ConfigStore.published(k))["data"] for k in RULE_ITEMS}
    return impact(drafts, published)


class TestChatBody(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: Optional[str] = None
    language: str = Field("en", max_length=8)
    prompt_profile: Optional[Dict[str, Any]] = None
    messages: Optional[Dict[str, Any]] = None
    escalation: Optional[Dict[str, Any]] = None


@router.post("/test-chat")
async def test_chat(body: TestChatBody, actor: Actor = Depends(require(P.PROMPTS_EDIT))):
    """One turn with the real model using the given drafts (FR-25). Never saved for review or analytics."""
    drafts = {k: getattr(body, k) for k in ("prompt_profile", "messages", "escalation") if getattr(body, k) is not None}
    problems = [e for k, v in drafts.items() for e in ITEMS[k].validate(v)]
    if problems:
        raise HTTPException(status_code=422, detail={"code": "invalid", "errors": problems})
    session = SessionStore.get(body.session_id) if body.session_id else None
    if session is None or not session.preview:
        session = SessionStore.get_or_create(None, language=body.language)
        session.preview = True
    final: Dict[str, Any] = {}
    with preview(drafts):
        async for event in ConversationOrchestrator.stream_turn(body.message, session_id=session.session_id,
                                                                selected_language=body.language):
            if event["type"] in ("final", "error"):
                final = event
    guard = prompt_profile.banned_topic(body.message, drafts.get("prompt_profile") or prompt_profile.current_profile())
    return {"session_id": session.session_id, "reply": final.get("text") or final.get("message") or "",
            "error": final.get("type") == "error", "tools": final.get("tools", []),
            "blocked_topic": guard["name"] if guard else None,
            "callback_card": bool(final.get("handoff_draft"))}
