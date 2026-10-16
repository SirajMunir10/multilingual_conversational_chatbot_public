import logging
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.core.config import load_config

logger = logging.getLogger("xo.usage")

_MAX_SESSIONS = 2000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class UsageTracker:
    """Per-session token, audio and character usage for cost monitoring (PRD §7 Cost control, FR-31).
    Kept in bounded memory; prices come from data/config/pricing.json."""

    _sessions: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()

    @classmethod
    def _session(cls, session_id: Optional[str]) -> Dict[str, Any]:
        sid = session_id or "unknown"
        if sid not in cls._sessions:
            cls._sessions[sid] = {"session_id": sid, "start_time": _now(), "end_time": _now(), "user_turns": 0,
                                  "llm": [], "stt": [], "tts": [], "embedding": []}
            while len(cls._sessions) > _MAX_SESSIONS:
                cls._sessions.popitem(last=False)
        cls._sessions.move_to_end(sid)
        entry = cls._sessions[sid]
        entry["end_time"] = _now()
        return entry

    @classmethod
    def record_turn(cls, session_id: Optional[str]) -> None:
        cls._session(session_id)["user_turns"] += 1

    @classmethod
    def record_llm(cls, session_id: Optional[str], model: str, prompt_tokens: int, cached_tokens: int, completion_tokens: int) -> None:
        cls._session(session_id)["llm"].append({"model": model, "prompt": int(prompt_tokens or 0), "cached": int(cached_tokens or 0),
                                                 "completion": int(completion_tokens or 0)})

    @classmethod
    def record_stt(cls, session_id: Optional[str], model: str, audio_seconds: float) -> None:
        cls._session(session_id)["stt"].append({"model": model, "seconds": round(float(audio_seconds), 2)})

    @classmethod
    def record_tts(cls, session_id: Optional[str], model: str, characters: int) -> None:
        cls._session(session_id)["tts"].append({"model": model, "chars": int(characters)})

    @classmethod
    def record_embedding(cls, session_id: Optional[str], model: str, tokens: int) -> None:
        cls._session(session_id)["embedding"].append({"model": model, "tokens": int(tokens or 0)})

    @classmethod
    def summary(cls, session_id: str) -> Dict[str, Any]:
        raw = cls._sessions.get(session_id)
        if not raw:
            return {"error": "Session not found."}
        pricing = load_config("pricing")

        def price(group: str, model: str, key: str) -> float:
            return float(pricing.get(group, {}).get(model, {}).get(key, 0.0))

        llm_cost = sum(
            (e["prompt"] - e["cached"]) / 1e6 * price("llm", e["model"], "input_per_1m")
            + e["cached"] / 1e6 * price("llm", e["model"], "cached_input_per_1m")
            + e["completion"] / 1e6 * price("llm", e["model"], "output_per_1m")
            for e in raw["llm"])
        stt_cost = sum(e["seconds"] / 60 * price("stt", e["model"], "per_minute") for e in raw["stt"])
        tts_cost = sum(e["chars"] / 1000 * price("tts", e["model"], "per_1k_chars") for e in raw["tts"])
        emb_cost = sum(e["tokens"] / 1e6 * price("embedding", e["model"], "per_1m_tokens") for e in raw["embedding"])
        return {
            "session_id": session_id,
            "start_time": raw["start_time"],
            "end_time": raw["end_time"],
            "user_turns": raw["user_turns"],
            "llm_calls": len(raw["llm"]),
            "llm_tokens": {"prompt": sum(e["prompt"] for e in raw["llm"]), "cached": sum(e["cached"] for e in raw["llm"]),
                           "completion": sum(e["completion"] for e in raw["llm"])},
            "stt_seconds": round(sum(e["seconds"] for e in raw["stt"]), 1),
            "tts_characters": sum(e["chars"] for e in raw["tts"]),
            "cost_usd": {"llm": round(llm_cost, 6), "stt": round(stt_cost, 6), "tts": round(tts_cost, 6),
                         "embedding": round(emb_cost, 6), "total": round(llm_cost + stt_cost + tts_cost + emb_cost, 6)},
        }

    @classmethod
    def recent_sessions(cls, limit: int = 50) -> list:
        return [cls.summary(sid) for sid in list(cls._sessions.keys())[-limit:]]
