"""Conversation orchestrator (PRD §6): one engine for text and voice (PRD §4, FR-1).

The LLM understands intent, slots, language and consent through tool arguments; every number,
listing and fact comes from a tool. Replies are streamed token by token (PRD §7 latency)."""
import difflib
import json
import logging
import secrets
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

from app.core.audit import AuditService
from app.core.config import load_config, settings
from app.core.security import redact_payment_data
from app.core.usage_tracker import UsageTracker
from app.db.conversation_store import ConversationStore
from app.llm.client import LLMService
from app.orchestrator import tools
from app.orchestrator.session_store import SessionContext, SessionStore
from app.services import escalation, prompt_profile

logger = logging.getLogger("xo.orchestrator")

def _squash(text: str) -> str:
    return " ".join(text.lower().split())


def _similar(a: str, b: str, threshold: float = 0.8) -> bool:
    return bool(a and b) and difflib.SequenceMatcher(None, a, b).ratio() >= threshold


class RepeatGuard:
    """Suppresses a model quirk where the whole answer is emitted twice (A\\nA).
    Text after a line break that is still a prefix of the opening paragraph is held back; if it turns out
    not to be a repeat, it is released."""

    def __init__(self) -> None:
        self.text = ""      # already shown to the user
        self.held = ""      # received but not yet shown (possible repeat)
        self.suppressing = False
        self.diverged = False

    def _emit(self, chunk: str) -> str:
        self.text += chunk
        return chunk

    def feed(self, token: str) -> str:
        if self.suppressing:
            return ""
        self.held += token
        if self.diverged:
            out, self.held = self.held, ""
            return self._emit(out)
        full = self.text + self.held
        head, sep, tail = full.partition("\n")
        if not sep or len(_squash(head)) < 20:
            out, self.held = self.held, ""
            return self._emit(out)
        # Everything up to and including the first line break is always shown.
        boundary = len(head) + 1 - len(self.text)
        shown = self._emit(self.held[:boundary]) if boundary > 0 else ""
        self.held = self.held[boundary:] if boundary > 0 else self.held
        tail_n, head_n = _squash(tail), _squash(head)
        looks_repeated = not tail_n or head_n.startswith(tail_n) or (len(tail_n) >= 8 and _similar(tail_n, head_n[: len(tail_n) + 4]))
        if looks_repeated:
            if tail_n and len(tail_n) >= min(len(head_n), 40):
                self.suppressing = True  # confirmed repeat: drop the duplicate
                self.held = ""
            return shown
        self.diverged = True
        out, self.held = self.held, ""
        return shown + self._emit(out)

    def final(self) -> str:
        return dedupe(self.text if self.suppressing else self.text + self.held)


def dedupe(text: str) -> str:
    """Removes consecutive duplicate paragraphs/lines (normalised)."""
    lines, out = text.split("\n"), []
    for line in lines:
        if out and line.strip() and len(line.strip()) >= 20 and _similar(_squash(line), _squash(out[-1]), 0.85):
            continue
        out.append(line)
    result = "\n".join(out).strip()
    half = len(result) // 2
    first, second = result[:half].strip(), result[half:].strip()
    if len(first) >= 20 and _similar(_squash(first), _squash(second), 0.85):
        return first
    return result


VOICE_NOTE = ("This turn is a VOICE conversation: reply in at most two short spoken sentences, no lists, no markdown, "
              "no listing numbers like #1. Write amounts with digits (e.g. AED 1,500,000); the voice engine reads them aloud.")


def localized_message(language: str, key: str) -> str:
    locales = load_config("locales")
    loc = locales["locales"].get(language) or locales["locales"][locales["default"]]
    return loc["messages"][key]


