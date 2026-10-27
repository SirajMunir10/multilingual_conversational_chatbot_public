"""Admin accounts (PRD FR-30): PostgreSQL when configured, bounded process memory otherwise.

Passwords are stored only as salted PBKDF2-SHA256 hashes. `token_version` changes on sign-out, password change,
role change and deactivation, which invalidates every session issued before."""
import hashlib
import hmac
import itertools
import re
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.admin.permissions import ROLES
from app.db.database import Database

MIN_PASSWORD_LENGTH = 12
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# PBKDF2-SHA256 at the OWASP-recommended work factor; available in every Python build (scrypt is not).
PBKDF2_ITERATIONS = 600_000
_PUBLIC = ("id", "email", "name", "role", "active", "created_at", "last_login_at")


class AdminUserError(ValueError):
    """A request that breaks an account rule; the message is a stable code the UI can show."""


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations, salt, digest = stored.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations))
        return hmac.compare_digest(candidate.hex(), digest)
    except (ValueError, TypeError):
        return False


# Used to spend the same time on unknown emails as on wrong passwords, so sign-in does not reveal which emails exist.
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def normalise_email(email: str) -> str:
    value = (email or "").strip().lower()
    if not _EMAIL.match(value) or len(value) > 255:
        raise AdminUserError("invalid_email")
    return value


def check_password_rules(password: str) -> None:
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise AdminUserError("password_too_short")


def _clean_name(name: str) -> str:
    value = " ".join((name or "").split())[:100]
    if not value:
        raise AdminUserError("invalid_name")
    return value


def _check_role(role: str) -> str:
    if role not in ROLES:
        raise AdminUserError("invalid_role")
    return role


