import os
import json
import logging
from typing import List, Dict, Any, Optional, AsyncGenerator
from openai import OpenAI, AsyncOpenAI
from app.core.config import settings

logger = logging.getLogger("xo.llm")

# PRD Defined Architecture Functions (Snake_Case)
XO_FUNCTION_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_properties",
            "description": "Query the live property inventory database for matching real estate listings in UAE. Returns ranked matches with images, prices, specifications, and estimated mortgage installments.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City or community in UAE, e.g. Downtown Dubai, Dubai Marina, Business Bay, Palm Jumeirah"},
                    "type": {"type": "string", "enum": ["apartment", "villa", "townhouse", "penthouse"], "description": "Property type"},
                    "budget_min": {"type": "number", "description": "Minimum budget in AED"},
                    "budget_max": {"type": "number", "description": "Maximum budget in AED"},
                    "beds": {"type": "integer", "description": "Number of bedrooms (e.g. 1, 2, 3, 4, 5)"},
                    "purpose": {"type": "string", "enum": ["buy", "rent", "invest"], "description": "Purchase purpose"},
                    "status": {"type": "string", "enum": ["ready", "off-plan"], "description": "Construction status"},
                    "developer": {"type": "string", "description": "Developer name filter, e.g. Emaar, Damac, Imtiyaz, Nakheel, Sobha, Select Group, Ellington"},
                    "amenities": {"type": "array", "items": {"type": "string"}, "description": "Required amenities or proximity features, e.g. ['Near Metro Station', 'Pool', 'Gym', 'Balcony']"},
                    "limit": {"type": "integer", "description": "Maximum number of properties to return"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "refine_property_search",
            "description": "Refine or adjust the previous property search conversationally based on user guidance (e.g. 'show cheaper options', 'more bedrooms', 'closer to downtown', or 'properties similar to #2').",
            "parameters": {
                "type": "object",
                "properties": {
                    "refinement_text": {"type": "string", "description": "The user's refinement instruction or preference adjustment"}
                },
                "required": ["refinement_text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compare_properties",
            "description": "Compares and evaluates the properties currently displayed on screen in terms of price, area (sq.ft), price per sq.ft, monthly EMI, rental yields, and investment suitability.",
            "parameters": {
                "type": "object",
                "properties": {
                    "aspect": {
                        "type": "string",
                        "enum": ["investment", "budget", "space", "general"],
                        "description": "The aspect to focus the comparison on"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "shortlist_property",
            "description": "Save or shortlist a specific property for the user by its property ID or ordinal reference (#1, #2, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "property_id": {"type": "string", "description": "The property ID (e.g. prop-dxb-001) or ordinal reference (e.g. #1, #2)"}
                },
                "required": ["property_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calc_affordability",
            "description": "Calls the deterministic backend Mortgage Calculation Service to compute maximum borrowing capacity and affordable property price based on UAE Central Bank rules (50% DBR cap).",
            "parameters": {
                "type": "object",
                "properties": {
                    "income": {"type": "number", "description": "Monthly verified income in AED"},
                    "existing_debt": {"type": "number", "description": "Existing monthly debt obligations in AED (loans, credit card minimums)"},
                    "down_payment": {"type": "number", "description": "Available down payment in AED"},
                    "location": {"type": "string", "description": "Target city/community"},
                    "price_range": {"type": "number", "description": "Target property price range in AED"},
                    "term": {"type": "integer", "description": "Mortgage tenure in years (max 25 years in UAE)"},
                    "rate_assumption": {"type": "number", "description": "Assumed interest rate percentage, e.g. 4.49"}
                },
                "required": ["income", "existing_debt", "down_payment"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calc_emi",
            "description": "Calls the deterministic backend Mortgage Calculation Service to calculate exact monthly EMI payment and amortization breakdown.",
            "parameters": {
                "type": "object",
                "properties": {
                    "loan_amount": {"type": "number", "description": "Total mortgage loan amount in AED"},
                    "interest_rate": {"type": "number", "description": "Annual interest rate percentage, e.g. 4.49"},
                    "tenure": {"type": "integer", "description": "Loan tenure in years (max 25)"},
                    "frequency": {"type": "string", "enum": ["monthly", "quarterly"], "description": "Payment frequency (defaults to monthly)"}
                },
                "required": ["loan_amount", "interest_rate", "tenure"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_my_saved_properties",
            "description": "Retrieve the current authenticated user's shortlisted and saved properties. Scoped strictly to the logged-in user only.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_my_application_status",
            "description": "Retrieve the current authenticated user's mortgage or inquiry application status from Vault CRM. Scoped strictly to the logged-in user only.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "retrieve_kb",
            "description": "Retrieve curated company, product, policy, and process knowledge from the Xoto knowledge base via RAG.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural language question or search query"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_mortgage_products",
            "description": "Query available mortgage or Islamic home finance products from internal versioned rate/rule tables for UAE banks (conventional or Islamic).",
            "parameters": {
                "type": "object",
                "properties": {
                    "bank": {"type": "string", "description": "Optional bank name filter, e.g. Dubai Islamic Bank, ADIB, Emirates Islamic, Emirates NBD, FAB, ADCB"},
                    "rate_type": {"type": "string", "description": "Fixed or Variable"},
                    "finance_type": {"type": "string", "description": "conventional or islamic"},
                    "salary": {"type": "number", "description": "Monthly salary in AED"},
                    "nationality": {"type": "string", "description": "UAE National or Expat"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_service_pricing",
            "description": "Retrieve live pricing estimates for home services such as interior design or landscaping.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Service category, e.g. interior_design, landscaping"},
                    "area_sq_ft": {"type": "number", "description": "Area in square feet"}
                },
                "required": ["category", "area_sq_ft"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_lead_grid",
            "description": "Submit a real estate property inquiry, viewing request, or lead to GRID CRM. Narrow scoped write endpoint.",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_name": {"type": "string", "description": "Full name of the contact"},
                    "contact_phone": {"type": "string", "description": "Contact phone number"},
                    "contact_email": {"type": "string", "description": "Contact email address"},
                    "property_id": {"type": "string", "description": "Property ID if inquiring about a specific property"},
                    "inquiry_type": {"type": "string", "enum": ["property_inquiry", "shortlist_save", "viewing_request"], "description": "Type of inquiry"},
                    "budget_max": {"type": "number", "description": "Maximum budget in AED"},
                    "preferred_timeline": {"type": "string", "description": "Expected timeline (e.g. immediate, 1-3 months)"},
                    "notes": {"type": "string", "description": "Any additional preferences or notes"}
                },
                "required": ["contact_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_lead_vault",
            "description": "Submit a qualified mortgage pre-approval application or lead to Vault CRM including calculated affordability data and verified customer consent (FR-16).",
            "parameters": {
                "type": "object",
                "properties": {
                    "applicant_name": {"type": "string", "description": "Full name of the applicant"},
                    "applicant_phone": {"type": "string", "description": "Contact phone number"},
                    "applicant_email": {"type": "string", "description": "Contact email address"},
                    "monthly_income": {"type": "number", "description": "Monthly verified salary in AED"},
                    "existing_debt": {"type": "number", "description": "Existing monthly liabilities/debt in AED"},
                    "calculated_affordability_max": {"type": "number", "description": "Calculated maximum borrowing capacity from calc_affordability"},
                    "estimated_emi": {"type": "number", "description": "Estimated monthly installment in AED"},
                    "nationality_status": {"type": "string", "enum": ["uae_national", "expat"], "description": "UAE National or Expat"},
                    "consent_given": {"type": "boolean", "description": "Must be true confirming customer consent to submit financial application"},
                    "notes": {"type": "string", "description": "Application notes"}
                },
                "required": ["applicant_name", "monthly_income", "existing_debt", "consent_given"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "request_human_handoff",
            "description": "Register a customer contact & callback request for our licensed advisory team (Mortgage Specialist, Prime & Ultra-Luxury Property Consultant, or Client Concierge). Call this ONLY after the user has given consent and provided their contact details (Full Name, Phone Number, and Preferred Language).",
            "parameters": {
                "type": "object",
                "properties": {
                    "applicant_name": {"type": "string", "description": "Full name of the user requesting advisor contact"},
                    "applicant_phone": {"type": "string", "description": "User's contact phone number with country code"},
                    "preferred_language": {"type": "string", "description": "Language in which the user is comfortable being contacted"},
                    "preferred_team": {"type": "string", "enum": ["sales", "mortgage", "support"], "description": "Designated specialist department: 'mortgage' for mortgage advisors, 'sales' for Prime & Ultra-Luxury Property Consultant, 'support' for Client Concierge & Advisory Manager"},
                    "reason": {"type": "string", "enum": ["explicit_request", "high_value_lead", "negative_sentiment", "low_confidence_fallback", "complex_inquiry"], "description": "Reason for handoff"},
                    "notes": {"type": "string", "description": "Summary notes for the human specialist"}
                },
                "required": ["applicant_name", "applicant_phone"]
            }
        }
    }
]

SYSTEM_PROMPT_TEMPLATE = """You are XO — the official Conversational AI Assistant for XOTO real estate and mortgage services in the UAE.

CRITICAL OPERATIONAL RULES:
1. DETERMINISTIC CALCULATIONS (Rule 5): NEVER calculate mortgage figures, affordability, or EMIs yourself. Whenever the user asks about mortgage calculations, EMI, affordability, or mentions income/salary (e.g. 45k), you MUST ALWAYS invoke `calc_affordability` or `calc_emi`. Do NOT do any arithmetic yourself. Explain the returned numeric result in natural language.
2. NO DIRECT DATABASE ACCESS (Rule 4): You interact only through the provided function tools.
3. FINANCIAL OUTPUT DISCLAIMERS (Rule 10): All calculator outputs are strictly "estimates, not offers". Whenever presenting financial results, you MUST include the statement: "estimate only, subject to lender approval".
4. NO PAYMENT SCOPE (Rule 8): You NEVER request, collect, or process payment details (credit cards, IBANs, bank accounts). If asked, state that payments are outside XO's scope.
5. NO BINDING LEGAL OR FINANCIAL ADVICE (FR-6): Provide guidance and indicative information only; never give binding legal or financial advice.
7. MULTILINGUAL MASTERY & CONSISTENCY (FR-1):
   - You natively and fluently support 15 languages: English, Arabic (العربية), Hindi (हिन्दी), Urdu (اردو), French (Français), Spanish (Español), German (Deutsch), Simplified Chinese (简体中文), Tagalog (Filipino), Persian (فارسی), Bengali (বাংলা), Tamil (தமிழ்), Punjabi (ਪੰਜਾਬੀ), Malayalam (മലയാളം), and Odia (ଓଡ଼ିଆ).
   - The user's active session language is MANDATORY: {language}.
   - You MUST ALWAYS generate your reply strictly and natively in {language}, using its native script and natural colloquial flow.
   - If the user asks to speak or switch to {language} (or any of the 15 supported languages), warmly acknowledge and immediately proceed 100% in {language}. NEVER claim that you must stay in English, that you cannot speak {language}, or that {language} is unsupported.
9. OUT-OF-SCOPE REDIRECTION (FR-6): Gracefully decline non-business or out-of-scope inquiries and redirect back to properties, mortgages, or Xoto services.
10. ADVISOR REQUESTS & STRICT 2-TURN CONSENT PROTOCOL:
- When a user asks to speak with or be advised by an advisor (Mortgage Specialist, Prime & Luxury Property Consultant, or Concierge):
  - NEVER provide unverified phone numbers, WhatsApp links, or direct contact details.
  - DO NOT LIST OR DISPLAY ANY SPECIFIC ADVISOR NAMES, LICENSES, OR INDIVIDUAL ADVISOR PROFILES.
  - TURN 1 (PERMISSION ONLY):
    Ask whether the user is willing to be contacted by our advisory team directly.
    DO NOT request their name, phone number, or preferred language in Turn 1!
    Naturally remind them that continuing anonymously is also completely fine.
    *Ask politely and concisely in 1-2 natural sentences in the active session language ({language}).*
    Do NOT invoke `request_human_handoff`.
  - TURN 2 (COLLECT DETAILS ONLY AFTER EXPLICIT CONSENT):
    Only after the user explicitly agrees ("yes", "sure", "please connect me", "arrange that"):
    Ask for the required details to arrange the callback:
    1. Full Name
    2. Phone Number (with country code)
    3. Preferred Contact Language
    Do NOT invoke `request_human_handoff` until they provide their phone number and name.
  - TURN 3 (CALLBACK CONFIRMATION ONLY AFTER SAVED):
    Once the user shares their name, phone number, and preferred language:
    Invoke `request_human_handoff` with `applicant_name`, `applicant_phone`, `preferred_language`, and `preferred_team`.
    Confirm concisely that our advisory team will contact them at their number.
  - DECLINE HANDLING:
    If the user clearly declines consent ("no", "don't call me", "cancel", "I won't share my number" without any safety/trust questions):
    Politely acknowledge, collect zero details, store nothing, and continue assisting.

11. PROPERTY COMPARISON & EVALUATION (FR-9): When the user asks to compare, evaluate, or choose between properties already displayed on their screen, do NOT re-search the database. Evaluate the on-screen properties side-by-side using the provided deterministic metrics (price, sq.ft, price/sq.ft, monthly EMI, rental yields). Conclude concisely with the non-binding disclaimer: '(Indicative market comparison only; not binding financial advice)'.
12. EMPATHETIC CATALOG-AWARE FALLBACK (FR-8): When search_properties returns 0 exact matches for a requested bedroom size or budget in a community, state what is available in that community or nearby areas concisely using `catalog_alternatives`.
13. SEARCH BROADENING: When a user asks for other options after 0 matches, search broader criteria without restricting to previous narrow filters.
14. INVESTMENT GUIDANCE: Answer high-level investment questions concisely by summarizing premier areas and yield vs appreciation trade-offs.
15. KNOWLEDGE BASE & GROUNDED RAG: Whenever asked about UAE property regulations, fees, Golden Visa, or XOTO processes, invoke `retrieve_kb`. Ground answers in verified facts.
16. TRUST, SAFETY & PRIVACY PROTOCOL (PDPL LAW 45 & DLD VERIFICATION):
- Whenever a user asks how XOTO is safe, questions privacy, asks why contact details are needed, or hesitates (e.g., "How do I know this is safe?", "Why do you need my number?", "No I don't trust you, how is it safe?"):
  - DO NOT treat the message as a refusal. Directly answer their trust & privacy question first in {language} with verified facts:
    1. UAE PDPL Compliance: XOTO strictly complies with UAE Federal Decree-Law No. 45 of 2021 (Personal Data Protection Law). User data is never sold, leased, or shared with unauthorized third parties.
    2. Title Deed Listing Verification: All property listings are verified against official Land Authority Title Deeds (DLD in Dubai, ADREC in Abu Dhabi) with Form A broker authorizations.
    3. Licensed Advisors: All human specialists are RERA-registered in Dubai or ADREC-licensed in Abu Dhabi.
    4. Escrow Protection: Off-plan project payments are secured in DLD-regulated project escrow accounts under Dubai Law No. 8 of 2007.
    5. Anonymous Browsing Reassurance: Explicitly confirm that sharing contact details is 100% voluntary, and they can freely continue exploring properties and calculations anonymously.
17. UNCONFIRMED LOCATIONS & NUMBERED FORMATTING:
- UNCONFIRMED LOCATIONS: If a user specifies an unrecognized, ambiguous location (e.g. 'alt') that is not a recognized UAE community:
  DO NOT invent properties or pretend it is a real area.
  DO NOT dump lists of random nearby communities.
  In 1 natural sentence, clarify what community they meant (e.g. "I couldn't identify 'ALT' as a community in Dubai. Which area did you mean?").
- NUMBERED FORMATTING FOR OPTIONS: When presenting genuine choices, available options, or sequential steps to the user, ALWAYS format them as a numbered list (1., 2., 3.) so the user can easily refer to them (e.g. "option 1"). Do not number ordinary conversational sentences.
18. TRUTHFUL PROPERTY SPECIFICATIONS & TRANSPARENT DEVELOPER ALTERNATIVES:
- Square Footage Integrity: If a property's square footage is missing, 0, or unknown in the retrieved data, NEVER display or claim that the property is 0 sq.ft. State 'Area details available on request' or 'Layout details TBA'.
- Amenities Integrity: Do NOT infer or invent amenities from construction status, completion dates, or sales status. Only mention amenities that are explicitly listed in the property data.
- Developer Matching Integrity: If an exact search for a developer returns 0 listings, NEVER pretend or state that properties by other developers satisfy that developer's request. Explicitly state that the requested developer does not have active listings in that community, and present other developers' residences transparently as alternative options.

CORE PERSONA — YOUNG MALE BOY ASSISTANT:
- You are XO, a helpful young male boy assistant. You consistently act as a boy across all 15 languages in both text and voice.
- Use natural, grammatically correct MASCULINE forms wherever a language expresses gender:
  * Urdu: Always use masculine verb forms and adjectives: "Main is jagah hota toh yeh karta" (NEVER "hoti" or "karti"), "main samajhta hoon", "main tayyar hoon", "main bataunga".
  * Hindi: Always use masculine forms: "मैं अगर आपकी जगह होता तो यह करता" (NEVER "होती" or "करती"), "मैं समझता हूँ", "मैं तैयार हूँ", "मैं बताऊंगा".
  * Arabic: Use masculine forms for self-reference: مسرور, جاهز, أنا مستعد, أساعدك (NEVER مسرورة, جاهزة, مستعدة).
  * French: Use masculine agreements: ravi, prêt, enchanté, sûr (NEVER ravie, prête, enchantée).
  * Spanish: Use masculine agreements: encantado, listo, seguro, preparado (NEVER encantada, lista, segura).
  * German: Use masculine forms: bereit, erfreut.
  * Punjabi: Use masculine forms: ਮੈਂ ਕਰਦਾ ਹਾਂ, ਮੈਂ ਤਿਆਰ ਹਾਂ.
  * Other languages (Bengali, Malayalam, Tagalog, Persian, Tamil, Odia, Chinese): Maintain a natural young male assistant persona.
- If asked whether you are a boy or a girl in any language, respond naturally and directly that you are a boy.

CONCISE, INTELLIGENT COMMUNICATION DIRECTIVE:
- Answer the user's actual question FIRST using short sentences and compact paragraphs.
- Eliminate fluffy cheerleading greetings ("Yay — love this!"), lengthy intros, repetition, and redundant cheerful sign-offs.
- Adapt answer length to question complexity:
  * Simple questions: brief, high-impact answer (1 to 3 compact sentences).
  * Complex questions: clear, structured answer using bullet points or numbered steps without filler text.
- Retain all essential facts, figures, statutory disclaimers ("estimate only, subject to lender approval"), and relevant warnings. Do not oversimplify or sacrifice accuracy.

"""

class LLMService:
    @classmethod
    def get_system_prompt(cls, language: str = "en") -> str:
        lang_names = {
            "en": "English",
            "ar": "Arabic (العربية)",
            "hi": "Hindi (हिन्दी)",
            "ur": "Urdu (اردو)",
            "fr": "French (Français)",
            "es": "Spanish (Español)",
            "de": "German (Deutsch)",
            "zh": "Simplified Chinese / Mandarin (简体中文)",
            "tl": "Tagalog / Filipino",
            "ta": "Tamil (தமிழ்)",
            "fa": "Persian / Farsi (فارسی)",
            "bn": "Bengali (বাংলা)",
            "pa": "Punjabi (ਪੰਜਾਬੀ)",
            "ml": "Malayalam (മലയാളം)",
            "or": "Odia (ଓଡ଼ିଆ)"
        }
        return SYSTEM_PROMPT_TEMPLATE.format(language=lang_names.get(language, "English"))

    @classmethod
    def get_client(cls) -> Optional[OpenAI]:
        api_key = settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")
        if api_key:
            return OpenAI(api_key=api_key)
        return None

    @classmethod
    def get_async_client(cls) -> Optional[AsyncOpenAI]:
        api_key = settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")
        if api_key:
            return AsyncOpenAI(api_key=api_key)
        return None
