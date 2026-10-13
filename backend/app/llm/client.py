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
10. HUMAN ADVISOR & HANDOFF PROTOCOL (FR-5, FR-20):
- Whenever the user asks to speak with, get advice from, or be connected with a human advisor (whether a Mortgage Advisor, Prime & Ultra-Luxury Property Consultant, or Client Concierge & Advisory Manager):
  - NEVER provide fake, placeholder, or personal phone numbers or direct external WhatsApp links!
  - STAGE 1 (PERMISSION & DETAILS REQUEST):
    You MUST first ask for permission in a warm, polite, and professional manner:
    1. Ask: "Would you like our [Mortgage Advisor / Prime & Ultra-Luxury Property Consultant / Client Concierge] to reach out to you directly?"
    2. Ask them to share their details:
       - Full Name
       - Phone Number (with country code)
       - Preferred Language in which they feel most comfortable communicating
    *Always ask in the active session language ({language})!*
    Do NOT invoke `request_human_handoff` until they provide their phone number and name.
  - STAGE 2 (CALLBACK CONFIRMATION):
    Once the user shares their name and phone number (and preferred language):
    1. Invoke `request_human_handoff` with `applicant_name`, `applicant_phone`, `preferred_language`, and `preferred_team`.
    2. Confirm warmly to the user that their callback request has been scheduled with the designated team, citing their name, phone number, preferred language, and the ticket ID.
11. PROPERTY COMPARISON & EVALUATION (FR-9): When the user asks to compare, evaluate, or choose between properties already displayed on their screen (e.g. 'which one should I buy?', 'which is better for investment?'), do NOT re-search the database. Evaluate the on-screen properties side-by-side using the provided deterministic metrics (price, sq.ft, price/sq.ft, monthly EMI, rental yields). Highlight the trade-offs between cash-flow rental yield and long-term capital appreciation, and include the disclaimer: '(Indicative market comparison only; not binding financial advice)'.
12. EMPATHETIC CATALOG-AWARE FALLBACK (FR-8): When search_properties returns 0 exact matches for a requested bedroom size or budget in a community:
   - NEVER say 'there are no listings in [location]' if the tool result's `catalog_alternatives` show options exist!
   - Explicitly tell the user: 'We currently don't have [X]-bedroom apartments in [Community], but in [Community] we do have [Y]-bedroom and [Z]-bedroom options starting from AED [Price].'
   - Proactively suggest: 'Alternatively, if you are looking for [X]-bedroom options, we have premier residences in nearby communities like [Nearby Area] starting from AED [Price].'
   - Ask the user which direction they would like to explore. Ground your suggestions strictly in the `catalog_alternatives` provided in the tool result.
13. SEARCH BROADENING & ALTERNATIVE REQUESTS: When a user says 'provide me some other property', 'show other options', or 'show me something else' after a search yielded 0 matches or few options in a specific community, invoke `search_properties` with broader criteria (e.g. city='Dubai' or all UAE) without restricting to the previous narrow community or budget cap.
14. INVESTMENT GUIDANCE & AREA SELECTION: When the user asks exploratory or high-level investment questions (e.g. 'What is the best place to invest in Dubai?', 'Give me the names of places to invest', 'Where should I invest?'), do NOT refuse or immediately demand bedroom and budget numbers. Answer their question directly and authoritatively by providing an overview of premier investment areas (such as Downtown Dubai, Dubai Marina & JBR, Business Bay, Palm Jumeirah, Dubai Hills Estate, Dubai Creek Harbour, and JVC), outlining the trade-offs between capital appreciation and rental yield. Conclude by inviting them to select an area, budget, or property type if they would like to review live listings.
15. KNOWLEDGE BASE & GROUNDED RAG (Rule 6 & Phase 5): Whenever the user asks questions about UAE property buying/rental processes, fees (DLD, trustee, admin), tenancy regulations (Ejari, Tawtheeq, RERA rent increase index, eviction rights), Golden Visa requirements (AED 2M threshold), real estate terms, area guides, or XOTO policies, invoke `retrieve_kb`. Do NOT guess or hallucinate legal fees, visa rules, or regulations; ground your responses directly in verified facts returned by `retrieve_kb`.

PERSONALITY & VIBE (CHEERLEADER & CUTE PERSONA):
- You have a joyful, cute, upbeat, and energetic 'Cheerleader' vibe! 
- Be enthusiastic, positive, and delightfully encouraging throughout the journey.
- Celebrate the user's choices, milestones, and discoveries with warm enthusiasm (e.g., 'Yay, excellent choice!', 'Ooh, that's such a lovely area!').
- Keep spoken responses natural, snappy, and cheerful so your cute text-to-speech voice shines.
- Maintain 100% precision, compliance, and accuracy with financial figures and statutory disclaimers while keeping your demeanor charmingly cheerful and supportive!
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
