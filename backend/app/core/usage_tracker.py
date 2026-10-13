import os
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

logger = logging.getLogger("xo.usage")

# Directory for persisted session usage records
USAGE_LOGS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "usage_logs")

# Verified & Reference Pricing Definitions
PRICING = {
    "stt": {
        "reference_per_min": 0.017,   # User reference rate (gpt-live-transcribe doc)
        "whisper_per_min": 0.006      # OpenAI official whisper-1 rate
    },
    "llm": {
        "input_per_1m": 0.25,         # $0.25 per 1,000,000 non-cached tokens
        "cached_input_per_1m": 0.025, # $0.025 per 1,000,000 cached tokens
        "output_per_1m": 2.00         # $2.00 per 1,000,000 output tokens
    },
    "tts": {
        "per_1k_chars": 0.04          # User reference rate ($0.04 per 1,000 chars)
    },
    "embedding": {
        "per_1m_tokens": 0.02         # OpenAI text-embedding-3-small ($0.02 per 1,000,000 tokens)
    }
}

class UsageTracker:
    """
    Centralized, zero-overhead API usage tracking engine for real conversation cost analysis.
    Captures exact provider metrics (audio duration, prompt/completion tokens, cached tokens,
    synthesized characters, and ElevenLabs character-cost credits) bound to session_id.
    """
    _sessions: Dict[str, Dict[str, Any]] = {}
    _latest_session_id: Optional[str] = None

    @classmethod
    def _ensure_session(cls, session_id: Optional[str]) -> str:
        sid = session_id or "default_session"
        if sid not in cls._sessions:
            cls._sessions[sid] = {
                "session_id": sid,
                "start_time": datetime.now(timezone.utc).isoformat(),
                "end_time": datetime.now(timezone.utc).isoformat(),
                "user_turns": 0,
                "assistant_turns": 0,
                "stt_events": [],
                "llm_events": [],
                "tts_events": [],
                "embedding_events": []
            }
        cls._latest_session_id = sid
        return sid

    @classmethod
    def _save_session_file(cls, sid: str) -> None:
        try:
            os.makedirs(USAGE_LOGS_DIR, exist_ok=True)
            filepath = os.path.join(USAGE_LOGS_DIR, f"session_{sid}.json")
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(cls._sessions[sid], f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Could not persist usage log for {sid}: {e}")

    @classmethod
    def record_turn(cls, session_id: Optional[str], role: str = "user") -> None:
        sid = cls._ensure_session(session_id)
        if role == "user":
            cls._sessions[sid]["user_turns"] += 1
        elif role == "assistant":
            cls._sessions[sid]["assistant_turns"] += 1
        cls._sessions[sid]["end_time"] = datetime.now(timezone.utc).isoformat()
        cls._save_session_file(sid)

    @classmethod
    def record_stt(
        cls,
        session_id: Optional[str],
        model: str,
        audio_duration_sec: float,
        audio_bytes: int,
        status: str = "success"
    ) -> None:
        sid = cls._ensure_session(session_id)
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model": model,
            "audio_duration_sec": round(float(audio_duration_sec), 2),
            "audio_bytes": int(audio_bytes),
            "status": status
        }
        cls._sessions[sid]["stt_events"].append(event)
        cls._sessions[sid]["end_time"] = event["timestamp"]
        cls._save_session_file(sid)
        logger.info(f"Recorded STT usage for [{sid}]: {audio_duration_sec:.2f}s ({model})")

    @classmethod
    def record_llm(
        cls,
        session_id: Optional[str],
        model: str,
        prompt_tokens: int,
        cached_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        tool_call_step: str = "primary"
    ) -> None:
        sid = cls._ensure_session(session_id)
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model": model,
            "prompt_tokens": int(prompt_tokens),
            "cached_tokens": int(cached_tokens),
            "completion_tokens": int(completion_tokens),
            "total_tokens": int(total_tokens),
            "tool_call_step": tool_call_step
        }
        cls._sessions[sid]["llm_events"].append(event)
        cls._sessions[sid]["end_time"] = event["timestamp"]
        cls._save_session_file(sid)
        logger.info(
            f"Recorded LLM usage for [{sid}]: {prompt_tokens} in ({cached_tokens} cached), "
            f"{completion_tokens} out (step={tool_call_step}, model={model})"
        )

    @classmethod
    def record_tts(
        cls,
        session_id: Optional[str],
        model: str,
        voice_id: str,
        character_count: int,
        provider_character_cost: Optional[int] = None,
        audio_bytes: Optional[int] = None,
        status: str = "success"
    ) -> None:
        sid = cls._ensure_session(session_id)
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model": model,
            "voice_id": voice_id,
            "character_count": int(character_count),
            "provider_character_cost": int(provider_character_cost) if provider_character_cost is not None else None,
            "audio_bytes": int(audio_bytes) if audio_bytes is not None else None,
            "status": status
        }
        cls._sessions[sid]["tts_events"].append(event)
        cls._sessions[sid]["end_time"] = event["timestamp"]
        cls._save_session_file(sid)
        logger.info(
            f"Recorded TTS usage for [{sid}]: {character_count} chars "
            f"(credits={provider_character_cost}, model={model})"
        )

    @classmethod
    def record_embedding(
        cls,
        session_id: Optional[str],
        model: str,
        prompt_tokens: int
    ) -> None:
        sid = cls._ensure_session(session_id)
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model": model,
            "prompt_tokens": int(prompt_tokens)
        }
        cls._sessions[sid]["embedding_events"].append(event)
        cls._sessions[sid]["end_time"] = event["timestamp"]
        cls._save_session_file(sid)
        logger.info(f"Recorded Embedding usage for [{sid}]: {prompt_tokens} tokens ({model})")

    @classmethod
    def get_latest_session_id(cls) -> Optional[str]:
        if cls._latest_session_id:
            return cls._latest_session_id
        # Scan usage_logs dir for the most recently modified file
        if os.path.exists(USAGE_LOGS_DIR):
            files = [
                os.path.join(USAGE_LOGS_DIR, f)
                for f in os.listdir(USAGE_LOGS_DIR)
                if f.startswith("session_") and f.endswith(".json")
            ]
            if files:
                latest_file = max(files, key=os.path.getmtime)
                filename = os.path.basename(latest_file)
                return filename.replace("session_", "").replace(".json", "")
        return None

    @classmethod
    def get_session_summary(cls, session_id: Optional[str] = None) -> Dict[str, Any]:
        sid = session_id or cls.get_latest_session_id()
        if not sid:
            return {"error": "No session usage records found."}

        # Load from in-memory or persisted file
        raw = cls._sessions.get(sid)
        if not raw:
            filepath = os.path.join(USAGE_LOGS_DIR, f"session_{sid}.json")
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                    cls._sessions[sid] = raw

        if not raw:
            return {"error": f"Session '{sid}' not found."}

        # Calculate durations
        try:
            start_dt = datetime.fromisoformat(raw["start_time"])
            end_dt = datetime.fromisoformat(raw["end_time"])
            elapsed_sec = max(0.0, (end_dt - start_dt).total_seconds())
        except Exception:
            elapsed_sec = 0.0

        # Aggregate STT
        stt_events = raw.get("stt_events", [])
        stt_req_count = len(stt_events)
        total_audio_sec = sum(e.get("audio_duration_sec", 0.0) for e in stt_events)
        total_audio_min = total_audio_sec / 60.0
        stt_cost_ref = round(total_audio_min * PRICING["stt"]["reference_per_min"], 6)
        stt_cost_whisper = round(total_audio_min * PRICING["stt"]["whisper_per_min"], 6)

        # Aggregate LLM
        llm_events = raw.get("llm_events", [])
        llm_req_count = len(llm_events)
        total_prompt_tokens = sum(e.get("prompt_tokens", 0) for e in llm_events)
        total_cached_tokens = sum(e.get("cached_tokens", 0) for e in llm_events)
        total_completion_tokens = sum(e.get("completion_tokens", 0) for e in llm_events)
        non_cached_tokens = max(0, total_prompt_tokens - total_cached_tokens)

        llm_input_cost = round((non_cached_tokens / 1_000_000) * PRICING["llm"]["input_per_1m"], 6)
        llm_cached_cost = round((total_cached_tokens / 1_000_000) * PRICING["llm"]["cached_input_per_1m"], 6)
        llm_output_cost = round((total_completion_tokens / 1_000_000) * PRICING["llm"]["output_per_1m"], 6)
        total_llm_cost = round(llm_input_cost + llm_cached_cost + llm_output_cost, 6)

        # Aggregate TTS
        tts_events = raw.get("tts_events", [])
        tts_req_count = len(tts_events)
        total_chars = sum(e.get("character_count", 0) for e in tts_events)
        provider_credits = sum(
            e.get("provider_character_cost", 0) for e in tts_events
            if e.get("provider_character_cost") is not None
        )
        total_tts_cost = round((total_chars / 1_000) * PRICING["tts"]["per_1k_chars"], 6)

        # Aggregate Embeddings
        emb_events = raw.get("embedding_events", [])
        emb_req_count = len(emb_events)
        total_emb_tokens = sum(e.get("prompt_tokens", 0) for e in emb_events)
        total_emb_cost = round((total_emb_tokens / 1_000_000) * PRICING["embedding"]["per_1m_tokens"], 6)

        # Grand Totals
        total_cost = round(stt_cost_ref + total_llm_cost + total_tts_cost + total_emb_cost, 6)
        elapsed_min = max(elapsed_sec / 60.0, 0.01) if elapsed_sec > 0 else 1.0
        audio_min = max(total_audio_min, 0.01) if total_audio_min > 0 else 1.0
        avg_cost_per_elapsed_min = round(total_cost / elapsed_min, 6)
        avg_cost_per_audio_min = round(total_cost / audio_min, 6) if total_audio_sec > 0 else 0.0

        return {
            "session_id": sid,
            "start_time": raw["start_time"],
            "end_time": raw["end_time"],
            "elapsed_seconds": round(elapsed_sec, 1),
            "elapsed_formatted": f"{int(elapsed_sec // 60)}m {int(elapsed_sec % 60)}s",
            "user_turns": raw.get("user_turns", 0),
            "assistant_turns": raw.get("assistant_turns", 0),
            "stt": {
                "requests": stt_req_count,
                "audio_seconds": round(total_audio_sec, 2),
                "audio_minutes": round(total_audio_min, 4),
                "cost_usd_reference": stt_cost_ref,
                "cost_usd_whisper_std": stt_cost_whisper,
                "rate_applied": f"${PRICING['stt']['reference_per_min']}/min"
            },
            "llm": {
                "requests": llm_req_count,
                "prompt_tokens_total": total_prompt_tokens,
                "cached_tokens": total_cached_tokens,
                "non_cached_tokens": non_cached_tokens,
                "completion_tokens": total_completion_tokens,
                "total_tokens": total_prompt_tokens + total_completion_tokens,
                "input_cost_usd": llm_input_cost,
                "cached_cost_usd": llm_cached_cost,
                "output_cost_usd": llm_output_cost,
                "total_cost_usd": total_llm_cost
            },
            "tts": {
                "requests": tts_req_count,
                "character_count": total_chars,
                "provider_character_cost": provider_credits,
                "cost_usd": total_tts_cost,
                "rate_applied": f"${PRICING['tts']['per_1k_chars']}/1k chars"
            },
            "embeddings": {
                "requests": emb_req_count,
                "prompt_tokens": total_emb_tokens,
                "cost_usd": total_emb_cost
            },
            "cost_summary": {
                "total_cost_usd": total_cost,
                "stt_cost_usd": stt_cost_ref,
                "llm_cost_usd": total_llm_cost,
                "tts_cost_usd": total_tts_cost,
                "embeddings_cost_usd": total_emb_cost,
                "cost_per_elapsed_min_usd": avg_cost_per_elapsed_min,
                "cost_per_audio_min_usd": avg_cost_per_audio_min,
                "projection_100": round(total_cost * 100, 2),
                "projection_1000": round(total_cost * 1_000, 2),
                "projection_10000": round(total_cost * 10_000, 2)
            }
        }