class ConversationOrchestrator:

    @classmethod
    def _messages(cls, session: SessionContext, user_text: str, channel: str,
                  notes: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = [{"role": "system", "content": LLMService.system_prompt(session.language, session.language_locked)}]
        if channel == "voice":
            messages.append({"role": "system", "content": VOICE_NOTE})
            if session.language_locked:
                messages.append({"role": "system", "content": "The user's speech was transcribed automatically and may appear in a related script; "
                                                              "keep replying in the session language unless they explicitly ask to switch."})
        if session.user_id:
            messages.append({"role": "system", "content": "The user is signed in; account tools will return their own data."})
        messages.extend(session.history)
        for note in notes or []:
            messages.append({"role": "system", "content": note})
        messages.append({"role": "user", "content": user_text})
        return messages

    @classmethod
    async def _call_llm(cls, session: SessionContext, messages: List[Dict[str, Any]], allow_tools: bool):
        kwargs: Dict[str, Any] = {
            "model": settings.LLM_MODEL,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
            "max_completion_tokens": settings.LLM_MAX_OUTPUT_TOKENS,
        }
        # "none" must be sent explicitly: if it is left out, gpt-6-luna uses its default reasoning level,
        # which OpenAI rejects together with function tools (HTTP 400 on every turn).
        if settings.LLM_REASONING_EFFORT:
            kwargs["reasoning_effort"] = settings.LLM_REASONING_EFFORT
        if allow_tools:
            kwargs["tools"] = tools.tool_schemas()
            kwargs["tool_choice"] = "auto"
        return await LLMService.client().chat.completions.create(**kwargs)

    @classmethod
    async def stream_turn(cls, message: str, session_id: Optional[str] = None, user_id: Optional[str] = None,
                          selected_language: Optional[str] = None, ui_language: Optional[str] = None,
                          channel: str = "text") -> AsyncGenerator[Dict[str, Any], None]:
        """Yields events: session, status, token, final, error."""
        started = time.monotonic()
        locales = load_config("locales")["locales"]
        session = SessionStore.get_or_create(session_id, user_id=user_id,
                                             language=ui_language if ui_language in locales else None)
        if selected_language in locales:
            session.language = selected_language
            session.language_locked = True
        yield {"type": "session", "session_id": session.session_id, "language": session.language}

        text = redact_payment_data((message or "").strip())[: settings.MAX_MESSAGE_CHARS]
        if not text:
            yield {"type": "error", "message": localized_message(session.language, "error_generic")}
            return
        UsageTracker.record_turn(session.session_id)
        SessionStore.add_transcript(session, "user", text)
        session.current_user_text = text

        # Banned topics (FR-25) are refused in code, before the model runs.
        topic = prompt_profile.banned_topic(text)
        if topic:
            reply = prompt_profile.banned_reply(topic, session.language)
            SessionStore.append_history(session, [{"role": "user", "content": text}, {"role": "assistant", "content": reply}])
            SessionStore.add_transcript(session, "assistant", reply)
            turn_id = cls._save_turn(session, channel, text, reply, ["guardrail"], started)
            yield {"type": "token", "text": reply}
            yield {"type": "final", "session_id": session.session_id, "language": session.language, "text": reply,
                   "tools": ["guardrail"], "turn_id": turn_id}
            return

        # Escalation rules (FR-29) that match before this turn become notes to the model; each is offered once.
        notes = escalation.turn_notes(session, text)
        offered = [n["id"] for n in notes if n["id"] != "frustration"]
        session.escalations_offered = session.escalations_offered + offered

        messages = cls._messages(session, text, channel, [n["note"] for n in notes])
        turn_messages: List[Dict[str, Any]] = [{"role": "user", "content": text}]
        ui: Dict[str, Any] = {}
        tools_used: List[str] = [f"escalation:{rule_id}" for rule_id in offered]
        final_text = ""
        first_token_at: Optional[float] = None

        try:
            for step in range(settings.LLM_MAX_TOOL_STEPS + 1):
                allow_tools = step < settings.LLM_MAX_TOOL_STEPS
                stream = await cls._call_llm(session, messages, allow_tools)
                content_parts: List[str] = []
                guard = RepeatGuard()
                calls: Dict[int, Dict[str, str]] = {}
                async for chunk in stream:
                    if getattr(chunk, "usage", None):
                        u = chunk.usage
                        cached = getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", 0) or 0
                        UsageTracker.record_llm(session.session_id, settings.LLM_MODEL, u.prompt_tokens, cached, u.completion_tokens)
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if delta.content:
                        if first_token_at is None:
                            first_token_at = time.monotonic()
                        content_parts.append(delta.content)
                        visible = guard.feed(delta.content)
                        if visible:
                            yield {"type": "token", "text": visible}
                    for tc in delta.tool_calls or []:
                        slot = calls.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                        if tc.id:
                            slot["id"] = tc.id
                        if tc.function and tc.function.name:
                            slot["name"] = tc.function.name
                            yield {"type": "status", "tool": tc.function.name}
                        if tc.function and tc.function.arguments:
                            slot["arguments"] += tc.function.arguments

                content = "".join(content_parts)
                if not calls:
                    final_text = guard.final()
                    break

                assistant_msg = {"role": "assistant", "content": content or None, "tool_calls": [
                    {"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"] or "{}"}}
                    for c in calls.values()]}
                messages.append(assistant_msg)
                turn_messages.append(assistant_msg)
                # Calculations run before searches in the same step; a search without a budget
                # then uses the affordability result just computed (FR-15).
                ordered = sorted(calls.values(), key=lambda c: 0 if c["name"].startswith("calc_") else 1)
                affordable_price: Optional[float] = None
                for c in ordered:
                    arguments = c["arguments"]
                    if c["name"] == "search_properties" and affordable_price:
                        try:
                            parsed = json.loads(arguments or "{}")
                            if not parsed.get("budget_max"):
                                parsed["budget_max"] = affordable_price
                                arguments = json.dumps(parsed)
                        except ValueError:
                            pass
                    result, payload = await tools.execute(session, c["name"], arguments)
                    if c["name"] == "calc_affordability" and result.get("max_property_price_aed"):
                        affordable_price = result["max_property_price_aed"]
                    tools_used.append(c["name"])
                    ui.update(payload)
                    if c["name"] == "set_language" and result.get("status") == "switched":
                        # Lets voice clients speak the rest of this reply in the new language.
                        yield {"type": "language", "language": session.language}
                    tool_msg = {"role": "tool", "tool_call_id": c["id"], "content": tools.compact(result)}
                    messages.append(tool_msg)
                    turn_messages.append(tool_msg)
                if content:
                    # Text emitted alongside tool calls is a preamble; keep it but start a new paragraph for the answer.
                    yield {"type": "token", "text": "\n\n"}
        except Exception as exc:
            logger.exception("LLM turn failed: %s", exc)
            cls._save_turn(session, channel, text, None, tools_used, started)
            yield {"type": "error", "message": localized_message(session.language, "error_generic")}
            return

        final_text = final_text.strip()
        turn_messages.append({"role": "assistant", "content": final_text})
        SessionStore.append_history(session, turn_messages)
        SessionStore.add_transcript(session, "assistant", final_text)

        elapsed = time.monotonic() - started
        AuditService.log_event("conversation_turn", "turn", "orchestrator", session_id=session.session_id, user_id=session.user_id,
                               details={"tools": tools_used, "language": session.language, "channel": channel,
                                        "first_token_sec": round(first_token_at - started, 2) if first_token_at else None,
                                        "total_sec": round(elapsed, 2)})
        turn_id = cls._save_turn(session, channel, text, final_text, tools_used, started)
        yield {"type": "final", "session_id": session.session_id, "language": session.language, "text": final_text,
               "tools": tools_used, "turn_id": turn_id, **ui}

    @staticmethod
    def _save_turn(session: SessionContext, channel: str, user_text: str, reply: Optional[str], tools_used: List[str],
                   started: float) -> Optional[str]:
        """Keeps the turn for admin review and analytics (FR-26, FR-31), in the background.
        Returns the reply's id, which the widget sends back with a thumbs up/down."""
        turn_id = secrets.token_hex(8) if reply is not None else None
        if turn_id:
            session.turn_ids = (session.turn_ids + [turn_id])[-200:]
        if session.preview:
            return turn_id
        cost = UsageTracker.summary(session.session_id).get("cost_usd", {}).get("total", 0.0)
        ConversationStore.save_in_background(ConversationStore.record_turn(
            session.session_id, language=session.language, channel=channel, user_text=user_text, reply=reply,
            tools=list(dict.fromkeys(tools_used)), latency_ms=int((time.monotonic() - started) * 1000), cost_usd=cost,
            turn_id=turn_id))
        return turn_id

    @classmethod
    async def process_turn(cls, message: str, **kwargs: Any) -> Dict[str, Any]:
        """Non-streaming convenience wrapper (voice pipeline, tests)."""
        final: Dict[str, Any] = {}
        async for event in cls.stream_turn(message, **kwargs):
            if event["type"] in ("final", "error"):
                final = event
            elif event["type"] == "session":
                final.setdefault("session_id", event["session_id"])
        return final


def sse(event: Dict[str, Any]) -> str:
    return f"data: {json.dumps(event, default=str, ensure_ascii=False)}\n\n"
