"""Advisor lead persistence (PRD FR-5, FR-16). Leads are stored only after explicit consent."""
import json
import logging
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.audit import AuditService
from app.core.config import settings

logger = logging.getLogger("xo.lead_store")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS advisor_leads (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(128) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    phone_number VARCHAR(64) NOT NULL,
    preferred_language VARCHAR(32) NOT NULL,
    advisor_type VARCHAR(64) NOT NULL,
    conversation_context JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_session_lead UNIQUE (session_id, phone_number)
);
CREATE INDEX IF NOT EXISTS idx_advisor_leads_created_at ON advisor_leads(created_at DESC);
-- Added with the review-card flow; safe to run on existing tables.
ALTER TABLE advisor_leads ADD COLUMN IF NOT EXISTS ticket_id VARCHAR(32);
ALTER TABLE advisor_leads ADD COLUMN IF NOT EXISTS consent_confirmed_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_advisor_leads_ticket ON advisor_leads(ticket_id);
"""


class LeadDatabaseService:
    _pool = None
    _memory: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()

    @classmethod
    async def init_db(cls) -> bool:
        if not settings.DATABASE_URL:
            logger.warning("DATABASE_URL not set: advisor leads are kept in process memory only (lost on restart).")
            return False
        try:
            import asyncpg
            cls._pool = await asyncpg.create_pool(dsn=settings.DATABASE_URL, min_size=1, max_size=5, timeout=10.0)
            async with cls._pool.acquire() as conn:
                await conn.execute(SCHEMA_SQL)
            logger.info("Connected to PostgreSQL lead store.")
            return True
        except Exception as exc:
            logger.error("PostgreSQL lead store unavailable: %s", exc)
            cls._pool = None
            return False

    @classmethod
    async def close_db(cls) -> None:
        if cls._pool:
            await cls._pool.close()
            cls._pool = None

    @classmethod
    def storage_mode(cls) -> str:
        return "postgres" if cls._pool else "memory"

    @classmethod
    async def save_advisor_lead(cls, session_id: str, full_name: str, phone_number: str, preferred_language: str,
                                advisor_type: str, conversation_context: Dict[str, Any], ticket_id: Optional[str] = None) -> Dict[str, Any]:
        """Returns {'saved': bool, 'storage': 'postgres'|'memory'|None}. 'saved' is True only after the write succeeded.
        Called only when the user confirmed the callback card, which is the consent time recorded."""
        now = datetime.now(timezone.utc)
        record = {
            "session_id": session_id, "ticket_id": ticket_id, "full_name": full_name.strip(), "phone_number": phone_number.strip(),
            "preferred_language": (preferred_language or "en").strip(), "advisor_type": advisor_type,
            "conversation_context": conversation_context, "consent_confirmed_at": now.isoformat(), "created_at": now.isoformat(),
        }
        outcome: Dict[str, Any] = {"saved": False, "storage": None}
        if cls._pool:
            try:
                async with cls._pool.acquire() as conn:
                    await conn.execute(
                        """INSERT INTO advisor_leads (session_id, ticket_id, full_name, phone_number, preferred_language, advisor_type,
                                                      conversation_context, consent_confirmed_at)
                           VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                           ON CONFLICT (session_id, phone_number) DO UPDATE SET
                               ticket_id = EXCLUDED.ticket_id, full_name = EXCLUDED.full_name,
                               preferred_language = EXCLUDED.preferred_language, advisor_type = EXCLUDED.advisor_type,
                               conversation_context = EXCLUDED.conversation_context, consent_confirmed_at = EXCLUDED.consent_confirmed_at""",
                        session_id, ticket_id, record["full_name"], record["phone_number"], record["preferred_language"], advisor_type,
                        json.dumps(conversation_context, default=str), now)
                outcome = {"saved": True, "storage": "postgres"}
            except Exception as exc:
                logger.error("Lead write to PostgreSQL failed: %s", exc)
        elif not settings.DATABASE_URL:
            cls._memory[f"{session_id}:{record['phone_number']}"] = record
            while len(cls._memory) > 5000:
                cls._memory.popitem(last=False)
            outcome = {"saved": True, "storage": "memory"}

        AuditService.log_event("business_write", "advisor_lead_persisted", "company_leads_db", session_id=session_id,
                               status="success" if outcome["saved"] else "failed",
                               details={"full_name": record["full_name"], "phone": record["phone_number"],
                                        "advisor_type": advisor_type, "ticket_id": ticket_id, "storage": outcome["storage"]})
        return outcome

    @classmethod
    async def list_leads(cls, limit: int = 100) -> List[Dict[str, Any]]:
        if cls._pool:
            async with cls._pool.acquire() as conn:
                rows = await conn.fetch("SELECT ticket_id, session_id, full_name, phone_number, preferred_language, advisor_type, "
                                        "consent_confirmed_at, created_at "
                                        "FROM advisor_leads ORDER BY created_at DESC LIMIT $1", limit)
                return [dict(r) for r in rows]
        return [{k: v for k, v in r.items() if k != "conversation_context"} for r in list(cls._memory.values())[-limit:]]

    @classmethod
    def clear_memory(cls) -> None:
        cls._memory.clear()
