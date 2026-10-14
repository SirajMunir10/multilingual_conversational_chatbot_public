import json
import logging
import re
import asyncio
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
from app.core.usage_tracker import UsageTracker

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
        UsageTracker.record_turn(session.session_id, role="user")

        # 5. Intent Routing & Slot Filling (FR-3, FR-4)
        intent = cls._classify_intent(sanitized_input, session)
        session.active_intent = intent
        if intent == "human_handoff":
            session.handoff_requested = True
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
        UsageTracker.record_turn(session.session_id, role="assistant")

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
            "saved_properties": response_data.get("saved_properties", []),
            "application_status": response_data.get("application_status"),
            "handoff_data": response_data.get("handoff_data"),
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

        # Differentiate informational questions about brokers/agents/commissions vs requests for callback
        informational_agent_terms = [
            "commission", "fee", "fees", "what is an agent", "what is a broker", "what does an agent do",
            "what does a broker do", "how much commission", "agent fee", "broker fee", "brokerage fee",
            "how much do brokers charge", "percentage", "rate of commission", "عمولة", "رسوم", "کمیشن", "दलाली"
        ]
        is_informational_agent_inquiry = any(t in lowered for t in informational_agent_terms)

        # Human Handoff intent keywords (FR-5, FR-20)
        handoff_phrases = [
            "speak with advisor", "talk to human", "talk to agent", "connect me", "transfer me",
            "speak to human", "speak to an agent", "human please", "talk to a person", "advisor please",
            "speak with an agent", "speak with agent", "talk to an advisor", "talk to advisor",
            "contact advisor", "request an advisor", "request advisor", "human advisor",
            "call me", "callback", "want to talk to someone", "need to speak", "reach out to me",
            "human", "agent", "advisor", "broker", "specialist", "consultant", "representative",
            "مستشار", "وكيل", "تحدث مع موظف", "تحدث مع إنسان", "إنسان", "موظف",
            "एजेंट", "सलाहकार", "इंसान", "बात करनी है", "ایجنٹ", "مشیر", "انسان سے بات",
            "humain", "conseiller", "représentant", "parler à un conseiller", "parler à un humain",
            "humano", "asesor", "agente", "hablar con un agente", "hablar con un humano",
            "mensch", "berater", "makler", "mit einem berater sprechen", "mit einem menschen sprechen",
            "人工", "客服", "房产顾问", "经纪人", "转人工", "人工服务",
            "ahente", "tagapayo", "kausapin ang tao", "makipag-usap sa tao",
            "مشاور", "کارشناس", "صحبت با مشاور", "صحبت با انسان", "نماینده", "اپراتور",
            "এজেন্ট", "পরামর্শদাতা", "মানুষের সাথে কথা", "উপদেষ্টা",
            "முகவர்", "ஆலோசகர்", "மனிதர்", "பேச வேண்டும்",
            "ਸਲਾਹਕਾਰ", "ਇਨਸਾਨ ਨਾਲ ਗੱਲ", "ਨੁਮਾਇੰਦਾ",
            "ഏജന്റ്", "ഉപദേശകൻ", "മനുഷ്യൻ", "സംസാരിക്കണം",
            "ପରାମର୍ଶଦାତା", "ମଣିଷ ସହିତ କଥା"
        ]
        is_explicit_handoff = not is_informational_agent_inquiry and any(
            (re.search(r'\b' + re.escape(w) + r'\b', lowered) if w.isascii() else (w in lowered))
            for w in handoff_phrases
        )

        # Contact information indicators
        has_phone_number = bool(re.search(r'(\+?\d{1,4}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{3,9})', text))
        has_contact_terms = any(w in lowered for w in ["phone", "number", "mobile", "whatsapp", "call me at", "reach me at", "my name is", "email"])

        # Trust, safety, and privacy inquiries (Article 53, UAE PDPL Law 45, DLD Title Deed verification)
        trust_safety_terms = [
            "safe", "safety", "trust", "proof", "privacy", "scam", "why", "how", "who",
            "protect", "law", "guarantee", "legit", "legitimate", "secure", "security", "pdpl", "article 53"
        ]
        is_trust_safety_inquiry = any((re.search(r'\b' + re.escape(w) + r'\b', lowered) if w.isascii() else (w in lowered)) for w in trust_safety_terms) or "?" in text

        # Check if user declined advisor callback consent
        decline_words = ["no", "never", "don't", "dont", "not willing", "cancel", "refuse", "stop", "i will not", "نہیں", "لا", "नहीं", "ਨਾ", "না", "விருப்பமில்லை", "வேண்டாம்", "അരുത്", "ନାହିଁ", "non", "nein", "buhay", "خیر", "نه", "不", "不用"]
        is_declining = any((re.search(r'\b' + re.escape(w) + r'\b', lowered) if w.isascii() else (w in lowered)) for w in decline_words) or lowered.strip() in decline_words

        # Only treat as a decline if it is a pure refusal WITHOUT a safety/trust question and without phone number
        if (session.handoff_requested or session.slots.advisor_consent_pending) and is_declining and not is_trust_safety_inquiry and not has_phone_number:
            session.slots.advisor_consent_pending = False
            session.slots.customer_consent_given = False
            return "handoff_declined"

        if is_trust_safety_inquiry and any(w in lowered for w in ["safe", "safety", "trust", "proof", "privacy", "scam", "protect", "guarantee", "legit", "legal", "pdpl", "article 53"]):
            return "trust_safety"

        # Check for affirmative consent in Turn 2
        affirmative_consent_words = [
            "yes", "sure", "please", "connect me", "arrange that", "okay", "ok", "yep", "yeah",
            "haan", "na'am", "naam", "agree", "proceed", "i agree", "i consent", "نعم", "हाँ", "ضرور", "جی ہاں"
        ]
        is_affirming_consent = any((re.search(r'\b' + re.escape(w) + r'\b', lowered) if w.isascii() else (w in lowered)) for w in affirmative_consent_words) or lowered.strip() in affirmative_consent_words

        if session.slots.advisor_consent_pending and is_affirming_consent:
            session.slots.customer_consent_given = True
            session.slots.advisor_consent_pending = False
            return "human_handoff"

        # Gender / Identity inquiry
        gender_kw = [
            "are you a boy or a girl", "are you a boy or girl", "are you a boy", "are you a girl",
            "are you male or female", "what is your gender", "are you male", "are you female",
            "larka ho ya larki", "ladka ho ya ladki", "kya tum ladke ho", "kya tum larke ho",
            "larka ho", "ladka ho", "larki ho", "ladki ho",
            "هل أنت ولد أم بنت", "هل انت ولد ام بنت", "هل أنت ذكر أم أنثى", "هل انت ولد",
            "tu es un garçon ou une fille", "tu es un garçon", "es-tu un garçon",
            "eres un chico o una chica", "eres un chico", "eres un niño",
            "bist du ein junge oder ein mädchen", "bist du ein junge",
            "你是男生还是女生", "你是男生吗", "ikaw ba ay lalaki o babae", "lalaki ka ba",
            "آیا شما پسر هستید یا دختر", "آیا شما پسر هستید",
            "তুমি কি ছেলে না মেয়ে", "তুমি কি ছেলে",
            "நீ பையனா அல்லது பெண்ணா", "நீ ஒரு பையனா",
            "ਤੁਸੀਂ ਮੁੰਡਾ ਹੋ ਜਾਂ ਕੁੜੀ", "ਕੀ ਤੁਸੀਂ ਮੁੰਡਾ ਹੋ",
            "നീ ആണാണോ പെണ്ണാണോ", "നീ ഒരു ആൺകുട്ടിയാണോ",
            "ତୁମେ ପୁଅ ନା ଝିଅ", "ତୁମେ କଣ ପୁଅ"
        ]
        if any(kw in lowered for kw in gender_kw):
            return "identity"

        if is_explicit_handoff or (
            (session.handoff_requested or session.active_intent == "human_handoff")
            and (has_phone_number or session.slots.customer_consent_given or has_contact_terms)
        ):
            return "human_handoff"

        # Account intent keywords (strictly scoped to user profile/vault access)
        account_kw = [
            "my application", "my status", "saved properties", "my shortlist",
            "view shortlist", "view my shortlist", "show shortlist", "show my shortlist",
            "saved shortlist", "my favorites", "my inquiries", "my saved", "saved homes",
            "shortlisted properties", "حسابي", "طلباتي", "عقاراتي", "عقاراتي المحفوظة",
            "قائمتي المحفوظة", "मेरा स्टेटस", "मेरी सेव की गई", "میری محفوظ",
            "mon dossier", "mes favoris", "mes biens enregistrés", "ma sélection",
            "mi solicitud", "mis favoritos", "mis propiedades guardadas",
            "meine anfrage", "gespeicherte immobilien", "meine favoriten",
            "我的申请", "收藏的房产", "我的收藏", "房产清单",
            "aking aplikasyon", "mga naka-save na ari-arian",
            "درخواست من", "املاک ذخیره شده", "علاقه‌مندی‌های من",
            "আমার সংরক্ষিত", "সংরক্ষিত সম্পত্তি",
            "என் சேமிக்கப்பட்ட",
            "ਮੇਰੀਆਂ ਸੁਰੱਖਿਅਤ",
            "എന്റെ പ്രോപ്പർട്ടികൾ",
            "ମୋର ସଂରକ୍ଷିତ"
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
            "اي واحد", "مقارنة", "أيهما أفضل", "أفضل للاستثمار", "तुलना", "कौन सा बेहतर", "موازنہ", "کون سا بہتر",
            "comparer", "lequel choisir", "lequel est meilleur", "quel est le meilleur",
            "comparar", "cuál es mejor", "cuál de estos", "cuál debería comprar",
            "vergleichen", "welches ist besser", "welches soll ich kaufen",
            "对比", "比较", "哪一个更好", "应该买哪个",
            "ihambing", "alin ang mas maganda",
            "مقایسه", "کدام بهتر است", "کدام را بخرم",
            "তুলনা", "কোনটি ভালো",
            "ஒப்பீடு", "எது சிறந்தது",
            "ਮੁਕਾਬਲਾ", "ਕਿਹੜਾ ਬਿਹਤਰ ਹੈ",
            "താരതമ്യം", "ഏതാണ് നല്ലത്",
            "ତୁଳନା", "କେଉଁଟି ଭଲ"
        ]
        if bool(session.last_recommended_properties) and any(kw in lowered for kw in comparison_kw):
            return "property_comparison"

        # Mortgage intent keywords
        mortgage_kw = [
            "emi", "monthly payment", "mortgage", "afford", "affordability", "interest rate", "loan", "down payment", "dbr",
            "قرض", "تمويل", "رهن", "دفعة شهرية", "किस्त", "लोन", "مارگیج",
            "hypothèque", "prêt", "taux d'intérêt", "mensualité", "crédit immobilier",
            "hipoteca", "préstamo", "tasa de interés", "pago mensual",
            "hypothek", "kredit", "zinssatz", "monatliche rate", "darlehen",
            "房贷", "贷款", "按揭", "月供", "利率",
            "sangla", "utang", "buwanang bayad",
            "وام مسکن", "وام", "اقساط", "نرخ بهره", "پرداخت ماهیانه",
            "বন্ধক", "ঋণ", "গৃহঋণ",
            "கடன்", "மாத தவணை",
            "ਕਰਜ਼ਾ", "ਕਿਸ਼ਤ",
            "വായ്പ", "പ്രതിമാസ അടവ്",
            "ଋଣ", "ମାସିକ କିସ୍ତି"
        ]
        if any(kw in lowered for kw in mortgage_kw):
            return "mortgage"

        # Property intent keywords
        property_kw = [
            "bedroom", "bed", "br", "apartment", "villa", "townhouse", "penthouse", "studio", "downtown", "marina", "hills", "property", "buy", "rent", "invest", "residence", "residences",
            "شقة", "فيلا", "عقار", "شراء", "إيجار", "फ्लैट", "پراپرٹی",
            "chambre", "appartement", "propriété", "acheter", "louer", "immobilier",
            "habitación", "apartamento", "departamento", "propiedad", "comprar", "alquilar",
            "schlafzimmer", "wohnung", "immobilie", "kaufen", "mieten",
            "卧室", "公寓", "别墅", "房产", "买房", "租房", "住宅",
            "kuwarto", "bahay", "lupa", "bumili", "umupa",
            "اتاق", "آپارتمان", "ویلا", "ملک", "خرید", "اجاره",
            "বেডরুম", "অ্যাপার্টমেন্ট", "বাড়ি", "ক্রয়",
            "படுக்கையறை", "அபார்ட்மெண்ட்", "வீடு", "வாங்க",
            "ਬੈੱਡਰੂਮ", "ਅਪਾਰਟਮੈਂਟ", "ਘਰ", "ਖਰੀਦਣਾ",
            "മുറി", "അപ്പാർട്ട്മെന്റ്", "വീട്", "വാങ്ങുക",
            "ରୁମ", "ଫ୍ଲାଟ", "ଘର", "କିଣିବା"
        ]
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
        bed_match = re.search(r'(\d+)\s*(?:bed|bedroom|br|bhk|غرف|غرفة|chambres?|dormitorios?|zimmer|房|室|kuwarto|اتاق|ঘর|படுக்கையறை|ਕਮਰਾ|മുറി|ରୁମ)', lowered)
        if bed_match:
            session.slots.property_beds = int(bed_match.group(1))

        # Extract budget / numbers with suffixes (e.g. 800k, 1.5m)
        num_k = re.search(r'(\d+(?:\.\d+)?)\s*(?:k|thousand|ألف|हज़ार|হাজার|ஆயிரம்|हजार|kilo|mil|tausend|هزار)', lowered)
        if num_k:
            val = float(num_k.group(1)) * 1000
            if session.active_intent == "property":
                session.slots.property_budget_max = val
            elif session.active_intent == "mortgage":
                session.slots.mortgage_income = val

        num_m = re.search(r'(\d+(?:\.\d+)?)\s*(?:m|million|مليون|मिलियन|মিলিয়ন|மில்லியன்|میلیون|milhão|millones|mio|万|亿)', lowered)
        if num_m:
            val = float(num_m.group(1)) * 1000000
            session.slots.property_budget_max = val

        # Specific Mortgage Income slot extraction (e.g., "earn 25000 AED", "salary 30,000", "45000 AED income")
        income_match = re.search(r'(?:earn|salary|income|راتب|دخل|मासिक आय|آمدنی|salaire|sueldo|gehalt|收入|sweldo|حقوق|বেতন|வருமானம்|ਤਨਖਾਹ|ശമ്പളം|ଦରମା)\s*(?:of|is|:)?\s*(?:aed|dhs)?\s*([0-9][0-9,]*)', lowered)
        if not income_match:
            income_match = re.search(r'([0-9][0-9,]*)\s*(?:aed|dhs)?\s*(?:income|salary|earn|per month|\/mo|monthly|شهري|ماہانہ)', lowered)
        if income_match:
            val_str = income_match.group(1).replace(',', '').strip()
            if val_str:
                try:
                    session.slots.mortgage_income = float(val_str)
                except ValueError:
                    pass

        # Comprehensive Mortgage Debt slot extraction (zero-debt phrases + explicit numeric amounts)
        zero_debt_patterns = [
            r"\b(zero|0|no|none|nil)\s+(debt|debts|liability|liabilities|loans?|car\s+loans?|commitments?)\b",
            r"\b(i\s+have\s+no|i\s+don't\s+have\s+any|have\s+no|don't\s+have\s+any)\s+(debt|debts|loans?|car\s+loans?|credit\s+cards?|liabilities)\b",
            r"\b(debt[- ]free|liability[- ]free|no\s+existing\s+debt|zero\s+existing\s+debt)\b",
            r"^(none|zero|0|nil|no)$"
        ]
        zero_debt_terms = [
            "لا توجد ديون", "بدون ديون", "صفر ديون", "لا ديون",
            "کوئی قرض نہیں", "قرض نہیں", "صفر قرض",
            "कोई कर्ज नहीं", "कोई ऋण नहीं", "कर्ज मुक्त", "ऋण मुक्त"
        ]
        if any(re.search(p, lowered) for p in zero_debt_patterns) or any(w in lowered for w in zero_debt_terms):
            session.slots.mortgage_existing_debt = 0.0
        else:
            debt_match = re.search(r'(?:debt|car loan|loan debt|liabilities|ديون|التزامات|कर्ज|वाجبات|dette|deuda|schulden|负债|utang|بدهی|ঋণ|கடன்|ਕਰਜ਼ਾ|കടം|ଋଣ)\s*(?:of|is|:)?\s*(?:aed|dhs)?\s*([0-9][0-9,]*)', lowered)
            if not debt_match:
                debt_match = re.search(r'([0-9][0-9,]*)\s*(?:aed|dhs)?\s*(?:car loan|loan debt|debt)', lowered)
            if debt_match:
                val_str = debt_match.group(1).replace(',', '').strip()
                if val_str:
                    try:
                        session.slots.mortgage_existing_debt = float(val_str)
                    except ValueError:
                        pass

        # Down payment extraction (e.g., "200000 down payment", "1 million down payment", "down payment 20%")
        dp_m = re.search(r'(\d+(?:\.\d+)?)\s*(?:m|million|مليون|मिलियन)\s*(?:down payment|downpayment)', lowered)
        if dp_m:
            session.slots.mortgage_down_payment = float(dp_m.group(1)) * 1000000
        else:
            dp_match = re.search(r'(?:down payment|downpayment|equity|دفعة أولى|ڈاؤن پیمنٹ|apport|pago inicial|anzahlung|首付|paunang bayad|پیش پرداخت|ডাউন পেমেন্ট|முன்பணம்|ਡਾਊਨ ਪੇਮੈਂਟ|ഡൗൺ പേയ്മെന്റ്|ଅଗ୍ରୀମ)\s*(?:of|is|:)?\s*(?:aed|dhs)?\s*([0-9][0-9,]*)', lowered)
            if not dp_match:
                dp_match = re.search(r'([0-9][0-9,]*)\s*(?:aed|dhs)?\s*(?:down payment|downpayment)', lowered)
            if dp_match:
                val_str = dp_match.group(1).replace(',', '').strip()
                if val_str:
                    try:
                        session.slots.mortgage_down_payment = float(val_str)
                    except ValueError:
                        pass

        # Extract property type
        for ptype in ["apartment", "villa", "townhouse", "penthouse"]:
            if ptype in lowered or \
               ("شقة" in text or "appartement" in lowered or "apartamento" in lowered or "wohnung" in lowered or "公寓" in text or "آپارتمان" in text or "অ্যাপার্টমেন্ট" in text or "அபார்ட்மெண்ட்" in text) and ptype == "apartment" or \
               ("فيلا" in text or "villa" in lowered or "chalet" in lowered or "别墅" in text or "ویلا" in text or "বাড়ি" in text or "வீடு" in text) and ptype == "villa":
                session.slots.property_type = ptype

        # Extract developer entity
        dev_map = [
            ("imtiyaz developments", "Imtiyaz"),
            ("imtiyaz", "Imtiyaz"),
            ("imtiaz", "Imtiyaz"),  # Common keyboard typo
            ("emaar", "Emaar"),
            ("damac", "Damac"),
            ("nakheel", "Nakheel"),
            ("sobha", "Sobha"),
            ("select group", "Select Group"),
            ("ellington", "Ellington"),
            ("meraas", "Meraas"),
            ("aldar", "Aldar")
        ]
        for pattern, canon_dev in dev_map:
            if re.search(r'\b' + re.escape(pattern) + r'\b', lowered):
                session.slots.property_developer = canon_dev
                break

        # Check for general "other property" requests to broaden search
        if any(w in lowered for w in ["other property", "other properties", "other options", "something else", "different property", "عقارات أخرى", "خيارات أخرى", "अन्य प्रॉपर्टी", "دوسری پراپرٹی"]):
            session.slots.property_city = "Dubai"
            session.slots.property_budget_max = None
        elif any(w in lowered for w in ["all uae", "in uae", "across uae", "all of uae", "find in uae", "in the uae", "uae", "everywhere in uae", "anywhere in uae"]):
            session.slots.property_city = "UAE"
        elif any(w in lowered for w in ["all dubai", "across dubai", "anywhere in dubai", "in dubai"]):
            if not any(loc in lowered for loc in ["downtown", "marina", "business bay", "dubai hills", "palm", "jvc", "creek", "jbr", "ranches", "jlt", "glt"]):
                session.slots.property_city = "Dubai"

        # Specific communities (ordered by specificity, with fuzzy typo resolution)
        comm_map = [
            ("palm jumeirah", "Palm Jumeirah"),
            ("palm", "Palm Jumeirah"),
            ("dubai hills estate", "Dubai Hills Estate"),
            ("dubai hills", "Dubai Hills Estate"),
            ("hills", "Dubai Hills Estate"),
            ("downtown dubai", "Downtown Dubai"),
            ("dwon town", "Downtown Dubai"),
            ("downtwon", "Downtown Dubai"),
            ("downtown", "Downtown Dubai"),
            ("dubai marina", "Dubai Marina"),
            ("marina", "Dubai Marina"),
            ("business bay", "Business Bay"),
            ("jumeirah lake towers", "JLT"),
            ("jlt", "JLT"),
            ("glt", "JLT"),  # Common keyboard typo (G next to J)
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
            ("yas", "Yas Island"),
            ("difc", "DIFC"),
            ("meydan", "Meydan"),
            ("majan", "Majan")
        ]
        matched_comm = False
        for pattern, canon in comm_map:
            if re.search(r'\b' + re.escape(pattern) + r'\b', lowered):
                session.slots.property_city = canon
                matched_comm = True
                if pattern in ["glt", "dwon town", "downtwon"]:
                    session.slots.inferred_location_note = f"Assuming you mean {canon}"
                else:
                    session.slots.inferred_location_note = None
                session.slots.unconfirmed_location = None
                break

        # Detect unconfirmed location pattern (e.g. "apartments in alt", "properties in alt")
        if not matched_comm and session.active_intent in ["property", "general"]:
            loc_match = re.search(r'\b(?:in|at|near|around|for)\s+([a-zA-Z]{2,15})\b', text)
            if loc_match:
                cand = loc_match.group(1).strip()
                cand_lower = cand.lower()
                common_non_locations = [
                    "dubai", "uae", "abu", "dhabi", "buy", "rent", "invest", "cash", "mortgage", "aed",
                    "budget", "apartment", "apartments", "villa", "villas", "townhouse", "sale", "ready",
                    "offplan", "off", "plan", "terms", "english", "arabic", "hindi", "urdu", "french",
                    "german", "spanish", "chinese", "tagalog", "bengali", "tamil", "punjabi", "malayalam",
                    "dia", "persian", "touch", "call", "details", "contact", "person", "advisor", "agent",
                    "broker", "specialist", "viewing", "mind", "general", "advance", "handover", "future",
                    "month", "year", "years", "my", "our", "their", "this", "that", "these", "those"
                ]
                if cand_lower not in common_non_locations and not any(cand_lower in c[0] for c in comm_map):
                    session.slots.unconfirmed_location = cand

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

        # Extract customer contact details (phone, name, language)
        phone_match = re.search(r'(?:phone|number|mobile|tel|contact|call|whatsapp)?[:\s]*(\+?\d{1,4}(?:[-.\s]?\d{1,9}){1,4})', text, re.IGNORECASE)
        if phone_match:
            candidate_phone = phone_match.group(1).strip()
            digits = re.sub(r'\D', '', candidate_phone)
            # Avoid matching property prices, budgets, or areas (must be 7-15 digits)
            is_financial_number = any(w in lowered for w in ["aed", "dirham", "price", "budget", "salary", "income", "sqft", "sq.ft", "million", "k"])
            if 7 <= len(digits) <= 15 and not (len(digits) <= 8 and is_financial_number):
                session.slots.customer_phone = candidate_phone
                session.slots.customer_consent_given = True

        name_match = re.search(r'(?:my name is|i am|name is|call me|name[:\s]+)\s*([A-Za-z\u0600-\u06FF\u0900-\u097F\u0B00-\u0B7F\s\'-]+?)(?:,|\.|\bphone\b|\bnumber\b|\bmobile\b|\bcall\b|\bwhatsapp\b|$)', text, re.IGNORECASE)
        if name_match:
            cand_name = name_match.group(1).strip()
            if cand_name and len(cand_name) >= 2:
                session.slots.customer_name = cand_name.title()

        # Extract preferred language if explicitly stated or provided in intake
        for lang_k, lang_meta in LanguageDetector.get_supported_locales().items():
            l_name = lang_meta["name"].lower()
            l_native = lang_meta["native"].lower()
            if re.search(r'\b' + re.escape(l_name) + r'\b', lowered) or re.search(r'\b' + re.escape(l_native) + r'\b', lowered):
                if session.slots.customer_consent_given or session.slots.advisor_consent_pending or any(w in lowered for w in ["language", "speak in", "speak", "comfortable in", "contact in", "talk in", "in", "باللغة", "भाषा", "ਭਾਸ਼ਾ", "ഭാഷ"]):
                    session.slots.customer_preferred_language = lang_meta["name"]
                    break

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

                if lang != "en":
                    locales = LanguageDetector.get_supported_locales()
                    lang_info = locales.get(lang, {"name": lang, "native": lang})
                    messages.append({
                        "role": "system",
                        "content": (
                            f"MANDATORY LANGUAGE DIRECTIVE: The user has selected {lang_info.get('name', lang)} ({lang_info.get('native', lang)}). "
                            f"You MUST generate your entire response 100% in {lang_info.get('name', lang)} using its native script ({lang_info.get('native', lang)}). "
                            f"Under NO circumstances should you reply in English or claim you can only speak English. "
                            f"Proceed enthusiastically in {lang_info.get('name', lang)}."
                        )
                    })

                tool_choice = "auto"
                comp_data = None
                has_contact_info = bool(session.slots.customer_phone)

                if session.active_intent == "human_handoff":
                    if has_contact_info:
                        tool_choice = {"type": "function", "function": {"name": "request_human_handoff"}}
                        c_name = session.slots.customer_name or "Client"
                        c_phone = session.slots.customer_phone
                        c_lang = session.slots.customer_preferred_language or lang
                        messages.append({
                            "role": "system",
                            "content": (
                                f"CONFIRM CALLBACK PROTOCOL: The user has provided their contact details "
                                f"(Name: {c_name}, Phone: {c_phone}, Preferred Language: {c_lang}). "
                                f"You MUST call `request_human_handoff` with applicant_name='{c_name}', "
                                f"applicant_phone='{c_phone}', and preferred_language='{c_lang}'. "
                                f"In your response, confirm concisely that our advisory team will contact them directly at {c_phone} in {c_lang}. "
                                f"DO NOT list or display any individual advisor names, licenses, phone numbers, or WhatsApp links."
                            )
                        })
                    elif session.slots.customer_consent_given:
                        # Turn 2: User explicitly agreed; ask for the 3 contact details
                        tool_choice = "none"
                        locales = LanguageDetector.get_supported_locales()
                        cur_lang = locales.get(lang, {}).get("name", "English")
                        messages.append({
                            "role": "system",
                            "content": (
                                f"MANDATORY ADVISOR INTAKE PROTOCOL (TURN 2 — CONTACT DETAILS): "
                                f"The user has explicitly agreed to have an advisor contact them directly. "
                                f"DO NOT invent, generate, or provide phone numbers or WhatsApp links, and DO NOT list individual advisor names! "
                                f"In a polite, concise response in {cur_lang}, request the necessary details to arrange the callback:\n"
                                f"1. Full Name\n"
                                f"2. Phone Number (with country code)\n"
                                f"3. Preferred Contact Language\n"
                                f"Do NOT call request_human_handoff until they provide their phone number and name."
                            )
                        })
                    else:
                        # Turn 1: User requested an advisor; ask for permission ONLY
                        tool_choice = "none"
                        session.slots.advisor_consent_pending = True
                        session.handoff_requested = True
                        locales = LanguageDetector.get_supported_locales()
                        cur_lang = locales.get(lang, {}).get("name", "English")
                        messages.append({
                            "role": "system",
                            "content": (
                                f"MANDATORY ADVISOR CONSENT PROTOCOL (TURN 1 — PERMISSION ONLY): "
                                f"The user is asking to speak with or be advised by a human advisor. "
                                f"DO NOT request their name, phone number, or preferred language in this response! "
                                f"DO NOT provide any individual advisor names, phone numbers, or WhatsApp links! "
                                f"In 1 to 2 natural, concise sentences in {cur_lang}: "
                                f"Ask whether they consent to having our licensed advisory team reach out for a direct consultation, "
                                f"and naturally reassure them that continuing to explore properties and calculations anonymously with you is completely fine. "
                                f"Do NOT call request_human_handoff."
                            )
                        })
                elif session.active_intent == "handoff_declined":
                    tool_choice = "none"
                    session.handoff_requested = False
                    messages.append({
                        "role": "system",
                        "content": (
                            f"The user has declined to share contact details for an advisor callback. "
                            f"Acknowledge their decision politely and concisely in {lang}. "
                            f"Explicitly confirm that no contact details will be collected or saved, and ask how else you can help with properties or mortgages."
                        )
                    })
                elif session.active_intent == "identity":
                    tool_choice = "none"
                    messages.append({
                        "role": "system",
                        "content": (
                            f"The user is asking about your gender or identity. "
                            f"Respond naturally, directly, and concisely in {lang} that you are XO, a young boy assistant. "
                            f"Ask how you can assist them with UAE properties or mortgage calculations today."
                        )
                    })
                elif session.active_intent == "account":
                    if any(w in user_text.lower() for w in ["application", "status", "طلب", "स्थिति", "صورتحال"]):
                        tool_choice = {"type": "function", "function": {"name": "get_my_application_status"}}
                    else:
                        tool_choice = {"type": "function", "function": {"name": "get_my_saved_properties"}}
                elif session.active_intent == "property_comparison":
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

                if session.slots.unconfirmed_location:
                    tool_choice = "none"
                    unc = session.slots.unconfirmed_location
                    messages.append({
                        "role": "system",
                        "content": (
                            f"UNCONFIRMED LOCATION DIRECTIVE: The user mentioned '{unc}', which is not a recognized Dubai community or developer. "
                            f"DO NOT invent properties, DO NOT pretend '{unc}' is a real area, and DO NOT dump a generic list of random Dubai communities! "
                            f"In 1 to 2 polite sentences in {lang}, clarify what they meant (e.g. asking whether they meant JLT, Al Barsha, or specific projects) and ask where they would prefer to focus."
                        )
                    })

                if session.slots.inferred_location_note:
                    messages.append({
                        "role": "system",
                        "content": (
                            f"TYPO RESOLUTION NOTE: The user typed a typo which was auto-resolved: '{session.slots.inferred_location_note}'. "
                            f"Acknowledge this transparently and naturally in your reply in {lang} while presenting the options."
                        )
                    })

                trust_safety_terms = ["safe", "safety", "trust", "proof", "privacy", "scam", "protect", "legal", "legit", "pdpl", "article 53", "dld", "rera"]
                if any(w in user_text.lower() for w in trust_safety_terms):
                    messages.append({
                        "role": "system",
                        "content": (
                            f"TRUST & VERIFICATION PROTOCOL (KB Article 53 & UAE Law): "
                            f"The user is asking about safety, privacy, trust, or verification. "
                            f"Under UAE Federal Decree-Law No. 45 of 2021 (PDPL) and DLD regulations, explain that their data is protected under banking-grade encryption and never sold or shared with third-party telemarketers. "
                            f"Confirm that property listings and title deeds are cross-referenced with DLD (Dubai Land Department) official records, off-plan projects are secured by Law No. 8 of 2007 Escrow accounts, and all advisors are RERA-certified. "
                            f"Reassure them that they are completely free to explore properties and calculate mortgage affordability 100% anonymously without providing any contact details. "
                            f"Respond directly and concisely in {lang}."
                        )
                    })

                response = await client.chat.completions.create(
                    model=settings.LLM_MODEL,
                    messages=messages,
                    tools=XO_FUNCTION_TOOLS,
                    tool_choice=tool_choice
                )

                if hasattr(response, "usage") and response.usage:
                    u = response.usage
                    cached_t = 0
                    if hasattr(u, "prompt_tokens_details") and u.prompt_tokens_details:
                        cached_t = getattr(u.prompt_tokens_details, "cached_tokens", 0) or 0
                    elif isinstance(u, dict) and "prompt_tokens_details" in u:
                        cached_t = u["prompt_tokens_details"].get("cached_tokens", 0)
                    UsageTracker.record_llm(
                        session_id=session.session_id,
                        model=settings.LLM_MODEL,
                        prompt_tokens=getattr(u, "prompt_tokens", 0),
                        cached_tokens=cached_t,
                        completion_tokens=getattr(u, "completion_tokens", 0),
                        total_tokens=getattr(u, "total_tokens", 0),
                        tool_call_step="primary"
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
                        if hasattr(second_response, "usage") and second_response.usage:
                            u2 = second_response.usage
                            cached_t2 = 0
                            if hasattr(u2, "prompt_tokens_details") and u2.prompt_tokens_details:
                                cached_t2 = getattr(u2.prompt_tokens_details, "cached_tokens", 0) or 0
                            elif isinstance(u2, dict) and "prompt_tokens_details" in u2:
                                cached_t2 = u2["prompt_tokens_details"].get("cached_tokens", 0)
                            UsageTracker.record_llm(
                                session_id=session.session_id,
                                model=settings.LLM_MODEL,
                                prompt_tokens=getattr(u2, "prompt_tokens", 0),
                                cached_tokens=cached_t2,
                                completion_tokens=getattr(u2, "completion_tokens", 0),
                                total_tokens=getattr(u2, "total_tokens", 0),
                                tool_call_step="tool_followup"
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
                        "saved_properties": tool_exec.get("saved_properties_result", {}).get("saved_properties", []),
                        "application_status": tool_exec.get("application_status_result"),
                        "handoff_data": tool_exec.get("handoff_result"),
                        "handoff_offered": bool(tool_exec.get("handoff_result")),
                        "tool_calls": [{"function": fn_name, "args": fn_args}],
                        "metadata": tool_exec.get("metadata", {})
                    }

                if session.active_intent == "human_handoff":
                    if has_contact_info:
                        from app.services.handoff_service import HandoffService
                        handoff_res = HandoffService.initiate_handoff(
                            session_id=session.session_id,
                            applicant_name=session.slots.customer_name,
                            applicant_phone=session.slots.customer_phone,
                            preferred_language=session.slots.customer_preferred_language or session.language,
                            reason="explicit_request",
                            user_id=session.user_id
                        )
                        return {
                            "text": reply_message.content or "",
                            "handoff_data": handoff_res,
                            "handoff_offered": True
                        }
                    else:
                        # User has not provided contact details yet; return conversational permission request without card
                        return {
                            "text": reply_message.content or "",
                            "handoff_offered": False
                        }

                if session.active_intent == "account" and session.user_id:
                    from app.services.account_service import AccountService
                    saved_data = AccountService.get_my_saved_properties(session.user_id, session_id=session.session_id)
                    app_data = AccountService.get_my_application_status(session.user_id, session_id=session.session_id)
                    return {
                        "text": reply_message.content or "",
                        "saved_properties": saved_data.get("saved_properties", []),
                        "application_status": app_data
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
            req_developer = fn_args.get("developer", session.slots.property_developer)

            filters = PropertySearchFilter(
                city=city_filter,
                type=fn_args.get("type", session.slots.property_type),
                budget_min=fn_args.get("budget_min", session.slots.property_budget_min),
                budget_max=b_max,
                beds=fn_args.get("beds", session.slots.property_beds),
                purpose=fn_args.get("purpose", session.slots.property_purpose),
                status=fn_args.get("status"),
                developer=req_developer,
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

                if filters.developer:
                    dev_alts = alts.get("developer_alternatives", {})
                    other_devs_in_comm = dev_alts.get("other_developers_in_community", [])
                    dev_other_comms = dev_alts.get("developer_other_communities", [])
                    guidance = (
                        f"CRITICAL INSTRUCTION: Exact search for developer '{filters.developer}' in '{location_name}' returned 0 matching listings. "
                        f"Do NOT say or pretend '{filters.developer}' has listings in '{location_name}'! "
                        f"Politely and directly inform the user that {filters.developer} does not currently have active listings in {location_name}. "
                    )
                    if other_devs_in_comm:
                        guidance += f"Mention that {location_name} has residences available by other premier developers such as {', '.join(other_devs_in_comm[:3])}. "
                    if dev_other_comms:
                        guidance += f"Mention that {filters.developer} offers projects in other communities such as {', '.join(dev_other_comms[:3])}. "
                    guidance += (
                        f"Proactively ask the user (in 1 single follow-up question) whether they would like to explore options by other developers in {location_name}, "
                        f"or see projects by {filters.developer} in other communities."
                    )
                    tool_summary["guidance_for_assistant"] = guidance
                elif alts.get("has_community_properties"):
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

        elif fn_name == "get_my_saved_properties":
            from app.services.account_service import AccountService
            res = AccountService.get_my_saved_properties(session.user_id, session_id=session.session_id)
            return {
                "saved_properties_result": res,
                "tool_result_for_llm": res
            }

        elif fn_name == "get_my_application_status":
            from app.services.account_service import AccountService
            res = AccountService.get_my_application_status(session.user_id, session_id=session.session_id)
            return {
                "application_status_result": res,
                "tool_result_for_llm": res
            }

        elif fn_name == "create_lead_grid":
            from app.gateways.grid_gateway import GridGateway, GridLeadPayload
            payload = GridLeadPayload(**fn_args)
            lead_res = GridGateway.create_lead(payload, session_id=session.session_id, user_id=session.user_id)
            return {
                "grid_lead_result": lead_res.model_dump(),
                "tool_result_for_llm": lead_res.model_dump()
            }

        elif fn_name == "create_lead_vault":
            from app.gateways.vault_gateway import VaultGateway, VaultMortgageLeadPayload
            payload = VaultMortgageLeadPayload(**fn_args)
            vault_res = VaultGateway.create_lead(payload, session_id=session.session_id, user_id=session.user_id)
            return {
                "vault_lead_result": vault_res.model_dump(),
                "tool_result_for_llm": vault_res.model_dump()
            }

        elif fn_name == "request_human_handoff":
            from app.services.handoff_service import HandoffService
            reason = fn_args.get("reason", "explicit_request")
            preferred_team = fn_args.get("preferred_team")
            notes = fn_args.get("notes")
            app_name = fn_args.get("applicant_name") or session.slots.customer_name
            app_phone = fn_args.get("applicant_phone") or session.slots.customer_phone
            pref_lang = fn_args.get("preferred_language") or session.slots.customer_preferred_language or session.language
            handoff_res = HandoffService.initiate_handoff(
                session_id=session.session_id,
                applicant_name=app_name,
                applicant_phone=app_phone,
                preferred_language=pref_lang,
                reason=reason,
                preferred_team=preferred_team,
                notes=notes,
                user_id=session.user_id
            )
            return {
                "handoff_result": handoff_res,
                "tool_result_for_llm": handoff_res
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

        elif fn_name == "get_my_saved_properties":
            saved_res = raw_res.get("saved_properties_result", {})
            if not saved_res.get("authenticated"):
                auth_msgs = {
                    "ar": "للوصول إلى عقاراتك المحفوظة والمختارة، يرجى تسجيل الدخول أولاً لحماية بياناتك الشخصية.",
                    "hi": "अपनी सेव की गई पसंदीदा प्रॉपर्टीज देखने के लिए, कृपया पहले साइन इन करें।",
                    "ur": "اپنی محفوظ شدہ پراپرٹیز دیکھنے کے لیے، براہ کرم پہلے سائن ان کریں۔",
                    "en": "To access your shortlisted properties, please sign in. All account data is strictly user-scoped and secure."
                }
                return {
                    "text": auth_msgs.get(lang, auth_msgs["en"]),
                    "saved_properties": [],
                    "tool_calls": [{"function": fn_name, "args": fn_args}]
                }
            
            items = saved_res.get("saved_properties", [])
            narratives = {
                "ar": f"أهلاً {saved_res.get('user_name', '')}! لديك {len(items)} عقارات محفوظة في قائمة رغباتك الخاصة.",
                "hi": f"नमस्ते {saved_res.get('user_name', '')}! आपकी विशलिस्ट में {len(items)} प्रॉपर्टीज सेव हैं।",
                "ur": f"خوش آمدید {saved_res.get('user_name', '')}! آپ کی فہرست میں {len(items)} محفوظ پراپرٹیز موجود ہیں۔",
                "en": f"Welcome back, {saved_res.get('user_name', '')}! You have {len(items)} premier residences saved in your portfolio."
            }
            return {
                "text": narratives.get(lang, narratives["en"]),
                "saved_properties": items,
                "tool_calls": [{"function": fn_name, "args": fn_args}]
            }

        elif fn_name == "get_my_application_status":
            app_res = raw_res.get("application_status_result", {})
            if not app_res.get("authenticated"):
                auth_msgs = {
                    "ar": "للاطلاع على حالة طلبات التمويل ومعاينات العقارات الخاصة بك، يرجى تسجيل الدخول أولاً.",
                    "hi": "अपने मॉर्गेज या प्रॉपर्टी आवेदनों की स्थिति देखने के लिए कृपया साइन इन करें।",
                    "ur": "اپنی مارگیج درخواست یا پراپرٹی کی صورتحال دیکھنے کے لیے براہ کرم لاگ ان کریں۔",
                    "en": "To check your application and viewing status, please sign in. Your inquiries are strictly confidential."
                }
                return {
                    "text": auth_msgs.get(lang, auth_msgs["en"]),
                    "application_status": None,
                    "tool_calls": [{"function": fn_name, "args": fn_args}]
                }

            apps = app_res.get("applications", [])
            narratives = {
                "ar": f"عزيزي {app_res.get('user_name', '')}، لديك {len(apps)} طلبات نشطة مسجلة في نظامنا (Vault & GRID).",
                "hi": f"नमस्ते {app_res.get('user_name', '')}، आपके {len(apps)} सक्रिय आवेदन हमारे सिस्टम में दर्ज हैं।",
                "ur": f"معزز {app_res.get('user_name', '')}، آپ کے {len(apps)} فعال درخواستیں ہمارے سسٹم میں رجسٹرڈ ہیں۔",
                "en": f"Hello {app_res.get('user_name', '')}, you have {len(apps)} active records in our system across Vault Mortgage and GRID."
            }
            return {
                "text": narratives.get(lang, narratives["en"]),
                "application_status": app_res,
                "tool_calls": [{"function": fn_name, "args": fn_args}]
            }

        elif fn_name == "create_lead_grid":
            grid_res = raw_res.get("grid_lead_result", {})
            lead_id = grid_res.get("lead_id", "GRID-LEAD")
            narratives = {
                "ar": f"تم تسجيل طلبك بنجاح في نظام إدارة العقارات (رقم المرجع: {lead_id}). سيتواصل معك أحد مستشارينا قريباً.",
                "hi": f"आपकी इंक्वायरी सफलतापूर्वक दर्ज कर ली गई है (संदर्भ संख्या: {lead_id})। हमारे विशेषज्ञ जल्द ही आपसे संपर्क करेंगे।",
                "ur": f"آپ کی درخواست کامیابی سے رجسٹر کر لی گئی ہے (ریفرنس نمبر: {lead_id})۔ ہمارے نمائندے جلد رابطہ کریں گے۔",
                "en": f"Your inquiry has been successfully lodged with GRID Real Estate (Reference: {lead_id}). A premier property consultant will contact you shortly."
            }
            return {
                "text": narratives.get(lang, narratives["en"]),
                "grid_lead": grid_res,
                "tool_calls": [{"function": fn_name, "args": fn_args}]
            }

        elif fn_name == "create_lead_vault":
            vault_res = raw_res.get("vault_lead_result", {})
            app_id = vault_res.get("application_id", "VAULT-MORT")
            narratives = {
                "ar": f"تم إرسال طلب التمويل العقاري المبدئي بنجاح إلى نظام Vault (رقم الطلب: {app_id}). جاري مراجعة الأهلية مع شركائنا من البنوك.",
                "hi": f"आपका मॉर्गेज प्री-अप्रूवल आवेदन Vault CRM में दर्ज हो चुका है (आवेदन आईडी: {app_id})। हमारे बैंक पार्टनर इसकी समीक्षा कर रहे हैं।",
                "ur": f"آپ کی مارگیج پری اپروول درخواست کامیابی سے Vault میں درج ہو گئی ہے (درخواست نمبر: {app_id})۔",
                "en": f"Your mortgage pre-qualification has been securely submitted to Vault CRM (Application ID: {app_id}). Our mortgage advisory desk is reviewing your file."
            }
            return {
                "text": narratives.get(lang, narratives["en"]),
                "vault_lead": vault_res,
                "tool_calls": [{"function": fn_name, "args": fn_args}]
            }

        elif fn_name == "request_human_handoff":
            handoff_res = raw_res.get("handoff_result", {})
            advisor = handoff_res.get("assigned_advisor", {})
            ticket_id = handoff_res.get("ticket_id", "XO-HD")
            c_phone = handoff_res.get("applicant_phone") or session.slots.customer_phone or "your registered number"
            c_name = handoff_res.get("applicant_name") or session.slots.customer_name or "Valued Client"
            c_lang = handoff_res.get("preferred_language") or session.slots.customer_preferred_language or session.language
            dept = advisor.get("department", "Advisory")
            lead_saved = handoff_res.get("lead_saved", True)
            if lead_saved:
                narratives = {
                    "ar": f"شكراً لك يا {c_name}! تم تسجيل طلبك بنجاح. سيتواصل معك مستشار من فريق {dept} مباشرة على رقمك ({c_phone}) باللغة {c_lang}. تذكرة المتابعة الخاصة بك هي: {ticket_id}.",
                    "hi": f"धन्यवाद {c_name}! आपका अनुरोध दर्ज कर लिया गया है। हमारे {dept} विभाग के सलाहकार आपसे {c_phone} पर {c_lang} में सीधे संपर्क करेंगे। संदर्भ टिकट: {ticket_id}।",
                    "ur": f"شکریہ {c_name}! آپ کی درخواست کامیابی سے درج کر لی گئی ہے۔ ہماری {dept} ٹیم کے مشیر آپ سے {c_phone} پر {c_lang} میں براہ راست رابطہ کریں گے۔ ریفرنس ٹکٹ: {ticket_id}۔",
                    "en": f"Thank you, {c_name}! Your request has been registered. An advisor from our {dept} team will reach out directly at {c_phone} in {c_lang}. Your reference ticket is {ticket_id}."
                }
            else:
                narratives = {
                    "ar": f"تم تسجيل استفسارك ({ticket_id}). يرجى التأكد من تزويدنا برقم هاتفك حتى يتمكن مستشارنا من التواصل معك.",
                    "hi": f"आपकी पूछताछ ({ticket_id}) दर्ज कर ली गई है। कृपया सलाहकार से संपर्क के लिए अपना फोन नंबर प्रदान करें।",
                    "ur": f"آپ کی انکوائری ({ticket_id}) درج کر لی گئی ہے۔ مشیر سے رابطے کے لیے اپنا فون نمبر فراہم کریں۔",
                    "en": f"We have recorded your inquiry ({ticket_id}). Please provide your contact phone number to receive an advisor callback."
                }
            return {
                "text": narratives.get(lang, narratives["en"]),
                "handoff_data": handoff_res,
                "handoff_offered": True,
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
                "fr": "Bienvenue ! Je suis ravi d'échanger avec vous en français ! 🎉 Comment puis-je vous aider aujourd'hui concernant l'immobilier ou les prêts aux Émirats ?",
                "es": "¡Bienvenido! ¡Me encanta hablar contigo en español! 🎉 ¿Cómo puedo ayudarte hoy con propiedades o hipotecas en los EAU?",
                "de": "Herzlich willkommen! Ich freue mich sehr, mich auf Deutsch mit Ihnen zu unterhalten! 🎉 Wie kann ich Ihnen heute bei Immobilien oder Hypotheken in den VAE helfen?",
                "zh": "欢迎！非常高兴用中文与您交流！🎉 今天我可以在阿联酋房产或房贷方面为您提供什么帮助？",
                "tl": "Maligayang pagdating! Masaya akong makipag-usap sa iyo sa Tagalog! 🎉 Paano kita matutulungan ngayon tungkol sa mga ari-arian o mortgage sa UAE?",
                "ta": "வணக்கம்! உங்களுடன் தமிழில் உரையாடுவதில் மிக்க மகிழ்ச்சி! 🎉 யுஏஇ சொத்துக்கள் அல்லது வீட்டுக் கடன் தொடர்பாக இன்று நான் உங்களுக்கு எவ்வாறு உதவ முடியும்?",
                "fa": "خوش آمدید! بسیار خوشحالم که می‌توانم با شما به زبان فارسی گفتگو کنم! 🎉 امروز چگونه می‌توانم در زمینه املاک یا وام مسکن در امارات به شما کمک کنم؟",
                "bn": "স্বাগতম! আপনার সাথে বাংলায় কথা বলতে পেরে আমি আনন্দিত! 🎉 সংযুক্ত আরব আমিরাতের প্রপার্টি বা মর্টগেজ বিষয়ে আজ আপনাকে কীভাবে সাহায্য করতে পারি?",
                "pa": "ਜੀ ਆਇਆਂ ਨੂੰ! ਤੁਹਾਡੇ ਨਾਲ ਪੰਜਾਬੀ ਵਿੱਚ ਗੱਲ ਕਰਕੇ ਬਹੁਤ ਖੁਸ਼ੀ ਹੋਈ! 🎉 ਅੱਜ ਮੈਂ ਯੂਏਈ ਵਿੱਚ ਜਾਇਦਾਦ ਜਾਂ ਮੌਰਗੇਜ ਸੰਬੰਧੀ ਤੁਹਾਡੀ ਕੀ ਮਦਦ ਕਰ ਸਕਦਾ ਹਾਂ?",
                "ml": "സ്വാഗതം! നിങ്ങളുമായി മലയാളത്തിൽ സംസാരിക്കുന്നതിൽ എനിക്ക് അതിയായ സന്തോഷമുണ്ട്! 🎉 യുഎഇ പ്രോപ്പർട്ടികൾ അല്ലെങ്കിൽ മോർട്ട്ഗേജ് സംബന്ധിച്ച് ഇന്ന് ഞാൻ നിങ്ങളെ എങ്ങനെ സഹായിക്കണം?",
                "or": "ସ୍ଵାଗତ! ଆପଣଙ୍କ ସହିତ ଓଡ଼ିଆରେ କଥାବାର୍ତ୍ତା କରିବାକୁ ପାଇ ମୁଁ ବହୁତ ଖୁସି! 🎉 ଆଜି ମୁଁ ୟୁଏଇ ପ୍ରପର୍ଟି କିମ୍ବା ମର୍ଗେଜ୍ ସମ୍ବନ୍ଧରେ ଆପଣଙ୍କୁ କିପରି ସାହାଯ୍ୟ କରିପାରିବି?",
                "en": "Welcome! I'm thrilled to chat with you in English! 🎉 How can I assist you today with premier UAE properties or mortgage financing?"
            }
            return {
                "text": greetings.get(lang, greetings["en"]),
                "property_results": []
            }

        # Identity / Gender inquiry (Young male boy assistant)
        if intent == "identity":
            boy_answers = {
                "en": "I am XO, a young boy assistant! I am here to help you find premier properties and guide you through mortgages across the UAE.",
                "ar": "أنا XO، فتى ومساعدك الذكي! أنا هنا لمساعدتك في استكشاف عقارات الإمارات وحسابات التمويل العقاري.",
                "hi": "मैं XO हूँ, एक लड़का असिस्टेंट! मैं यूएई में प्रॉपर्टीज खोजने और होम लोन की गणना में आपकी सहायता करने के लिए यहाँ हूँ।",
                "ur": "میں XO ہوں، ایک نوجوان لڑکا اسسٹنٹ! میں یو اے ای میں پراپرٹیز تلاش کرنے اور مارگیج میں آپ کی رہنمائی کے لیے حاضر ہوں۔",
                "fr": "Je suis XO, un jeune garçon assistant ! Je suis là pour vous aider à explorer l'immobilier et les prêts aux Émirats.",
                "es": "¡Soy XO, un chico asistente! Estoy aquí para ayudarte a explorar propiedades e hipotecas en los EAU.",
                "de": "Ich bin XO, ein junger Assistent (Junge)! Ich bin hier, um Ihnen bei Immobilien und Hypotheken in den VAE zu helfen.",
                "zh": "我是 XO，一名年轻的男生助手！我在这里协助您探索阿联酋房产和按揭贷款。",
                "tl": "Ako si XO, isang batang lalaking assistant! Nandito ako para tulungan ka sa mga ari-arian at mortgage sa UAE.",
                "fa": "من XO هستم، یک دستیار پسر جوان! من اینجا هستم تا در زمینه املاک و وام مسکن در امارات به شما کمک کنم.",
                "bn": "আমি XO, একজন তরুণ ছেলে সহকারী! সংযুক্ত আরব আমিরাতের প্রপার্টি ও মর্টগেজে আপনাকে সাহায্য করতে আমি এখানে আছি।",
                "pa": "ਮੈਂ XO ਹਾਂ, ਇੱਕ ਮੁੰਡਾ ਸਹਾਇਕ! ਮੈਂ UAE ਵਿੱਚ ਪ੍ਰਾਪਰਟੀ ਅਤੇ ਮੌਰਗੇਜ ਵਿੱਚ ਤੁਹਾਡੀ ਮਦਦ ਕਰਨ ਲਈ ਇੱਥੇ ਹਾਂ।",
                "ta": "நான் XO, ஒரு பையன் உதவியாளர்! யுஏஇ ரியல் எஸ்டேட் மற்றும் வீட்டுக் கடன்களில் உங்களுக்கு உதவ நான் இங்கே இருக்கிறேன்.",
                "ml": "ഞാൻ XO, ഒരു ആൺകുട്ടി അസിസ്റ്റന്റ്! യുഎഇയിലെ പ്രോപ്പർട്ടികളും മോർട്ട്ഗേജുകളും കണ്ടെത്താൻ നിങ്ങളെ സഹായിക്കാൻ ഞാൻ ഇവിടെയുണ്ട്.",
                "or": "ମୁଁ XO, ଜଣେ ପୁଅ ଆସିଷ୍ଟାଣ୍ଟ! UAE ରେ ପ୍ରପର୍ଟି ଏବଂ ମର୍ଗେଜ୍ ରେ ଆପଣଙ୍କୁ ସାହାଯ୍ୟ କରିବା ପାଇଁ ମୁଁ ଏଠାରେ ଅଛି।"
            }
            return {
                "text": boy_answers.get(lang, boy_answers["en"]),
                "property_results": []
            }

        # User declined consent for advisor callback
        if intent == "handoff_declined":
            session.handoff_requested = False
            decline_responses = {
                "en": "Understood! I will not collect or store your contact details. How else can I assist you with properties or mortgages today?",
                "ar": "مفهوم تماماً! لن يتم جمع أو حفظ أي بيانات اتصال خاصة بك. كيف يمكنني مساعدتك أكثر في عقارات أو تمويل الإمارات اليوم؟",
                "hi": "समझ गया! आपका कोई संपर्क विवरण सुरक्षित नहीं किया जाएगा। मैं प्रॉपर्टीज या होम लोन में आपकी और क्या मदद कर सकता हूँ?",
                "ur": "سمجھ گیا۔ آپ کی کوئی رابطہ تفصیلات محفوظ نہیں کی جائیں گی۔ میں پراپرٹیز یا مارگیج میں آپ کی مزید کیا مدد کر سکتا ہوں؟",
                "fr": "C'est bien noté ! Aucune coordonnée ne sera enregistrée. Comment puis-je vous aider autrement concernant les biens ou les prêts ?",
                "es": "¡Entendido! No se guardará ningún dato de contacto. ¿Cómo más puedo ayudarte con propiedades o hipotecas hoy?",
                "de": "Verstanden! Ihre Kontaktdaten werden weder erfasst noch gespeichert. Wie kann ich Ihnen heute sonst bei Immobilien oder Hypotheken helfen?",
                "zh": "明白了！我们不会收集或保存您的任何联系方式。今天我还能在房产或贷款方面为您提供什么帮助？",
                "tl": "Naintindihan ko! Hindi namin kokolektahin o ise-save ang iyong impormasyon. Paano pa kita matutulungan ngayon?",
                "fa": "متوجه شدم! هیچ اطلاعات تماسی از شما ذخیره نخواهد شد. چگونه می‌توانم در زمینه املاک یا وام به شما کمک کنم؟",
                "bn": "বুঝতে পেরেছি! আপনার কোনো যোগাযোগের তথ্য সংরক্ষণ করা হবে না। আজ আপনাকে আর কীভাবে সাহায্য করতে পারি?",
                "pa": "ਸਮਝ ਗਿਆ! ਤੁਹਾਡਾ ਕੋਈ ਸੰਪਰਕ ਵੇਰਵਾ ਸੁਰੱਖਿਅਤ ਨਹੀਂ ਕੀਤਾ ਜਾਵੇਗਾ। ਮੈਂ ਜਾਇਦਾਦ ਜਾਂ ਮੌਰਗੇਜ ਵਿੱਚ ਤੁਹਾਡੀ ਹੋਰ ਕੀ ਮਦਦ ਕਰ ਸਕਦਾ ਹਾਂ?",
                "ta": "புரிந்துகொண்டேன்! உங்கள் தொடர்பு விவரங்கள் எதுவும் சேமிக்கப்படாது. இன்று நான் உங்களுக்கு வேறு எவ்வாறு உதவ முடியும்?",
                "ml": "മനസ്സിലായി! നിങ്ങളുടെ വിവരങ്ങളൊന്നും സൂക്ഷിക്കില്ല. ഞാൻ നിങ്ങളെ എങ്ങനെ സഹായിക്കണം?",
                "or": "ବୁଝିପାରିଲି! ଆପଣଙ୍କ କୌଣସି ଯୋଗାଯୋଗ ବିବରଣୀ ସଂରକ୍ଷଣ କରାଯିବ ନାହିଁ। ଆଜି ମୁଁ ଆପଣଙ୍କୁ ଅନ୍ୟ କିପରି ସାହାଯ୍ୟ କରିପାରିବି?"
            }
            return {
                "text": decline_responses.get(lang, decline_responses["en"]),
                "handoff_offered": False
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

        # 3. HUMAN HANDOFF INTENT (FR-5, FR-20)
        elif intent == "human_handoff":
            has_phone = bool(session.slots.customer_phone)

            if not has_phone:
                if not session.slots.customer_consent_given:
                    session.slots.advisor_consent_pending = True
                    session.handoff_requested = True
                    turn1_prompts = {
                        "en": "Would you like me to connect you with one of our licensed human advisors for personalized consultation? Exploring properties and calculations anonymously with me is always welcome as well.",
                        "ar": "هل تود أن أربطك بأحد مستشارينا العقاريين المعتمدين لتقديم استشارة مخصصة؟ يمكنك دائماً متابعة البحث والحسابات بدون أي التزام وبشكل مجهول.",
                        "hi": "क्या आप व्यक्तिगत सलाह के लिए हमारे प्रमाणित सलाहकार से जुड़ना चाहेंगे? आप मेरे साथ बिना किसी संपर्क विवरण के भी खोज जारी रख सकते हैं।",
                        "ur": "کیا آپ ذاتی مشورے کے لیے ہمارے مستند انسانی ایڈوائزر سے رابطہ کرنا چاہیں گے؟ آپ میرے ساتھ بغیر کسی رابطہ تفصیلات کے بھی اطمینان سے سرچ جاری رکھ سکتے ہیں۔"
                    }
                    return {
                        "text": turn1_prompts.get(lang, turn1_prompts["en"]),
                        "handoff_offered": True
                    }

                # Turn 2: User gave consent; request contact details
                turn2_prompts = {
                    "en": (
                        f"To arrange your direct callback, please share:\n"
                        f"1. **Full Name**\n"
                        f"2. **Phone Number** (with country code)\n"
                        f"3. **Preferred Contact Language**"
                    ),
                    "ar": (
                        f"لترتيب اتصالك المباشر، يرجى تزويدنا بـ:\n"
                        f"1. **الاسم الكامل**\n"
                        f"2. **رقم الهاتف** (مع رمز الدولة)\n"
                        f"3. **اللغة المفضلة للتواصل**"
                    ),
                    "hi": (
                        f"सीधे संपर्क के लिए कृपया निम्नलिखित विवरण साझा करें:\n"
                        f"1. **पूरा नाम**\n"
                        f"2. **फोन नंबर** (कंट्री कोड के साथ)\n"
                        f"3. **पसंदीदा संपर्क भाषा**"
                    ),
                    "ur": (
                        f"براہ راست رابطے کے لیے، برائے مہربانی درج کریں:\n"
                        f"1. **پورا نام**\n"
                        f"2. **فون نمبر** (کنٹری کوڈ کے ساتھ)\n"
                        f"3. **پسندیدہ رابطہ زبان**"
                    ),
                    "or": (
                        f"ଦୟାକରି ପ୍ରଦାନ କରନ୍ତୁ:\n"
                        f"1. **ସମ୍ପୂର୍ଣ୍ଣ ନାମ**\n"
                        f"2. **ଫୋନ୍ ନମ୍ବର** (କଣ୍ଟ୍ରି କୋଡ୍ ସହିତ)\n"
                        f"3. **ପସନ୍ଦର ଯୋଗାଯୋଗ ଭାଷା**"
                    )
                }
                return {
                    "text": turn2_prompts.get(lang, turn2_prompts["en"]),
                    "handoff_offered": False
                }

            from app.services.handoff_service import HandoffService
            c_name = session.slots.customer_name or "Valued Client"
            c_phone = session.slots.customer_phone or ""
            c_lang = session.slots.customer_preferred_language or lang
            handoff_res = HandoffService.initiate_handoff(
                session_id=session.session_id,
                applicant_name=c_name,
                applicant_phone=c_phone,
                preferred_language=c_lang,
                reason="explicit_request",
                user_id=session.user_id
            )
            advisor = handoff_res.get("assigned_advisor", {})
            ticket_id = handoff_res.get("ticket_id", "XO-HD")
            dept = advisor.get("department", "Advisory")
            lead_saved = handoff_res.get("lead_saved", True)

            if lead_saved:
                confirmations = {
                    "en": f"Thank you, {c_name}! Your request has been registered. An advisor from our {dept} team will reach out directly at {c_phone} in {c_lang}. Reference ticket: {ticket_id}.",
                    "ar": f"شكراً لك يا {c_name}! تم تسجيل طلبك بنجاح. سيتواصل معك مستشار من فريق {dept} مباشرة على الرقم {c_phone} باللغة {c_lang}. تذكرة المتابعة: {ticket_id}.",
                    "hi": f"धन्यवाद {c_name}! आपका अनुरोध दर्ज कर लिया गया है। हमारे {dept} विभाग के सलाहकार आपसे {c_phone} पर {c_lang} में सीधे संपर्क करेंगे। संदर्भ टिकट: {ticket_id}।",
                    "ur": f"شکریہ {c_name}! آپ کی درخواست کامیابی سے درج کر لی گئی ہے۔ ہماری {dept} ٹیم کے مشیر آپ سے {c_phone} پر {c_lang} میں براہ راست رابطہ کریں گے۔ ریفرنس ٹکٹ: {ticket_id}۔",
                    "or": f"ଧନ୍ୟବାଦ {c_name}! ଆପଣଙ୍କ ଅନୁରୋଧ ପଞ୍ଜୀକୃତ ହୋଇଛି। ଆମର {dept} ଟିମ୍ ପରାମର୍ଶଦାତା {c_phone} ରେ {c_lang} ରେ ଆପଣଙ୍କୁ ସିଧାସଳଖ ଯୋଗାଯୋଗ କରିବେ। ରେଫରେନ୍ସ ଟିକେଟ୍: {ticket_id}।"
                }
            else:
                confirmations = {
                    "en": f"We have recorded your inquiry ({ticket_id}). Please ensure your contact phone number is provided to receive an advisor callback.",
                    "ar": f"تم تسجيل استفسارك ({ticket_id}). يرجى التأكد من تزويدنا برقم هاتفك حتى يتمكن مستشارنا من التواصل معك.",
                    "hi": f"आपकी पूछताछ ({ticket_id}) दर्ज कर ली गई है। कृपया सलाहकार से संपर्क के लिए अपना फोन नंबर प्रदान करें।",
                    "ur": f"آپ کی انکوائری ({ticket_id}) درج کر لی گئی ہے۔ مشیر سے رابطے کے لیے اپنا فون نمبر فراہم کریں۔",
                    "or": f"ଆପଣଙ୍କ ଅନୁରୋଧ ରେକର୍ଡ ହୋଇଛି ({ticket_id})। ପରାମର୍ଶଦାତା ଯୋଗାଯୋଗ ପାଇଁ ଦୟାକରି ଫୋନ୍ ନମ୍ବର ପ୍ରଦାନ କରନ୍ତୁ।"
                }

            return {
                "text": confirmations.get(lang, confirmations["en"]),
                "handoff_data": handoff_res,
                "handoff_offered": True,
                "tool_calls": [{"function": "request_human_handoff", "args": {"applicant_name": c_name, "applicant_phone": c_phone, "preferred_language": c_lang}}]
            }

        # 4. ACCOUNT INTENT (FR-21, FR-22)
        elif intent == "account":
            from app.services.account_service import AccountService
            if not session.user_id:
                auth_prompts = {
                    "ar": "للوصول إلى عقاراتك المحفوظة وحالة طلباتك، يرجى تسجيل الدخول أولاً. جميع بياناتك الشخصية محمية بالكامل وخاصة بحسابك.",
                    "hi": "अपनी सेव की गई पसंदीदा प्रॉपर्टीज और लोन आवेदनों का स्टेटस देखने के लिए कृपया साइन इन करें। आपकी व्यक्तिगत जानकारी पूरी तरह सुरक्षित है।",
                    "ur": "اپنی محفوظ شدہ پراپرٹیز اور درخواستوں کا اسٹیٹس دیکھنے کے لیے براہ کرم پہلے سائن ان کریں۔ تمام ڈیٹا محفوظ اور نجی ہے۔",
                    "en": "To access your shortlisted properties and active application status, please sign in. All account data is strictly user-scoped and private."
                }
                return {
                    "text": auth_prompts.get(lang, auth_prompts["en"]),
                    "saved_properties": [],
                    "tool_calls": [{"function": "get_my_saved_properties"}]
                }

            saved_data = AccountService.get_my_saved_properties(session.user_id, session_id=session.session_id)
            app_data = AccountService.get_my_application_status(session.user_id, session_id=session.session_id)
            user_name = saved_data.get("user_name", "Valued Client")
            saved_count = saved_data.get("count", 0)
            apps_count = app_data.get("total_count", 0)

            responses = {
                "ar": f"مرحباً بك {user_name}! لديك {saved_count} عقارات محفوظة في قائمتك، و{apps_count} طلبات نشطة مسجلة في نظامنا (Vault & GRID). يمكنك الاطلاع على التفاصيل أدناه.",
                "hi": f"नमस्ते {user_name}! आपकी विशलिस्ट में {saved_count} प्रॉपर्टीज सेव हैं और {apps_count} सक्रिय आवेदन हमारे सिस्टम में दर्ज हैं। आप नीचे विवरण देख सकते हैं।",
                "ur": f"خوش آمدید {user_name}! آپ کی لسٹ میں {saved_count} محفوظ پراپرٹیز اور {apps_count} فعال درخواستیں ہمارے سسٹم میں موجود ہیں۔ تفصیلات نیچے ملاحظہ کریں۔",
                "en": f"Welcome back, {user_name}! You have {saved_count} saved residences in your portfolio and {apps_count} active applications on record (Vault Mortgage & GRID). Here are your account details:"
            }

            return {
                "text": responses.get(lang, responses["en"]),
                "saved_properties": saved_data.get("saved_properties", []),
                "application_status": app_data,
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
        user_id: Optional[str] = None,
        manual_language: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """
        Progressive streaming conversational turn generator (Server-Sent Events).
        Streams tokens with progressive cadence, preserving full formatting,
        and yields complete metadata upon conclusion.
        """
        try:
            response = await cls.process_user_turn(
                user_message=user_message,
                session_id=session_id,
                user_id=user_id,
                manual_language=manual_language
            )
            full_text = response.get("text", "")
            tokens = re.findall(r'\S+\s*|\s+', full_text) if full_text else [""]

            for tok in tokens:
                chunk = {
                    "token": tok,
                    "session_id": response["session_id"],
                    "language": response["language"],
                    "is_final": False
                }
                yield f"data: {json.dumps(chunk)}\n\n"
                await asyncio.sleep(0.015)

            final_chunk = {
                "token": "",
                "session_id": response["session_id"],
                "language": response["language"],
                "is_final": True,
                "text": full_text,
                "property_results": response.get("property_results"),
                "mortgage_result": response.get("mortgage_result"),
                "saved_properties": response.get("saved_properties"),
                "application_status": response.get("application_status"),
                "handoff_data": response.get("handoff_data"),
                "handoff_offered": response.get("handoff_offered", False),
                "tool_calls": response.get("tool_calls", [])
            }
            yield f"data: {json.dumps(final_chunk)}\n\n"

        except Exception as exc:
            logger.error(f"Error in stream_user_turn: {exc}", exc_info=True)
            err_msg = exc.detail if hasattr(exc, "detail") else str(exc)
            err_chunk = {
                "token": "",
                "session_id": session_id or "",
                "is_final": True,
                "error": err_msg
            }
            yield f"data: {json.dumps(err_chunk)}\n\n"

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
                "fr": "Aucune carte de propriété n'est actuellement affichée à l'écran pour comparaison. Veuillez d'abord rechercher un bien.",
                "es": "Actualmente no hay fichas de propiedades en pantalla para comparar. Por favor, busque propiedades primero.",
                "de": "Derzeit werden keine Immobilienkarten zum Vergleich angezeigt. Bitte suchen Sie zuerst nach Immobilien.",
                "zh": "当前屏幕上没有可供对比的房产卡片。请先搜索房产（例如：'搜索迪拜山庄的两居室'）。",
                "tl": "Kasalukuyang walang mga property card sa screen para ihambing. Mangyaring maghanap muna ng ari-arian.",
                "fa": "در حال حاضر هیچ کارت ملکی برای مقایسه روی صفحه نمایش وجود ندارد. لطفاً ابتدا ملکی را جستجو کنید.",
                "bn": "তুলনা করার জন্য স্ক্রিনে বর্তমানে কোনো প্রপার্টি কার্ড নেই। দয়া করে প্রথমে প্রপার্টি অনুসন্ধান করুন।",
                "ta": "ஒப்பிடுவதற்கு திரையில் சொத்து அட்டைகள் எதுவும் இல்லை. முதலில் சொத்தைத் தேடுங்கள்.",
                "pa": "ਮੁਕਾਬਲੇ ਲਈ ਸਕ੍ਰੀਨ 'ਤੇ ਕੋਈ ਪ੍ਰਾਪਰਟੀ ਕਾਰਡ ਨਹੀਂ ਹੈ। ਕਿਰਪਾ ਕਰਕੇ ਪਹਿਲਾਂ ਪ੍ਰਾਪਰਟੀ ਖੋਜੋ।",
                "ml": "താരതമ്യം ചെയ്യാൻ സ്ക്രീനിൽ നിലവിൽ പ്രോപ്പർട്ടി കാർഡുകളൊന്നുമില്ല. ആദ്യം ഒരു പ്രോപ്പർട്ടി തിരയുക.",
                "or": "ତୁଳନା କରିବାକୁ ସ୍କ୍ରିନରେ ବର୍ତ୍ତମାନ କୌଣସି ପ୍ରପର୍ଟି କାର୍ଡ ନାହିଁ। ଦୟାକରି ପ୍ରଥମେ ପ୍ରପର୍ଟି ଖୋଜନ୍ତୁ।",
                "en": "There are currently no active property cards on screen to compare. Please search for a community or property first (e.g. 'Show 2 BHK in Dubai Hills'), and I will gladly evaluate them for you."
            }
            return empty_msgs.get(lang, empty_msgs["en"])

        disclaimers = {
            "ar": "\n\n*(مقارنة سوقية استرشادية فقط؛ وليست استشارة مالية ملزمة)*",
            "hi": "\n\n*(केवल सांकेतिक बाज़ार तुलना; कोई बाध्यकारी वित्तीय सलाह नहीं)*",
            "ur": "\n\n*(صرف اشارے کے طور پر مارکیٹ کا موازنہ؛ کوئی قانونی یا مالی مشورہ نہیں)*",
            "fr": "\n\n*(Comparaison indicative du marché uniquement ; aucun conseil financier contraignant)*",
            "es": "\n\n*(Solo comparación indicativa de mercado; no es asesoramiento financiero vinculante)*",
            "de": "\n\n*(Nur indikativer Marktvergleich; keine verbindliche Finanzberatung)*",
            "zh": "\n\n*（仅供参考的市场对比；不构成具有约束力的财务建议）*",
            "tl": "\n\n*(Pahiwatig lamang na paghahambing sa merkado; hindi nagbubuklod na payo sa pananalapi)*",
            "fa": "\n\n*(صرفاً مقایسه بازار به صورت تقریبی؛ هیچ‌گونه مشاوره مالی الزام‌آور نیست)*",
            "bn": "\n\n*(केवल নির্দেশক বাজার তুলনা; কোন বাধ্যতামূলক আর্থিক পরামর্শ নয়)*",
            "ta": "\n\n*(சுட்டிக்காட்டும் சந்தை ஒப்பீடு மட்டுமே; பிணைப்பு நிதி ஆலோசனை அல்ல)*",
            "pa": "\n\n*(ਸਿਰਫ਼ ਸੰਕੇਤਕ ਮਾਰਕੀਟ ਤੁਲਨਾ; ਕੋਈ ਪਾਬੰਦ ਵਿੱਤੀ ਸਲਾਹ ਨਹੀਂ)*",
            "ml": "\n\n*(സൂചകമായ മാർക്കറ്റ് താരതമ്യം മാത്രം; ബാധ്യസ്ഥമായ സാമ്പത്തിക ഉപദേശമല്ല)*",
            "or": "\n\n*(କେବଳ ସୂଚକ ବଜାର ତୁଳନା; କୌଣସି ବାଧ୍ୟତାମୂଳକ ଆର୍ଥିକ ପରାମର୍ଶ ନୁହେଁ)*",
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
                if len(tiers) > 1:
                    tier_strs = [f"{t['beds']} غرف نوم (بدءاً من {t['starting_price_aed']:,.0f} درهم)" for t in tiers[:2]]
                    comm_desc = f"تتوفر خيارات متعددة تشمل {', '.join(tier_strs)}"
                else:
                    comm_desc = f"تتوفر شقق {s['beds']} غرف نوم فاخرة (مثل *{s['title']}* بسعر {s['price']:,.0f} درهم)"
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
                if len(tiers) > 1:
                    tier_strs = [f"{t['beds']} बेडरूम (शुरुआती कीमत {t['starting_price_aed']:,.0f} AED)" for t in tiers[:2]]
                    comm_desc = f"हमारे पास {', '.join(tier_strs)} के विकल्प उपलब्ध हैं"
                else:
                    comm_desc = f"हमारे पास लक्ज़री {s['beds']} बेडरूम निवास उपलब्ध हैं (जैसे *{s['title']}* मूल्य {s['price']:,.0f} AED)"
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
                if len(tiers) > 1:
                    tier_strs = [f"{t['beds']} بیڈ روم (ابتدائی قیمت {t['starting_price_aed']:,.0f} درہم)" for t in tiers[:2]]
                    comm_desc = f"ہمارے پاس {', '.join(tier_strs)} کی رہائشیں دستیاب ہیں"
                else:
                    comm_desc = f"لگژری {s['beds']} بیڈ روم رہائشیں دستیاب ہیں (جیسے *{s['title']}* قیمت {s['price']:,.0f} درہم)"
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
