"""Drafts, published versions and rollback for admin-editable configuration (PRD FR-25, FR-27, FR-29).

Publishing adds a numbered version (never edits one) and applies it to XO at once. Every instance loads the latest
versions at start-up and checks for newer ones every 30 seconds, so several backend instances stay in step. A version
that fails validation is ignored and XO keeps using the built-in file. PostgreSQL when configured, memory otherwise."""
import asyncio
import copy
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.admin.config_items import ITEMS
from app.core import config
from app.db.database import Database

logger = logging.getLogger("xo.admin.config")

REFRESH_SEC = 30


class ConfigError(ValueError):
    """A request that breaks a publishing rule. `code` is stable for the UI; `errors` lists validation problems."""

    def __init__(self, code: str, errors: Optional[List[str]] = None):
        super().__init__(code)
        self.code = code
        self.errors = errors or []


def _iso(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def item(name: str):
    spec = ITEMS.get(name)
    if not spec:
        raise ConfigError("not_found")
    return spec


class ConfigStore:
    _versions: Dict[str, List[Dict[str, Any]]] = {}
    _drafts: Dict[str, Dict[str, Any]] = {}
    _applied: Dict[str, int] = {}

    @classmethod
    def reset_memory(cls) -> None:
        cls._versions.clear()
        cls._drafts.clear()
        for name in list(cls._applied):
            config.set_published(name, None)
        cls._applied.clear()

    # ---- what XO uses ----

    @classmethod
    def _apply(cls, name: str, version: int, data: Any) -> None:
        errors = ITEMS[name].validate(data)
        if errors:
            logger.error("Version %s of %s is invalid and was not applied: %s", version, name, "; ".join(errors[:3]))
            config.set_published(name, None)
        else:
            config.set_published(name, data)
        cls._applied[name] = version

    @classmethod
    async def load_published(cls) -> None:
        """Applies the latest published version of every item (start-up and periodic refresh)."""
        if Database.pool:
            rows = await Database.pool.fetch(
                """SELECT DISTINCT ON (item) item, version, data FROM config_versions WHERE item = ANY($1::text[])
                   ORDER BY item, version DESC""", list(ITEMS))
            for row in rows:
                if cls._applied.get(row["item"]) != row["version"]:
                    cls._apply(row["item"], row["version"], _json(row["data"]))
            return
        for name, versions in cls._versions.items():
            if versions and cls._applied.get(name) != versions[-1]["version"]:
                cls._apply(name, versions[-1]["version"], versions[-1]["data"])

    @classmethod
    async def refresh_forever(cls) -> None:
        while True:
            await asyncio.sleep(REFRESH_SEC)
            try:
                await cls.load_published()
            except Exception as exc:  # a database hiccup must never stop the loop
                logger.warning("Could not refresh published configuration: %s", exc)

    # ---- reads ----

    @classmethod
    async def published(cls, name: str) -> Dict[str, Any]:
        """The latest published version, or version 0 = the built-in file."""
        spec = item(name)
        if Database.pool:
            row = await Database.pool.fetchrow(
                "SELECT version, data, note, published_by, published_at FROM config_versions WHERE item = $1 ORDER BY version DESC LIMIT 1",
                name)
            if row:
                return {**{k: _iso(v) for k, v in dict(row).items()}, "data": _json(row["data"])}
        elif cls._versions.get(name):
            return {k: _iso(v) for k, v in cls._versions[name][-1].items()}
        return {"version": 0, "data": spec.seed(), "note": "Built-in", "published_by": None, "published_at": None}

    @classmethod
    async def draft(cls, name: str) -> Optional[Dict[str, Any]]:
        item(name)
        if Database.pool:
            row = await Database.pool.fetchrow(
                "SELECT data, base_version, updated_by, updated_at FROM config_drafts WHERE item = $1", name)
            return {**{k: _iso(v) for k, v in dict(row).items()}, "data": _json(row["data"])} if row else None
        found = cls._drafts.get(name)
        return {k: _iso(v) for k, v in found.items()} if found else None

    @classmethod
    async def versions(cls, name: str) -> List[Dict[str, Any]]:
        item(name)
        if Database.pool:
            rows = await Database.pool.fetch(
                "SELECT version, note, published_by, published_at FROM config_versions WHERE item = $1 ORDER BY version DESC", name)
            history = [{k: _iso(v) for k, v in dict(r).items()} for r in rows]
        else:
            history = [{k: _iso(v) for k, v in entry.items() if k != "data"} for entry in reversed(cls._versions.get(name, []))]
        return history + [{"version": 0, "note": "Built-in", "published_by": None, "published_at": None}]

    @classmethod
    async def version(cls, name: str, number: int) -> Dict[str, Any]:
        spec = item(name)
        if number == 0:
            return {"version": 0, "data": spec.seed(), "note": "Built-in", "published_by": None, "published_at": None}
        if Database.pool:
            row = await Database.pool.fetchrow(
                "SELECT version, data, note, published_by, published_at FROM config_versions WHERE item = $1 AND version = $2",
                name, number)
            if row:
                return {**{k: _iso(v) for k, v in dict(row).items()}, "data": _json(row["data"])}
        else:
            for entry in cls._versions.get(name, []):
                if entry["version"] == number:
                    return {k: _iso(v) for k, v in entry.items()}
        raise ConfigError("version_not_found")

    # ---- writes ----

    @classmethod
    async def save_draft(cls, name: str, data: Any, base_version: int, actor: Dict[str, Any]) -> Dict[str, Any]:
        """Keeps the working copy (even with problems); publishing is what requires it to be valid."""
        item(name)
        if len(json.dumps(data, default=str)) > 400_000:
            raise ConfigError("too_large")
        now = datetime.now(timezone.utc)
        if Database.pool:
            await Database.pool.execute(
                """INSERT INTO config_drafts (item, data, base_version, updated_by) VALUES ($1, $2::jsonb, $3, $4)
                   ON CONFLICT (item) DO UPDATE SET data = EXCLUDED.data, base_version = EXCLUDED.base_version,
                   updated_by = EXCLUDED.updated_by, updated_at = NOW()""",
                name, json.dumps(data), base_version, actor["email"])
        else:
            cls._drafts[name] = {"data": copy.deepcopy(data), "base_version": base_version, "updated_by": actor["email"],
                                 "updated_at": now}
        return {"data": data, "base_version": base_version, "updated_by": actor["email"], "updated_at": now.isoformat()}

    @classmethod
    async def discard_draft(cls, name: str) -> None:
        item(name)
        if Database.pool:
            await Database.pool.execute("DELETE FROM config_drafts WHERE item = $1", name)
        else:
            cls._drafts.pop(name, None)

    @classmethod
    async def _add_version(cls, name: str, data: Any, note: str, actor: Dict[str, Any], expected_current: int) -> int:
        errors = ITEMS[name].validate(data)
        if errors:
            raise ConfigError("invalid", errors)
        note = (note or "").strip()[:500]
        if Database.pool:
            async with Database.pool.acquire() as conn:
                async with conn.transaction():
                    # Serialises publishers of the same item, so two people cannot both publish "version N + 1".
                    await conn.execute("SELECT pg_advisory_xact_lock(hashtext('config:' || $1))", name)
                    current = await conn.fetchval("SELECT COALESCE(MAX(version), 0) FROM config_versions WHERE item = $1", name)
                    if current != expected_current:
                        raise ConfigError("stale_draft")
                    version = current + 1
                    await conn.execute(
                        "INSERT INTO config_versions (item, version, data, note, published_by) VALUES ($1, $2, $3::jsonb, $4, $5)",
                        name, version, json.dumps(data), note, actor["email"])
                    await conn.execute("DELETE FROM config_drafts WHERE item = $1", name)
        else:
            versions = cls._versions.setdefault(name, [])
            current = versions[-1]["version"] if versions else 0
            if current != expected_current:
                raise ConfigError("stale_draft")
            version = current + 1
            versions.append({"version": version, "data": copy.deepcopy(data), "note": note, "published_by": actor["email"],
                             "published_at": datetime.now(timezone.utc)})
            cls._drafts.pop(name, None)
        cls._apply(name, version, data)
        return version

    @classmethod
    async def publish(cls, name: str, note: str, actor: Dict[str, Any]) -> int:
        """Publishes the draft. Refused if it is invalid, or if someone published since the draft was started."""
        draft = await cls.draft(name)
        if not draft:
            raise ConfigError("no_draft")
        return await cls._add_version(name, draft["data"], note, actor, draft["base_version"])

    @classmethod
    async def rollback(cls, name: str, number: int, note: str, actor: Dict[str, Any]) -> int:
        """Publishes an earlier version again, as a new version (history is never rewritten)."""
        old = await cls.version(name, number)
        current = (await cls.published(name))["version"]
        return await cls._add_version(name, old["data"], note or f"Rolled back to version {number}", actor, current)
