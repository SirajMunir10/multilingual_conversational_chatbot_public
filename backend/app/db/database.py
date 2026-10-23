"""Shared PostgreSQL connection pool and schema (PRD §5.6 admin data, FR-5/FR-16 leads).

One pool serves every store. Without DATABASE_URL (local development, tests) the stores fall back to
bounded process memory, so the app still runs; on Render the database keeps admin data across restarts."""
import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger("xo.db")

# Idempotent: every statement is safe to run on each start against an existing database.
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS admin_users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    role VARCHAR(32) NOT NULL,
    password_hash TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    token_version INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMPTZ
);

-- One row per sign-in, so signing out ends only that browser's session.
CREATE TABLE IF NOT EXISTS admin_sessions (
    id VARCHAR(64) PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_admin_sessions_user ON admin_sessions(user_id);

CREATE TABLE IF NOT EXISTS admin_activity (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actor_email VARCHAR(255) NOT NULL,
    actor_role VARCHAR(32) NOT NULL,
    action VARCHAR(64) NOT NULL,
    resource VARCHAR(255) NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_admin_activity_created ON admin_activity(created_at DESC);

CREATE TABLE IF NOT EXISTS conversations (
    session_id VARCHAR(128) PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    language VARCHAR(16) NOT NULL DEFAULT 'en',
    channels TEXT[] NOT NULL DEFAULT '{}',
    user_turns INTEGER NOT NULL DEFAULT 0,
    failed_turns INTEGER NOT NULL DEFAULT 0,
    tools TEXT[] NOT NULL DEFAULT '{}',
    handoff_ticket VARCHAR(32),
    lead_saved BOOLEAN NOT NULL DEFAULT FALSE,
    cost_usd NUMERIC(12, 6) NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_conversations_updated ON conversations(updated_at DESC);

CREATE TABLE IF NOT EXISTS conversation_messages (
    id BIGSERIAL PRIMARY KEY,
    session_id VARCHAR(128) NOT NULL REFERENCES conversations(session_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    role VARCHAR(16) NOT NULL,
    content TEXT NOT NULL,
    language VARCHAR(16) NOT NULL DEFAULT 'en',
    channel VARCHAR(8) NOT NULL DEFAULT 'text',
    tools TEXT[] NOT NULL DEFAULT '{}',
    latency_ms INTEGER
);
CREATE INDEX IF NOT EXISTS idx_conversation_messages_session ON conversation_messages(session_id, id);
-- Each assistant reply has an id the widget uses for thumbs up/down (FR-26).
ALTER TABLE conversation_messages ADD COLUMN IF NOT EXISTS turn_id VARCHAR(32);
CREATE INDEX IF NOT EXISTS idx_conversation_messages_turn ON conversation_messages(session_id, turn_id);

-- Visitor thumbs up (1) / down (-1) on a reply; one rating per reply, the latest wins.
CREATE TABLE IF NOT EXISTS message_feedback (
    session_id VARCHAR(128) NOT NULL,
    turn_id VARCHAR(32) NOT NULL,
    rating SMALLINT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (session_id, turn_id)
);

-- Admin review of a reply (FR-26): good/bad, flagged for review, note.
CREATE TABLE IF NOT EXISTS message_reviews (
    message_id BIGINT PRIMARY KEY REFERENCES conversation_messages(id) ON DELETE CASCADE,
    verdict VARCHAR(8),
    flagged BOOLEAN NOT NULL DEFAULT FALSE,
    note TEXT NOT NULL DEFAULT '',
    reviewed_by VARCHAR(255) NOT NULL,
    reviewed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Corrected answers waiting to be published to the knowledge base (FR-26 → FR-24).
CREATE TABLE IF NOT EXISTS kb_drafts (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by VARCHAR(255) NOT NULL,
    source_message_id BIGINT REFERENCES conversation_messages(id) ON DELETE SET NULL,
    language VARCHAR(16) NOT NULL DEFAULT 'en',
    title VARCHAR(255) NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'draft'
);

-- Knowledge base (PRD FR-24): every change to an article is a new row; the latest row per article is live.
CREATE TABLE IF NOT EXISTS kb_versions (
    article_id VARCHAR(120) NOT NULL,
    version INTEGER NOT NULL,
    data JSONB NOT NULL,
    embedding JSONB,
    action VARCHAR(16) NOT NULL DEFAULT 'published',
    note TEXT NOT NULL DEFAULT '',
    published_by VARCHAR(255) NOT NULL,
    published_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (article_id, version)
);

-- Web pages kept in the knowledge base and refreshed on a schedule (PRD FR-18, FR-24).
CREATE TABLE IF NOT EXISTS kb_sources (
    id SERIAL PRIMARY KEY,
    url TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL DEFAULT '',
    added_by VARCHAR(255) NOT NULL,
    added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_fetched_at TIMESTAMPTZ,
    last_status VARCHAR(16) NOT NULL DEFAULT 'new',
    last_error TEXT NOT NULL DEFAULT '',
    content_hash VARCHAR(64) NOT NULL DEFAULT '',
    article_ids JSONB NOT NULL DEFAULT '[]'
);

-- Published versions of admin-editable configuration (PRD FR-25, FR-27, FR-29): never edited, only added to.
CREATE TABLE IF NOT EXISTS config_versions (
    item VARCHAR(64) NOT NULL,
    version INTEGER NOT NULL,
    data JSONB NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    published_by VARCHAR(255) NOT NULL,
    published_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (item, version)
);

-- One working draft per item, based on a published version.
CREATE TABLE IF NOT EXISTS config_drafts (
    item VARCHAR(64) PRIMARY KEY,
    data JSONB NOT NULL,
    base_version INTEGER NOT NULL,
    updated_by VARCHAR(255) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Small admin settings such as the monthly AI budget (PRD §7 cost control).
CREATE TABLE IF NOT EXISTS admin_settings (
    key VARCHAR(64) PRIMARY KEY,
    value JSONB NOT NULL,
    updated_by VARCHAR(255) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


class Database:
    """Holds the shared asyncpg pool. `pool` is None when no database is configured or reachable."""

    pool = None

    @classmethod
    async def init(cls) -> bool:
        if not settings.DATABASE_URL:
            logger.warning("DATABASE_URL not set: admin data, conversations and leads are kept in process memory only.")
            return False
        try:
            import asyncpg
            cls.pool = await asyncpg.create_pool(dsn=settings.DATABASE_URL, min_size=1, max_size=5, timeout=10.0)
            async with cls.pool.acquire() as conn:
                # One instance migrates at a time when several start together.
                async with conn.transaction():
                    await conn.execute("SELECT pg_advisory_xact_lock(4242001)")
                    await conn.execute(SCHEMA_SQL)
            logger.info("Connected to PostgreSQL.")
            return True
        except Exception as exc:
            logger.error("PostgreSQL unavailable, using process memory: %s", exc)
            await cls.close()
            return False

    @classmethod
    async def close(cls) -> None:
        if cls.pool:
            await cls.pool.close()
        cls.pool = None

    @classmethod
    def enabled(cls) -> bool:
        return cls.pool is not None

    @classmethod
    def mode(cls) -> Optional[str]:
        return "postgres" if cls.pool else "memory"
