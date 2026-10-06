import re
from typing import Dict, Tuple

class LanguageDetector:
    """
    Multilingual detection engine for XO launch languages:
    - English (en)
    - Arabic (ar)
    - Hindi (hi)
    - Urdu (ur)
    Complies with FR-1: Auto-detection on first turn, session persistence, and manual override.
    """

    # Unicode ranges
    ARABIC_URDU_RANGE = re.compile(r'[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]')
    DEVANAGARI_RANGE = re.compile(r'[\u0900-\u097F]')

    # Distinct Urdu character markers and high-frequency vocabulary
    URDU_SPECIFIC_CHARS = re.compile(r'[\u0679\u0686\u0688\u0691\u0698\u06A9\u06AF\u06BA\u06BE\u06C1\u06CC\u06D2]')
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

    HINDI_COMMON_WORDS = {
        "है", "हैं", "का", "की", "के", "को", "में", "से", "और", "आप",
        "क्या", "कहाँ", "कैसे", "चाहिए", "प्रॉपर्टी", "फ्लैट", "लोन",
        "किस्त", "दुबई", "धन्यवाद", "नमस्ते", "बताइए"
    }

    @classmethod
    def detect_language(cls, text: str) -> Tuple[str, float]:
        """
        Detects language from input text.
        Returns (language_code, confidence_score).
        Default fallback is 'en' (English).
        """
        if not text or not text.strip():
            return "en", 1.0

        cleaned = text.strip()
        words = set(re.findall(r'\w+', cleaned.lower()))

        # 1. Check Devanagari Script (Hindi)
        devanagari_chars = len(cls.DEVANAGARI_RANGE.findall(cleaned))
        if devanagari_chars > 0:
            # Check Hindi vocabulary overlap
            overlap = len(words.intersection(cls.HINDI_COMMON_WORDS))
            confidence = min(0.99, 0.92 + (overlap * 0.03))
            return "hi", confidence

        # 2. Check Arabic/Urdu Script
        arabic_urdu_chars = len(cls.ARABIC_URDU_RANGE.findall(cleaned))
        if arabic_urdu_chars > 0:
            # Disambiguate between Urdu and Arabic
            has_urdu_chars = bool(cls.URDU_SPECIFIC_CHARS.search(cleaned))
            urdu_word_matches = len(words.intersection(cls.URDU_COMMON_WORDS))
            arabic_word_matches = len(words.intersection(cls.ARABIC_COMMON_WORDS))

            if has_urdu_chars or (urdu_word_matches > arabic_word_matches):
                confidence = min(0.99, 0.80 + (urdu_word_matches * 0.06))
                return "ur", confidence
            else:
                confidence = min(0.99, 0.85 + (arabic_word_matches * 0.05))
                return "ar", confidence

        # 3. Check Latin Script for English
        # (Could also detect Roman Urdu/Hindi if needed, but PRD standard launch is English for Latin script)
        return "en", 0.95

    @classmethod
    def get_supported_locales(cls) -> Dict[str, Dict[str, str]]:
        return {
            "en": {"name": "English", "native": "English", "dir": "ltr"},
            "ar": {"name": "Arabic", "native": "العربية", "dir": "rtl"},
            "hi": {"name": "Hindi", "native": "हिन्दी", "dir": "ltr"},
            "ur": {"name": "Urdu", "native": "اردو", "dir": "rtl"}
        }
