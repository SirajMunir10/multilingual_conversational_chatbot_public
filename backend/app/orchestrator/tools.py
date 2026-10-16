"""Function-calling tools exposed to the LLM (PRD §6: function calls only, no direct DB access).

Each handler returns (result_for_llm, ui_payload). result_for_llm is compact JSON the model narrates;
ui_payload carries cards for the widget (listings, calculator results, handoff status)."""
import json
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from pydantic import ValidationError

from app.core.config import load_config
from app.gateways.inventory_gateway import Listing
from app.gateways.services_gateway import ServicesGateway
from app.orchestrator.session_store import SessionContext
from app.services.account_service import AccountService
from app.services.handoff_service import HandoffService
from app.services.mortgage_service import (AffordabilityInput, EligibilityInput, EMIInput, MortgageCalculationService,
                                           MortgageInputError)
from app.services.property_service import PropertyDiscoveryService, SearchFilters
from app.services.rag_service import RAGService

logger = logging.getLogger("xo.tools")

ToolResult = Tuple[Dict[str, Any], Dict[str, Any]]


def _fn(name: str, description: str, properties: Dict[str, Any], required: Optional[List[str]] = None) -> Dict[str, Any]:
    return {"type": "function", "function": {"name": name, "description": description,
                                             "parameters": {"type": "object", "properties": properties, "required": required or [],
                                                            "additionalProperties": False}}}


_RESIDENCY = {"type": "string", "enum": ["uae_national", "uae_resident", "non_resident"],
              "description": "Buyer residency. Omit if unknown (UAE resident is assumed)."}
_NUM = {"type": "number"}
_OUTSTANDING = {"type": "boolean", "description": "True if the user has an outstanding mortgage on another property (second-home terms). A fully paid-off property does not count."}
_STATUS = {"type": "string", "enum": ["ready", "off_plan"]}
_PURPOSE = {"type": "string", "enum": ["home", "investment"]}
_ELIGIBILITY_PARAMS = {
    "residency": {"type": "string", "enum": ["uae_national", "uae_resident", "non_resident"], "description": "uae_resident = expat living in the UAE"},
    "age": {"type": "integer"},
    "employment_type": {"type": "string", "enum": ["salaried", "self_employed"]},
    "monthly_income": {"type": "number", "description": "Gross monthly income in AED (convert yearly or 'k' amounts)."},
    "monthly_debts": {"type": "number", "description": "Existing monthly loan instalments in AED (car, personal, other mortgage); 0 if none."},
    "credit_card_limits": {"type": "number", "description": "Total credit card limits in AED (not the balance); 0 if none."},
    "interest_rate": {"type": "number", "description": "Annual %, only if the user gave one."},
    "tenure_years": {"type": "integer", "description": "Requested term, 1-25 years."},
    "property_price": {"type": "number", "description": "Price of the property the user has chosen, AED."},
    "valuation": {"type": "number", "description": "Bank valuation, if known (the lower of price and valuation is used)."},
    "down_payment": {"type": "number", "description": "AED, if the user gave it."},
    "has_outstanding_mortgage": _OUTSTANDING, "property_status": _STATUS, "purpose": _PURPOSE,
    "expected_annual_rent": {"type": "number", "description": "Investment property only: expected yearly rent in AED."},
    "emirate": {"type": "string"},
}
_INT = {"type": "integer"}

