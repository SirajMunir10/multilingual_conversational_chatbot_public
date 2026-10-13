import re
from typing import Dict, Tuple, Optional

class LanguageDetector:
    """
    Multilingual detection engine for XO launch languages (16 total):
    - English (en), Arabic (ar), Hindi (hi), Urdu (ur)
    - Russian (ru), French (fr), German (de), Spanish (es), Turkish (tr)
    - Tamil (ta), Telugu (te), Bengali (bn), Punjabi (pa), Gujarati (gu), Marwadi (mwr), Odia (or)
    Complies with FR-1: Auto-detection on first turn, session persistence, and manual override.
    """

    # Unicode script ranges
    ARABIC_URDU_RANGE = re.compile(r'[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]')
    DEVANAGARI_RANGE = re.compile(r'[\u0900-\u097F]')
    CYRILLIC_RANGE = re.compile(r'[\u0400-\u04FF]')
    TAMIL_RANGE = re.compile(r'[\u0B80-\u0BFF]')
    TELUGU_RANGE = re.compile(r'[\u0C00-\u0C7F]')
    BENGALI_RANGE = re.compile(r'[\u0980-\u09FF]')
    GURMUKHI_RANGE = re.compile(r'[\u0A00-\u0A7F]')
    GUJARATI_RANGE = re.compile(r'[\u0A80-\u0AFF]')
    ODIA_RANGE = re.compile(r'[\u0B00-\u0B7F]')

    # Distinct Urdu character markers
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

    MARWADI_COMMON_WORDS = {
        "म्हाने", "म्हारो", "म्हारी", "थारो", "थारी", "घणो", "घणी", "घणा",
        "चोखो", "चोखी", "कांई", "होसी", "कोनी", "हुवे", "कस्या", "कद", "जद",
        "अठे", "बठे", "किणी", "घणे", "चाहीजे"
    }

    # High-frequency Latin vocabulary markers for European & Eurasian languages
    FRENCH_COMMON_WORDS = {
        "le", "la", "les", "des", "du", "un", "une", "bonjour", "appartement",
        "maison", "immobilier", "dubai", "merci", "avec", "pour", "prix", "acheter", "louer"
    }
    GERMAN_COMMON_WORDS = {
        "der", "die", "das", "und", "in", "den", "dem", "wohnung", "haus",
        "immobilien", "dubai", "hallo", "kauf", "kaufen", "miete", "mit", "preise"
    }
    SPANISH_COMMON_WORDS = {
        "el", "la", "los", "las", "un", "una", "de", "en", "hola", "propiedad",
        "apartamento", "piso", "gracias", "por", "para", "con", "inmobiliaria", "comprar"
    }
    TURKISH_COMMON_WORDS = {
        "ve", "bir", "icin", "için", "merhaba", "daire", "ev", "emlak", "dubai",
        "satilik", "satılık", "kiralik", "kiralık", "tesekkurler", "teşekkürler", "fiyat"
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

        # 1. Distinct Regional Indic Scripts
        if len(cls.TAMIL_RANGE.findall(cleaned)) > 0:
            return "ta", 0.98

        if len(cls.TELUGU_RANGE.findall(cleaned)) > 0:
            return "te", 0.98

        if len(cls.BENGALI_RANGE.findall(cleaned)) > 0:
            return "bn", 0.98

        if len(cls.GURMUKHI_RANGE.findall(cleaned)) > 0:
            return "pa", 0.98

        if len(cls.GUJARATI_RANGE.findall(cleaned)) > 0:
            return "gu", 0.98

        if len(cls.ODIA_RANGE.findall(cleaned)) > 0:
            return "or", 0.98

        # 2. Cyrillic Script (Russian)
        if len(cls.CYRILLIC_RANGE.findall(cleaned)) > 0:
            return "ru", 0.98

        # 3. Devanagari Script (Disambiguate Hindi vs Marwadi)
        if len(cls.DEVANAGARI_RANGE.findall(cleaned)) > 0:
            marwadi_matches = sum(1 for w in cls.MARWADI_COMMON_WORDS if w in cleaned)
            if marwadi_matches > 0:
                return "mwr", min(0.99, 0.90 + (marwadi_matches * 0.04))
            hindi_matches = sum(1 for w in cls.HINDI_COMMON_WORDS if w in cleaned)
            confidence = min(0.99, 0.92 + (hindi_matches * 0.03))
            return "hi", confidence

        # 4. Arabic/Urdu Script
        arabic_urdu_chars = len(cls.ARABIC_URDU_RANGE.findall(cleaned))
        if arabic_urdu_chars > 0:
            has_urdu_chars = bool(cls.URDU_SPECIFIC_CHARS.search(cleaned))
            urdu_word_matches = sum(1 for w in cls.URDU_COMMON_WORDS if w in cleaned)
            arabic_word_matches = sum(1 for w in cls.ARABIC_COMMON_WORDS if w in cleaned)

            if has_urdu_chars or (urdu_word_matches > arabic_word_matches):
                confidence = min(0.99, 0.80 + (urdu_word_matches * 0.06))
                return "ur", confidence
            else:
                confidence = min(0.99, 0.85 + (arabic_word_matches * 0.05))
                return "ar", confidence

        # 5. Latin Script Disambiguation (FR, DE, ES, TR vs EN)
        # Check distinctive diacritics first
        if any(c in cleaned for c in "éèêëàâùûçÉÈÊÀÇ"):
            return "fr", 0.95
        if any(c in cleaned for c in "äöüßÄÖÜ"):
            return "de", 0.95
        if any(c in cleaned for c in "ñáíóú¿¡ÑÁÍÓÚ"):
            return "es", 0.95
        if any(c in cleaned for c in "ğışçöüĞİŞÇÖÜ"):
            return "tr", 0.95

        # Check distinctive high-frequency vocabulary (excluding international overlaps like 'in', 'dubai')
        lowered_words = set(re.findall(r'[a-zA-Z]+', cleaned.lower()))
        fr_words = {"bonjour", "cherche", "appartement", "maison", "merci", "acheter", "louer", "combien", "dans"}
        de_words = {"hallo", "suche", "wohnung", "kaufen", "mieten", "preise", "gibt", "hier", "bitte", "möchte"}
        es_words = {"hola", "busco", "apartamento", "piso", "propiedad", "gracias", "comprar", "alquilar", "cuánto", "cuanto"}
        tr_words = {"merhaba", "daire", "satılık", "kiralık", "arıyorum", "fiyat", "istiyorum", "lütfen", "teşekkürler"}

        if len(lowered_words.intersection(fr_words)) >= 1:
            return "fr", 0.94
        if len(lowered_words.intersection(de_words)) >= 1:
            return "de", 0.94
        if len(lowered_words.intersection(es_words)) >= 1:
            return "es", 0.94
        if len(lowered_words.intersection(tr_words)) >= 1:
            return "tr", 0.94

        # Default fallback for Latin script
        return "en", 0.95

    @classmethod
    def check_explicit_language_switch(cls, text: str) -> Optional[str]:
        """
        Detects if the user is explicitly requesting to switch conversation language across all 16 locales.
        """
        if not text:
            return None
        lowered = text.lower().strip()

        # Arabic switch patterns
        if any(p in lowered for p in [
            "switch to arabic", "speak in arabic", "speak arabic", "in arabic", "talk in arabic",
            "بالعربي", "عربي", "تكلم عربي", "تحدث بالعربية", "باللغة العربية"
        ]):
            return "ar"

        # English switch patterns
        if any(p in lowered for p in [
            "switch to english", "speak in english", "speak english", "in english", "talk in english",
            "change language to english", "انجليزي", "بالانجليزي", "अंग्रेजी में"
        ]):
            return "en"

        # Urdu switch patterns
        if any(p in lowered for p in [
            "switch to urdu", "speak in urdu", "speak urdu", "in urdu", "talk in urdu",
            "اردو میں", "اردو", "اردو بولیں"
        ]):
            return "ur"

        # Hindi switch patterns
        if any(p in lowered for p in [
            "switch to hindi", "speak in hindi", "speak hindi", "in hindi", "talk in hindi",
            "हिंदी में", "हिंदी", "हिंदी बोलो"
        ]):
            return "hi"

        # Russian switch patterns
        if any(p in lowered for p in [
            "switch to russian", "speak in russian", "speak russian", "in russian",
            "по-русски", "на русском", "русский", "говори по-русски"
        ]):
            return "ru"

        # French switch patterns
        if any(p in lowered for p in [
            "switch to french", "speak in french", "speak french", "in french",
            "en français", "parler français", "français"
        ]):
            return "fr"

        # German switch patterns
        if any(p in lowered for p in [
            "switch to german", "speak in german", "speak german", "in german",
            "auf deutsch", "deutsch sprechen", "deutsch"
        ]):
            return "de"

        # Spanish switch patterns
        if any(p in lowered for p in [
            "switch to spanish", "speak in spanish", "speak spanish", "in spanish",
            "en español", "hablar español", "español"
        ]):
            return "es"

        # Turkish switch patterns
        if any(p in lowered for p in [
            "switch to turkish", "speak in turkish", "speak turkish", "in turkish",
            "türkçe", "türkçe konuş", "türkçe konuşun"
        ]):
            return "tr"

        # Tamil switch patterns
        if any(p in lowered for p in [
            "switch to tamil", "speak in tamil", "speak tamil", "in tamil",
            "தமிழ்", "தமிழில் பேசு", "தமிழில்"
        ]):
            return "ta"

        # Telugu switch patterns
        if any(p in lowered for p in [
            "switch to telugu", "speak in telugu", "speak telugu", "in telugu",
            "తెలుగు", "తెలుగులో మాట్లాడు", "తెలుగులో"
        ]):
            return "te"

        # Bengali switch patterns
        if any(p in lowered for p in [
            "switch to bengali", "speak in bengali", "speak bengali", "in bengali",
            "বাংলা", "বাংলায় কথা বলুন", "বাংলায়"
        ]):
            return "bn"

        # Punjabi switch patterns
        if any(p in lowered for p in [
            "switch to punjabi", "speak in punjabi", "speak punjabi", "in punjabi",
            "ਪੰਜਾਬੀ", "ਪੰਜਾਬੀ ਵਿੱਚ", "ਪੰਜਾਬੀ ਬੋਲੋ"
        ]):
            return "pa"

        # Gujarati switch patterns
        if any(p in lowered for p in [
            "switch to gujarati", "speak in gujarati", "speak gujarati", "in gujarati",
            "ગુજરાતી", "ગુજરાતીમાં વાત કરો", "ગુજરાતીમાં"
        ]):
            return "gu"

        # Marwadi switch patterns
        if any(p in lowered for p in [
            "switch to marwadi", "speak in marwadi", "speak marwadi", "in marwadi",
            "मारवाड़ी", "मारवाड़ी में", "मारवाड़ी बोलो", "राजस्थानी"
        ]):
            return "mwr"

        # Odia switch patterns
        if any(p in lowered for p in [
            "switch to odia", "speak in odia", "speak odia", "in odia",
            "ଓଡ଼ିଆ", "ଓଡ଼ିଆରେ କଥା ହୁଅ", "ଓଡ଼ିଆରେ"
        ]):
            return "or"

        return None

    @classmethod
    def get_supported_locales(cls) -> Dict[str, Dict[str, str]]:
        return {
            "en": {"name": "English", "native": "English", "dir": "ltr"},
            "ar": {"name": "Arabic", "native": "العربية", "dir": "rtl"},
            "hi": {"name": "Hindi", "native": "हिन्दी", "dir": "ltr"},
            "ur": {"name": "Urdu", "native": "اردو", "dir": "rtl"},
            "ru": {"name": "Russian", "native": "Русский", "dir": "ltr"},
            "fr": {"name": "French", "native": "Français", "dir": "ltr"},
            "de": {"name": "German", "native": "Deutsch", "dir": "ltr"},
            "es": {"name": "Spanish", "native": "Español", "dir": "ltr"},
            "tr": {"name": "Turkish", "native": "Türkçe", "dir": "ltr"},
            "ta": {"name": "Tamil", "native": "தமிழ்", "dir": "ltr"},
            "te": {"name": "Telugu", "native": "తెలుగు", "dir": "ltr"},
            "bn": {"name": "Bengali", "native": "বাংলা", "dir": "ltr"},
            "pa": {"name": "Punjabi", "native": "ਪੰਜਾਬੀ", "dir": "ltr"},
            "gu": {"name": "Gujarati", "native": "ગુજરાતી", "dir": "ltr"},
            "mwr": {"name": "Marwadi", "native": "मारवाड़ी", "dir": "ltr"},
            "or": {"name": "Odia", "native": "ଓଡ଼ିଆ", "dir": "ltr"}
        }
