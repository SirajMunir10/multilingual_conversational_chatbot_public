"""Escalation rules (PRD FR-29): when XO offers a human advisor, and to which team.

A rule never saves anything: it makes XO *offer* the advisor callback card, and the visitor's explicit confirmation is
still required before a lead is stored (FR-5, FR-16). The three teams are the ones visitors can pick on the callback
card; their internal queue names (shown on leads) can be changed. The built-in rules reproduce XO's behaviour before
the admin module: explicit requests are always honoured and an unanswerable question offers an advisor."""
import re
from typing import Any, Dict, List, Optional

from app.core.config import override

ITEM = "escalation"
TEAM_KEYS = ("mortgage", "sales", "support")
RULE_TYPES = ("explicit_request", "low_confidence", "keywords", "high_value", "frustration")


def builtin_rules() -> Dict[str, Any]:
    return {
        "teams": [
            {"key": "mortgage", "queue": "Mortgage Advisory"},
            {"key": "sales", "queue": "Property Advisory"},
            {"key": "support", "queue": "Client Support"},
        ],
        "rules": [
            {"id": "explicit_request", "type": "explicit_request", "enabled": True, "team": "auto",
             "label": "The visitor asks for a person"},
            {"id": "low_confidence", "type": "low_confidence", "enabled": True, "team": "auto", "after_misses": 1,
             "label": "XO cannot answer from the knowledge base"},
            {"id": "keywords", "type": "keywords", "enabled": False, "team": "support", "keywords": [],
             "label": "The visitor mentions a sensitive word"},
            {"id": "high_value", "type": "high_value", "enabled": False, "team": "mortgage",
             "min_property_aed": 5_000_000, "min_loan_aed": 4_000_000, "label": "High-value lead"},
            {"id": "frustration", "type": "frustration", "enabled": False, "team": "support",
             "label": "The visitor sounds frustrated"},
        ],
    }


def current_rules() -> Dict[str, Any]:
    return override(ITEM) or builtin_rules()


def queue_names() -> Dict[str, str]:
    """Team key → the queue name shown on leads (e.g. "Mortgage Advisory")."""
    names = {t["key"]: t["queue"] for t in current_rules()["teams"]}
    return {k: names.get(k) or v["queue"] for k, v in zip(TEAM_KEYS, builtin_rules()["teams"])}


def _rule(rules: Dict[str, Any], rule_type: str) -> Optional[Dict[str, Any]]:
    return next((r for r in rules["rules"] if r["type"] == rule_type and r.get("enabled")), None)


def _matches(text: str, keyword: str) -> bool:
    k = keyword.casefold().strip()
    if not k:
        return False
    lowered = text.casefold()
    if k.isascii():
        return re.search(r"(?<![\w])" + re.escape(k) + r"(?![\w])", lowered) is not None
    return k in lowered


def _offer(rule: Dict[str, Any], reason: str) -> str:
    team = rule.get("team") or "auto"
    who = "the most suitable team" if team == "auto" else f"team '{team}' ({queue_names()[team]})"
    return (f"Escalation rule — {reason}. Offer the visitor a call back from {who}. Ask permission first; use "
            "request_human_handoff only after they agree and give their name and phone. Offer it once; if they decline, "
            "keep helping.")


