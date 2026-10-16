#!/usr/bin/env python3
"""Prints per-conversation usage and cost from the backend admin API (PRD §7 cost control).

Usage:
  XO_BACKEND_URL=https://<backend> XO_ADMIN_KEY=<key> python scripts/get_cost_report.py [session_id]
"""
import json
import os
import sys
import urllib.error
import urllib.request


def fetch(path: str):
    base = os.environ.get("XO_BACKEND_URL", "http://localhost:8000").rstrip("/")
    key = os.environ.get("XO_ADMIN_KEY", "")
    req = urllib.request.Request(f"{base}{path}", headers={"X-Admin-Key": key, "User-Agent": "XO-Usage-Reporter/2.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        sys.exit(f"Request failed (HTTP {e.code}). Check XO_ADMIN_KEY and XO_BACKEND_URL.")
    except Exception as e:
        sys.exit(f"Could not reach the backend: {e}")


def show(s: dict) -> None:
    if "error" in s:
        print(s["error"])
        return
    c = s["cost_usd"]
    print("=" * 60)
    print(f"Session {s['session_id']}  ({s['start_time']} → {s['end_time']})")
    print(f"User turns: {s['user_turns']}   LLM calls: {s['llm_calls']}")
    t = s["llm_tokens"]
    print(f"LLM tokens: {t['prompt']:,} in ({t['cached']:,} cached) / {t['completion']:,} out   ${c['llm']:.5f}")
    print(f"STT audio: {s['stt_seconds']} s   ${c['stt']:.5f}")
    print(f"TTS characters: {s['tts_characters']:,}   ${c['tts']:.5f}")
    print(f"Embeddings: ${c['embedding']:.5f}")
    print(f"TOTAL: ${c['total']:.5f}")


def main() -> None:
    if len(sys.argv) > 1:
        show(fetch(f"/api/admin/usage/{sys.argv[1]}"))
        return
    sessions = fetch("/api/admin/usage?limit=20")
    if not sessions:
        print("No conversations recorded since the backend started.")
    for s in sessions:
        show(s)


if __name__ == "__main__":
    main()
