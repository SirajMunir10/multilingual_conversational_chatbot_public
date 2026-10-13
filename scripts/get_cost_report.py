#!/usr/bin/env python3
import sys
import json
import urllib.request
import urllib.error

DEFAULT_BACKEND = "https://xoto-backend.onrender.com"

def fetch_summary(endpoint_url: str):
    req = urllib.request.Request(endpoint_url, headers={"User-Agent": "XO-Usage-Reporter/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read().decode("utf-8")
            return json.loads(data)
    except urllib.error.HTTPError as e:
        print(f"Error fetching report (HTTP {e.code}): {e.reason}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Network error connecting to backend: {e}", file=sys.stderr)
        return None

def print_report(s: dict):
    if not s or "error" in s:
        print("\n[!] No active or recent conversation usage data found.")
        print("    Please conduct a conversation in the UI first, then run this command again.\n")
        return

    stt = s.get("stt", {})
    llm = s.get("llm", {})
    tts = s.get("tts", {})
    emb = s.get("embeddings", {})
    cost = s.get("cost_summary", {})

    print("=" * 70)
    print("       XO — REAL CONVERSATION API USAGE & ESTIMATED COST REPORT")
    print("=" * 70)
    print(f" Session ID:           {s.get('session_id')}")
    print(f" Start Time (UTC):     {s.get('start_time')}")
    print(f" End Time (UTC):       {s.get('end_time')}")
    print(f" Elapsed Duration:     {s.get('elapsed_formatted')} ({s.get('elapsed_seconds')}s)")
    print(f" Conversation Turns:   {s.get('user_turns')} User / {s.get('assistant_turns')} Assistant")
    print("-" * 70)

    print(" 1. SPEECH-TO-TEXT (STT) — OpenAI gpt-live-transcribe (whisper-1)")
    print(f"    - Transcription Requests:  {stt.get('requests', 0)}")
    print(f"    - Total Audio Duration:    {stt.get('audio_seconds', 0):.2f} sec ({stt.get('audio_minutes', 0):.3f} min)")
    print(f"    - Cost (Reference Rate):   ${stt.get('cost_usd_reference', 0):.6f} (applied at {stt.get('rate_applied', '$0.017/min')})")
    print(f"    - Cost (Whisper Standard): ${stt.get('cost_usd_whisper_std', 0):.6f} (at $0.006/min)")
    print("-" * 70)

    print(" 2. LARGE LANGUAGE MODEL (LLM) — OpenAI gpt-5-mini")
    print(f"    - Completion Calls:        {llm.get('requests', 0)}")
    print(f"    - Total Prompt Tokens:     {llm.get('prompt_tokens_total', 0):,}")
    print(f"      • Cached Input Tokens:   {llm.get('cached_tokens', 0):,} (${llm.get('cached_cost_usd', 0):.6f} @ $0.025/1M)")
    print(f"      • Non-Cached Tokens:     {llm.get('non_cached_tokens', 0):,} (${llm.get('input_cost_usd', 0):.6f} @ $0.25/1M)")
    print(f"    - Completion Tokens:       {llm.get('completion_tokens', 0):,} (${llm.get('output_cost_usd', 0):.6f} @ $2.00/1M)")
    print(f"    - Total LLM Tokens:        {llm.get('total_tokens', 0):,}")
    print(f"    - Total LLM Cost:          ${llm.get('total_cost_usd', 0):.6f}")
    print("-" * 70)

    print(" 3. TEXT-TO-SPEECH (TTS) — ElevenLabs Flash v2.5")
    print(f"    - Synthesis Requests:      {tts.get('requests', 0)}")
    print(f"    - Synthesized Characters:  {tts.get('character_count', 0):,}")
    print(f"    - Provider Credits Billed: {tts.get('provider_character_cost', 0):,} characters (character-cost header)")
    print(f"    - Total TTS Cost:          ${tts.get('cost_usd', 0):.6f} (applied at {tts.get('rate_applied', '$0.04/1k chars')})")
    print("-" * 70)

    if emb.get('requests', 0) > 0:
        print(" 4. VECTOR EMBEDDINGS (RAG) — OpenAI text-embedding-3-small")
        print(f"    - Embedding Requests:      {emb.get('requests', 0)}")
        print(f"    - Embedding Tokens:        {emb.get('prompt_tokens', 0):,}")
        print(f"    - Total Embedding Cost:    ${emb.get('cost_usd', 0):.6f} (@ $0.02/1M)")
        print("-" * 70)

    print(" 5. COST SUMMARY & PROJECTIONS")
    print(f"    - Total Session Cost:      ${cost.get('total_cost_usd', 0):.6f}")
    print(f"      • STT Component:         ${cost.get('stt_cost_usd', 0):.6f}")
    print(f"      • LLM Component:         ${cost.get('llm_cost_usd', 0):.6f}")
    print(f"      • TTS Component:         ${cost.get('tts_cost_usd', 0):.6f}")
    if emb.get('requests', 0) > 0:
        print(f"      • RAG Component:         ${cost.get('embeddings_cost_usd', 0):.6f}")
    print(f"    - Avg Cost / Elapsed Min:  ${cost.get('cost_per_elapsed_min_usd', 0):.6f}/min")
    print(f"    - Avg Cost / Audio Min:    ${cost.get('cost_per_audio_min_usd', 0):.6f}/min of user speech")
    print("    - Scale Projections (at similar 2-minute conversation profile):")
    print(f"      • 100 conversations:     ${cost.get('projection_100', 0):.2f}")
    print(f"      • 1,000 conversations:   ${cost.get('projection_1000', 0):.2f}")
    print(f"      • 10,000 conversations:  ${cost.get('projection_10000', 0):.2f}")
    print("=" * 70)

def main():
    session_id = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else None
    base_url = "http://localhost:8000" if "--local" in sys.argv else DEFAULT_BACKEND

    if session_id:
        url = f"{base_url}/api/admin/usage/{session_id}"
    else:
        url = f"{base_url}/api/admin/usage/latest"

    print(f"Fetching conversation report from: {url} ...")
    summary = fetch_summary(url)
    print_report(summary)

if __name__ == "__main__":
    main()
