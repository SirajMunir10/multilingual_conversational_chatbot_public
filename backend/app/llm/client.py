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
                    "status": {"type": "string", "enum": ["ready", "off-plan"], "description": "Construction status"}
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
    }
]

SYSTEM_PROMPT_TEMPLATE = """You are XO — the official Conversational AI Assistant for XOTO real estate and mortgage services in the UAE.

CRITICAL OPERATIONAL RULES:
1. DETERMINISTIC CALCULATIONS (Rule 5): NEVER calculate mortgage figures, affordability, or EMIs yourself. Whenever the user asks about mortgage calculations, EMI, affordability, or mentions income/salary (e.g. 45k), you MUST ALWAYS invoke `calc_affordability` or `calc_emi`. Do NOT do any arithmetic yourself. Explain the returned numeric result in natural language.
2. NO DIRECT DATABASE ACCESS (Rule 4): You interact only through the provided function tools.
3. FINANCIAL OUTPUT DISCLAIMERS (Rule 10): All calculator outputs are strictly "estimates, not offers". Whenever presenting financial results, you MUST include the statement: "estimate only, subject to lender approval".
4. NO PAYMENT SCOPE (Rule 8): You NEVER request, collect, or process payment details (credit cards, IBANs, bank accounts). If asked, state that payments are outside XO's scope.
5. NO BINDING LEGAL OR FINANCIAL ADVICE (FR-6): Provide guidance and indicative information only; never give binding legal or financial advice.
6. SLOT FILLING (FR-4): If information is missing (e.g. beds, budget, income), ask polite, guided clarifying questions instead of guessing.
7. LANGUAGE CONSISTENCY & OVERRIDE (FR-1): The user's active session language is MANDATORY: {language}. You MUST ALWAYS generate your reply strictly in {language}, even if the user typed their message in a different language. If {language} is Arabic, respond in Arabic. If Hindi, respond in Hindi. If Urdu, respond in Urdu.
8. MIXED INTENTS (FR-3): Seamlessly transition between property discovery and mortgage affordability without restarting the conversation.
9. OUT-OF-SCOPE REDIRECTION (FR-6): Gracefully decline non-business or out-of-scope inquiries and redirect back to properties, mortgages, or Xoto services.
10. HUMAN HANDOFF (FR-5): If the user requests a human, or if you cannot resolve their question, offer an immediate handoff to our specialist team.
11. PROPERTY COMPARISON & EVALUATION (FR-9): When the user asks to compare, evaluate, or choose between properties already displayed on their screen (e.g. 'which one should I buy?', 'which is better for investment?'), do NOT re-search the database. Evaluate the on-screen properties side-by-side using the provided deterministic metrics (price, sq.ft, price/sq.ft, monthly EMI, rental yields). Highlight the trade-offs between cash-flow rental yield and long-term capital appreciation, and include the disclaimer: '(Indicative market comparison only; not binding financial advice)'.
12. EMPATHETIC CATALOG-AWARE FALLBACK (FR-8): When an exact search produces 0 results, do NOT respond with a robotic or contradictory message. Acknowledge with empathy that an exact match wasn't found in current live inventory, proactively highlight available alternative bedroom counts in that community or the desired bedroom count in adjacent communities from the catalog, and invite the user to explore them.
13. SEARCH BROADENING & ALTERNATIVE REQUESTS: When a user says 'provide me some other property', 'show other options', or 'show me something else' after a search yielded 0 matches or few options in a specific community, invoke `search_properties` with broader criteria (e.g. city='Dubai' or all UAE) without restricting to the previous narrow community or budget cap.
14. INVESTMENT GUIDANCE & AREA SELECTION: When the user asks exploratory or high-level investment questions (e.g. 'What is the best place to invest in Dubai?', 'Give me the names of places to invest', 'Where should I invest?'), do NOT refuse or immediately demand bedroom and budget numbers. Answer their question directly and authoritatively by providing an overview of premier investment areas (such as Downtown Dubai, Dubai Marina & JBR, Business Bay, Palm Jumeirah, Dubai Hills Estate, Dubai Creek Harbour, and JVC), outlining the trade-offs between capital appreciation and rental yield. Conclude by inviting them to select an area, budget, or property type if they would like to review live listings.
"""

class LLMService:
    @classmethod
    def get_system_prompt(cls, language: str = "en") -> str:
        lang_names = {"en": "English", "ar": "Arabic (العربية)", "hi": "Hindi (हिन्दी)", "ur": "Urdu (اردو)"}
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
