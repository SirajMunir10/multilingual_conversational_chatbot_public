import re
from typing import Dict, Tuple, Optional

class LanguageDetector:
    """
    Multilingual detection engine for XO expanded languages (15 locales):
    - Core 4: English (en), Arabic (ar), Hindi (hi), Urdu (ur)
    - Expanded 11: Bengali (bn), Malayalam (ml), Tagalog (tl), Persian (fa),
                   Tamil (ta), Punjabi (pa), Odia (or), French (fr),
                   Spanish (es), German (de), Chinese (zh)
    Complies with FR-1: Auto-detection on first turn, session persistence, and manual override.
    """

    # Unicode ranges for non-Latin writing systems
    ARABIC_URDU_PERSIAN_RANGE = re.compile(r'[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]')
    DEVANAGARI_RANGE = re.compile(r'[\u0900-\u097F]')      # Hindi
    BENGALI_RANGE = re.compile(r'[\u0980-\u09FF]')         # Bengali
    GURMUKHI_RANGE = re.compile(r'[\u0A00-\u0A7F]')        # Punjabi
    TAMIL_RANGE = re.compile(r'[\u0B80-\u0BFF]')           # Tamil
    ODIA_RANGE = re.compile(r'[\u0B00-\u0B7F]')            # Odia
    MALAYALAM_RANGE = re.compile(r'[\u0D00-\u0D7F]')       # Malayalam
    CHINESE_RANGE = re.compile(r'[\u4E00-\u9FFF]')         # Chinese (Mandarin / Simplified)

    # Specific Perso-Arabic Disambiguation Markers
    URDU_SPECIFIC_CHARS = re.compile(r'[\u0679\u0688\u0691\u06BA\u06C1\u06D2]')
    PERSIAN_SPECIFIC_CHARS = re.compile(r'[\u067E\u0686\u0698\u06AF]')  # پ, چ, ژ, گ

    URDU_COMMON_WORDS = {
        "ہے", "ہیں", "کا", "کی", "کے", "کو", "میں", "سے", "اور", "آپ",
        "کیا", "کیوں", "کب", "کہاں", "کیسے", "کریں", "شکریہ", "براہ", "کرم",
        "پراپرٹی", "مارگیج", "گھر", "اپارٹمنٹ", "چاہیے", "کتنا", "ہوگا"
    }

    ARABIC_COMMON_WORDS = {
        "في", "من", "إلى", "على", "ما", "هذا", "هذه", "هل", "أين", "كم",
        "عقار", "شقة", "فيلا", "تمويل", "قرض", "رهن", "عقاري", "دبي",
        "شكرا", "مرحبا", "أريد", "شراء", "إيجار", "دفعة", "شهرية", "السلام"
    }

    PERSIAN_COMMON_WORDS = {
        "در", "از", "به", "با", "این", "که", "برای", "سلام", "میخواهم",
        "آپارتمان", "قیمت", "درهم", "خرید", "اجاره", "وام", "مسکن", "خانه",
        "ملک", "دبی", "تشکر", "ممنون", "لطفا", "چقدر", "است", "هست"
    }

    HINDI_COMMON_WORDS = {
        "है", "हैं", "का", "की", "के", "को", "में", "سے", "और", "आप",
        "क्या", "कहाँ", "कैसे", "चाहिए", "प्रॉपर्टी", "फ्लैट", "लोन",
        "किस्त", "दुबई", "धन्यवाद", "नमस्ते", "बताइए"
    }

    # Latin Script Language Lexicons
    FRENCH_WORDS = {
        "bonjour", "salut", "cherche", "appartement", "immobilier", "combien",
        "acheter", "louer", "prix", "crédit", "merci", "propriété", "pour",
        "dans", "avec", "est", "une", "des", "les"
    }

    SPANISH_WORDS = {
        "hola", "busco", "apartamento", "piso", "propiedad", "cuánto", "cuanto",
        "comprar", "alquilar", "precio", "hipoteca", "gracias", "para", "en",
        "con", "una", "los", "las", "por"
    }

    GERMAN_WORDS = {
        "hallo", "guten", "suche", "wohnung", "immobilien", "kaufen", "mieten",
        "preis", "kredit", "danke", "bitte", "wieviel", "mit", "eine", "der",
        "die", "das", "für"
    }

    TAGALOG_WORDS = {
        "kamusta", "kumusta", "salamat", "po", "bahay", "condo", "magkano",
        "gusto", "bili", "upa", "pautang", "lugar", "ang", "mga", "ng", "sa",
        "para", "ko", "mo"
    }

    @classmethod
    def detect_language(cls, text: str) -> Tuple[str, float]:
        """
        Detects language from input text across all 15 supported locales.
        Returns (language_code, confidence_score).
        Default fallback is 'en' (English).
        """
        if not text or not text.strip():
            return "en", 1.0

        cleaned = text.strip()
        words = set(re.findall(r'\w+', cleaned.lower()))

        # 1. Non-Latin Unique Script Detections
        if len(cls.CHINESE_RANGE.findall(cleaned)) > 0:
            return "zh", 0.98

        if len(cls.BENGALI_RANGE.findall(cleaned)) > 0:
            return "bn", 0.98

        if len(cls.TAMIL_RANGE.findall(cleaned)) > 0:
            return "ta", 0.98

        if len(cls.MALAYALAM_RANGE.findall(cleaned)) > 0:
            return "ml", 0.98

        if len(cls.GURMUKHI_RANGE.findall(cleaned)) > 0:
            return "pa", 0.98

        if len(cls.ODIA_RANGE.findall(cleaned)) > 0:
            return "or", 0.98

        if len(cls.DEVANAGARI_RANGE.findall(cleaned)) > 0:
            overlap = len(words.intersection(cls.HINDI_COMMON_WORDS))
            confidence = min(0.99, 0.92 + (overlap * 0.03))
            return "hi", confidence

        # 2. Perso-Arabic Script Disambiguation (ar vs ur vs fa)
        if len(cls.ARABIC_URDU_PERSIAN_RANGE.findall(cleaned)) > 0:
            has_urdu_chars = bool(cls.URDU_SPECIFIC_CHARS.search(cleaned))
            has_persian_chars = bool(cls.PERSIAN_SPECIFIC_CHARS.search(cleaned))

            urdu_matches = len(words.intersection(cls.URDU_COMMON_WORDS))
            arabic_matches = len(words.intersection(cls.ARABIC_COMMON_WORDS))
            persian_matches = len(words.intersection(cls.PERSIAN_COMMON_WORDS))

            # Urdu unique characters (ٹ, ڈ, ڑ, ں, ے) NEVER exist in Persian or Arabic
            if has_urdu_chars or (urdu_matches > arabic_matches and urdu_matches > persian_matches):
                return "ur", min(0.99, 0.85 + (urdu_matches * 0.05))

            # Persian lexical matches
            if persian_matches > arabic_matches:
                return "fa", min(0.99, 0.85 + (persian_matches * 0.05))

            # If Persian/Urdu shared chars (پ, چ, ژ, گ) exist without Urdu-specific chars
            if has_persian_chars:
                if urdu_matches >= persian_matches and urdu_matches > 0:
                    return "ur", 0.90
                return "fa", 0.90

            # Default Arabic script
            return "ar", min(0.99, 0.85 + (arabic_matches * 0.05))

        # 3. Latin Script Disambiguation (fr, es, de, tl, en)
        fr_overlap = len(words.intersection(cls.FRENCH_WORDS))
        es_overlap = len(words.intersection(cls.SPANISH_WORDS))
        de_overlap = len(words.intersection(cls.GERMAN_WORDS))
        tl_overlap = len(words.intersection(cls.TAGALOG_WORDS))

        scores = [
            ("fr", fr_overlap),
            ("es", es_overlap),
            ("de", de_overlap),
            ("tl", tl_overlap)
        ]
        best_lang, best_score = max(scores, key=lambda x: x[1])
        if best_score >= 1:
            return best_lang, min(0.96, 0.85 + (best_score * 0.05))

        # Default fallback for Latin Script
        return "en", 0.95

    EXPLICIT_SWITCH_TARGETS = {
        "or": {
            "aliases": ["odia", "oriya", "odiya", "odin", "odio", "ଓଡ଼ିଆ"],
            "native": ["ଓଡ଼ିଆରେ କଥା ହୁଅ", "ଓଡ଼ିଆରେ", "ଓଡ଼ିଆ"]
        },
        "ar": {
            "aliases": ["arabic", "arabi", "العربية", "عربي"],
            "native": ["بالعربي", "عربي", "تكلم عربي", "تحدث بالعربية", "باللغة العربية"]
        },
        "hi": {
            "aliases": ["hindi", "हिंदी", "हिन्दी"],
            "native": ["हिंदी में", "हिंदी बोलो", "हिन्दी में"]
        },
        "ur": {
            "aliases": ["urdu", "اردو"],
            "native": ["اردو میں", "اردو بولیں"]
        },
        "fr": {
            "aliases": ["french", "français", "francais"],
            "native": ["parler français", "en français", "français", "francais"]
        },
        "es": {
            "aliases": ["spanish", "español", "espanol"],
            "native": ["hablar español", "en español", "español", "espanol"]
        },
        "de": {
            "aliases": ["german", "deutsch"],
            "native": ["auf deutsch", "deutsch sprechen", "deutsch"]
        },
        "zh": {
            "aliases": ["chinese", "mandarin", "中文", "普通话"],
            "native": ["讲中文", "说中文", "用中文", "中文", "普通话"]
        },
        "tl": {
            "aliases": ["tagalog", "filipino", "taglog"],
            "native": ["mag-tagalog", "sa tagalog", "tagalog", "filipino"]
        },
        "ta": {
            "aliases": ["tamil", "தமிழ்"],
            "native": ["தமிழில் பேசு", "தமிழில்", "தமிழ்"]
        },
        "fa": {
            "aliases": ["persian", "farsi", "فارسی"],
            "native": ["فارسی صحبت کن", "به زبان فارسی", "فارسی"]
        },
        "bn": {
            "aliases": ["bengali", "bangla", "বাংলা"],
            "native": ["বাংলায় কথা বলুন", "বাংলায়", "বাংলা"]
        },
        "pa": {
            "aliases": ["punjabi", "panjabi", "ਪੰਜਾਬੀ"],
            "native": ["ਪੰਜਾਬੀ ਵਿੱਚ ਬੋਲੋ", "ਪੰਜਾਬੀ ਵਿੱਚ", "ਪੰਜਾਬੀ"]
        },
        "ml": {
            "aliases": ["malayalam", "മലയാളം"],
            "native": ["മലയാളത്തിൽ സംസാരിക്കൂ", "മലയാളത്തിൽ", "മലയാളം"]
        },
        "en": {
            "aliases": ["english", "inglés", "anglais", "englisch"],
            "native": ["انجليزي", "بالانجليزي", "अंग्रेजी में"]
        }
    }

    @classmethod
    def check_explicit_language_switch(cls, text: str) -> Optional[str]:
        """
        Detects if the user is explicitly requesting to switch conversation language
        across all 15 supported locales, supporting flexible phrasings and common variants.
        """
        if not text:
            return None
        lowered = text.lower().strip()

        for lang_code, data in cls.EXPLICIT_SWITCH_TARGETS.items():
            # 1. Native script triggers
            if any(p in lowered for p in data["native"]):
                return lang_code

            # 2. Flexible English / cross-language conversational request patterns
            alias_pattern = '|'.join(re.escape(a) for a in data["aliases"])
            pattern = (
                rf'(?:switch\s+to|speak\s+in|speak|talk\s+in|talk|chat\s+in|write\s+in|reply\s+in|respond\s+in|'
                rf'responses?\s+in|convo\s+in|conversation\s+in|start(?:\s+the\s+convo)?\s+in|use|only\s+in|in)\s+'
                rf'(?:the\s+)?(?:{alias_pattern})\b|'
                rf'\b(?:{alias_pattern})\s+(?:please|only|responses?|language)\b'
            )
            if re.search(pattern, lowered):
                return lang_code

        return None

    @classmethod
    def get_supported_locales(cls) -> Dict[str, Dict[str, str]]:
        return {
            "en": {"name": "English", "native": "English", "dir": "ltr"},
            "ar": {"name": "Arabic", "native": "العربية", "dir": "rtl"},
            "hi": {"name": "Hindi", "native": "हिन्दी", "dir": "ltr"},
            "ur": {"name": "Urdu", "native": "اردو", "dir": "rtl"},
            "fr": {"name": "French", "native": "Français", "dir": "ltr"},
            "es": {"name": "Spanish", "native": "Español", "dir": "ltr"},
            "de": {"name": "German", "native": "Deutsch", "dir": "ltr"},
            "zh": {"name": "Chinese", "native": "中文 (简体)", "dir": "ltr"},
            "tl": {"name": "Tagalog", "native": "Filipino", "dir": "ltr"},
            "ta": {"name": "Tamil", "native": "தமிழ்", "dir": "ltr"},
            "fa": {"name": "Persian", "native": "فارسی", "dir": "rtl"},
            "bn": {"name": "Bengali", "native": "বাংলা", "dir": "ltr"},
            "pa": {"name": "Punjabi", "native": "ਪੰਜਾਬੀ", "dir": "ltr"},
            "ml": {"name": "Malayalam", "native": "മലയാളം", "dir": "ltr"},
            "or": {"name": "Odia", "native": "ଓଡ଼ିଆ", "dir": "ltr"}
        }