TOOL_SCHEMAS: List[Dict[str, Any]] = [
    _fn("search_properties", "Search properties for sale: live off-plan projects and sample ready listings. Call as soon as the user gives a location, budget or bedroom count.", {
        "location": {"type": "string", "description": "Community, area or emirate as the user said it (e.g. 'JVC', 'Dubai Marina', 'Sharjah', 'UAE')."},
        "property_type": {"type": "string", "enum": ["apartment", "villa", "townhouse", "penthouse", "duplex"]},
        "bedrooms": {"type": "number", "description": "0 for studio."},
        "budget_min": {"type": "number", "description": "AED"},
        "budget_max": {"type": "number", "description": "AED"},
        "purpose": {"type": "string", "enum": ["buy", "rent", "invest"]},
        "status": {"type": "string", "enum": ["ready", "off-plan", "any"]},
        "developer": {"type": "string"},
        "amenities": {"type": "array", "items": {"type": "string"}, "description": "Must-have amenities, e.g. pool, gym, metro."},
    }),
    _fn("get_listing_details", "Full details of a listing currently shown, by its number (#1, #2…).", {"ref": _INT}, ["ref"]),
    _fn("find_similar", "Find properties similar to a shown listing, by its number.", {"ref": _INT}, ["ref"]),
    _fn("compare_listings", "Compare shown listings side by side (price, size, price per sq ft, estimated monthly payment).",
        {"refs": {"type": "array", "items": {"type": "integer"}, "minItems": 2}}, ["refs"]),
    _fn("calc_affordability", "How much the user can borrow and the property price it supports (approved UAE eligibility logic: 50% debt burden at a stress-tested rate, income multiple, LTV). Needs residency, age, employment type and gross monthly income; the result names anything missing.", _ELIGIBILITY_PARAMS),
    _fn("calc_emi", "Monthly mortgage payment. Give either property_price (down payment defaults to the legal minimum for the profile) or loan_amount.", {
        "property_price": _NUM, "loan_amount": _NUM, "down_payment": {"type": "number", "description": "AED"},
        "residency": _RESIDENCY, "interest_rate": {"type": "number", "description": "Annual %, only if the user gave one."},
        "tenure_years": _INT, "frequency": {"type": "string", "enum": ["monthly", "quarterly"]},
        "has_outstanding_mortgage": _OUTSTANDING, "property_status": _STATUS, "purpose": _PURPOSE,
    }),
    _fn("check_eligibility", "Full mortgage eligibility check (approved UAE build logic): verdict eligible / eligible for a lower amount / not eligible / can borrow up to, eligible loan, tightest limit, instalment at the real and stress rate, debt burden after the loan and cash needed upfront. Use when the user asks if they qualify, especially for a specific property.", _ELIGIBILITY_PARAMS),
    _fn("calc_purchase_costs", "Buying costs (registration, trustee, agent, mortgage fees) for a property price and emirate.", {
        "property_price": _NUM, "emirate": {"type": "string", "description": "dubai, abu_dhabi, sharjah, ras_al_khaimah or ajman"},
        "loan_amount": {"type": "number", "description": "Mortgage amount, if financed."}, "resale": {"type": "boolean"},
    }, ["property_price"]),
    _fn("get_lending_rules", "XOTO's approved lending rule table: LTV / minimum down payment (off-plan, residency, AED 5M threshold, first/second home), 50% debt-burden limit, stress test, income multiple, minimum income, age limits, maximum term, benchmark rate, application documents.", {
        "residency": _RESIDENCY,
    }),
    _fn("get_mortgage_products", "Indicative bank mortgage / Islamic home-finance products from XOTO's internal rate table.", {
        "bank": {"type": "string"}, "finance_type": {"type": "string", "enum": ["conventional", "islamic"]},
        "rate_type": {"type": "string", "description": "e.g. fixed, variable"}, "salary": _NUM,
    }),
    _fn("estimate_offers", "Indicative offers (rate and monthly payment) from partner bank products for a loan amount.", {
        "loan_amount": _NUM, "monthly_income": _NUM, "residency": _RESIDENCY, "tenure_years": _INT,
        "finance_type": {"type": "string", "enum": ["conventional", "islamic"]},
    }, ["loan_amount"]),
    _fn("retrieve_kb", "Search XOTO's knowledge base: buying/renting process, fees, laws, Ejari, off-plan, escrow, Golden Visa, area guides and yields, mortgage rules, XOTO services, trust and privacy. Write the query in English.",
        {"query": {"type": "string"}}, ["query"]),
    _fn("get_service_pricing", "Indicative quotation for XOTO home services (e.g. interior design, landscaping, smart home).",
        {"category": {"type": "string"}, "area_sq_ft": _NUM}, ["category", "area_sq_ft"]),
    _fn("shortlist_property", "Save a shown listing to the user's shortlist, by its number.", {"ref": _INT}, ["ref"]),
    _fn("get_my_saved_properties", "The signed-in user's own saved properties.", {}),
    _fn("get_my_application_status", "The signed-in user's own mortgage/property application status.", {}),
    _fn("request_human_handoff", "Show the user a review card for an advisor callback (they confirm or edit it there; nothing is saved until they confirm). Only after the user consented AND gave name and phone.", {
        "full_name": {"type": "string"}, "phone": {"type": "string", "description": "As the user typed it; local UAE numbers are accepted."},
        "preferred_language": {"type": "string", "description": "Language for the call, as a language code (e.g. en, ar, hi). Defaults to the conversation language."},
        "consent_confirmed": {"type": "boolean", "description": "True only if the user explicitly agreed to be contacted."},
        "team": {"type": "string", "enum": ["mortgage", "sales", "support"]},
        "summary": {"type": "string", "description": "One-line summary of what the user needs."},
    }, ["full_name", "phone", "consent_confirmed"]),
    _fn("set_language", "Switch the conversation language when the user writes in or asks for another supported language.",
        {"language": {"type": "string", "description": "ISO code", "enum": None}}, ["language"]),
]


