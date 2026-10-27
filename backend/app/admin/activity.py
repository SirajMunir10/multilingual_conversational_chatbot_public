"""Admin activity trail (PRD §7 auditability): who changed what, and when, in the admin module."""
import json
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional

from app.db.database import Database

_MAX_MEMORY = 5000


class ActivityLog:
    _memory: Deque[Dict[str, Any]] = deque(maxlen=_MAX_MEMORY)

    @classmethod
    async def record(cls, actor: Dict[str, Any], action: str, resource: str, details: Optional[Dict[str, Any]] = None) -> None:
        """`details` must never contain passwords or tokens; callers pass only what changed."""
        entry = {"created_at": datetime.now(timezone.utc), "actor_email": actor["email"], "actor_role": actor["role"],
                 "action": action, "resource": resource, "details": details or {}}
        if Database.pool:
            await Database.pool.execute(
                "INSERT INTO admin_activity (actor_email, actor_role, action, resource, details) VALUES ($1, $2, $3, $4, $5)",
                entry["actor_email"], entry["actor_role"], action, resource, json.dumps(entry["details"], default=str))
            return
        cls._memory.appendleft(entry)

    @classmethod
    async def recent(cls, limit: int = 100, actor_email: Optional[str] = None, action: Optional[str] = None) -> List[Dict[str, Any]]:
        limit = max(1, min(limit, 500))
        if Database.pool:
            rows = await Database.pool.fetch(
                """SELECT created_at, actor_email, actor_role, action, resource, details FROM admin_activity
                   WHERE ($2::text IS NULL OR actor_email = $2) AND ($3::text IS NULL OR action = $3)
                   ORDER BY created_at DESC LIMIT $1""", limit, actor_email, action)
            items = [dict(r) for r in rows]
            for item in items:
                if isinstance(item["details"], str):
                    item["details"] = json.loads(item["details"])
        else:
            items = [dict(e) for e in cls._memory
                     if (not actor_email or e["actor_email"] == actor_email) and (not action or e["action"] == action)][:limit]
        for item in items:
            item["created_at"] = item["created_at"].isoformat()
        return items

    @classmethod
    def reset_memory(cls) -> None:
        cls._memory.clear()
