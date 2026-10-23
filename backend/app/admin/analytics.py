"""Analytics dashboard figures (PRD FR-31, §2 goals, §7 cost control), computed from saved conversations.

Definitions shown to admins:
- Handled by XO: conversations with at least one successful reply and no advisor handoff (PRD goal ≥40%).
- Lead conversion: conversations where the visitor confirmed an advisor callback (lead saved).
- Satisfaction: thumbs up ÷ (thumbs up + thumbs down) on XO replies.
- Topics: what the bot did for the visitor, from the tools it used.
- Where conversations end: the last thing that happened before the visitor left."""
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from app.admin.privacy import mask_personal_data

REPORT_TZ = ZoneInfo("Asia/Dubai")

_TOPICS = {
    "property": ("Property search", {"search_properties", "get_listing_details", "find_similar", "compare_listings", "shortlist_property"}),
    "mortgage": ("Mortgage & affordability", {"calc_affordability", "calc_emi", "check_eligibility", "calc_purchase_costs",
                                              "get_lending_rules", "get_mortgage_products", "estimate_offers"}),
    "knowledge": ("Knowledge question", {"retrieve_kb"}),
    "services": ("XOTO services pricing", {"get_service_pricing"}),
    "account": ("Own account", {"get_my_saved_properties", "get_my_application_status"}),
    "advisor": ("Advisor request", {"request_human_handoff"}),
}
_TOOL_TOPIC = {tool: key for key, (_, tools) in _TOPICS.items() for tool in tools}

_ENDINGS = {
    "lead": "Advisor callback saved",
    "error": "After an error",
    "first_reply": "After the first reply",
    "property": "After property results",
    "mortgage": "After a mortgage result",
    "knowledge": "After a knowledge answer",
    "advisor": "During an advisor request",
    "other": "After general chat",
}


def report_range(days: int, now: Optional[datetime] = None) -> Dict[str, datetime]:
    """The last `days` calendar days in Dubai time, ending now."""
    days = max(1, min(days, 366))
    now = now or datetime.now(timezone.utc)
    local_today = now.astimezone(REPORT_TZ).date()
    start_local = datetime.combine(local_today - timedelta(days=days - 1), datetime.min.time(), REPORT_TZ)
    return {"start": start_local.astimezone(timezone.utc), "end": now + timedelta(seconds=1)}


def month_start(now: Optional[datetime] = None) -> datetime:
    local = (now or datetime.now(timezone.utc)).astimezone(REPORT_TZ)
    return datetime(local.year, local.month, 1, tzinfo=REPORT_TZ).astimezone(timezone.utc)


def topics_of(tools: List[str]) -> List[str]:
    return list(dict.fromkeys(_TOOL_TOPIC[t] for t in tools or [] if t in _TOOL_TOPIC))


def ending_of(conv: Dict[str, Any]) -> str:
    if conv.get("lead_saved"):
        return "lead"
    if conv.get("last_role") == "user":
        return "error"
    if conv.get("user_turns", 0) <= 1:
        return "first_reply"
    last = topics_of(conv.get("last_tools") or [])
    for key in ("advisor", "property", "mortgage", "knowledge"):
        if key in last:
            return key
    return "other"


def handled_by_xo(conv: Dict[str, Any]) -> bool:
    return not conv.get("handoff_ticket") and conv.get("failed_turns", 0) < conv.get("user_turns", 0)


def _pct(part: float, whole: float) -> Optional[float]:
    return round(100.0 * part / whole, 1) if whole else None


