import json
import logging
import re
from typing import Dict, Any, List, Optional, AsyncGenerator
from app.core.config import settings
from app.core.security import assert_no_payment_intent, sanitize_input_for_injection
from app.core.audit import AuditService
from app.orchestrator.language_detector import LanguageDetector
from app.orchestrator.session_store import SessionStore, SessionContext
from app.llm.client import LLMService, XO_FUNCTION_TOOLS
from app.gateways.inventory_gateway import PropertyInventoryGateway
from app.gateways.mortgage_rules_gateway import MortgageRulesGateway
from app.gateways.services_gateway import ServicesGateway
from app.gateways.grid_gateway import GridGateway
from app.gateways.vault_gateway import VaultGateway
from app.services.mortgage_service import (
    MortgageCalculationService,
    AffordabilityInput,
    EMIInput,
    EligibilityInput
)
from app.services.property_service import PropertyDiscoveryService, PropertySearchFilter

logger = logging.getLogger("xo.orchestrator")

class ConversationOrchestrator:
    """
    Core conversation orchestration engine.
    Unified orchestrator for BOTH text and voice (Rule 7).
    Handles language detection, session context, slot-filling, intent routing,
    function calling, and guardrail enforcement.
    """

    @classmethod
    async def process_user_turn(
        cls,
        user_message: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        manual_language: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Processes a single turn of user interaction.
        Returns response object containing message text, active language, intent,
        structured cards (properties, mortgage breakdown), and tool calls.
        """
        # 1. Payment Guardrail Check (Rule 8 / FR-23b)
        assert_no_payment_intent(user_message)

        # 2. Prompt Injection Sanitization
        sanitized_input = sanitize_input_for_injection(user_message)

        # 3. Retrieve or Create Session Context (FR-2)
        session = SessionStore.get_or_create_session(session_id, user_id=user_id)

        # 4. Multilingual Detection & Override (FR-1)
        explicit_switch = LanguageDetector.check_explicit_language_switch(sanitized_input)
        if explicit_switch:
            session.language = explicit_switch
            session.language_manually_overridden = True
            logger.info(f"Explicit language switch detected for session {session.session_id}: {explicit_switch}")
        elif manual_language and manual_language in settings.LAUNCH_LANGUAGES:
            session.language = manual_language
            session.language_manually_overridden = True
        elif not session.language_manually_overridden:
            detected_lang, confidence = LanguageDetector.detect_language(sanitized_input)
            if detected_lang != "en" and confidence >= 0.80:
                session.language = detected_lang
                logger.info(f"Script-based language switch detected for session {session.session_id}: {detected_lang}")
            elif len(session.messages) == 0:
                session.language = detected_lang
                logger.info(f"Auto-detected language for session {session.session_id}: {detected_lang} (confidence {confidence:.2f})")

        # Record User Message
        SessionStore.add_message(
            session_id=session.session_id,
            role="user",
            content=sanitized_input,
            language=session.language
        )

        # 5. Intent Routing & Slot Filling (FR-3, FR-4)
        intent = cls._classify_intent(sanitized_input, session)
        session.active_intent = intent
        cls._extract_slots(sanitized_input, session)

        # 6. Generate Response via LLM / Function Calling
        response_data = await cls._generate_reply(session, sanitized_input)

        # Record Assistant Message
        SessionStore.add_message(
            session_id=session.session_id,
            role="assistant",
            content=response_data["text"],
            language=session.language,
            metadata=response_data.get("metadata", {})
        )

        # Audit Log Event
        AuditService.log_event(
            event_type="conversation_turn",
            action="process_turn",
            resource="orchestrator",
            session_id=session.session_id,
            user_id=user_id,
            details={
                "intent": intent,
                "language": session.language,
                "has_tool_call": bool(response_data.get("tool_calls"))
            }
        )

        return {
            "session_id": session.session_id,
            "language": session.language,
            "intent": intent,
            "text": response_data["text"],
            "property_results": response_data.get("property_results", []),
            "mortgage_result": response_data.get("mortgage_result"),
            "handoff_offered": response_data.get("handoff_offered", False),
            "tool_calls": response_data.get("tool_calls", [])
        }

    @classmethod
    def _classify_intent(cls, text: str, session: SessionContext) -> str:
        """
        Classifies user query into PRD architecture domains:
        - property: search, discovery, refinement, location, bedrooms, budget
        - mortgage: affordability, eligibility, EMI, interest rates, borrowing
        - account: saved properties, application status, prior inquiries
        - general: company info, policies, processes, Xoto overview, greetings
        Supports mixed intents without restarting context (FR-3).
        """
        lowered = text.lower()

        # Explicit language switch or language preference is general conversational intent
        if LanguageDetector.check_explicit_language_switch(text):
            return "general"

        # Account intent keywords (strictly scoped to user profile/vault access)
        account_kw = [
            "my application", "my status", "saved properties", "my shortlist",
            "view shortlist", "view my shortlist", "show shortlist", "show my shortlist",
            "saved shortlist", "my favorites", "my inquiries", "حسابي", "طلباتي",
            "قائمتي المحفوظة", "मेरा स्टेटस"
        ]
        if any(kw in lowered for kw in account_kw):
            return "account"

        # Property comparison / evaluation intent (FR-9)
        # Evaluates properties already displayed on screen rather than triggering a new search
        comparison_kw = [
            "among these", "between these", "which one", "which of these", "which of the two", 
            "what do you suggest", "which should i buy", "which one should i buy", "which is better",
            "which should i be buying", "compare", "comparison", "most beneficial", "better investment",
            "which to buy", "should i buy", "which would you recommend",
            "اي واحد", "مقارنة", "أيهما أفضل", "أفضل للاستثمار", "तुलना", "कौन सा बेहतर", "موازنہ", "کون سا بہتر"
        ]
        if bool(session.last_recommended_properties) and any(kw in lowered for kw in comparison_kw):
            return "property_comparison"

        # Mortgage intent keywords
        mortgage_kw = ["emi", "monthly payment", "mortgage", "afford", "affordability", "interest rate", "loan", "down payment", "dbr", "قرض", "تمويل", "رهن", "دفعة شهرية", "किस्त", "लोन", "مارگیج"]
        if any(kw in lowered for kw in mortgage_kw):
            return "mortgage"

        # Property intent keywords
        property_kw = ["bedroom", "bed", "br", "apartment", "villa", "townhouse", "penthouse", "studio", "downtown", "marina", "hills", "property", "buy", "rent", "invest", "residence", "residences", "شقة", "فيلا", "عقار", "شراء", "إيجار", "फ्लैट", "پراپرٹی"]
        if any(kw in lowered for kw in property_kw):
            return "property"

        # If previous intent was property or mortgage and user is refining (e.g. "cheaper", "how about 3 beds", "other property")
        if session.active_intent in ["property", "mortgage"] and any(w in lowered for w in ["cheaper", "more", "less", "bigger", "smaller", "show", "near", "other"]):
            return session.active_intent

        return "general"

    @classmethod
    def _extract_slots(cls, text: str, session: SessionContext) -> None:
        """
        Conversational slot filling memory (FR-4, FR-7, FR-12).
        Extracts numbers, bedroom counts, budget ranges, and locations.
        """
        # If user is evaluating / comparing on-screen properties, do NOT overwrite search slots
        if session.active_intent == "property_comparison":
            return

        lowered = text.lower()

        # Extract bedrooms
        bed_match = re.search(r'(\d+)\s*(?:bed|bedroom|br|bhk|غرف)', lowered)
        if bed_match:
            session.slots.property_beds = int(bed_match.group(1))

        # Extract budget / numbers with suffixes (e.g. 800k, 1.5m)
        num_k = re.search(r'(\d+(?:\.\d+)?)\s*(?:k|thousand|ألف|हज़ार)', lowered)
        if num_k:
            val = float(num_k.group(1)) * 1000
            if session.active_intent == "property":
                session.slots.property_budget_max = val
            elif session.active_intent == "mortgage":
                session.slots.mortgage_income = val

        num_m = re.search(r'(\d+(?:\.\d+)?)\s*(?:m|million|مليون|मिलियन)', lowered)
        if num_m:
            val = float(num_m.group(1)) * 1000000
            session.slots.property_budget_max = val

        # Specific Mortgage Income slot extraction (e.g., "earn 25000 AED", "salary 30,000", "25000 per month")
        income_match = re.search(r'(?:earn|salary|income|راتب|دخل|मासिक आय|آمدنی)\s*(?:of|is|:)?\s*(?:aed|dhs)?\s*([0-9,]+)', lowered)
        if income_match:
            session.slots.mortgage_income = float(income_match.group(1).replace(',', ''))
        else:
            monthly_match = re.search(r'([0-9,]{4,})\s*(?:aed|dhs)?\s*(?:per month|\/mo|monthly|شهري|ماہانہ)', lowered)
            if monthly_match:
                session.slots.mortgage_income = float(monthly_match.group(1).replace(',', ''))

        # Specific Mortgage Debt slot extraction (e.g., "2000 AED car loan debt", "debt of 1500")
        debt_match = re.search(r'(?:debt|car loan|loan debt|liabilities|ديون|التزامات|कर्ज|واجبات)\s*(?:of|is|:)?\s*(?:aed|dhs)?\s*([0-9,]+)', lowered)
        if debt_match:
            session.slots.mortgage_existing_debt = float(debt_match.group(1).replace(',', ''))
        else:
            debt_match_alt = re.search(r'([0-9,]{3,})\s*(?:aed|dhs)?\s*(?:car loan|loan debt|debt)', lowered)
            if debt_match_alt:
                session.slots.mortgage_existing_debt = float(debt_match_alt.group(1).replace(',', ''))

        # Down payment extraction (e.g., "200000 down payment", "down payment 20%")
        dp_match = re.search(r'(?:down payment|downpayment|equity|دفعة أولى|ڈاؤن پیمنٹ)\s*(?:of|is|:)?\s*(?:aed|dhs)?\s*([0-9,]+)', lowered)
        if dp_match:
            session.slots.mortgage_down_payment = float(dp_match.group(1).replace(',', ''))

        # Extract property type
        for ptype in ["apartment", "villa", "townhouse", "penthouse"]:
            if ptype in lowered or ("شقة" in text and ptype == "apartment") or ("فيلا" in text and ptype == "villa"):
                session.slots.property_type = ptype

        # Check for general "other property" requests to broaden search
        if any(w in lowered for w in ["other property", "other properties", "other options", "something else", "different property", "عقارات أخرى", "خيارات أخرى", "अन्य प्रॉपर्टी", "دوسری پراپرٹی"]):
            session.slots.property_city = "Dubai"
            session.slots.property_budget_max = None
        elif any(w in lowered for w in ["all uae", "in uae", "across uae", "all of uae", "find in uae", "in the uae", "uae", "everywhere in uae", "anywhere in uae"]):
            session.slots.property_city = "UAE"
        elif any(w in lowered for w in ["all dubai", "across dubai", "anywhere in dubai", "in dubai"]):
            if not any(loc in lowered for loc in ["downtown", "marina", "business bay", "dubai hills", "palm", "jvc", "creek", "jbr", "ranches"]):
                session.slots.property_city = "Dubai"

        # Specific communities (ordered by specificity)
        comm_map = [
            ("palm jumeirah", "Palm Jumeirah"),
            ("palm", "Palm Jumeirah"),
            ("dubai hills estate", "Dubai Hills Estate"),
            ("dubai hills", "Dubai Hills Estate"),
            ("hills", "Dubai Hills Estate"),
            ("downtown dubai", "Downtown Dubai"),
            ("downtown", "Downtown Dubai"),
            ("dubai marina", "Dubai Marina"),
            ("marina", "Dubai Marina"),
            ("business bay", "Business Bay"),
            ("jumeirah village circle", "Jumeirah Village Circle"),
            ("jvc", "Jumeirah Village Circle"),
            ("dubai creek harbour", "Dubai Creek Harbour"),
            ("dubai creek", "Dubai Creek Harbour"),
            ("creek harbour", "Dubai Creek Harbour"),
            ("creek harbor", "Dubai Creek Harbour"),
            ("creek", "Dubai Creek Harbour"),
            ("dubai greek harbour", "Dubai Creek Harbour"),
            ("dubai greek harbor", "Dubai Creek Harbour"),
            ("greek harbour", "Dubai Creek Harbour"),
            ("greek harbor", "Dubai Creek Harbour"),
            ("jumeirah beach residence", "JBR"),
            ("jbr", "JBR"),
            ("arabian ranches iii", "Arabian Ranches III"),
            ("arabian ranches", "Arabian Ranches III"),
            ("ranches", "Arabian Ranches III"),
            ("yas island", "Yas Island"),
            ("yas", "Yas Island")
        ]
        for pattern, canon in comm_map:
            if re.search(r'\b' + re.escape(pattern) + r'\b', lowered):
                session.slots.property_city = canon
                break

        # Extract amenity / proximity preferences
        has_amenity_kw = any(w in lowered for w in ["metro", "مترو", "मेट्रो", "pool", "مسبح", "gym", "جيم", "balcony", "شرفة"])
        is_fresh_property_search = any(w in lowered for w in [
            "show me", "find me", "provide me", "give me", "look for", "search",
            "ابحث", "اريد", "أريد", "دیکھو"
        ]) or any(w in lowered for w in ["1 bhk", "2 bhk", "3 bhk", "1br", "2br", "3br", "1 bedroom", "2 bedroom", "3 bedroom", "all apartments", "all properties"])
        if is_fresh_property_search and not has_amenity_kw:
            session.slots.property_amenities = []

        if any(w in lowered for w in ["metro", "مترو", "मेट्रो"]):
            if "Near Metro Station" not in session.slots.property_amenities:
                session.slots.property_amenities.append("Near Metro Station")
        elif "pool" in lowered or "مسبح" in lowered:
            if "Pool" not in session.slots.property_amenities:
                session.slots.property_amenities.append("Pool")
        elif "gym" in lowered or "جيم" in lowered:
            if "Gym" not in session.slots.property_amenities:
                session.slots.property_amenities.append("Gym")
        elif "balcony" in lowered or "شرفة" in lowered:
            if "Balcony" not in session.slots.property_amenities:
                session.slots.property_amenities.append("Balcony")

    @classmethod
    async def _generate_reply(cls, session: SessionContext, user_text: str) -> Dict[str, Any]:
        """
        Generates the conversational response. If an OpenAI API key is configured,
        it uses gpt-5-mini with function calling. Otherwise, it executes deterministic
        local reasoning ensuring the prototype is always live, fast, and testable.
        """
        lang = session.language
        client = LLMService.get_async_client()

        # If live OpenAI client available, invoke gpt-5-mini
        if client and settings.OPENAI_API_KEY:
            try:
                system_prompt = LLMService.get_system_prompt(lang)
                messages = [{"role": "system", "content": system_prompt}]
                for m in session.messages[-8:]:
                    messages.append({"role": m.role, "content": m.content})

                tool_choice = "auto"
                comp_data = None
                if session.active_intent == "property_comparison":
                    tool_choice = "none"
                    comp_data = PropertyDiscoveryService.compare_displayed_properties(session.last_recommended_properties)
                    comp_context = (
                        f"THE USER IS ASKING TO COMPARE / EVALUATE THE PROPERTIES CURRENTLY DISPLAYED ON THEIR SCREEN.\n"
                        f"Precalculated deterministic metrics (Rule 5: No LLM math, use these numbers directly):\n"
                        f"{json.dumps(comp_data, indent=2)}\n\n"
                        f"CRITICAL INSTRUCTIONS:\n"
                        f"- Compare the properties side-by-side using these precalculated figures (price, area sq.ft, price/sq.ft, monthly EMI, rental yields).\n"
                        f"- Provide a balanced investment advisory evaluation based on their goal (e.g., lower capital entry / cash-flow yield vs. capital growth & golf prestige).\n"
                        f"- Answer strictly in {lang}.\n"
                        f"- MANDATORY (Rule 10): Include the non-binding disclaimer: '(Indicative market comparison only; not binding financial advice)'."
                    )
                    messages.append({"role": "system", "content": comp_context})
                elif session.active_intent == "mortgage" and session.slots.mortgage_income:
                    tool_choice = {"type": "function", "function": {"name": "calc_affordability"}}
                elif session.active_intent == "property" and (session.slots.property_beds or session.slots.property_budget_max or session.slots.property_city):
                    is_exploratory = any(w in user_text.lower() for w in [
                        "where to invest", "best place", "best places", "places to invest", 
                        "best area", "best areas", "top areas", "top places", "names of the places",
                        "where can i invest", "where should i invest", "good place to invest", "options to invest"
                    ])
                    is_analytical = any(w in user_text.lower() for w in [
                        "average price", "average cost", "average size", "average pricing", "what is the average", "whats the average",
                        "how much on average", "price range", "متوسط سعر", "متوسط السعر", "औसत कीमत", "اوسط قیمت"
                    ])
                    is_search_request = any(w in user_text.lower() for w in [
                        "show", "find", "get", "need", "want", "search", "looking for", "provide", "give me", "list",
                        "ابحث", "اريد", "أريد", "دیکھو", "चाहिए", "दिखाइए"
                    ]) or (bool(session.slots.property_beds) and any(w in user_text.lower() for w in ["bhk", "bedroom", "br", "apartment", "villa", "townhouse"]))

                    if is_search_request and not is_analytical and not is_exploratory:
                        tool_choice = {"type": "function", "function": {"name": "search_properties"}}

                # If user already searched and has active inventory in session, inject metrics context for analytical questions
                if session.last_recommended_properties:
                    props = session.last_recommended_properties
                    total_count = len(props)
                    prices = [p.get("price", 0) for p in props if p.get("price")]
                    areas = [p.get("sq_ft") or p.get("sqft") or 0 for p in props if (p.get("sq_ft") or p.get("sqft"))]
                    avg_p = round(sum(prices) / len(prices)) if prices else 0
                    min_p = min(prices) if prices else 0
                    max_p = max(prices) if prices else 0
                    avg_a = round(sum(areas) / len(areas)) if areas else 0
                    inv_summary = (
                        f"ACTIVE DISPLAYED INVENTORY SUMMARY IN USER'S CURRENT SESSION:\n"
                        f"- Total active listings: {total_count}\n"
                        f"- Average price: AED {avg_p:,}\n"
                        f"- Price range: AED {min_p:,} to AED {max_p:,}\n"
                        f"- Average area: {avg_a} sq.ft\n"
                        f"CRITICAL INSTRUCTIONS:\n"
                        f"- If the user asks analytical questions about these active listings (e.g., 'what is the average price', 'average size', 'price range', 'what do you recommend among these'), "
                        f"answer directly and enthusiastically using these exact precalculated figures in {lang}!\n"
                        f"- Do NOT trigger a redundant search_properties tool call when answering analytical questions about these active listings."
                    )
                    messages.append({"role": "system", "content": inv_summary})

                response = await client.chat.completions.create(
                    model=settings.LLM_MODEL,
                    messages=messages,
                    tools=XO_FUNCTION_TOOLS,
                    tool_choice=tool_choice
                )

                choice = response.choices[0]
                reply_message = choice.message

                # Handle 2-step function calling loop
                if reply_message.tool_calls:
                    tool_call = reply_message.tool_calls[0]
                    fn_name = tool_call.function.name
                    fn_args = json.loads(tool_call.function.arguments)

                    tool_exec = await cls._execute_tool_raw(fn_name, fn_args, session)

                    # Build tool call message and tool response message
                    messages.append({
                        "role": "assistant",
                        "content": reply_message.content or "",
                        "tool_calls": [
                            {
                                "id": tool_call.id,
                                "type": "function",
                                "function": {
                                    "name": fn_name,
                                    "arguments": tool_call.function.arguments
                                }
                            }
                        ]
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(tool_exec.get("tool_result_for_llm", {}))
                    })

                    try:
                        second_response = await client.chat.completions.create(
                            model=settings.LLM_MODEL,
                            messages=messages
                        )
                        final_text = second_response.choices[0].message.content or ""
                    except Exception as e2:
                        logger.warning(f"Error in second LLM completion after tool call: {e2}")
                        narrative = await cls._execute_tool_and_narrate(fn_name, fn_args, session)
                        final_text = narrative.get("text", "")

                    return {
                        "text": final_text,
                        "property_results": tool_exec.get("property_results", []),
                        "mortgage_result": tool_exec.get("mortgage_result"),
                        "shortlist_status": tool_exec.get("shortlist_status"),
                        "kb_result": tool_exec.get("kb_result"),
                        "tool_calls": [{"function": fn_name, "args": fn_args}],
                        "metadata": tool_exec.get("metadata", {})
                    }

                if session.active_intent == "property_comparison":
                    return {
                        "text": reply_message.content or "",
                        "property_results": session.last_recommended_properties,
                        "metadata": {"comparison": comp_data}
                    }

                return {"text": reply_message.content or ""}
            except Exception as e:
                logger.warning(f"OpenAI LLM ({settings.LLM_MODEL}) call error: {e}. Executing prototype deterministic engine.")

        # High-Fidelity Prototype Deterministic Engine
        return await cls._deterministic_engine(session, user_text)

    @classmethod
    async def _execute_tool_raw(
        cls,
        fn_name: str,
        fn_args: Dict[str, Any],
        session: SessionContext
    ) -> Dict[str, Any]:
        """
        Executes gateway or calculation tool and returns structured data for both the UI
        and the LLM 2-step completion loop.
        """
        if fn_name == "search_properties":
            latest_msg = session.messages[-1].content.lower() if session.messages else ""
            is_broaden = any(w in latest_msg for w in ["other property", "other properties", "other options", "something else", "different property", "عقارات أخرى", "خيارات أخرى", "अन्य प्रॉपर्टी", "دوسری پراپرٹی"])

            raw_city = "Dubai" if is_broaden else fn_args.get("city", session.slots.property_city)
            if raw_city and raw_city.upper() in ["UAE", "ALL UAE", "ANYWHERE"]:
                city_filter = None
                location_name = "the UAE"
            else:
                city_filter = raw_city
                location_name = raw_city or "Dubai"

            b_max = None if is_broaden else fn_args.get("budget_max", session.slots.property_budget_max)
            req_amenities = fn_args.get("amenities") or (session.slots.property_amenities if session.slots.property_amenities else None)
            req_limit = fn_args.get("limit")

            filters = PropertySearchFilter(
                city=city_filter,
                type=fn_args.get("type", session.slots.property_type),
                budget_min=fn_args.get("budget_min", session.slots.property_budget_min),
                budget_max=b_max,
                beds=fn_args.get("beds", session.slots.property_beds),
                purpose=fn_args.get("purpose", session.slots.property_purpose),
                status=fn_args.get("status"),
                amenities=req_amenities,
                limit=req_limit
            )

            listings = PropertyDiscoveryService.search_and_rank(
                filters=filters,
                session_id=session.session_id
            )
            session.last_recommended_properties = listings

            count = len(listings)
            prices = [p.get("price", 0) for p in listings if p.get("price")]
            areas = [p.get("sq_ft") or p.get("sqft") or 0 for p in listings if (p.get("sq_ft") or p.get("sqft"))]
            avg_p = round(sum(prices) / len(prices)) if prices else 0
            min_p = min(prices) if prices else 0
            max_p = max(prices) if prices else 0
            avg_a = round(sum(areas) / len(areas)) if areas else 0

            tool_summary = {
                "status": "success",
                "location": location_name,
                "total_matching_properties": count,
                "average_price_aed": avg_p,
                "min_price_aed": min_p,
                "max_price_aed": max_p,
                "average_area_sqft": avg_a,
                "properties_sample": [
                    {
                        "id": p["id"],
                        "title": p.get("title", ""),
                        "price_aed": p.get("price", 0),
                        "beds": p.get("beds", 0),
                        "sqft": p.get("sq_ft") or p.get("sqft") or 0,
                        "location": p.get("location") or p.get("community", ""),
                        "amenities": p.get("amenities", [])
                    }
                    for p in listings[:6]
                ]
            }

            if count == 0:
                alts = PropertyDiscoveryService.find_catalog_alternatives(filters)
                tool_summary["catalog_alternatives"] = alts

                if alts.get("has_community_properties"):
                    tiers = [
                        f"{b['beds']}BR {b['type']} (starting from AED {b['starting_price_aed']:,.0f})"
                        for b in alts.get("available_beds_in_community", [])
                    ]
                    other_comm_tiers = [
                        f"{oc['community']} ({oc['beds']}BR from AED {oc['starting_price_aed']:,.0f})"
                        for oc in alts.get("other_communities_summary", [])[:3]
                    ]
                    guidance = (
                        f"CRITICAL INSTRUCTION: Exact search returned 0 matching listings in {location_name}. "
                        f"Do NOT say 'no listings found for {location_name}' or that {location_name} has no properties! "
                        f"Politely explain that while {filters.beds or 'the requested'}-bedroom units matching the exact search are not currently available in {location_name}, "
                        f"we DO have these residences available in {location_name}: {', '.join(tiers)}. "
                    )
                    if other_comm_tiers:
                        guidance += f"Additionally, {filters.beds or '1'}-bedroom units are available in neighboring prime communities: {', '.join(other_comm_tiers)}. "
                    guidance += (
                        f"Proactively ask the user if they'd like to explore the {location_name} options (e.g. 2BHK or 3BHK) "
                        f"or see {filters.beds or '1'}-bedroom residences in neighboring communities like Dubai Marina, Downtown Dubai, or Business Bay."
                    )
                    tool_summary["guidance_for_assistant"] = guidance
                elif alts.get("has_other_comm_alternatives"):
                    other_comm_tiers = [
                        f"{oc['community']} ({oc['beds']}BR from AED {oc['starting_price_aed']:,.0f})"
                        for oc in alts.get("other_communities_summary", [])[:3]
                    ]
                    tool_summary["guidance_for_assistant"] = (
                        f"No active listings match the criteria in {location_name}. "
                        f"However, matching {filters.beds or ''}-bedroom properties are available in: {', '.join(other_comm_tiers)}. "
                        f"Proactively recommend exploring these alternative communities or broadening across Dubai."
                    )
                else:
                    tool_summary["guidance_for_assistant"] = (
                        f"No listings found matching criteria in {location_name}. Suggest broadening the search across Dubai or adjusting the budget and bedroom filters."
                    )

            return {
                "property_results": listings,
                "location_name": location_name,
                "filters": filters,
                "tool_result_for_llm": tool_summary
            }

        elif fn_name == "calc_affordability":
            income = float(fn_args.get("income", session.slots.mortgage_income or 25000.0))
            debt = float(fn_args.get("existing_debt", session.slots.mortgage_existing_debt or 0.0))
            down_payment = float(fn_args.get("down_payment", session.slots.mortgage_down_payment or 0.0))
            term = int(fn_args.get("term", 25))
            rate = float(fn_args.get("rate_assumption", 4.49))

            afford_res = MortgageCalculationService.calc_affordability(
                AffordabilityInput(
                    income=income,
                    existing_debt=debt,
                    down_payment=down_payment,
                    term=term,
                    rate_assumption=rate,
                    consent_given=True
                ),
                session_id=session.session_id,
                user_id=session.user_id
            )
            session.last_mortgage_result = afford_res
            return {
                "mortgage_result": afford_res,
                "income": income,
                "tool_result_for_llm": afford_res
            }

        elif fn_name == "calc_emi":
            loan = float(fn_args.get("loan_amount", 1000000.0))
            rate = float(fn_args.get("interest_rate", 4.49))
            tenure = int(fn_args.get("tenure", 25))
            freq = str(fn_args.get("frequency", "monthly"))

            emi_res = MortgageCalculationService.calc_emi(
                EMIInput(
                    loan_amount=loan,
                    interest_rate=rate,
                    tenure=tenure,
                    frequency=freq
                ),
                session_id=session.session_id,
                user_id=session.user_id
            )
            session.last_mortgage_result = emi_res
            return {
                "mortgage_result": emi_res,
                "loan": loan,
                "rate": rate,
                "tenure": tenure,
                "tool_result_for_llm": emi_res
            }

        elif fn_name == "refine_property_search":
            refinement = PropertyDiscoveryService.refine_search(
                session_id=session.session_id,
                refinement_text=fn_args.get("refinement_text", ""),
                nationality="expat"
            )
            listings = refinement.get("properties", [])
            session.last_recommended_properties = listings
            return {
                "property_results": listings,
                "refinement": refinement,
                "tool_result_for_llm": refinement
            }

        elif fn_name == "shortlist_property":
            raw_pid = fn_args.get("property_id", "")
            target_pid = raw_pid
            ord_match = re.search(r'#?(\d+)', str(raw_pid))
            if ord_match and session.last_recommended_properties:
                idx = int(ord_match.group(1)) - 1
                if 0 <= idx < len(session.last_recommended_properties):
                    target_pid = session.last_recommended_properties[idx]["id"]

            shortlist_res = PropertyDiscoveryService.shortlist_property(
                session_id=session.session_id,
                property_id=target_pid,
                user_id=session.user_id
            )
            return {
                "shortlist_status": shortlist_res,
                "property_id": target_pid,
                "tool_result_for_llm": shortlist_res
            }

        elif fn_name == "compare_properties":
            comp = PropertyDiscoveryService.compare_displayed_properties(session.last_recommended_properties)
            return {
                "property_results": session.last_recommended_properties,
                "metadata": {"comparison": comp},
                "tool_result_for_llm": comp
            }

        elif fn_name == "get_mortgage_products":
            prods = MortgageRulesGateway.get_mortgage_products(
                bank=fn_args.get("bank"),
                rate_type=fn_args.get("rate_type"),
                salary=fn_args.get("salary"),
                nationality=fn_args.get("nationality"),
                finance_type=fn_args.get("finance_type"),
                session_id=session.session_id
            )
            return {
                "mortgage_products": prods,
                "tool_result_for_llm": {"count": len(prods), "products": prods[:5]}
            }

        elif fn_name in ["get_my_saved_properties", "get_my_application_status"]:
            if not session.user_id:
                return {
                    "tool_result_for_llm": {"status": "auth_required", "message": "Sign in required to view account data"}
                }
            return {
                "tool_result_for_llm": {"status": "authenticated", "user_id": session.user_id, "saved_count": 2, "active_applications": 1}
            }

        elif fn_name == "retrieve_kb":
            from app.services.rag_service import RAGService
            kb_query = fn_args.get("query", "")
            kb_res = RAGService.retrieve_kb(kb_query, session_id=session.session_id)
            return {
                "kb_result": kb_res,
                "tool_result_for_llm": kb_res
            }

        return {"tool_result_for_llm": {"status": "executed"}}

    @classmethod
    async def _execute_tool_and_narrate(
        cls,
        fn_name: str,
        fn_args: Dict[str, Any],
        session: SessionContext
    ) -> Dict[str, Any]:
        """
        Executes scoped API gateway or deterministic calculation tools
        and narrates the result strictly conforming to Rule 5, Rule 4, and Rule 10.
        """
        lang = session.language
        raw_res = await cls._execute_tool_raw(fn_name, fn_args, session)

        if fn_name == "calc_affordability":
            afford_res = raw_res["mortgage_result"]
            income = raw_res["income"]
            summary = afford_res["affordability_summary"]
            narratives = {
                "ar": f"بناءً على ضوابط مصرف الإمارات المركزي (سقف 50% لعبء الدين)، بدخل شهري {income:,.0f} درهم، فإن القسط الشهري الأقصى التقديري هو {summary['max_allowable_monthly_emi_aed']:,.0f} درهم، مما يتيح لك تمويلاً أقصى يصل إلى {summary['max_borrowing_capacity_aed']:,.0f} درهم وميزانية شراء حتى {summary['max_property_price_aed']:,.0f} درهم ({afford_res['disclaimer']}).",
                "hi": f"यूएई सेंट्रल बैंक के 50% डीबीआर कैप के अनुसार, {income:,.0f} AED मासिक आय पर आपकी अधिकतम मासिक ईएमआई {summary['max_allowable_monthly_emi_aed']:,.0f} AED बनती है, जिससे {summary['max_borrowing_capacity_aed']:,.0f} AED का अधिकतम लोन और {summary['max_property_price_aed']:,.0f} AED तक की प्रॉपर्टी खरीदी जा सकती है ({afford_res['disclaimer']})।",
                "ur": f"یو اے ای سنٹرل بینک کے 50% DBR ضابطے کے تحت، {income:,.0f} درہم ماہانہ آمدنی پر آپ کی زیادہ سے زیادہ متوقع ماہانہ قسط {summary['max_allowable_monthly_emi_aed']:,.0f} درہم ہے، جس سے آپ کو {summary['max_borrowing_capacity_aed']:,.0f} درہم تک کا قرض اور {summary['max_property_price_aed']:,.0f} درہم تک کی پراپرٹی بجٹ حاصل ہو سکتی ہے ({afford_res['disclaimer']})۔",
                "en": f"Based on UAE Central Bank rules (50% DBR cap), for a monthly income of AED {income:,.0f}, your maximum estimated monthly installment is AED {summary['max_allowable_monthly_emi_aed']:,.0f}, giving an estimated borrowing capacity of AED {summary['max_borrowing_capacity_aed']:,.0f} and an affordable property purchase price of up to AED {summary['max_property_price_aed']:,.0f} ({afford_res['disclaimer']})."
            }
            return {
                "text": narratives.get(lang, narratives["en"]),
                "mortgage_result": afford_res,
                "tool_calls": [{"function": fn_name, "args": fn_args}]
            }

        elif fn_name == "calc_emi":
            emi_res = raw_res["mortgage_result"]
            loan = raw_res["loan"]
            rate = raw_res["rate"]
            tenure = raw_res["tenure"]
            narratives = {
                "ar": f"لقرض تمويلي قدره {loan:,.0f} درهم بفائدة {rate}% على مدار {tenure} سنة، فإن القسط الشهري التقديري هو {emi_res['periodic_installment_aed']:,.0f} درهم ({emi_res['disclaimer']}). إجمالي الفائدة المستحقة طوال الفترة هو {emi_res['total_interest_payable_aed']:,.0f} درهم.",
                "hi": f"{loan:,.0f} AED लोन राशि पर {rate}% ब्याज दर और {tenure} साल की अवधि के लिए आपकी अनुमानित मासिक ईएमआई {emi_res['periodic_installment_aed']:,.0f} AED होगी ({emi_res['disclaimer']})। कुल देय ब्याज {emi_res['total_interest_payable_aed']:,.0f} AED है।",
                "ur": f"{loan:,.0f} درہم کے قرض پر {rate}% سود اور {tenure} سال کی مدت کے لیے، متوقع ماہانہ قسط {emi_res['periodic_installment_aed']:,.0f} درہم ہوگی ({emi_res['disclaimer']})۔ کل قابلِ ادائیگی سود {emi_res['total_interest_payable_aed']:,.0f} درہم ہے۔",
                "en": f"For a loan amount of AED {loan:,.0f} at {rate}% annual interest over {tenure} years, your estimated monthly payment is AED {emi_res['periodic_installment_aed']:,.0f} ({emi_res['disclaimer']}). Total interest payable over the term is AED {emi_res['total_interest_payable_aed']:,.0f}."
            }
            return {
                "text": narratives.get(lang, narratives["en"]),
                "mortgage_result": emi_res,
                "tool_calls": [{"function": fn_name, "args": fn_args}]
            }

        elif fn_name == "search_properties":
            listings = raw_res.get("property_results", [])
            location_name = raw_res.get("location_name", "Dubai")
            filters = raw_res.get("filters")
            if len(listings) > 0:
                narratives = {
                    "ar": f"لقد وجدت {len(listings)} عقارات تناسب بحثك في {location_name}. يمكنك التحقق من قسط الرهن العقاري التقديري أو حفظها في قائمتك المفضلة.",
                    "hi": f"मुझे {location_name} में आपकी प्राथमिकताओं के अनुसार {len(listings)} बेहतरीन प्रॉपर्टीज मिली हैं। आप हर प्रॉपर्टी के लिए ईएमआई चेक कर सकते हैं या उन्हें शॉर्टलिस्ट कर सकते हैं।",
                    "ur": f"مجھے {location_name} میں آپ کی تلاش کے مطابق {len(listings)} مناسب پراپرٹیز ملی ہیں۔ آپ ہر پراپرٹی کے لیے مارگیج قسط چیک کر سکتے ہیں یا شارٹ لسٹ کر سکتے ہیں۔",
                    "en": f"I found {len(listings)} premier properties matching your criteria in {location_name}. You can check estimated mortgage payments or shortlist any property."
                }
                text_out = narratives.get(lang, narratives["en"])
            else:
                alts = PropertyDiscoveryService.find_catalog_alternatives(filters)
                text_out = cls._format_catalog_fallback_narrative(filters, location_name, alts, lang)

            return {
                "text": text_out,
                "property_results": listings,
                "tool_calls": [{"function": fn_name, "args": fn_args}]
            }

        elif fn_name == "refine_property_search":
            listings = raw_res.get("property_results", [])
            refinement = raw_res.get("refinement", {})
            narratives = {
                "ar": f"تم تحديث البحث حسب تفضيلك. إليك {len(listings)} خيارات معدلة تناسب طلبك:",
                "hi": f"आपकी प्राथमिकता के आधार पर सर्च को रिफाइन कर दिया गया है। यहाँ {len(listings)} अपडेटेड विकल्प हैं:",
                "ur": f"آپ کی ترجیح کے مطابق نتائج کو اپ ڈیٹ کر دیا گیا ہے۔ یہ رہے {len(listings)} اپ ڈیٹڈ آپشنز:",
                "en": f"I have refined your search based on your preference ({refinement.get('action')}). Here are {len(listings)} updated recommendations:"
            }
            return {
                "text": narratives.get(lang, narratives["en"]),
                "property_results": listings,
                "tool_calls": [{"function": fn_name, "args": fn_args}]
            }

        elif fn_name == "shortlist_property":
            shortlist_res = raw_res.get("shortlist_status", {})
            target_pid = raw_res.get("property_id", "")
            if shortlist_res.get("success"):
                title = shortlist_res.get("property_title", target_pid)
                status_word = "saved to" if shortlist_res.get("status") == "saved" else "removed from"
                reply = f"Property '{title}' has been {status_word} your shortlist (Total: {shortlist_res.get('total_shortlisted', 0)})."
                if shortlist_res.get("requires_lead_capture"):
                    reply += " Since you are browsing as a guest, please share your email or phone to keep your shortlist saved and receive property brochures."
            else:
                reply = shortlist_res.get("error", "Unable to shortlist property.")

            return {
                "text": reply,
                "shortlist_status": shortlist_res,
                "tool_calls": [{"function": fn_name, "args": fn_args}]
            }

        elif fn_name == "compare_properties":
            comp = raw_res.get("metadata", {}).get("comparison", {})
            reply = cls._format_comparison_narrative(comp, lang)
            return {
                "text": reply,
                "property_results": session.last_recommended_properties,
                "metadata": {"comparison": comp},
                "tool_calls": [{"function": fn_name, "args": fn_args}]
            }

        elif fn_name == "get_mortgage_products":
            prods = raw_res.get("mortgage_products", [])
            return {
                "text": f"Found {len(prods)} mortgage products matching your criteria from UAE partner banks.",
                "tool_calls": [{"function": fn_name, "args": fn_args}]
            }

        elif fn_name in ["get_my_saved_properties", "get_my_application_status"]:
            if not session.user_id:
                return {
                    "text": "Please sign in to access your saved properties and application status.",
                    "tool_calls": [{"function": fn_name, "args": fn_args}]
                }
            return {
                "text": f"Retrieved profile for user {session.user_id}. You have 2 saved properties and 1 active pre-qualification application in Vault CRM.",
                "tool_calls": [{"function": fn_name, "args": fn_args}]
            }

        elif fn_name == "retrieve_kb":
            kb_res = raw_res.get("kb_result", {})
            if kb_res.get("status") == "success":
                short_ans = kb_res.get("short_answer", "")
                detail = kb_res.get("detail", "")
                disc = kb_res.get("disclaimer", "")
                text = f"{short_ans}\n\n{detail}"
                if disc:
                    text += f"\n\n*(Legal Disclaimer: {disc})*"
            elif kb_res.get("status") == "scope_restricted":
                text = kb_res.get("message", "")
            else:
                text = kb_res.get("message", "Sorry, that topic is outside of my knowledge base.")
            return {
                "text": text,
                "kb_result": kb_res,
                "tool_calls": [{"function": fn_name, "args": fn_args}]
            }

        return {
            "text": "Your request has been processed.",
            "tool_calls": [{"function": fn_name, "args": fn_args}]
        }

    @classmethod
    async def _deterministic_engine(cls, session: SessionContext, user_text: str) -> Dict[str, Any]:
        """
        High-fidelity prototype engine implementing PRD flows:
        - Property search & ranked matches
        - Guided slot-filling questions (FR-4)
        - Mortgage affordability cross-sell (FR-11)
        - Pure deterministic math engine (Rule 5)
        - Multilingual responses in EN, AR, HI, UR
        """
        lang = session.language
        intent = session.active_intent

        # Explicit language switch requests
        if LanguageDetector.check_explicit_language_switch(user_text):
            greetings = {
                "ar": "أهلاً بك! بكل سرور، يسعدني جداً التحدث معك باللغة العربية! 🎉 كيف يمكنني مساعدتك اليوم بخصوص عقارات دبي أو حساب التمويل العقاري؟",
                "hi": "नमस्ते! मुझे आपके साथ हिंदी में बातचीत करने में बहुत खुशी होगी! 🎉 आज मैं आपकी क्या सहायता कर सकता हूँ?",
                "ur": "خوش آمدید! مجھے آپ سے اردو میں بات چیت کر کے بہت خوشی ہو رہی ہے! 🎉 آج میں دبئی میں پراپرٹیز یا مارگیج کے حوالے سے آپ کی کیا مدد کر سکتا ہوں؟",
                "en": "Welcome! I'm thrilled to chat with you in English! 🎉 How can I assist you today with premier UAE properties or mortgage financing?"
            }
            return {
                "text": greetings.get(lang, greetings["en"]),
                "property_results": []
            }

        # Check for average price or size statistical inquiry
        avg_inquiry = any(w in user_text.lower() for w in ["average price", "average pricing", "average cost", "average size", "متوسط سعر", "متوسط السعر", "औसत कीमत", "اوسط قیمت"])
        if avg_inquiry:
            props = session.last_recommended_properties
            if not props and session.slots.property_beds:
                filters = PropertySearchFilter(
                    city=session.slots.property_city or "Dubai Marina",
                    beds=session.slots.property_beds,
                    type=session.slots.property_type or "apartment"
                )
                props = PropertyDiscoveryService.search_and_rank(filters, session.session_id)
            if props:
                prices = [p.get("price", 0) for p in props if p.get("price")]
                areas = [p.get("sq_ft") or p.get("sqft") or 0 for p in props if (p.get("sq_ft") or p.get("sqft"))]
                avg_p = round(sum(prices) / len(prices)) if prices else 0
                min_p = min(prices) if prices else 0
                max_p = max(prices) if prices else 0
                avg_a = round(sum(areas) / len(areas)) if areas else 0
                narratives = {
                    "ar": f"متوسط سعر الشقق المكونة من {session.slots.property_beds or 1} غرف في {session.slots.property_city or 'دبي مارينا'} هو {avg_p:,.0f} درهم إماراتي (تتراوح الأسعار بين {min_p:,.0f} و {max_p:,.0f} درهم بمتوسط مساحة {avg_a} قدم مربع). 🎉",
                    "hi": f"{session.slots.property_city or 'दुबई मरीना'} में {session.slots.property_beds or 1} बीएचके अपार्टमेंट्स की औसत कीमत {avg_p:,.0f} AED है (कीमतें {min_p:,.0f} से {max_p:,.0f} AED के बीच हैं)। 🎉",
                    "ur": f"{session.slots.property_city or 'دبئی مرینا'} میں {session.slots.property_beds or 1} بی ایچ کے اپارٹمنٹس کی اوسط قیمت {avg_p:,.0f} درہم ہے (قیمتیں {min_p:,.0f} سے {max_p:,.0f} درہم کے درمیان ہیں)۔ 🎉",
                    "en": f"The average price for {session.slots.property_beds or 1} BHK apartments in {session.slots.property_city or 'Dubai Marina'} is AED {avg_p:,.0f} (ranging from AED {min_p:,.0f} to AED {max_p:,.0f} with an average size of {avg_a} sq.ft)! 🎉"
                }
                return {
                    "text": narratives.get(lang, narratives["en"]),
                    "property_results": []
                }

        # 0. PROPERTY COMPARISON & EVALUATION INTENT (FR-9)
        if intent == "property_comparison":
            comp = PropertyDiscoveryService.compare_displayed_properties(session.last_recommended_properties)
            reply = cls._format_comparison_narrative(comp, lang)
            return {
                "text": reply,
                "property_results": session.last_recommended_properties,
                "metadata": {"comparison": comp},
                "tool_calls": [{"function": "compare_properties", "args": {}}]
            }

        # 1. PROPERTY DISCOVERY INTENT
        if intent == "property":
            # Check for shortlisting request: "save #1", "shortlist #2", "save property"
            is_filter_shortlist = any(w in user_text.lower() for w in ["shortlist those", "shortlist only", "shortlist the ones", "only shortlist"])
            if not is_filter_shortlist and any(w in user_text.lower() for w in ["shortlist #", "save #", "save property", "shortlist this", "احفظ", "पसंदीदा", "محفوظ"]):
                raw_pid = None
                ord_match = re.search(r'#?(\d+)', user_text)
                if ord_match and session.last_recommended_properties:
                    idx = int(ord_match.group(1)) - 1
                    if 0 <= idx < len(session.last_recommended_properties):
                        raw_pid = session.last_recommended_properties[idx]["id"]
                elif session.last_recommended_properties:
                    raw_pid = session.last_recommended_properties[0]["id"]

                if raw_pid:
                    shortlist_res = PropertyDiscoveryService.shortlist_property(
                        session_id=session.session_id,
                        property_id=raw_pid,
                        user_id=session.user_id
                    )
                    reply = f"Property '{shortlist_res.get('property_title', raw_pid)}' has been {shortlist_res.get('status')} in your shortlist (Total: {shortlist_res.get('total_shortlisted', 0)})."
                    if shortlist_res.get("requires_lead_capture"):
                        reply += " Please enter your email or WhatsApp number to keep your shortlist saved."
                    return {
                        "text": reply,
                        "shortlist_status": shortlist_res,
                        "tool_calls": [{"function": "shortlist_property", "args": {"property_id": raw_pid}}]
                    }

            # Check for refinement: "cheaper", "more bedrooms", "like #2", "closer to", "near", "metro", "only shortlist those"
            if session.last_recommended_properties and any(w in user_text.lower() for w in ["cheaper", "more bedroom", "fewer bedroom", "luxury", "like #", "similar to", "close to", "near", "metro", "مترو", "only those", "with metro", "only shortlist", "shortlist those"]):
                refinement = PropertyDiscoveryService.refine_search(
                    session_id=session.session_id,
                    refinement_text=user_text,
                    nationality="expat"
                )
                listings = refinement.get("properties", [])
                return {
                    "text": f"I refined your property recommendations based on your request ({refinement.get('action')}). Here are {len(listings)} matching options:",
                    "property_results": listings,
                    "tool_calls": [{"function": "refine_property_search", "args": {"refinement_text": user_text}}]
                }

            # Check for general "other property" requests after zero or previous search
            if any(w in user_text.lower() for w in ["other property", "other properties", "other options", "something else", "different property", "عقارات أخرى", "خيارات أخرى", "अन्य प्रॉपर्टी", "دوسری پراپرٹی"]):
                session.slots.property_city = "Dubai"

            beds = session.slots.property_beds
            budget = session.slots.property_budget_max
            city = session.slots.property_city
            ptype = session.slots.property_type
            purpose = session.slots.property_purpose

            # Check if user is asking exploratory investment questions (places, areas, where to invest)
            investment_place_inquiry = any(w in user_text.lower() for w in [
                "where to invest", "best place", "best places", "places to invest", 
                "best area", "best areas", "top areas", "top places", "names of the places",
                "where can i invest", "where should i invest", "good place to invest", "options to invest",
                "أفضل منطقة", "أين أستثمر", "أماكن للاستثمار", "مناطق الاستثمار",
                "निवेश के लिए सबसे अच्छी जगह", "कहाँ निवेश करें", "انویسٹ کرنے کے لیے بہترین جگہ", "کہاں سرمایہ کاری کریں"
            ])
            if investment_place_inquiry:
                guidance = {
                    "en": (
                        "Here are the premier investment destinations across Dubai to consider based on current market dynamics:\n\n"
                        "1. **Downtown Dubai**: Iconic hub with high tenant demand, strong liquidity, and steady capital appreciation.\n"
                        "2. **Dubai Marina & JBR**: High-demand waterfront living with consistent short-term & holiday rental yields.\n"
                        "3. **Business Bay**: Prime commercial & residential corridor adjacent to Downtown with attractive entry prices.\n"
                        "4. **Palm Jumeirah**: World-renowned luxury island commanding premier capital value and ultra-luxury demand.\n"
                        "5. **Dubai Hills Estate**: Master-planned golf and park community favored by families for long-term growth.\n"
                        "6. **Dubai Creek Harbour**: Emerging waterfront district positioned for substantial future infrastructure growth.\n"
                        "7. **JVC (Jumeirah Village Circle)**: Top-tier gross rental yields (7%–8%+) ideal for cash-flow focused investors.\n\n"
                        "*(Guidance and market overview only; not binding financial advice)*. Which of these communities would you like to explore live listings in?"
                    ),
                    "ar": (
                        "إليك أبرز الوجهات الاستثمارية الرائدة في دبي بناءً على حركة السوق الحالية:\n\n"
                        "1. **وسط مدينة دبي (Downtown)**: طلب إيجاري مرتفع ونمو قوي في القيمة الرأسمالية.\n"
                        "2. **دبي مارينا وJBR**: وجهة بحرية حيوية وعوائد إيجارية ممتازة.\n"
                        "3. **الخليج التجاري (Business Bay)**: موقع استراتيجي محاذي لوسط المدينة بأسعار دخول مجدية.\n"
                        "4. **نخلة جميرا**: عنوان الفخامة العالمية والطلب الفائق على العقارات الفاخرة.\n"
                        "5. **دبي هيلز استيت**: مجمع متكامل للمجولف والحدائق ومثالي للعائلات.\n"
                        "6. **خور دبي (Creek Harbour)**: منطقة واعدة بنمو مستقبلي كبير.\n"
                        "7. **قرية جميرا الدائرية (JVC)**: عوائد إيجارية مرتفعة (7%–8%+) للمستثمرين الباحثين عن التدفق النقدي.\n\n"
                        "*(معلومات إرشادية فقط؛ لا تعتبر مشورة مالية ملزمة)*. هل ترغب في استعراض العقارات المتاحة في أي من هذه المناطق؟"
                    ),
                    "hi": (
                        "मौजूदा बाज़ार के अनुसार दुबई में निवेश के लिए शीर्ष इलाके निम्नलिखित हैं:\n\n"
                        "1. **डाउनटाउन दुबई**: उच्च मांग और मजबूत कैपिटल एप्रिसिएशन।\n"
                        "2. **दुबई मरीना और JBR**: वाटरफ्रंट लाइफस्टाइल और बेहतरीन रेंटल यील्ड।\n"
                        "3. **बिजनेस बे**: डाउनटाउन के नज़दीक और आकर्षक निवेश विकल्प।\n"
                        "4. **पाम जुमेराह**: विश्वस्तरीय लग्जरी और प्रीमियम विला व अपार्टमेंट्स।\n"
                        "5. **दुबई हिल्स एस्टेट**: गोल्फ और पार्कों से भरपूर फैमिली कम्युनिटी।\n"
                        "6. **दुबई क्रीक हार्बर**: भविष्य के बड़े विकास और शानदार रिटर्न के लिए।\n"
                        "7. **JVC**: उच्च रेंटल रिटर्न (7%–8%+) के लिए सबसे पसंदीदा।\n\n"
                        "*(केवल सांकेतिक मार्गदर्शन; बाध्यकारी वित्तीय सलाह नहीं)*। आप इनमें से किस इलाके की प्रॉपर्टीज देखना चाहेंगे?"
                    ),
                    "ur": (
                        "دبئی میں سرمایہ کاری کے لیے موجودہ مارکیٹ کے مطابق بہترین علاقے درج ذیل ہیں:\n\n"
                        "1. **ڈاؤن ٹاؤن دبئی**: بلند مانگ اور بہترین کیپیٹل اپریسی ایشن۔\n"
                        "2. **دبئی مرینا اور JBR**: شاندار واٹر فرنٹ اور بہترین رینٹل ریٹرنز۔\n"
                        "3. **بزنس بے**: ڈاؤن ٹاؤن کے قریب اور بہترین سرمایہ کاری مواقع۔\n"
                        "4. **پام جمیرہ**: دنیا کا مشہور پرتعیش جزیرہ اور ہائی ویلیو پراپرٹیز۔\n"
                        "5. **دبئی ہلز اسٹیٹ**: فیملیز کے لیے پرسکون ماحول اور طویل مدتی منافع۔\n"
                        "6. **دبئی کریک ہاربر**: مستقبل کی شاندار گروتھ اور نئے انفراسٹرکچر والا علاقہ۔\n"
                        "7. **JVC**: زیادہ رینٹل آمدنی (7%–8%+) حاصل کرنے کے لیے بہترین۔\n\n"
                        "*(صرف رہنمائی اور مارکیٹ جائزہ؛ حتمی مالیاتی مشورہ نہیں)*۔ آپ ان میں سے کس علاقے میں پراپرٹیز دیکھنا چاہیں گے؟"
                    )
                }
                return {"text": guidance.get(lang, guidance["en"])}

            # Check if key filters are present or ask clarifying questions (FR-4, FR-7)
            if not beds and not budget and not city:
                questions = {
                    "ar": "يسعدني مساعدتك في العثور على العقار المثالي في الإمارات! هل تبحث عن شراء للسكن أم للاستثمار، وما هو نوع العقار وعدد غرف النوم والميزانية التقريبية؟",
                    "hi": "दुबई में आपकी पसंदीदा प्रॉपर्टी खोजने में मुझे ख़ुशी होगी! आप रहने के लिए खरीद रहे हैं या निवेश के लिए, अपार्टमेंट या विला, और कितने बेडरूम?",
                    "ur": "دبئی میں آپ کی پسندیدہ پراپرٹی تلاش کرنے میں مجھے خوشی ہوگی! آپ رہائش کے لیے خرید رہے ہیں یا سرمایہ کاری کے لیے، اور آپ کا کتنا بجٹ ہے؟",
                    "en": "I'd be delighted to help you discover premier properties in the UAE! Are you looking for an apartment or villa, how many bedrooms, and what is your approximate budget?"
                }
                return {"text": questions.get(lang, questions["en"])}

            # Handle broad UAE search vs specific city
            raw_city = city
            if raw_city and raw_city.upper() in ["UAE", "ALL UAE", "ANYWHERE"]:
                city_filter = None
                display_city = "the UAE"
            else:
                city_filter = raw_city
                display_city = raw_city or "Dubai"

            # Query live Property Inventory API Gateway (FR-8, FR-11)
            filters = PropertySearchFilter(
                city=city_filter,
                type=ptype,
                budget_max=budget,
                beds=beds,
                purpose=purpose,
                amenities=session.slots.property_amenities or None
            )
            listings = PropertyDiscoveryService.search_and_rank(
                filters=filters,
                session_id=session.session_id
            )

            if len(listings) > 0:
                reply_templates = {
                    "ar": f"لقد وجدت {len(listings)} عقارات مميزة تناسب معاييرك في {display_city}. يمكنك التحقق من قسط الرهن العقاري التقديري أو حفظها في قائمتك المفضلة.",
                    "hi": f"मुझे आपके बजट और प्राथमिकताओं के अनुसार {display_city} में {len(listings)} बेहतरीन प्रॉपर्टीज मिली हैं। आप हर प्रॉपर्टी के लिए ईएमआई चेक कर सकते हैं या उन्हें शॉर्टलिस्ट कर सकते हैं।",
                    "ur": f"مجھے آپ کی ترجیحات کے مطابق {display_city} میں {len(listings)} بہترین پراپرٹیز ملی ہیں۔ کیا آپ ان پراپرٹیز کے لیے مارگیج قسط چیک کرنا چاہتے ہیں یا شارٹ لسٹ کرنا چاہتے ہیں؟",
                    "en": f"I found {len(listings)} prime properties matching your preferences in {display_city}. Every listing includes estimated mortgage payments, or you can shortlist your favorites."
                }
                text_out = reply_templates.get(lang, reply_templates["en"])
            else:
                alts = PropertyDiscoveryService.find_catalog_alternatives(filters)
                text_out = cls._format_catalog_fallback_narrative(filters, display_city, alts, lang)

            return {
                "text": text_out,
                "property_results": listings,
                "tool_calls": [{"function": "search_properties", "args": {"beds": beds, "budget_max": budget, "city": city}}]
            }

        # 2. MORTGAGE INTENT
        elif intent == "mortgage":
            # Check for required inputs: income, debt, down payment
            income = session.slots.mortgage_income
            if not income:
                questions = {
                    "ar": "لحساب قدرتك التمويلية والقسط الشهري بدقة، هل يمكنك تزويدي بصافي دخلك الشهري (بالدرهم) وأي التزامات مالية حالية؟",
                    "hi": "आपकी मॉर्गेज पात्रता और मासिक किस्त (EMI) की गणना के लिए, कृपया अपनी मासिक आय (AED में) और मौजूदा लोन/कर्ज बताएं?",
                    "ur": "آپ کی مارگیج اہلیت اور ماہانہ قسط کا تخمینہ لگانے کے لیے، براہ کرم اپنی ماہانہ آمدنی (AED میں) اور موجودہ واجبات بتائیں؟",
                    "en": "To calculate your indicative mortgage affordability and monthly payment, what is your approximate monthly income in AED and any existing monthly debt obligations?"
                }
                return {"text": questions.get(lang, questions["en"])}

            # Deterministic calculation using pure math service (Rule 5)
            debt = session.slots.mortgage_existing_debt or 0.0
            down_payment = session.slots.mortgage_down_payment or 0.0
            afford_res = MortgageCalculationService.calc_affordability(
                AffordabilityInput(
                    income=income,
                    existing_debt=debt,
                    down_payment=down_payment,
                    term=25,
                    rate_assumption=4.49,
                    consent_given=True
                ),
                session_id=session.session_id,
                user_id=session.user_id
            )
            session.last_mortgage_result = afford_res
            summary = afford_res["affordability_summary"]
            max_monthly_emi = summary["max_allowable_monthly_emi_aed"]
            indicative_loan = summary["max_borrowing_capacity_aed"]
            max_prop_price = summary["max_property_price_aed"]

            responses = {
                "ar": f"بناءً على دخل شهري قدره {income:,.0f} درهم ونسبة عبء الدين القصوى (50%)، فإن الحد الأقصى للقسط الشهري التقديري هو {max_monthly_emi:,.0f} درهم، مما يتيح لك تمويلاً تقريبياً قدره {indicative_loan:,.0f} درهم وميزانية شراء تصل إلى {max_prop_price:,.0f} درهم ({afford_res['disclaimer']}). هل ترغب في استعراض العقارات المطابقة لهذه الميزانية؟",
                "hi": f"आपकी {income:,.0f} AED मासिक आय और यूएई सेंट्रल बैंक के 50% डीबीआर नियम के आधार पर, आपकी अधिकतम अनुमानित ईएमआई {max_monthly_emi:,.0f} AED है, जिससे लगभग {indicative_loan:,.0f} AED का लोन और {max_prop_price:,.0f} AED तक की प्रॉपर्टी संभव है ({afford_res['disclaimer']})। क्या आप इस बजट में प्रॉपर्टीज देखना चाहते हैं?",
                "ur": f"آپ کی {income:,.0f} درہم ماہانہ آمدنی اور UAE سینٹرل بینک کے 50% DBR ضابطے کے تحت، متوقع ماہانہ قسط تقریباً {max_monthly_emi:,.0f} درہم بنتی ہے، جس سے تقریباً {indicative_loan:,.0f} درہم کا قرض اور {max_prop_price:,.0f} درہم تک کی پراپرٹی ممکن ہے ({afford_res['disclaimer']})۔ کیا آپ اس بجٹ میں دستیاب پراپرٹیز دیکھنا چاہتے ہیں؟",
                "en": f"Based on a monthly income of AED {income:,.0f} and the UAE Central Bank 50% Debt Burden Ratio cap, your estimated maximum monthly payment is AED {max_monthly_emi:,.0f}, indicating an estimated borrowing capacity of approximately AED {indicative_loan:,.0f} and maximum property price of AED {max_prop_price:,.0f} ({afford_res['disclaimer']}). Would you like to view matching properties within this budget?"
            }

            return {
                "text": responses.get(lang, responses["en"]),
                "mortgage_result": afford_res,
                "tool_calls": [{"function": "calc_affordability", "args": {"income": income, "debt": debt, "down_payment": down_payment}}]
            }

        # 3. ACCOUNT INTENT
        elif intent == "account":
            if not session.user_id:
                auth_prompts = {
                    "ar": "للوصول إلى عقاراتك المحفوظة أو حالة طلب التمويل، يرجى تسجيل الدخول لحماية بياناتك الشخصية.",
                    "hi": "अपनी सेव की गई प्रॉपर्टीज या लोन आवेदन का स्टेटस देखने के लिए कृपया लॉग इन करें।",
                    "ur": "اپنی محفوظ شدہ پراپرٹیز یا مارگیج درخواست کا اسٹیٹس جاننے کے لیے براہ کرم لاگ ان کریں۔",
                    "en": "To access your shortlisted properties or mortgage application status, please sign in. All account data is strictly protected and user-scoped."
                }
                return {"text": auth_prompts.get(lang, auth_prompts["en"])}

            return {
                "text": f"Your account ({session.user_id}) has 2 saved properties in Downtown Dubai and 1 active pre-approval application in Vault CRM under review.",
                "tool_calls": [{"function": "get_my_saved_properties"}, {"function": "get_my_application_status"}]
            }

        # 4. GENERAL / RAG / GREETING INTENT
        else:
            is_greeting = any(w in user_text.lower() for w in ["hi", "hello", "hey", "good morning", "good evening", "مرحبا", "أهلا", "اهلا", "سلام", "नमस्ते", "ہیلو"]) and len(user_text.strip().split()) <= 4
            if is_greeting:
                greetings = {
                    "ar": "مرحباً بك! أنا XO، مساعدك الذكي للعقارات والتمويل العقاري في الإمارات. يمكنني مساعدتك في البحث عن عقارات، أو احتساب قدرتك على التمويل، أو الإجابة على أي استفسار. كيف أساعدك اليوم؟ 🎉",
                    "hi": "नमस्ते! मैं XO हूँ, यूएई में प्रॉपर्टी और होम लोन के लिए आपका एआई सहायक। आप प्रॉपर्टी सर्च, मॉर्गेज ईएमआई कैलकुलेशन या किसी भी सवाल के लिए पूछ सकते हैं। 🎉",
                    "ur": "خوش آمدید! میں XO ہوں، دبئی اور متحدہ عرب امارات میں رئیل اسٹیٹ اور مارگیج کے لیے آپ کا AI اسسٹنٹ۔ میں پراپرٹی کی تلاش یا قسط کے حساب میں آپ کی مدد کر سکتا ہوں۔ 🎉",
                    "en": "Hello! I am XO, your Conversational AI Assistant for premier real estate and mortgages in the UAE. I can help you discover luxury properties, calculate your mortgage affordability and EMI, or answer any questions about our services. How may I assist you today? 🎉"
                }
                return {"text": greetings.get(lang, greetings["en"])}

            # Ground through RAGService
            from app.services.rag_service import RAGService
            kb_res = RAGService.retrieve_kb(user_text, session_id=session.session_id)

            if kb_res.get("status") == "success":
                short_ans = kb_res.get("short_answer", "")
                detail = kb_res.get("detail", "")
                disc = kb_res.get("disclaimer", "")
                reply = f"{short_ans}\n\n{detail}"
                if disc:
                    reply += f"\n\n*(Legal Disclaimer: {disc})*"
                return {
                    "text": reply,
                    "kb_result": kb_res,
                    "tool_calls": [{"function": "retrieve_kb", "args": {"query": user_text}}]
                }
            elif kb_res.get("status") == "scope_restricted":
                return {
                    "text": kb_res.get("message", ""),
                    "kb_result": kb_res,
                    "tool_calls": [{"function": "retrieve_kb", "args": {"query": user_text}}]
                }

            # Low confidence fallback per Domain 11.4
            fallback_detail = kb_res.get("detail", "")
            return {
                "text": f"{kb_res.get('short_answer', '')}\n\n{fallback_detail}",
                "kb_result": kb_res,
                "tool_calls": [{"function": "retrieve_kb", "args": {"query": user_text}}]
            }

    @classmethod
    async def stream_user_turn(
        cls,
        user_message: str,
        session_id: Optional[str] = None,
        manual_language: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """
        Streaming generator supporting perceived latency < 2s (PRD Sec 7).
        Yields Server-Sent Events (SSE) formatted text tokens.
        """
        response = await cls.process_user_turn(
            user_message=user_message,
            session_id=session_id,
            manual_language=manual_language
        )
        full_text = response["text"]
        words = full_text.split(" ")

        for i, word in enumerate(words):
            chunk = {
                "token": word + (" " if i < len(words) - 1 else ""),
                "session_id": response["session_id"],
                "language": response["language"],
                "is_final": (i == len(words) - 1),
                "property_results": response.get("property_results") if (i == len(words) - 1) else None,
                "mortgage_result": response.get("mortgage_result") if (i == len(words) - 1) else None
            }
            yield f"data: {json.dumps(chunk)}\n\n"

    @classmethod
    def _format_comparison_narrative(cls, comp: Dict[str, Any], lang: str) -> str:
        """
        FR-9 Multi-Turn Refinement & Comparison (Rule 5: No LLM math, Rule 10: Disclaimers):
        Synthesizes an advisory side-by-side comparison across displayed properties.
        """
        items = comp.get("properties", [])
        if not items:
            empty_msgs = {
                "ar": "لا توجد حالياً بطاقات عقارات معروضة على الشاشة للمقارنة. يرجى البحث عن عقارات أولاً (مثال: 'ابحث عن شقة غرفتين في دبي هيلز').",
                "hi": "तुलना करने के लिए स्क्रीन पर कोई प्रॉपर्टी कार्ड उपलब्ध नहीं है। कृपया पहले प्रॉपर्टी सर्च करें (उदा. 'दुबई हिल्स में 2 BHK दिखाओ')।",
                "ur": "موازنہ کرنے کے لیے اسکرین پر کوئی پراپرٹی کارڈ موجود نہیں ہے۔ براہ کرم پہلے سرچ کریں (مثال: 'دبئی ہلز میں 2 بی ایچ کے دکھائیں')۔",
                "en": "There are currently no active property cards on screen to compare. Please search for a community or property first (e.g. 'Show 2 BHK in Dubai Hills'), and I will gladly evaluate them for you."
            }
            return empty_msgs.get(lang, empty_msgs["en"])

        disclaimers = {
            "ar": "\n\n*(مقارنة سوقية استرشادية فقط؛ وليست استشارة مالية ملزمة)*",
            "hi": "\n\n*(केवल सांकेतिक बाज़ार तुलना; कोई बाध्यकारी वित्तीय सलाह नहीं)*",
            "ur": "\n\n*(صرف اشارے کے طور پر مارکیٹ کا موازنہ؛ کوئی قانونی یا مالی مشورہ نہیں)*",
            "en": "\n\n*(Indicative market comparison only; not binding financial advice)*"
        }
        disc = disclaimers.get(lang, disclaimers["en"])

        if lang == "ar":
            lines = [f"### 📊 تحليل استثماري مقارن ({len(items)} عقارات معروضة حالياً):\n"]
            for idx, p in enumerate(items, start=1):
                lines.append(
                    f"**{idx}. {p['title']}** ({p['community']})\n"
                    f"• السعر الإجمالي: {p['price']:,.0f} درهم | المساحة: {p['sq_ft']} قدم مربع\n"
                    f"• سعر القدم المربع: {p['price_per_sq_ft']:,.0f} درهم/قدم\n"
                    f"• الدفعة الأولى (20%): {p['down_payment_aed']:,.0f} درهم\n"
                    f"• القسط الشهري التقديري: ~{p['monthly_emi_aed']:,.0f} درهم/شهرياً\n"
                    f"• العائد التأجيري الإجمالي التقديري: {p['estimated_rental_yield']}\n"
                )
            if len(items) >= 2:
                cheapest = min(items, key=lambda x: x["price"])
                priciest = max(items, key=lambda x: x["price"])
                lines.append(
                    "#### 💡 التوصية الاستثمارية والتقييم:\n"
                    f"• **لتحقيق أعلى عائد تأجيري ونقطة دخول مالية أقل:** خيار **{cheapest['title']}** ({cheapest['price']:,.0f} درهم) هو الأنسب، بفضل انخفاض رأس المال المطلوب وسعر قدم يبلغ {cheapest['price_per_sq_ft']:,.0f} درهم وعائد تأجيري قوي يتراوح بين 6.5% إلى 7.0%.\n\n"
                    f"• **لنمو رأس المال على المدى الطويل والفخامة:** خيار **{priciest['title']}** ({priciest['price']:,.0f} درهم) يتميز بإطلالة مباشرة على ملعب الغولف ومساحة أوسع ({priciest['sq_ft']} قدم) واستقطاب كبار المستأجرين."
                )
            return "\n".join(lines) + disc

        elif lang == "hi":
            lines = [f"### 📊 तुलनात्मक निवेश विश्लेषण (स्क्रीन पर उपलब्ध {len(items)} प्रॉपर्टीज):\n"]
            for idx, p in enumerate(items, start=1):
                lines.append(
                    f"**{idx}. {p['title']}** ({p['community']})\n"
                    f"• कुल मूल्य: {p['price']:,.0f} AED | क्षेत्रफल: {p['sq_ft']} वर्ग फुट\n"
                    f"• दर प्रति वर्ग फुट: {p['price_per_sq_ft']:,.0f} AED/वर्ग फुट\n"
                    f"• डाउन पेमेंट (20%): {p['down_payment_aed']:,.0f} AED\n"
                    f"• अनुमानित मासिक ईएमआई: ~{p['monthly_emi_aed']:,.0f} AED/माह\n"
                    f"• अनुमानित रेंटल यील्ड: {p['estimated_rental_yield']}\n"
                )
            if len(items) >= 2:
                cheapest = min(items, key=lambda x: x["price"])
                priciest = max(items, key=lambda x: x["price"])
                lines.append(
                    "#### 💡 निवेश सिफारिश व निष्कर्ष:\n"
                    f"• **अधिक रेंटल यील्ड और कम लागत के लिए:** **{cheapest['title']}** ({cheapest['price']:,.0f} AED) अधिक कुशल विकल्प है (6.5% - 7.0% यील्ड)।\n\n"
                    f"• **प्रीमियम कैपिटल ग्रोथ व गोल्फ व्यू के लिए:** **{priciest['title']}** ({priciest['price']:,.0f} AED) बड़ा लेआउट ({priciest['sq_ft']} वर्ग फुट) और हाई-एंड प्रोफाइल प्रदान करता है।"
                )
            return "\n".join(lines) + disc

        elif lang == "ur":
            lines = [f"### 📊 تقابلی انویسٹمنٹ تجزیہ (اسکرین پر موجود {len(items)} پراپرٹیز):\n"]
            for idx, p in enumerate(items, start=1):
                lines.append(
                    f"**{idx}. {p['title']}** ({p['community']})\n"
                    f"• کل قیمت: {p['price']:,.0f} درہم | رقبہ: {p['sq_ft']} مربع فٹ\n"
                    f"• فی مربع فٹ قیمت: {p['price_per_sq_ft']:,.0f} درہم\n"
                    f"• ڈاؤن پیمنٹ (20%): {p['down_payment_aed']:,.0f} درہم\n"
                    f"• متوقع ماہانہ قسط: ~{p['monthly_emi_aed']:,.0f} درہم/ماہانہ\n"
                    f"• متوقع کرایہ منافع (Yield): {p['estimated_rental_yield']}\n"
                )
            if len(items) >= 2:
                cheapest = min(items, key=lambda x: x["price"])
                priciest = max(items, key=lambda x: x["price"])
                lines.append(
                    "#### 💡 سرمایہ کاری کا مشورہ:\n"
                    f"• **بہترین کرایہ آمدنی اور کم لاگت کے لیے:** **{cheapest['title']}** ({cheapest['price']:,.0f} درہم) سب سے مؤثر انٹری پوائنٹ ہے (6.5% - 7.0% منافع)۔\n\n"
                    f"• **کیپیٹل گروتھ اور پریمیم طرزِ زندگی کے لیے:** **{priciest['title']}** ({priciest['price']:,.0f} درہم) بڑا رقبہ ({priciest['sq_ft']} مربع فٹ) اور گالف ویو فراہم کرتا ہے۔"
                )
            return "\n".join(lines) + disc

        else: # English
            lines = [f"### 📊 Comparative Investment Evaluation ({len(items)} On-Screen Properties)\n"]
            lines.append("Here is an objective side-by-side comparison of the residences currently displayed:\n")
            for idx, p in enumerate(items, start=1):
                lines.append(
                    f"**{idx}. {p['title']}** ({p['community']})\n"
                    f"• **Purchase Price:** AED {p['price']:,.0f} | **Area:** {p['sq_ft']} sq.ft\n"
                    f"• **Capital Rate:** AED {p['price_per_sq_ft']:,.0f} / sq.ft\n"
                    f"• **Down Payment (20%):** AED {p['down_payment_aed']:,.0f}\n"
                    f"• **Est. Monthly EMI:** ~AED {p['monthly_emi_aed']:,.0f} / mo (25-year tenure @ 4.29%)\n"
                    f"• **Benchmark Rental Yield:** {p['estimated_rental_yield']}\n"
                )
            if len(items) >= 2:
                cheapest = min(items, key=lambda x: x["price"])
                priciest = max(items, key=lambda x: x["price"])
                lines.append(
                    "#### 💡 Investment Advisory Assessment & Recommendation:\n"
                    f"• **For Pure Rental Yield & Cash-on-Cash Return:** **{cheapest['title']}** (AED {cheapest['price']:,.0f}) is the more efficient entry point. "
                    f"At AED {cheapest['price_per_sq_ft']:,.0f}/sq.ft, it requires lower upfront equity (AED {cheapest['down_payment_aed']:,.0f}) and yields a strong 6.5% – 7.0% gross return with high family rental liquidity in Dubai Hills.\n\n"
                    f"• **For Capital Appreciation & Executive Prestige:** **{priciest['title']}** (AED {priciest['price']:,.0f}) commands a premium position directly on the golf course with a larger layout ({priciest['sq_ft']} sq.ft). "
                    f"It appeals to executive corporate tenants and offers superior long-term capital preservation and asset value growth."
                )
            return "\n".join(lines) + disc

    @classmethod
    def _format_catalog_fallback_narrative(
        cls,
        filters: PropertySearchFilter,
        location_name: str,
        alts: Dict[str, Any],
        lang: str
    ) -> str:
        """
        FR-8 Empathetic & Catalog-Aware Fallbacks:
        Inspects catalog when exact criteria yields 0 results, presenting alternatives conversationally.
        """
        beds_str = f"{filters.beds}-bedroom " if filters.beds else ""
        has_same = alts.get("has_same_comm_alternatives", False)
        has_other = alts.get("has_other_comm_alternatives", False)

        if lang == "ar":
            if has_same and has_other:
                s = alts["same_community_alternatives"][0]
                o = alts["other_community_alternatives"][0]
                tiers = alts.get("available_beds_in_community", [])
                comm_desc = f"تتوفر خيارات متعددة تشمل {', '.join([f'{t['beds']} غرف نوم (بدءاً من {t['starting_price_aed']:,.0f} درهم)' for t in tiers[:2]])}" if len(tiers) > 1 else f"تتوفر شقق {s['beds']} غرف نوم فاخرة (مثل *{s['title']}* بسعر {s['price']:,.0f} درهم)"
                return (
                    f"بحثتُ في قائمة العقارات الحالية، وللأسف لا تتوفر حالياً شقق {beds_str}في {location_name} تطابق ميزانيتك ومعاييرك بدقة.\n\n"
                    f"ومع ذلك، لدينا بدائل مميزة ومباشرة في النظام:\n"
                    f"• **في {location_name}:** {comm_desc} (مثل *{s['title']}*).\n"
                    f"• **في مجمعات مجاورة:** تتوفر شقق {o['beds']} غرف في {o['community']} (مثل *{o['title']}* بسعر {o['price']:,.0f} درهم) وداون تاون دبي.\n\n"
                    f"هل ترغب في استعراض الخيارات المتاحة في {location_name}، أم تفضل رؤية شقق {o['beds']} غرف في المجمعات المجاورة؟"
                )
            elif has_same:
                s = alts["same_community_alternatives"][0]
                return (
                    f"للأسف لم أجد شقق {beds_str}متاحة حالياً في {location_name}. "
                    f"ولكن تتوفر لدينا وحدات {s['beds']} غرف نوم راقية في {location_name} (مثل *{s['title']}* بسعر {s['price']:,.0f} درهم). هل ترغب في الاطلاع عليها؟"
                )
            elif has_other:
                o = alts["other_community_alternatives"][0]
                return (
                    f"لم تتوفر وحدات مطابقة تماماً في {location_name}، ولكن تتوفر شقق {o['beds']} غرف نوم ممتازة في {o['community']} (مثل *{o['title']}* بسعر {o['price']:,.0f} درهم). هل تود استعراضها؟"
                )
            else:
                return f"لم أجد حالياً عقارات نشطة تطابق هذه المعايير في {location_name}. هل ترغب في توسيع البحث ليشمل كافة مناطق دبي أو تعديل الميزانية وعدد الغرف؟"

        elif lang == "hi":
            if has_same and has_other:
                s = alts["same_community_alternatives"][0]
                o = alts["other_community_alternatives"][0]
                tiers = alts.get("available_beds_in_community", [])
                comm_desc = f"हमारे पास {', '.join([f'{t['beds']} बेडरूम (शुरुआती कीमत {t['starting_price_aed']:,.0f} AED)' for t in tiers[:2]])} के विकल्प उपलब्ध हैं" if len(tiers) > 1 else f"हमारे पास लक्ज़री {s['beds']} बेडरूम निवास उपलब्ध हैं (जैसे *{s['title']}* मूल्य {s['price']:,.0f} AED)"
                return (
                    f"मैंने हमारे लाइव इन्वेंट्री की जांच की, दुर्भाग्य से {location_name} में {beds_str}अपार्टमेंट के लिए सटीक मैच अभी उपलब्ध नहीं है।\n\n"
                    f"हालाँकि, आपके लिए बेहतरीन विकल्प मौजूद हैं:\n"
                    f"• **{location_name} में:** {comm_desc} (जैसे *{s['title']}*)।\n"
                    f"• **नजदीकी कम्युनिटीज में:** हमारे पास {o['community']} और डाउनटाउन दुबई में {o['beds']} बेडरूम विकल्प उपलब्ध हैं (जैसे *{o['title']}* मूल्य {o['price']:,.0f} AED)।\n\n"
                    f"क्या आप {location_name} में उपलब्ध विकल्प देखना चाहेंगे, या नजदीकी क्षेत्रों में {o['beds']} बेडरूम विकल्प देखना पसंद करेंगे?"
                )
            elif has_same:
                s = alts["same_community_alternatives"][0]
                return f"दुर्भाग्य से {location_name} में सटीक {beds_str}अपार्टमेंट नहीं मिला, लेकिन {location_name} में शानदार {s['beds']} बेडरूम विकल्प (जैसे *{s['title']}* मूल्य {s['price']:,.0f} AED) उपलब्ध हैं। क्या आप इन्हें देखना चाहेंगे?"
            elif has_other:
                o = alts["other_community_alternatives"][0]
                return f"{location_name} में लिस्टिंग नहीं मिली, लेकिन {o['community']} में बेहतरीन {o['beds']} बेडरूम विकल्प (जैसे *{o['title']}*) उपलब्ध हैं। क्या मैं आपको ये विकल्प दिखाऊं?"
            else:
                return f"{location_name} में इस सटीक मानदंड पर कोई लिस्टिंग नहीं मिली। क्या आप पूरे दुबई में अन्य विकल्प देखना चाहेंगे?"

        elif lang == "ur":
            if has_same and has_other:
                s = alts["same_community_alternatives"][0]
                o = alts["other_community_alternatives"][0]
                tiers = alts.get("available_beds_in_community", [])
                comm_desc = f"ہمارے پاس {', '.join([f'{t['beds']} بیڈ روم (ابتدائی قیمت {t['starting_price_aed']:,.0f} درہم)' for t in tiers[:2]])} کی رہائشیں دستیاب ہیں" if len(tiers) > 1 else f"لگژری {s['beds']} بیڈ روم رہائشیں دستیاب ہیں (جیسے *{s['title']}* قیمت {s['price']:,.0f} درہم)"
                return (
                    f"میں نے لائیو انوینٹری چیک کی ہے، بدقسمتی سے {location_name} میں آپ کے عین مطابق {beds_str}اپارٹمنٹ فی الوقت دستیاب نہیں ہے۔\n\n"
                    f"تاہم، ہمارے کیٹلاگ میں شاندار متبادل موجود ہیں:\n"
                    f"• **{location_name} میں:** {comm_desc} (جیسے *{s['title']}*)۔\n"
                    f"• **قریبی علاقوں میں:** {o['community']} اور ڈاؤن ٹاؤن دبئی میں {o['beds']} بیڈ روم رہائشیں دستیاب ہیں (جیسے *{o['title']}* قیمت {o['price']:,.0f} درہم)۔\n\n"
                    f"کیا آپ {location_name} میں دستیاب آپشنز دیکھنا چاہیں گے، یا قریبی علاقوں میں {o['beds']} بیڈ روم آپشنز؟"
                )
            elif has_same:
                s = alts["same_community_alternatives"][0]
                return f"{location_name} میں اس وقت {beds_str}اپارٹمنٹ دستیاب نہیں، لیکن {location_name} میں {s['beds']} بیڈ روم رہائشیں (جیسے *{s['title']}* قیمت {s['price']:,.0f} درہم) موجود ہیں۔ کیا آپ انہیں دیکھنا چاہیں گے؟"
            elif has_other:
                o = alts["other_community_alternatives"][0]
                return f"{location_name} میں نتائج نہیں ملے، لیکن {o['community']} میں شاندار {o['beds']} بیڈ روم رہائشیں (جیسے *{o['title']}*) موجود ہیں۔ کیا آپ ان کا معائنہ کرنا چاہیں گے؟"
            else:
                return f"{location_name} میں ان شرائط پر کوئی پراپرٹی نہیں ملی۔ کیا آپ اپنا بجٹ یا بیڈ رومز کی تعداد ایڈجسٹ کرنا چاہیں گے؟"

        else: # English
            if has_same and has_other:
                s = alts["same_community_alternatives"][0]
                o = alts["other_community_alternatives"][0]
                tiers = alts.get("available_beds_in_community", [])
                if len(tiers) > 1:
                    tiers_txt = ", ".join([f"{t['beds']}-bedroom {t['type']}s (starting from AED {t['starting_price_aed']:,.0f})" for t in tiers[:2]])
                    comm_txt = f"• **Within {location_name}:** We have luxury residences available in {tiers_txt} (such as *{s['title']}*)."
                else:
                    comm_txt = f"• **Within {location_name}:** We have luxury {s['beds']}-bedroom residences available (such as *{s['title']}* at AED {s['price']:,.0f})."

                other_summary = alts.get("other_communities_summary", [])
                if other_summary:
                    o_top = other_summary[0]
                    other_txt = f"• **In nearby prime communities:** We have exceptional {o_top['beds']}-bedroom residences in {o_top['community']} (starting from AED {o_top['starting_price_aed']:,.0f}, such as *{o_top['sample_title']}*) and Downtown Dubai."
                else:
                    other_txt = f"• **In nearby prime communities:** We have exceptional {o['beds']}-bedroom residences available in {o['community']} (such as *{o['title']}* at AED {o['price']:,.0f}) and Downtown Dubai."

                return (
                    f"I checked our live inventory, but unfortunately we don't currently have an active {beds_str}listing in {location_name} matching your exact parameters.\n\n"
                    f"However, we have relevant options available in the catalog:\n"
                    f"{comm_txt}\n"
                    f"{other_txt}\n\n"
                    f"Would you like me to show you the available options in {location_name}, or explore {beds_str or '1-bedroom '}residences in adjacent areas like {o['community']}?"
                )
            elif has_same:
                s = alts["same_community_alternatives"][0]
                tiers = alts.get("available_beds_in_community", [])
                if len(tiers) > 1:
                    tiers_txt = ", ".join([f"{t['beds']}-bedroom {t['type']}s (from AED {t['starting_price_aed']:,.0f})" for t in tiers[:2]])
                    return (
                        f"We couldn't find an exact {beds_str}match in {location_name} in our live inventory. "
                        f"However, we do have luxury residences in {location_name} including {tiers_txt} (such as *{s['title']}* at AED {s['price']:,.0f}). "
                        f"Would you like to explore those?"
                    )
                return (
                    f"We couldn't find an exact {beds_str}match in {location_name} in our live inventory. "
                    f"However, we do have luxury {s['beds']}-bedroom residences in {location_name} (such as *{s['title']}* at AED {s['price']:,.0f}). "
                    f"Would you like to explore those?"
                )
            elif has_other:
                o = alts["other_community_alternatives"][0]
                other_summary = alts.get("other_communities_summary", [])
                if other_summary:
                    o_top = other_summary[0]
                    return (
                        f"We couldn't find active listings matching your exact criteria in {location_name}. "
                        f"However, we have exceptional {o_top['beds']}-bedroom residences in {o_top['community']} (such as *{o_top['sample_title']}* at AED {o_top['starting_price_aed']:,.0f}) and Downtown Dubai. "
                        f"Would you like me to present these alternative properties?"
                    )
                return (
                    f"We couldn't find active listings matching your exact criteria in {location_name}. "
                    f"However, we have exceptional {o['beds']}-bedroom residences in {o['community']} (such as *{o['title']}* at AED {o['price']:,.0f}). "
                    f"Would you like me to present these alternative properties?"
                )
            else:
                return (
                    f"I currently found 0 active listings matching your exact criteria in {location_name}. "
                    f"Would you like me to broaden the search across all prime Dubai communities, or adjust your budget and bedroom preferences?"
                )
