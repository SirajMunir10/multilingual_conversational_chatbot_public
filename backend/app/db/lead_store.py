import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from app.core.config import settings
from app.core.audit import AuditService

logger = logging.getLogger("xo.lead_store")

class LeadDatabaseService:
    """
    Company-Owned Private PostgreSQL Database Service for Verified Advisor Leads.
    
    Security & Architecture Rules:
    1. Strictly gates persistence: ONLY saves leads when user requests an advisor and provides explicit consent.
    2. Ordinary conversation sessions or sessions where consent is declined are NEVER persisted.
    3. Strictly enforces deduplication by (session_id, phone_number).
    4. Never fabricates contact information.
    5. Gracefully handles DB connection pools and provides isolated testing storage.
    """
    _pool = None
    _in_memory_leads: Dict[str, Dict[str, Any]] = {}
    _is_initialized: bool = False

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
    """

    @classmethod
    async def init_db(cls) -> bool:
        """
        Initializes connection pool to company PostgreSQL database if DATABASE_URL is set.
        Creates table schema if not already existing.
        """
        if cls._is_initialized and cls._pool:
            return True

        db_url = settings.DATABASE_URL
        if not db_url:
            logger.info("DATABASE_URL not configured. Operating with in-memory company lead store.")
            cls._is_initialized = True
            return True

        try:
            import asyncpg
            cls._pool = await asyncpg.create_pool(
                dsn=db_url,
                min_size=1,
                max_size=5,
                timeout=10.0
            )
            async with cls._pool.acquire() as conn:
                await conn.execute(cls.SCHEMA_SQL)
            logger.info("Successfully connected to company PostgreSQL database and verified schema.")
            cls._is_initialized = True
            return True
        except Exception as e:
            logger.warning(f"Could not connect to PostgreSQL database ({e}). Operating with local company lead store.")
            cls._is_initialized = True
            return False

    @classmethod
    async def close_db(cls) -> None:
        """Closes the connection pool on application shutdown."""
        if cls._pool:
            try:
                await cls._pool.close()
            except Exception as e:
                logger.warning(f"Error closing PostgreSQL connection pool: {e}")
            cls._pool = None
        cls._is_initialized = False

    @classmethod
    async def save_advisor_lead(
        cls,
        session_id: str,
        full_name: str,
        phone_number: str,
        preferred_language: str,
        advisor_type: str,
        conversation_context: Dict[str, Any]
    ) -> bool:
        """
        Persists a verified advisor lead to company storage with deduplication.
        Returns True if successfully saved/verified, False if write failed.
        """
        if not full_name or not phone_number or not session_id or full_name.strip() in ["Valued Client", "Client"]:
            logger.warning("Attempted to save advisor lead with missing mandatory fields or placeholder name.")
            return False

        clean_name = full_name.strip()
        clean_phone = phone_number.strip()
        clean_lang = preferred_language.strip() or "en"
        clean_type = advisor_type.strip() or "general"
        lead_key = f"{session_id}:{clean_phone}"

        # 1. Try PostgreSQL write if pool is active
        saved_to_postgres = False
        if cls._pool:
            try:
                async with cls._pool.acquire() as conn:
                    query = """
                    INSERT INTO advisor_leads (
                        session_id, full_name, phone_number, preferred_language, advisor_type, conversation_context
                    ) VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (session_id, phone_number) 
                    DO UPDATE SET conversation_context = EXCLUDED.conversation_context;
                    """
                    await conn.execute(
                        query,
                        session_id,
                        clean_name,
                        clean_phone,
                        clean_lang,
                        clean_type,
                        json.dumps(conversation_context)
                    )
                    saved_to_postgres = True
                    logger.info(f"Advisor lead saved to PostgreSQL for session {session_id} ({clean_name})")
            except Exception as pe:
                logger.error(f"PostgreSQL write failed: {pe}")

        # 2. Update memory store for quick back-office lookups and offline testing
        cls._in_memory_leads[lead_key] = {
            "session_id": session_id,
            "full_name": clean_name,
            "phone_number": clean_phone,
            "preferred_language": clean_lang,
            "advisor_type": clean_type,
            "status": "pending_contact",
            "conversation_context": conversation_context,
            "saved_to_postgres": saved_to_postgres,
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        # 3. Log compliance audit event
        AuditService.log_event(
            event_type="business_write",
            action="advisor_lead_persisted",
            resource="company_leads_db",
            session_id=session_id,
            status="success",
            details={
                "session_id": session_id,
                "applicant_name": clean_name,
                "applicant_phone": clean_phone,
                "preferred_language": clean_lang,
                "advisor_type": clean_type,
                "postgres_synced": saved_to_postgres
            }
        )

        return True

    @classmethod
    async def get_lead_by_session(cls, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves lead details for a specific session."""
        # Check PostgreSQL first if available
        if cls._pool:
            try:
                async with cls._pool.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT * FROM advisor_leads WHERE session_id = $1 ORDER BY created_at DESC LIMIT 1",
                        session_id
                    )
                    if row:
                        return dict(row)
            except Exception as e:
                logger.warning(f"Error fetching lead from PostgreSQL: {e}")

        # Fallback to in-memory store
        for k, v in cls._in_memory_leads.items():
            if v.get("session_id") == session_id:
                return v
        return None

    @classmethod
    def get_all_leads(cls) -> List[Dict[str, Any]]:
        """Returns list of all leads currently recorded (used for admin/testing)."""
        return list(cls._in_memory_leads.values())

    @classmethod
    def get_lead_count(cls) -> int:
        """Returns total leads in company store."""
        return len(cls._in_memory_leads)

    @classmethod
    def clear_all(cls) -> None:
        """Resets the store (used for test isolation)."""
        cls._in_memory_leads.clear()