def _normalise_question(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", (text or "").lower())).strip()


def headline(conversations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The headline rates of a period (also used for the previous period, to show the change)."""
    total = len(conversations)
    up = sum(c["thumbs_up"] for c in conversations)
    down = sum(c["thumbs_down"] for c in conversations)
    cost = sum(c["cost_usd"] for c in conversations)
    return {"conversations": total,
            "handled_by_xo_pct": _pct(sum(1 for c in conversations if handled_by_xo(c)), total),
            "lead_conversion_pct": _pct(sum(1 for c in conversations if c["lead_saved"]), total),
            "satisfaction_pct": _pct(up, up + down),
            "cost_per_conversation_usd": round(cost / total, 4) if total else None}


def build_report(conversations: List[Dict[str, Any]], *, start: datetime, end: datetime, month_cost_usd: float,
                 budget: Dict[str, Any], show_personal_data: bool,
                 previous: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    total = len(conversations)
    turns = sum(c["user_turns"] for c in conversations)
    up = sum(c["thumbs_up"] for c in conversations)
    down = sum(c["thumbs_down"] for c in conversations)
    cost = sum(c["cost_usd"] for c in conversations)
    leads = sum(1 for c in conversations if c["lead_saved"])

    # Daily figures in Dubai time, every day in the range present (zero days included), for the chart and the trends.
    by_day: Dict[date, List[Dict[str, Any]]] = {}
    for c in conversations:
        by_day.setdefault(c["started_at"].astimezone(REPORT_TZ).date(), []).append(c)
    first_day: date = start.astimezone(REPORT_TZ).date()
    last_day: date = (end - timedelta(seconds=1)).astimezone(REPORT_TZ).date()
    daily = []
    day = first_day
    while day <= last_day:
        todays = by_day.get(day, [])
        daily.append({"date": day.isoformat(), "conversations": len(todays),
                      "handled_by_xo": sum(1 for c in todays if handled_by_xo(c)),
                      "leads": sum(1 for c in todays if c["lead_saved"]),
                      "thumbs_up": sum(c["thumbs_up"] for c in todays), "thumbs_down": sum(c["thumbs_down"] for c in todays),
                      "cost_usd": round(sum(c["cost_usd"] for c in todays), 6)})
        day += timedelta(days=1)

    topic_counts: Counter = Counter(t for c in conversations for t in topics_of(c["tools"]))
    no_tool = sum(1 for c in conversations if not topics_of(c["tools"]))
    topics = [{"key": k, "label": _TOPICS[k][0], "conversations": n} for k, n in topic_counts.most_common()]
    if no_tool:
        topics.append({"key": "general", "label": "General chat only", "conversations": no_tool})

    endings_count: Counter = Counter(ending_of(c) for c in conversations)
    endings = [{"key": k, "label": _ENDINGS[k], "conversations": n} for k, n in endings_count.most_common()]

    questions: Counter = Counter()
    examples: Dict[str, str] = {}
    for c in conversations:
        key = _normalise_question(c.get("first_question") or "")
        if key:
            questions[key] += 1
            examples.setdefault(key, (c["first_question"] or "").strip()[:200])
    top_questions = [{"question": examples[k] if show_personal_data else mask_personal_data(examples[k]), "conversations": n}
                     for k, n in questions.most_common(8)]

    languages = [{"language": lang, "conversations": n} for lang, n in Counter(c["language"] for c in conversations).most_common()]
    channels = Counter(ch for c in conversations for ch in (c["channels"] or ["text"]))

    monthly_budget = budget.get("monthly_usd")
    alert_pct = budget.get("alert_pct", 80)
    used_pct = _pct(month_cost_usd, monthly_budget) if monthly_budget else None
    return {
        "range": {"start": start.isoformat(), "end": end.isoformat(), "timezone": "Asia/Dubai"},
        "totals": {
            "conversations": total,
            "user_messages": turns,
            "handled_by_xo_pct": _pct(sum(1 for c in conversations if handled_by_xo(c)), total),
            "lead_conversion_pct": _pct(leads, total),
            "leads": leads,
            "satisfaction_pct": _pct(up, up + down),
            "thumbs_up": up,
            "thumbs_down": down,
            "failed_messages": sum(c["failed_turns"] for c in conversations),
            "cost_usd": round(cost, 4),
            "cost_per_conversation_usd": round(cost / total, 4) if total else None,
        },
        "previous": headline(previous) if previous is not None else None,
        "daily": daily,
        "topics": topics,
        "endings": endings,
        "top_questions": top_questions,
        "languages": languages,
        "channels": {"text": channels.get("text", 0), "voice": channels.get("voice", 0)},
        "budget": {
            "monthly_usd": monthly_budget,
            "alert_pct": alert_pct,
            "month_cost_usd": round(month_cost_usd, 4),
            "used_pct": used_pct,
            "alert": bool(used_pct is not None and used_pct >= alert_pct),
        },
    }
