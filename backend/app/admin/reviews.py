"""Conversation review and feedback loop (PRD FR-26).

Reviewers mark XO replies good or bad, flag them for attention and leave a note. The review queue holds every
flagged reply and every reply a visitor rated thumbs-down that nobody has reviewed yet. A corrected answer can be
saved as a knowledge-base draft, which the knowledge-base module (FR-24) publishes."""
import itertools
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.db.conversation_store import ConversationStore
from app.db.database import Database

VERDICTS = ("good", "bad")


class ReviewError(ValueError):
    """A request that breaks a review rule; the message is a stable code the UI can show."""


def _iso(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


class ReviewStore:
    _reviews: Dict[int, Dict[str, Any]] = {}
    _drafts: List[Dict[str, Any]] = []
    _draft_ids = itertools.count(1)

    @classmethod
    def reset_memory(cls) -> None:
        cls._reviews.clear()
        cls._drafts.clear()
        cls._draft_ids = itertools.count(1)

    @classmethod
    def memory_review(cls, message_id: int) -> Optional[Dict[str, Any]]:
        return cls._reviews.get(message_id)

    @classmethod
    async def review(cls, message_id: int, *, verdict: Optional[str], flagged: bool, note: str, reviewer: str) -> Dict[str, Any]:
        if verdict is not None and verdict not in VERDICTS:
            raise ReviewError("invalid_verdict")
        message = await ConversationStore.message(message_id)
        if not message or message["role"] != "assistant":
            raise ReviewError("not_found")
        note = (note or "").strip()[:2000]
        if Database.pool:
            row = await Database.pool.fetchrow(
                """INSERT INTO message_reviews (message_id, verdict, flagged, note, reviewed_by) VALUES ($1, $2, $3, $4, $5)
                   ON CONFLICT (message_id) DO UPDATE SET verdict = EXCLUDED.verdict, flagged = EXCLUDED.flagged,
                   note = EXCLUDED.note, reviewed_by = EXCLUDED.reviewed_by, reviewed_at = NOW()
                   RETURNING verdict, flagged, note, reviewed_by, reviewed_at""",
                message_id, verdict, flagged, note, reviewer)
            return {k: _iso(v) for k, v in dict(row).items()}
        review = {"verdict": verdict, "flagged": flagged, "note": note, "reviewed_by": reviewer,
                  "reviewed_at": datetime.now(timezone.utc)}
        cls._reviews[message_id] = review
        return {k: _iso(v) for k, v in review.items()}

    @classmethod
    async def reviews_for(cls, message_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        if not message_ids:
            return {}
        if Database.pool:
            rows = await Database.pool.fetch(
                "SELECT message_id, verdict, flagged, note, reviewed_by, reviewed_at FROM message_reviews WHERE message_id = ANY($1::bigint[])",
                message_ids)
            return {r["message_id"]: {k: _iso(v) for k, v in dict(r).items() if k != "message_id"} for r in rows}
        return {i: {k: _iso(v) for k, v in cls._reviews[i].items()} for i in message_ids if i in cls._reviews}

    @classmethod
    async def queue(cls, limit: int = 100) -> List[Dict[str, Any]]:
        """Replies needing attention: flagged, or rated thumbs-down and not reviewed yet. Newest first."""
        limit = max(1, min(limit, 500))
        if Database.pool:
            rows = await Database.pool.fetch(
                """SELECT m.id AS message_id, m.session_id, m.content AS reply, m.language, m.created_at, f.rating,
                          r.verdict, COALESCE(r.flagged, FALSE) AS flagged, COALESCE(r.note, '') AS note, r.reviewed_by,
                          (SELECT u.content FROM conversation_messages u WHERE u.session_id = m.session_id AND u.role = 'user'
                             AND u.id < m.id ORDER BY u.id DESC LIMIT 1) AS question
                   FROM conversation_messages m
                   LEFT JOIN message_feedback f ON f.session_id = m.session_id AND f.turn_id = m.turn_id
                   LEFT JOIN message_reviews r ON r.message_id = m.id
                   WHERE m.role = 'assistant' AND (COALESCE(r.flagged, FALSE) OR (f.rating = -1 AND r.message_id IS NULL))
                   ORDER BY m.id DESC LIMIT $1""", limit)
            return [{k: _iso(v) for k, v in dict(r).items()} for r in rows]

        items = []
        messages = ConversationStore.memory_messages()
        for i, m in enumerate(messages):
            if m["role"] != "assistant":
                continue
            rating = ConversationStore.memory_rating(m["session_id"], m["turn_id"])
            review = cls._reviews.get(m["id"])
            if not ((review and review["flagged"]) or (rating == -1 and not review)):
                continue
            question = next((p["content"] for p in reversed(messages[:i]) if p["session_id"] == m["session_id"] and p["role"] == "user"), None)
            items.append({"message_id": m["id"], "session_id": m["session_id"], "reply": m["content"], "language": m["language"],
                          "created_at": _iso(m["created_at"]), "rating": rating, "verdict": review and review["verdict"],
                          "flagged": bool(review and review["flagged"]), "note": review["note"] if review else "",
                          "reviewed_by": review and review["reviewed_by"], "question": question})
        items.sort(key=lambda x: x["message_id"], reverse=True)
        return items[:limit]

    # ---- Knowledge-base drafts from corrected answers ----

    @classmethod
    async def create_draft(cls, *, created_by: str, source_message_id: Optional[int], language: str, title: str,
                           question: str, answer: str) -> Dict[str, Any]:
        title, question, answer = " ".join((title or "").split())[:255], (question or "").strip(), (answer or "").strip()
        if not title:
            raise ReviewError("title_required")
        if not question or not answer:
            raise ReviewError("question_and_answer_required")
        if len(question) > 2000 or len(answer) > 8000:
            raise ReviewError("too_long")
        if source_message_id is not None and not await ConversationStore.message(source_message_id):
            raise ReviewError("not_found")
        if Database.pool:
            row = await Database.pool.fetchrow(
                """INSERT INTO kb_drafts (created_by, source_message_id, language, title, question, answer)
                   VALUES ($1, $2, $3, $4, $5, $6) RETURNING *""",
                created_by, source_message_id, language, title, question, answer)
            return {k: _iso(v) for k, v in dict(row).items()}
        draft = {"id": next(cls._draft_ids), "created_at": datetime.now(timezone.utc), "created_by": created_by,
                 "source_message_id": source_message_id, "language": language, "title": title, "question": question,
                 "answer": answer, "status": "draft"}
        cls._drafts.append(draft)
        return {k: _iso(v) for k, v in draft.items()}

    @classmethod
    async def drafts(cls, status: str = "draft") -> List[Dict[str, Any]]:
        if Database.pool:
            rows = await Database.pool.fetch("SELECT * FROM kb_drafts WHERE status = $1 ORDER BY id DESC LIMIT 500", status)
            return [{k: _iso(v) for k, v in dict(r).items()} for r in rows]
        return [{k: _iso(v) for k, v in d.items()} for d in reversed(cls._drafts) if d["status"] == status]

    @classmethod
    async def set_draft_status(cls, draft_id: int, status: str) -> Dict[str, Any]:
        """'published' once it became a knowledge-base entry, 'dismissed' when an editor decides not to use it."""
        if Database.pool:
            row = await Database.pool.fetchrow("UPDATE kb_drafts SET status = $2 WHERE id = $1 AND status = 'draft' RETURNING *",
                                               draft_id, status)
            if not row:
                raise ReviewError("not_found")
            return {k: _iso(v) for k, v in dict(row).items()}
        draft = next((d for d in cls._drafts if d["id"] == draft_id and d["status"] == "draft"), None)
        if not draft:
            raise ReviewError("not_found")
        draft["status"] = status
        return {k: _iso(v) for k, v in draft.items()}

    @classmethod
    async def draft(cls, draft_id: int) -> Optional[Dict[str, Any]]:
        return next((d for d in await cls.drafts() if d["id"] == draft_id), None)