def turn_notes(session: Any, user_text: str) -> List[Dict[str, str]]:
    """Rules matched before this turn: [{"id", "note"}]. Each rule is offered at most once per conversation, except the
    frustration rule, which is guidance the model applies when the visitor's tone shows it."""
    rules = current_rules()
    offered = set(getattr(session, "escalations_offered", []) or [])
    notes: List[Dict[str, str]] = []

    rule = _rule(rules, "keywords")
    if rule and rule["id"] not in offered:
        hit = next((k for k in rule.get("keywords") or [] if _matches(user_text or "", k)), None)
        if hit:
            notes.append({"id": rule["id"], "note": _offer(rule, f"the visitor mentioned “{hit}”")})

    rule = _rule(rules, "high_value")
    if rule and rule["id"] not in offered:
        calc = getattr(session, "last_calculation", None) or {}
        price = max([calc.get("max_property_price_aed") or 0, (calc.get("inputs") or {}).get("property_price") or 0]
                    + [(item.get("listing") or {}).get("price_from") or 0 for item in getattr(session, "displayed_listings", []) or []])
        loan = max(calc.get("loan_amount_aed") or 0, calc.get("max_loan_aed") or 0, calc.get("eligible_loan_aed") or 0)
        if price >= rule.get("min_property_aed", float("inf")) or loan >= rule.get("min_loan_aed", float("inf")):
            notes.append({"id": rule["id"], "note": _offer(rule, "this is a high-value enquiry")})

    rule = _rule(rules, "frustration")
    if rule:
        team = rule.get("team") or "support"
        notes.append({"id": rule["id"], "note": (
            "Escalation rule — if the visitor sounds frustrated or upset, apologise briefly and offer a call back from "
            + ("the most suitable team" if team == "auto" else f"team '{team}' ({queue_names()[team]})")
            + "; ask permission first and offer it once.")})
    return notes


def low_confidence_instruction(misses: int) -> str:
    """What XO is told when the knowledge base has no reliable answer, after `misses` such questions this conversation."""
    rule = _rule(current_rules(), "low_confidence")
    if rule and misses >= int(rule.get("after_misses", 1)):
        team = rule.get("team") or "support"
        who = "an advisor" if team == "auto" else f"an advisor from team '{team}' ({queue_names()[team]})"
        return f"The knowledge base has no reliable answer. Say you don't know and offer to connect the user with {who}."
    return "The knowledge base has no reliable answer. Say you don't know; do not guess."


def validate(data: Any) -> List[str]:
    if not isinstance(data, dict):
        return ["The escalation rules are not in the expected format."]
    errors: List[str] = []
    teams = data.get("teams")
    if not isinstance(teams, list) or [t.get("key") for t in teams] != list(TEAM_KEYS):
        errors.append("The three teams (mortgage, property, support) must stay; only their queue names can change.")
    else:
        for t in teams:
            if not str(t.get("queue") or "").strip() or len(str(t.get("queue"))) > 60:
                errors.append(f"The {t['key']} team needs a queue name of up to 60 characters.")
    rules = data.get("rules")
    if not isinstance(rules, list) or sorted(r.get("type") for r in rules) != sorted(RULE_TYPES):
        return errors + ["Each kind of rule must appear exactly once."]
    for r in rules:
        if r.get("team") not in TEAM_KEYS + ("auto",):
            errors.append(f"“{r.get('label') or r.get('type')}” must route to a team.")
        if r["type"] == "explicit_request" and not r.get("enabled"):
            errors.append("Visitors can always ask for a person (PRD FR-5); this rule cannot be switched off.")
        if r["type"] == "low_confidence":
            misses = r.get("after_misses")
            if isinstance(misses, bool) or not isinstance(misses, int) or not 1 <= misses <= 10:
                errors.append("“XO cannot answer” needs a number of unanswered questions between 1 and 10.")
        if r["type"] == "keywords":
            words = r.get("keywords")
            if not isinstance(words, list) or any(not isinstance(w, str) or len(w.strip()) < 2 or len(w) > 60 for w in words):
                errors.append("Keywords must be words or phrases of 2 to 60 characters.")
            elif r.get("enabled") and not words:
                errors.append("Add at least one keyword, or switch the keyword rule off.")
        if r["type"] == "high_value":
            for key, label in (("min_property_aed", "property value"), ("min_loan_aed", "loan amount")):
                value = r.get(key)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not 100_000 <= value <= 1_000_000_000:
                    errors.append(f"The high-value {label} must be between AED 100,000 and AED 1,000,000,000.")
    return errors