def _schemas() -> List[Dict[str, Any]]:
    codes = list(load_config("locales")["locales"].keys())
    out = json.loads(json.dumps(TOOL_SCHEMAS))
    for schema in out:
        if schema["function"]["name"] == "set_language":
            schema["function"]["parameters"]["properties"]["language"]["enum"] = codes
    return out


def tool_schemas() -> List[Dict[str, Any]]:
    return _schemas()


def _listing_from(session: SessionContext, ref: Any) -> Optional[Listing]:
    try:
        idx = int(ref) - 1
    except (TypeError, ValueError):
        return None
    if 0 <= idx < len(session.displayed_listings):
        return Listing(**session.displayed_listings[idx]["listing"])
    return None


def _show(session: SessionContext, listings: List[Listing], residency: Optional[str] = None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Registers listings as the currently shown set (#1..#n) and returns (llm_rows, cards)."""
    session.displayed_listings = [{"ref": i, "listing": l.model_dump()} for i, l in enumerate(listings, 1)]
    rows = [{"ref": i, **l.summary()} for i, l in enumerate(listings, 1)]
    cards = [PropertyDiscoveryService.to_card(l, i, residency) for i, l in enumerate(listings, 1)]
    return rows, cards


async def _search(session: SessionContext, args: Dict[str, Any]) -> ToolResult:
    filters = SearchFilters(**{k: v for k, v in args.items() if v not in (None, "", [])})
    res = await PropertyDiscoveryService.search(filters, session_id=session.session_id)
    out: Dict[str, Any] = {k: v for k, v in res.items() if k not in ("results", "alternatives")}
    ui: Dict[str, Any] = {}
    if res["results"]:
        rows, cards = _show(session, res["results"])
        out["shown"] = rows
        ui["property_results"] = cards
    alts = res.get("alternatives") or []
    if alts:
        first = alts[0]
        rows, cards = _show(session, first["listings"])
        out["alternatives"] = [{"relaxed_filter": a["relaxed_filter"], "count": a["count"]} for a in alts]
        out["shown_alternatives"] = {"relaxed_filter": first["relaxed_filter"], "listings": rows}
        out["instruction"] = (f"No exact matches. Say so in one sentence, then present these as alternatives that differ in "
                              f"'{first['relaxed_filter']}'.")
        ui["property_results"] = cards
        ui["results_are_alternatives"] = first["relaxed_filter"]
    if not res["offplan_feed_available"]:
        out["note"] = "The live off-plan feed is temporarily unavailable; only sample ready listings were searched."
    return out, ui


async def _details(session: SessionContext, args: Dict[str, Any]) -> ToolResult:
    listing = _listing_from(session, args.get("ref"))
    if not listing:
        return {"error": "No listing with that number is currently shown."}, {}
    return {"ref": args["ref"], **listing.summary(), "baths": listing.baths, "sale_status": listing.sale_status}, {}


async def _similar(session: SessionContext, args: Dict[str, Any]) -> ToolResult:
    listing = _listing_from(session, args.get("ref"))
    if not listing:
        return {"error": "No listing with that number is currently shown."}, {}
    pool = await PropertyDiscoveryService.all_listings(session.session_id)
    similar = PropertyDiscoveryService.similar(listing, pool)
    rows, cards = _show(session, similar)
    return {"reference": listing.title, "shown": rows}, {"property_results": cards}


async def _compare(session: SessionContext, args: Dict[str, Any]) -> ToolResult:
    listings = [l for l in (_listing_from(session, r) for r in args.get("refs") or []) if l]
    if len(listings) < 2:
        return {"error": f"Only {len(session.displayed_listings)} listing(s) are currently shown; ask which ones to compare."}, {}
    return PropertyDiscoveryService.compare(listings), {}


def _calc_ui(session: SessionContext, result: Dict[str, Any]) -> Dict[str, Any]:
    session.last_calculation = result
    return {"mortgage_result": result}


async def _affordability(session: SessionContext, args: Dict[str, Any]) -> ToolResult:
    res = MortgageCalculationService.calc_affordability(AffordabilityInput(**args), session.session_id, session.user_id)
    return res, _calc_ui(session, res)


async def _emi(session: SessionContext, args: Dict[str, Any]) -> ToolResult:
    res = MortgageCalculationService.calc_emi(EMIInput(**args), session.session_id, session.user_id)
    return res, _calc_ui(session, res)


async def _eligibility(session: SessionContext, args: Dict[str, Any]) -> ToolResult:
    res = MortgageCalculationService.check_eligibility(EligibilityInput(**args), session.session_id, session.user_id)
    return res, _calc_ui(session, res)


async def _costs(session: SessionContext, args: Dict[str, Any]) -> ToolResult:
    res = MortgageCalculationService.calc_purchase_costs(args["property_price"], args.get("emirate"), args.get("loan_amount"),
                                                         args.get("resale", True), session.session_id)
    return res, {}


async def _lending_rules(session: SessionContext, args: Dict[str, Any]) -> ToolResult:
    return MortgageCalculationService.lending_rules(args.get("residency")), {}


async def _products(session: SessionContext, args: Dict[str, Any]) -> ToolResult:
    return MortgageCalculationService.get_products(session_id=session.session_id, **args), {}


async def _offers(session: SessionContext, args: Dict[str, Any]) -> ToolResult:
    return MortgageCalculationService.estimate_offers(session_id=session.session_id, **args), {}


async def _kb(session: SessionContext, args: Dict[str, Any]) -> ToolResult:
    return await RAGService.retrieve(args.get("query", ""), session.session_id), {}


async def _services(session: SessionContext, args: Dict[str, Any]) -> ToolResult:
    return ServicesGateway.get_service_pricing(args["category"], float(args["area_sq_ft"]), session.session_id), {}


async def _shortlist(session: SessionContext, args: Dict[str, Any]) -> ToolResult:
    listing = _listing_from(session, args.get("ref"))
    if not listing:
        return {"error": "No listing with that number is currently shown."}, {}
    if listing.id not in session.shortlisted:
        session.shortlisted.append(listing.id)
    if session.user_id:
        AccountService.save_property(session.user_id, listing.id, session.session_id)
        return {"status": "saved_to_account", "listing": listing.title}, {"shortlisted": listing.id}
    return {"status": "saved_for_this_session", "listing": listing.title,
            "note": "The user is not signed in; the shortlist lasts for this chat. Offer an advisor callback if they want it kept."}, {"shortlisted": listing.id}


async def _saved(session: SessionContext, args: Dict[str, Any]) -> ToolResult:
    return AccountService.get_my_saved_properties(session.user_id, session.session_id), {}


async def _status(session: SessionContext, args: Dict[str, Any]) -> ToolResult:
    return AccountService.get_my_application_status(session.user_id, session.session_id), {}


async def _handoff(session: SessionContext, args: Dict[str, Any]) -> ToolResult:
    res = HandoffService.prepare_callback(session, args.get("full_name", ""), args.get("phone", ""), args.get("preferred_language", ""),
                                          bool(args.get("consent_confirmed")), args.get("team"), args.get("summary"))
    ui = {"handoff_draft": res["details"]} if res.get("status") == "awaiting_confirmation" else {}
    return res, ui


async def _confirm_language_switch(text: str, target: str, explicit_only: bool = False) -> bool:
    """Guards against switching on a single foreign word: the message must be written in the
    target language or explicitly ask for it. When the user picked the language from the menu,
    only an explicit request counts (speech transcripts can come back in a related script, e.g. Urdu as Hindi).
    Uses a tiny LLM classification (no word lists)."""
    from app.core.config import settings
    from app.llm.client import LLMService
    try:
        resp = await LLMService.client().chat.completions.create(
            model=settings.LLM_MODEL, reasoning_effort=settings.LLM_REASONING_EFFORT or None, max_completion_tokens=40,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": "Return JSON {\"written_in\": ISO-639-1 code of the language the message is mainly written in, "
                                                    "\"requests_language\": ISO-639-1 code the user explicitly asks the assistant to use, or null}."},
                      {"role": "user", "content": text[:500]}])
        data = json.loads(resp.choices[0].message.content or "{}")
        aliases = {"fil": "tl"}
        written = aliases.get(data.get("written_in"), data.get("written_in"))
        requested = aliases.get(data.get("requests_language"), data.get("requests_language"))
        return target == requested if explicit_only else target in (written, requested)
    except Exception:
        return True


async def _set_language(session: SessionContext, args: Dict[str, Any]) -> ToolResult:
    code = args.get("language")
    if code not in load_config("locales")["locales"]:
        return {"error": "unsupported_language"}, {}
    if code == session.language:
        return {"language": code, "status": "already_active"}, {}
    if not await _confirm_language_switch(session.current_user_text, code, explicit_only=session.language_locked):
        return {"status": "not_switched", "language": session.language,
                "instruction": "Keep replying in the session language; the user did not ask to switch."}, {}
    session.language = code
    session.language_locked = False
    return {"language": code, "status": "switched"}, {"language": code}


HANDLERS: Dict[str, Callable[[SessionContext, Dict[str, Any]], Awaitable[ToolResult]]] = {
    "search_properties": _search, "get_listing_details": _details, "find_similar": _similar, "compare_listings": _compare,
    "calc_affordability": _affordability, "calc_emi": _emi, "check_eligibility": _eligibility, "calc_purchase_costs": _costs,
    "get_lending_rules": _lending_rules, "get_mortgage_products": _products, "estimate_offers": _offers, "retrieve_kb": _kb, "get_service_pricing": _services,
    "shortlist_property": _shortlist, "get_my_saved_properties": _saved, "get_my_application_status": _status,
    "request_human_handoff": _handoff, "set_language": _set_language,
}


async def execute(session: SessionContext, name: str, raw_args: str) -> ToolResult:
    """Runs a tool and converts any input problem into a message the model can explain to the user."""
    handler = HANDLERS.get(name)
    if not handler:
        return {"error": f"Unknown tool {name}"}, {}
    try:
        args = json.loads(raw_args or "{}")
        args = {k: v for k, v in args.items() if v is not None}
        return await handler(session, args)
    except MortgageInputError as exc:
        return {"error": "invalid_input", "message": str(exc)}, {}
    except ValidationError as exc:
        fields = ", ".join(".".join(str(p) for p in e["loc"]) for e in exc.errors())
        return {"error": "invalid_input", "message": f"Missing or invalid: {fields}. Ask the user for it."}, {}
    except Exception as exc:
        logger.exception("Tool %s failed", name)
        return {"error": "tool_unavailable", "message": "This service is temporarily unavailable. Tell the user briefly and offer an alternative."}, {}


def compact(result: Dict[str, Any], limit: int = 6000) -> str:
    """JSON for the model, trimmed so very large tool results never blow up the context."""
    text = json.dumps(result, default=str, ensure_ascii=False)
    if len(text) <= limit:
        return text
    trimmed = {k: v for k, v in result.items() if k not in ("amortization_schedule", "purchase_costs", "checks")}
    text = json.dumps(trimmed, default=str, ensure_ascii=False)
    return text[:limit]
