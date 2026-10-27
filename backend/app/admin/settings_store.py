"""Small admin settings (e.g. the monthly AI budget). PostgreSQL when configured, process memory otherwise."""
import json
from datetime import datetime, timezone
from typing import Any, Dict

from app.db.database import Database


class SettingsStore:
    _memory: Dict[str, Dict[str, Any]] = {}

    @classmethod
    async def get(cls, key: str, default: Any = None) -> Any:
        if Database.pool:
            value = await Database.pool.fetchval("SELECT value FROM admin_settings WHERE key = $1", key)
            return json.loads(value) if isinstance(value, str) else (value if value is not None else default)
        entry = cls._memory.get(key)
        return entry["value"] if entry else default

    @classmethod
    async def set(cls, key: str, value: Any, updated_by: str) -> None:
        if Database.pool:
            await Database.pool.execute(
                """INSERT INTO admin_settings (key, value, updated_by) VALUES ($1, $2, $3)
                   ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_by = EXCLUDED.updated_by, updated_at = NOW()""",
                key, json.dumps(value), updated_by)
            return
        cls._memory[key] = {"value": value, "updated_by": updated_by, "updated_at": datetime.now(timezone.utc)}

    @classmethod
    def reset_memory(cls) -> None:
        cls._memory.clear()
