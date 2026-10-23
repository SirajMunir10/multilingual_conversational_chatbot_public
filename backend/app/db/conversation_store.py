"""Conversation history for the admin module (PRD FR-26 review, FR-31 analytics).

Each finished turn is written in the background, so saving never delays the reply. Payment data is already
removed from user text before it reaches here (FR-23b). PostgreSQL when configured, bounded memory otherwise."""
import asyncio
import itertools
import logging
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from app.db.database import Database

logger = logging.getLogger("xo.conversations")

_MAX_MEMORY_CONVERSATIONS = 2000
_MAX_SUMMARIES = 20000
_pending: Set["asyncio.Task[Any]"] = set()


def _merge(values: List[str], new: List[str]) -> List[str]:
    return values + [v for v in new if v and v not in values]


class ConversationStore:
    _memory: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
    _feedback: Dict[tuple, int] = {}
    _message_ids = itertools.count(1)

    @classmethod
    def save_in_background(cls, coro: Any) -> None:
        """Runs a write without blocking the caller; failures are logged, never raised into the conversation."""
        task = asyncio.ensure_future(coro)
        _pending.add(task)

        def done(t: "asyncio.Task[Any]") -> None:
            _pending.discard(t)
            if not t.cancelled() and t.exception():
                logger.error("Saving conversation data failed: %s", t.exception())
        task.add_done_callback(done)

    @classmethod
    async def flush(cls) -> None:
        """Waits for background writes (shutdown, tests)."""
        while _pending:
            await asyncio.gather(*list(_pending), return_exceptions=True)

    # ------------------------------------------------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------------------------------------------------

    @classmethod
    async def record_turn(cls, session_id: str, *, language: str, channel: str, user_text: str, reply: Optional[str],
                          tools: List[str], latency_ms: Optional[int], cost_usd: float, turn_id: Optional[str] = None) -> None:
        """`reply` is None when the turn failed (counted for drop-off analytics)."""
        failed = reply is None
        now = datetime.now(timezone.utc)
        if Database.pool:
            async with Database.pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        """INSERT INTO conversations (session_id, language, channels, user_turns, failed_turns, tools, cost_usd)
                           VALUES ($1, $2, ARRAY[$3::text], 1, $4, $5::text[], $6)
                           ON CONFLICT (session_id) DO UPDATE SET
                               updated_at = NOW(), language = EXCLUDED.language,
                               channels = (SELECT ARRAY(SELECT DISTINCT unnest(conversations.channels || EXCLUDED.channels))),
                               user_turns = conversations.user_turns + 1,
                               failed_turns = conversations.failed_turns + EXCLUDED.failed_turns,
                               tools = (SELECT ARRAY(SELECT DISTINCT unnest(conversations.tools || EXCLUDED.tools))),
                               cost_usd = GREATEST(conversations.cost_usd, EXCLUDED.cost_usd)""",
                        session_id, language, channel, 1 if failed else 0, tools, cost_usd)
                    await conn.execute(
                        """INSERT INTO conversation_messages (session_id, role, content, language, channel) VALUES ($1, 'user', $2, $3, $4)""",
                        session_id, user_text, language, channel)
                    if not failed:
                        await conn.execute(
                            """INSERT INTO conversation_messages (session_id, role, content, language, channel, tools, latency_ms, turn_id)
                               VALUES ($1, 'assistant', $2, $3, $4, $5::text[], $6, $7)""",
                            session_id, reply, language, channel, tools, latency_ms, turn_id)
            return

        conv = cls._memory.get(session_id)
        if conv is None:
            conv = {"session_id": session_id, "started_at": now, "updated_at": now, "language": language, "channels": [],
                    "user_turns": 0, "failed_turns": 0, "tools": [], "handoff_ticket": None, "lead_saved": False,
                    "cost_usd": 0.0, "messages": []}
            cls._memory[session_id] = conv
            while len(cls._memory) > _MAX_MEMORY_CONVERSATIONS:
                cls._memory.popitem(last=False)
        cls._memory.move_to_end(session_id)
        conv.update(updated_at=now, language=language, channels=_merge(conv["channels"], [channel]),
                    user_turns=conv["user_turns"] + 1, failed_turns=conv["failed_turns"] + (1 if failed else 0),
                    tools=_merge(conv["tools"], tools), cost_usd=max(conv["cost_usd"], cost_usd))
        conv["messages"].append({"id": next(cls._message_ids), "turn_id": None, "role": "user", "content": user_text,
                                 "language": language, "channel": channel, "tools": [], "latency_ms": None, "created_at": now})
        if not failed:
            conv["messages"].append({"id": next(cls._message_ids), "turn_id": turn_id, "role": "assistant", "content": reply,
                                     "language": language, "channel": channel, "tools": tools, "latency_ms": latency_ms,
                                     "created_at": now})

    @classmethod
    async def record_handoff(cls, session_id: str, ticket_id: str) -> None:
        """The user confirmed the advisor callback card and the lead was saved (FR-5, FR-16)."""
        if Database.pool:
            await Database.pool.execute(
                """INSERT INTO conversations (session_id, handoff_ticket, lead_saved) VALUES ($1, $2, TRUE)
                   ON CONFLICT (session_id) DO UPDATE SET handoff_ticket = EXCLUDED.handoff_ticket, lead_saved = TRUE,
                   updated_at = NOW()""", session_id, ticket_id)
            return
        conv = cls._memory.get(session_id)
        if conv:
            conv.update(handoff_ticket=ticket_id, lead_saved=True)

    @classmethod
    async def update_cost(cls, session_id: str, cost_usd: float) -> None:
        """Speech is generated after the reply is saved, so its cost is added when the audio has been produced."""
        if Database.pool:
            await Database.pool.execute(
                "UPDATE conversations SET cost_usd = GREATEST(cost_usd, $2) WHERE session_id = $1", session_id, cost_usd)
            return
        conv = cls._memory.get(session_id)
        if conv:
            conv["cost_usd"] = max(conv["cost_usd"], cost_usd)

    @classmethod
    async def set_feedback(cls, session_id: str, turn_id: str, rating: Optional[int]) -> None:
        """Visitor thumbs on one reply: 1 up, -1 down, None removes the rating (FR-26)."""
        if Database.pool:
            if rating is None:
                await Database.pool.execute("DELETE FROM message_feedback WHERE session_id = $1 AND turn_id = $2", session_id, turn_id)
            else:
                await Database.pool.execute(
                    """INSERT INTO message_feedback (session_id, turn_id, rating) VALUES ($1, $2, $3)
                       ON CONFLICT (session_id, turn_id) DO UPDATE SET rating = EXCLUDED.rating, updated_at = NOW()""",
                    session_id, turn_id, rating)
            return
        if rating is None:
            cls._feedback.pop((session_id, turn_id), None)
        else:
            cls._feedback[(session_id, turn_id)] = rating

    # ------------------------------------------------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------------------------------------------------

    @classmethod
    async def get(cls, session_id: str) -> Optional[Dict[str, Any]]:
        """One conversation with its messages, each with the visitor rating (1, -1 or None)."""
        if Database.pool:
            row = await Database.pool.fetchrow("SELECT * FROM conversations WHERE session_id = $1", session_id)
            if not row:
                return None
            messages = await Database.pool.fetch(
                """SELECT m.id, m.turn_id, m.role, m.content, m.language, m.channel, m.tools, m.latency_ms, m.created_at,
                          f.rating
                   FROM conversation_messages m
                   LEFT JOIN message_feedback f ON f.session_id = m.session_id AND f.turn_id = m.turn_id
                   WHERE m.session_id = $1 ORDER BY m.id""", session_id)
            conv = dict(row)
            conv["cost_usd"] = float(conv["cost_usd"])
            conv["messages"] = [dict(m) for m in messages]
            return conv
        conv = cls._memory.get(session_id)
        if not conv:
            return None
        messages = [{**m, "rating": cls._feedback.get((session_id, m["turn_id"])) if m["turn_id"] else None}
                    for m in conv["messages"]]
        return {**conv, "messages": messages}

    @classmethod
    async def message(cls, message_id: int) -> Optional[Dict[str, Any]]:
        if Database.pool:
            row = await Database.pool.fetchrow("SELECT * FROM conversation_messages WHERE id = $1", message_id)
            return dict(row) if row else None
        for conv in cls._memory.values():
            for m in conv["messages"]:
                if m["id"] == message_id:
                    return {**m, "session_id": conv["session_id"]}
        return None

    @classmethod
    async def summaries(cls, start: datetime, end: datetime, search: Optional[str] = None) -> List[Dict[str, Any]]:
        """One row per conversation started in [start, end), newest activity first, for analytics and the review list.
        `search` matches any message text (case-insensitive) or the exact session id."""
        needle = (search or "").strip().lower() or None
        if Database.pool:
            rows = await Database.pool.fetch(
                """SELECT c.session_id, c.started_at, c.updated_at, c.language, c.channels, c.user_turns, c.failed_turns,
                          c.tools, c.handoff_ticket, c.lead_saved, c.cost_usd,
                          (SELECT m.content FROM conversation_messages m WHERE m.session_id = c.session_id AND m.role = 'user'
                             ORDER BY m.id LIMIT 1) AS first_question,
                          (SELECT m.tools FROM conversation_messages m WHERE m.session_id = c.session_id AND m.role = 'assistant'
                             ORDER BY m.id DESC LIMIT 1) AS last_tools,
                          (SELECT m.role FROM conversation_messages m WHERE m.session_id = c.session_id
                             ORDER BY m.id DESC LIMIT 1) AS last_role,
                          (SELECT COUNT(*) FROM message_feedback f WHERE f.session_id = c.session_id AND f.rating = 1) AS thumbs_up,
                          (SELECT COUNT(*) FROM message_feedback f WHERE f.session_id = c.session_id AND f.rating = -1) AS thumbs_down,
                          (SELECT COUNT(*) FROM message_reviews r JOIN conversation_messages m ON m.id = r.message_id
                             WHERE m.session_id = c.session_id AND r.flagged) AS flagged,
                          (SELECT COUNT(*) FROM message_reviews r JOIN conversation_messages m ON m.id = r.message_id
                             WHERE m.session_id = c.session_id AND r.verdict = 'bad') AS reviewed_bad,
                          (SELECT COUNT(*) FROM message_reviews r JOIN conversation_messages m ON m.id = r.message_id
                             WHERE m.session_id = c.session_id AND r.verdict = 'good') AS reviewed_good
                   FROM conversations c
                   WHERE c.started_at >= $1 AND c.started_at < $2
                     AND ($3::text IS NULL OR c.session_id = $3 OR EXISTS (
                         SELECT 1 FROM conversation_messages m WHERE m.session_id = c.session_id
                         AND position($3 in lower(m.content)) > 0))
                   ORDER BY c.updated_at DESC LIMIT $4""", start, end, needle, _MAX_SUMMARIES)
            out = []
            for r in rows:
                item = dict(r)
                item["cost_usd"] = float(item["cost_usd"])
                item["last_tools"] = list(item["last_tools"] or [])
                out.append(item)
            return out

        from app.admin.reviews import ReviewStore  # local import: reviews build on this store
        out = []
        for conv in reversed(cls._memory.values()):
            if not (start <= conv["started_at"] < end):
                continue
            msgs = conv["messages"]
            if needle and conv["session_id"] != needle and not any(needle in m["content"].lower() for m in msgs):
                continue
            assistant = [m for m in msgs if m["role"] == "assistant"]
            ratings = [cls._feedback.get((conv["session_id"], m["turn_id"])) for m in assistant if m["turn_id"]]
            reviews = [ReviewStore.memory_review(m["id"]) for m in assistant]
            reviews = [r for r in reviews if r]
            out.append({
                **{k: conv[k] for k in ("session_id", "started_at", "updated_at", "language", "channels", "user_turns",
                                        "failed_turns", "tools", "handoff_ticket", "lead_saved", "cost_usd")},
                "first_question": next((m["content"] for m in msgs if m["role"] == "user"), None),
                "last_tools": list(assistant[-1]["tools"]) if assistant else [],
                "last_role": msgs[-1]["role"] if msgs else None,
                "thumbs_up": ratings.count(1), "thumbs_down": ratings.count(-1),
                "flagged": sum(1 for r in reviews if r["flagged"]),
                "reviewed_bad": sum(1 for r in reviews if r["verdict"] == "bad"),
                "reviewed_good": sum(1 for r in reviews if r["verdict"] == "good"),
            })
        out.sort(key=lambda s: s["updated_at"], reverse=True)
        return out[:_MAX_SUMMARIES]

    @classmethod
    def memory_messages(cls) -> List[Dict[str, Any]]:
        """All messages in memory with their session id (memory mode only; used by the review queue)."""
        return [{**m, "session_id": c["session_id"]} for c in cls._memory.values() for m in c["messages"]]

    @classmethod
    def memory_rating(cls, session_id: str, turn_id: Optional[str]) -> Optional[int]:
        return cls._feedback.get((session_id, turn_id)) if turn_id else None

    @classmethod
    def reset_memory(cls) -> None:
        cls._memory.clear()
        cls._feedback.clear()
        cls._message_ids = itertools.count(1)
