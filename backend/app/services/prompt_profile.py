"""XO's instructions as an editable profile (PRD FR-25).

The built-in `prompts/system_prompt.md` is split into a persona and its `##` sections. Sections that carry PRD rules
(truthfulness, deterministic calculations, advisor consent, scope and safety) are locked: an admin version must keep
them word for word. Unchanged, the profile renders the built-in file exactly, so publishing nothing changes nothing.
Guided journeys, a tone per language and banned topics are added to the instructions only when an admin fills them in;
banned topics are also enforced in code before the model runs (`banned_topic`)."""
import re
from functools import lru_cache
from typing import Any, Dict, List, Optional

from app.core.config import builtin_config, load_prompt, override

PROFILE_ITEM = "prompt_profile"

# Values filled in at every turn. Each must stay somewhere in the instructions.
PLACEHOLDERS = ("language_name", "language_native", "language_writing", "language_mode", "supported_languages",
                "default_tenure", "benchmark_rate", "today")

# Sections whose titles start with these carry PRD rules (FR-6, FR-13, FR-16, FR-23b) and cannot be edited.
LOCKED_PREFIXES = ("Truthfulness", "Calculations", "Advisor handoff", "Scope and safety")

MAX_TEXT = 20_000


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")[:40] or "section"


@lru_cache(maxsize=1)
def builtin_profile() -> Dict[str, Any]:
    """The profile parsed from the built-in instruction file (the seed and the fallback)."""
    text = load_prompt("system_prompt")
    parts = re.split(r"(?m)^## ", text)
    sections = []
    for raw in parts[1:]:
        title, _, body = raw.partition("\n")
        sections.append({"id": _slug(title), "title": title, "body": body,
                         "locked": title.startswith(LOCKED_PREFIXES)})
    return {"persona": parts[0], "sections": sections, "journeys": [], "tone_by_language": {}, "banned_topics": []}


def with_current_locks(profile: Any) -> Any:
    """The profile with its locked sections replaced by the built-in text. Locked sections carry PRD rules, so a stored
    copy can never change them, and improving them in the built-in file reaches every published version."""
    if not isinstance(profile, dict) or not isinstance(profile.get("sections"), list):
        return profile
    locked = {s["id"]: s for s in builtin_profile()["sections"] if s["locked"]}
    sections = [dict(locked[s["id"]]) if isinstance(s, dict) and s.get("id") in locked else s for s in profile["sections"]]
    return {**profile, "sections": sections}


def current_profile() -> Dict[str, Any]:
    published = override(PROFILE_ITEM)
    return with_current_locks(published) if published else builtin_profile()


def render_template(profile: Dict[str, Any], language: str) -> str:
    """The instructions before the per-turn values are filled in."""
    text = profile["persona"] + "".join(f"## {s['title']}\n{s['body']}" for s in profile["sections"])
    extras: List[str] = []
    journeys = [j for j in profile.get("journeys") or [] if j.get("steps")]
    if journeys:
        lines = ["## Guided journeys",
                 "When a conversation matches one of these journeys, follow its steps in order. Ask one question at a time "
                 "and skip any step the visitor has already answered."]
        for j in journeys:
            lines.append(f"### {j['title']}")
            lines += [f"{i}. {step}" for i, step in enumerate(j["steps"], 1)]
        extras.append("\n".join(lines))
    tone = (profile.get("tone_by_language") or {}).get(language)
    if tone:
        extras.append(f"## Tone in this language\n{tone}")
    banned = [t["name"] for t in profile.get("banned_topics") or [] if t.get("name")]
    if banned:
        extras.append("## Topics you never discuss\nPolitely decline and steer back to UAE property, mortgages or XOTO "
                      "services if the visitor asks about: " + "; ".join(banned) + ".")
    if extras:
        text = text.rstrip("\n") + "\n\n" + "\n\n".join(extras) + "\n"
    return text


def fill(template: str, values: Dict[str, Any]) -> str:
    """Replaces only the known placeholders, so braces typed by an admin stay as they are."""
    for key in PLACEHOLDERS:
        template = template.replace("{" + key + "}", str(values.get(key, "")))
    return template


def banned_topic(text: str, profile: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """The banned topic the visitor's message matches, if any (checked in code before the model runs)."""
    lowered = (text or "").casefold()
    for topic in (profile or current_profile()).get("banned_topics") or []:
        for keyword in topic.get("keywords") or []:
            k = keyword.casefold().strip()
            if not k:
                continue
            if k.isascii():
                if re.search(r"(?<![\w])" + re.escape(k) + r"(?![\w])", lowered):
                    return topic
            elif k in lowered:
                return topic
    return None


def banned_reply(topic: Dict[str, Any], language: str) -> str:
    replies = topic.get("reply") or {}
    return replies.get(language) or replies.get("en") or (
        "I can't help with that topic. I can help with UAE property, mortgages or XOTO services.")


def validate(profile: Any) -> List[str]:
    """Problems that block publishing, as plain sentences for the admin."""
    errors: List[str] = []
    if not isinstance(profile, dict):
        return ["The instructions are not in the expected format."]
    base = builtin_profile()
    if not str(profile.get("persona") or "").strip():
        errors.append("The persona (opening paragraph) cannot be empty.")
    sections = profile.get("sections")
    if not isinstance(sections, list) or not sections:
        return errors + ["The instructions need their sections."]
    by_id = {s.get("id"): s for s in sections if isinstance(s, dict)}
    for locked in (s for s in base["sections"] if s["locked"]):
        mine = by_id.get(locked["id"])
        if not mine or mine.get("title") != locked["title"] or mine.get("body") != locked["body"]:
            errors.append(f"The locked section “{locked['title']}” must stay exactly as it is (PRD rule).")
    for s in sections:
        if not isinstance(s, dict) or not str(s.get("title") or "").strip() or "\n" in str(s.get("title")):
            errors.append("Every section needs a one-line title.")
            break
    if not errors:
        rendered = render_template(profile, "en")
        for key in PLACEHOLDERS:
            if "{" + key + "}" in render_template(base, "en") and "{" + key + "}" not in rendered:
                errors.append(f"The placeholder {{{key}}} was removed; XO needs it to fill in live values.")
        if len(rendered) > MAX_TEXT:
            errors.append(f"The instructions are too long ({len(rendered):,} characters; the limit is {MAX_TEXT:,}).")
    languages = set(builtin_config("locales")["locales"])
    for code in (profile.get("tone_by_language") or {}):
        if code not in languages:
            errors.append(f"Unknown language code “{code}” in the tone settings.")
    for j in profile.get("journeys") or []:
        if not str(j.get("title") or "").strip() or not [s for s in j.get("steps") or [] if str(s).strip()]:
            errors.append("Every guided journey needs a title and at least one step.")
            break
    for t in profile.get("banned_topics") or []:
        keywords = [k for k in t.get("keywords") or [] if len(str(k).strip()) >= 2]
        if not str(t.get("name") or "").strip() or not keywords:
            errors.append("Every banned topic needs a name and at least one keyword of two or more characters.")
            break
        if not str((t.get("reply") or {}).get("en") or "").strip():
            errors.append(f"The banned topic “{t.get('name')}” needs an English reply (the fallback).")
            break
    return errors
