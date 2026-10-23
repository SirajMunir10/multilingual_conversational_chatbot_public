"""Admin insights (PRD FR-31 analytics, FR-26 conversation review and feedback loop, §7 cost control).
Every endpoint requires a role that grants the permission it declares (FR-30). Phone numbers and emails typed
by visitors are masked for roles without access to personal data (FR-22)."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.admin import permissions as P
from app.admin.activity import ActivityLog
from app.admin.analytics import build_report, ending_of, handled_by_xo, month_start, report_range, topics_of
from app.admin.auth import Actor, require, require_any
from app.admin.privacy import mask_personal_data
from app.admin.reviews import ReviewError, ReviewStore
from app.admin.settings_store import SettingsStore
from app.db.conversation_store import ConversationStore

router = APIRouter(prefix="/api/admin", tags=["Admin insights"])

BUDGET_KEY = "ai_budget"
_TOPIC_LABELS = {"property": "Property", "mortgage": "Mortgage", "knowledge": "Knowledge", "services": "Services",
                 "account": "Account", "advisor": "Advisor"}


def _sees_personal_data(actor: Actor) -> bool:
    return P.LEADS_VIEW in actor["permissions"]


def _text(actor: Actor, value: Optional[str]) -> Optional[str]:
    return value if _sees_personal_data(actor) else mask_personal_data(value)


def _iso(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


def _review_error(exc: ReviewError) -> HTTPException:
    code = str(exc)
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND if code == "not_found" else status.HTTP_400_BAD_REQUEST, detail=code)


# --------------------------------------------------------------------------------------------------------------------
# Analytics and budget
# --------------------------------------------------------------------------------------------------------------------

async def _budget() -> Dict[str, Any]:
    return await SettingsStore.get(BUDGET_KEY, {"monthly_usd": None, "alert_pct": 80})


@router.get("/analytics")
async def analytics(days: int = 30, actor: Actor = Depends(require(P.ANALYTICS_VIEW))):
    rng = report_range(days)
    conversations = await ConversationStore.summaries(rng["start"], rng["end"])
    month = await ConversationStore.summaries(month_start(), rng["end"])
    # The same number of days just before, for the "vs previous period" change.
    previous = await ConversationStore.summaries(rng["start"] - (rng["end"] - rng["start"]), rng["start"])
    return build_report(conversations, start=rng["start"], end=rng["end"], month_cost_usd=sum(c["cost_usd"] for c in month),
                        budget=await _budget(), show_personal_data=_sees_personal_data(actor), previous=previous)


class BudgetChange(BaseModel):
    monthly_usd: Optional[float] = Field(None, ge=0, le=1_000_000, description="None switches the budget off.")
    alert_pct: int = Field(80, ge=1, le=100)


@router.get("/budget")
async def get_budget(actor: Actor = Depends(require(P.ANALYTICS_VIEW))):
    return await _budget()


@router.put("/budget")
async def set_budget(payload: BudgetChange, actor: Actor = Depends(require(P.BUDGET_EDIT))):
    before = await _budget()
    value = {"monthly_usd": payload.monthly_usd, "alert_pct": payload.alert_pct}
    await SettingsStore.set(BUDGET_KEY, value, actor["email"])
    changes = {k: {"from": before.get(k), "to": value[k]} for k in value if before.get(k) != value[k]}
    if changes:
        await ActivityLog.record(actor, "budget_updated", "settings:ai_budget", changes)
    return value


# --------------------------------------------------------------------------------------------------------------------
# Conversation review
# --------------------------------------------------------------------------------------------------------------------

def _matches(c: Dict[str, Any], language: Optional[str], channel: Optional[str], outcome: Optional[str],
             rating: Optional[str], review: Optional[str]) -> bool:
    if language and c["language"] != language:
        return False
    if channel and channel not in (c["channels"] or []):
        return False
    if outcome == "lead" and not c["lead_saved"]:
        return False
    if outcome == "handled" and not handled_by_xo(c):
        return False
    if outcome == "failed" and not c["failed_turns"]:
        return False
    if rating == "up" and not c["thumbs_up"]:
        return False
    if rating == "down" and not c["thumbs_down"]:
        return False
    if review == "flagged" and not c["flagged"]:
        return False
    if review in ("good", "bad") and not c[f"reviewed_{review}"]:
        return False
    if review == "unreviewed" and (c["reviewed_good"] or c["reviewed_bad"]):
        return False
    return True


@router.get("/conversations")
async def conversations(days: int = 30, language: Optional[str] = None, channel: Optional[str] = None,
                        outcome: Optional[str] = None, rating: Optional[str] = None, review: Optional[str] = None,
                        q: Optional[str] = Query(None, max_length=200), page: int = 1, page_size: int = 25,
                        actor: Actor = Depends(require(P.CONVERSATIONS_VIEW))):
    rng = report_range(days)
    rows = [c for c in await ConversationStore.summaries(rng["start"], rng["end"], search=q)
            if _matches(c, language, channel, outcome, rating, review)]
    page_size = max(5, min(page_size, 100))
    page = max(1, page)
    items = rows[(page - 1) * page_size: page * page_size]
    return {
        "total": len(rows), "page": page, "page_size": page_size,
        "items": [{
            "session_id": c["session_id"], "started_at": _iso(c["started_at"]), "updated_at": _iso(c["updated_at"]),
            "language": c["language"], "channels": c["channels"], "user_turns": c["user_turns"],
            "failed_turns": c["failed_turns"], "lead_saved": c["lead_saved"], "handoff_ticket": c["handoff_ticket"],
            "cost_usd": c["cost_usd"], "first_question": _text(actor, c["first_question"]),
            "topics": [_TOPIC_LABELS[t] for t in topics_of(c["tools"])], "ending": ending_of(c),
            "thumbs_up": c["thumbs_up"], "thumbs_down": c["thumbs_down"], "flagged": c["flagged"],
            "reviewed_good": c["reviewed_good"], "reviewed_bad": c["reviewed_bad"],
        } for c in items],
    }


@router.get("/conversations/{session_id}")
async def conversation(session_id: str, actor: Actor = Depends(require(P.CONVERSATIONS_VIEW))):
    conv = await ConversationStore.get(session_id)
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    reviews = await ReviewStore.reviews_for([m["id"] for m in conv["messages"] if m["role"] == "assistant"])
    return {
        "session_id": conv["session_id"], "started_at": _iso(conv["started_at"]), "updated_at": _iso(conv["updated_at"]),
        "language": conv["language"], "channels": conv["channels"], "user_turns": conv["user_turns"],
        "failed_turns": conv["failed_turns"], "lead_saved": conv["lead_saved"], "handoff_ticket": conv["handoff_ticket"],
        "cost_usd": conv["cost_usd"], "personal_data_masked": not _sees_personal_data(actor),
        "messages": [{
            "id": m["id"], "role": m["role"], "content": _text(actor, m["content"]), "created_at": _iso(m["created_at"]),
            "language": m["language"], "channel": m["channel"], "latency_ms": m["latency_ms"],
            "topics": [_TOPIC_LABELS[t] for t in topics_of(m["tools"] or [])], "rating": m["rating"],
            "review": reviews.get(m["id"]),
        } for m in conv["messages"]],
    }


class ReviewChange(BaseModel):
    verdict: Optional[str] = Field(None, pattern="^(good|bad)$")
    flagged: bool = False
    note: str = Field("", max_length=2000)


@router.put("/messages/{message_id}/review")
async def review_message(message_id: int, payload: ReviewChange, actor: Actor = Depends(require(P.CONVERSATIONS_REVIEW))):
    try:
        result = await ReviewStore.review(message_id, verdict=payload.verdict, flagged=payload.flagged, note=payload.note,
                                          reviewer=actor["email"])
    except ReviewError as exc:
        raise _review_error(exc)
    await ActivityLog.record(actor, "reply_reviewed", f"message:{message_id}",
                             {"verdict": payload.verdict, "flagged": payload.flagged})
    return result


@router.get("/review-queue")
async def review_queue(limit: int = 100, actor: Actor = Depends(require(P.CONVERSATIONS_VIEW))):
    items = await ReviewStore.queue(limit)
    for item in items:
        item["question"], item["reply"] = _text(actor, item["question"]), _text(actor, item["reply"])
    return items


class DraftRequest(BaseModel):
    source_message_id: Optional[int] = None
    language: str = Field("en", max_length=16)
    title: str = Field(..., max_length=255)
    question: str = Field(..., max_length=2000)
    answer: str = Field(..., max_length=8000)


@router.post("/kb-drafts", status_code=status.HTTP_201_CREATED)
async def create_kb_draft(payload: DraftRequest, actor: Actor = Depends(require(P.CONVERSATIONS_REVIEW))):
    try:
        draft = await ReviewStore.create_draft(created_by=actor["email"], source_message_id=payload.source_message_id,
                                               language=payload.language, title=payload.title, question=payload.question,
                                               answer=payload.answer)
    except ReviewError as exc:
        raise _review_error(exc)
    await ActivityLog.record(actor, "kb_draft_created", f"kb_draft:{draft['id']}", {"title": draft["title"]})
    return draft


@router.get("/kb-drafts")
async def kb_drafts(actor: Actor = Depends(require_any(P.KB_EDIT, P.CONVERSATIONS_REVIEW))) -> List[Dict[str, Any]]:
    return await ReviewStore.drafts()