def public(user: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not user:
        return None
    out = {k: user.get(k) for k in _PUBLIC}
    for key in ("created_at", "last_login_at"):
        if isinstance(out[key], datetime):
            out[key] = out[key].isoformat()
    return out


class AdminUserStore:
    _memory: Dict[int, Dict[str, Any]] = {}
    _sessions: Dict[str, Dict[str, Any]] = {}
    _ids = itertools.count(1)

    @classmethod
    def reset_memory(cls) -> None:
        cls._memory.clear()
        cls._sessions.clear()
        cls._ids = itertools.count(1)

    @classmethod
    async def count_active_admins(cls, exclude_id: Optional[int] = None) -> int:
        if Database.pool:
            return await Database.pool.fetchval(
                "SELECT COUNT(*) FROM admin_users WHERE role = 'admin' AND active AND id <> $1", exclude_id or 0)
        return sum(1 for u in cls._memory.values() if u["role"] == "admin" and u["active"] and u["id"] != exclude_id)

    @classmethod
    async def count(cls) -> int:
        if Database.pool:
            return await Database.pool.fetchval("SELECT COUNT(*) FROM admin_users")
        return len(cls._memory)

    @classmethod
    async def create(cls, email: str, name: str, role: str, password: str) -> Dict[str, Any]:
        email, name, role = normalise_email(email), _clean_name(name), _check_role(role)
        check_password_rules(password)
        password_hash = hash_password(password)
        if Database.pool:
            row = await Database.pool.fetchrow(
                """INSERT INTO admin_users (email, name, role, password_hash) VALUES ($1, $2, $3, $4)
                   ON CONFLICT (email) DO NOTHING RETURNING *""", email, name, role, password_hash)
            if not row:
                raise AdminUserError("email_taken")
            return dict(row)
        if any(u["email"] == email for u in cls._memory.values()):
            raise AdminUserError("email_taken")
        user = {"id": next(cls._ids), "email": email, "name": name, "role": role, "password_hash": password_hash,
                "active": True, "token_version": 0, "created_at": datetime.now(timezone.utc), "last_login_at": None}
        cls._memory[user["id"]] = user
        return dict(user)

    @classmethod
    async def get(cls, user_id: int) -> Optional[Dict[str, Any]]:
        if Database.pool:
            row = await Database.pool.fetchrow("SELECT * FROM admin_users WHERE id = $1", user_id)
            return dict(row) if row else None
        user = cls._memory.get(user_id)
        return dict(user) if user else None

    @classmethod
    async def get_by_email(cls, email: str) -> Optional[Dict[str, Any]]:
        email = (email or "").strip().lower()
        if Database.pool:
            row = await Database.pool.fetchrow("SELECT * FROM admin_users WHERE email = $1", email)
            return dict(row) if row else None
        user = next((u for u in cls._memory.values() if u["email"] == email), None)
        return dict(user) if user else None

    @classmethod
    async def list(cls) -> List[Dict[str, Any]]:
        if Database.pool:
            rows = await Database.pool.fetch("SELECT * FROM admin_users ORDER BY active DESC, name")
            return [dict(r) for r in rows]
        return sorted((dict(u) for u in cls._memory.values()), key=lambda u: (not u["active"], u["name"]))

    @classmethod
    async def update(cls, user_id: int, *, name: Optional[str] = None, role: Optional[str] = None,
                     active: Optional[bool] = None) -> Dict[str, Any]:
        user = await cls.get(user_id)
        if not user:
            raise AdminUserError("not_found")
        new_name = _clean_name(name) if name is not None else user["name"]
        new_role = _check_role(role) if role is not None else user["role"]
        new_active = bool(active) if active is not None else user["active"]
        losing_admin = user["role"] == "admin" and user["active"] and (new_role != "admin" or not new_active)
        if losing_admin and await cls.count_active_admins(exclude_id=user_id) == 0:
            raise AdminUserError("last_admin")
        # A role change or deactivation signs the person out everywhere.
        bump = 1 if (new_role != user["role"] or new_active != user["active"]) else 0
        if Database.pool:
            row = await Database.pool.fetchrow(
                """UPDATE admin_users SET name = $2, role = $3, active = $4, token_version = token_version + $5
                   WHERE id = $1 RETURNING *""", user_id, new_name, new_role, new_active, bump)
            return dict(row)
        stored = cls._memory[user_id]
        stored.update(name=new_name, role=new_role, active=new_active, token_version=stored["token_version"] + bump)
        return dict(stored)

    @classmethod
    async def set_password(cls, user_id: int, password: str) -> None:
        check_password_rules(password)
        password_hash = hash_password(password)
        if Database.pool:
            await Database.pool.execute(
                "UPDATE admin_users SET password_hash = $2, token_version = token_version + 1 WHERE id = $1", user_id, password_hash)
            return
        if user_id in cls._memory:
            cls._memory[user_id].update(password_hash=password_hash, token_version=cls._memory[user_id]["token_version"] + 1)

    # ---- Sessions: one per sign-in; `token_version` still ends all of a person's sessions at once ----

    @classmethod
    async def create_session(cls, user_id: int, ttl_sec: int) -> str:
        session_id = secrets.token_urlsafe(24)
        now = datetime.now(timezone.utc)
        expires = datetime.fromtimestamp(now.timestamp() + ttl_sec, timezone.utc)
        if Database.pool:
            async with Database.pool.acquire() as conn:
                await conn.execute("DELETE FROM admin_sessions WHERE user_id = $1 AND (expires_at < NOW() OR revoked_at IS NOT NULL)", user_id)
                await conn.execute("INSERT INTO admin_sessions (id, user_id, expires_at) VALUES ($1, $2, $3)", session_id, user_id, expires)
            return session_id
        for sid in [s for s, v in cls._sessions.items() if v["expires_at"] < now or v["revoked"]]:
            cls._sessions.pop(sid, None)
        cls._sessions[session_id] = {"user_id": user_id, "expires_at": expires, "revoked": False}
        return session_id

    @classmethod
    async def session_active(cls, session_id: str, user_id: int) -> bool:
        if not session_id:
            return False
        if Database.pool:
            return bool(await Database.pool.fetchval(
                "SELECT 1 FROM admin_sessions WHERE id = $1 AND user_id = $2 AND revoked_at IS NULL AND expires_at > NOW()",
                session_id, user_id))
        s = cls._sessions.get(session_id)
        return bool(s and s["user_id"] == user_id and not s["revoked"] and s["expires_at"] > datetime.now(timezone.utc))

    @classmethod
    async def revoke_session(cls, session_id: str) -> None:
        if Database.pool:
            await Database.pool.execute("UPDATE admin_sessions SET revoked_at = NOW() WHERE id = $1", session_id)
        elif session_id in cls._sessions:
            cls._sessions[session_id]["revoked"] = True

    @classmethod
    async def record_login(cls, user_id: int) -> None:
        now = datetime.now(timezone.utc)
        if Database.pool:
            await Database.pool.execute("UPDATE admin_users SET last_login_at = $2 WHERE id = $1", user_id, now)
        elif user_id in cls._memory:
            cls._memory[user_id]["last_login_at"] = now
