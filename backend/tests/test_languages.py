"""Supported languages (PRD FR-1, FR-33): every language is fully configured, written in its own script, and says and
hears the XOTO and XO names correctly. Adding a language is a locales.json change; these tests hold every entry to it."""
import unicodedata
import unittest

from app.core.config import load_config
from app.llm.client import LLMService
from app.services.brand_terms import normalize_transcript, spoken_text
from app.services.language_script import foreign_script, script_matches, tidy_punctuation

LOCALES = load_config("locales")


class TestLanguageConfig(unittest.TestCase):

    def test_every_language_is_complete(self):
        required_messages = set(LOCALES["locales"][LOCALES["default"]]["messages"])
        for code, lang in LOCALES["locales"].items():
            with self.subTest(code):
                for field in ("name", "native", "dir", "script", "writing", "tts_language_code"):
                    self.assertTrue(lang.get(field), field)
                self.assertIn("stt_language", lang)  # None when the speech model does not accept a hint (Odia)
                self.assertIn(lang["dir"], ("ltr", "rtl"))
                self.assertEqual(set(lang["messages"]), required_messages)
                self.assertTrue(lang["brand"]["xoto"] and lang["brand"]["xo"])
                if lang["script"] != "LATIN":   # the declared script is a real Unicode script, and the native name uses it
                    self.assertTrue(any(unicodedata.name(c, "").startswith(lang["script"]) for c in lang["native"]))
                    self.assertTrue(script_matches(lang["messages"]["error_generic"], code))

    def test_new_languages(self):
        expected = {"ru": "CYRILLIC", "tr": "LATIN", "gu": "GUJARATI", "ne": "DEVANAGARI", "it": "LATIN", "te": "TELUGU"}
        for code, script in expected.items():
            self.assertEqual(LOCALES["locales"][code]["script"], script)
        self.assertEqual(LOCALES["locales"]["tl"]["name"], "Filipino")
        self.assertEqual(len(LOCALES["locales"]), 21)

    def test_instructions_list_every_language(self):
        prompt = LLMService.system_prompt("ru", True)
        for lang in LOCALES["locales"].values():
            self.assertIn(lang["name"], prompt)
        self.assertIn("Russian", prompt)
        self.assertIn("'вы'", prompt)  # the language's writing instruction reaches the model


class TestScripts(unittest.TestCase):

    def test_replies_in_their_own_script(self):
        self.assertTrue(script_matches("Ваш ежемесячный платёж — 8 337 AED.", "ru"))
        self.assertFalse(script_matches("Your monthly payment is 8,337 AED.", "ru"))
        self.assertTrue(script_matches("તમારો માસિક હપ્તો 8,337 AED છે.", "gu"))
        self.assertFalse(script_matches("आपकी मासिक किस्त 8,337 AED है।", "gu"))
        self.assertTrue(script_matches("మీ నెలవారీ వాయిదా 8,337 AED.", "te"))
        self.assertTrue(script_matches("तपाईंको मासिक किस्ता ८,३३७ AED हो।", "ne"))
        # A stray word in a third alphabet (seen live: Georgian in a Nepali reply) is caught and rewritten.
        self.assertFalse(script_matches("थप शुल्क लाग्न सक्छ। კონკრეტ मूल्य थाहा भएमा, खर्च निकालिदिन्छु।", "ne"))
        self.assertTrue(script_matches("Aylık ödemeniz 8.337 AED, ağustos ayından itibaren.", "tr"))
        self.assertTrue(script_matches("La rata mensile è di 8.337 AED.", "it"))

    def test_other_alphabets_are_noticed(self):
        self.assertTrue(foreign_script("Здравствуйте, можно на русском?", "tr"))
        self.assertTrue(foreign_script("मुझे हिंदी में बताइए", "ru"))
        self.assertFalse(foreign_script("Можно по-русски?", "ru"))
        # Accented Latin letters are not another alphabet: these replies keep streaming word by word.
        self.assertFalse(foreign_script("Merhaba, Türkçe konuşabilir misiniz? Çok teşekkürler.", "tr"))
        self.assertFalse(foreign_script("Perché la rata è più alta?", "it"))
        self.assertFalse(foreign_script("Où se trouve l'appartement ? Très bien.", "fr"))

    def test_nepali_full_stop(self):
        self.assertEqual(tidy_punctuation("धन्यवाद۔", "ne"), "धन्यवाद।")
        self.assertEqual(tidy_punctuation("Спасибо۔", "ru"), "Спасибо.")


class TestBrandNames(unittest.TestCase):

    def test_said_in_each_language(self):
        self.assertEqual(spoken_text("Добро пожаловать в XOTO, я XO.", "ru"), "Добро пожаловать в Экс-ото, я Экс-О.")
        self.assertIn("એક્સ-ઓટો", spoken_text("XOTO માં સ્વાગત છે", "gu"))
        self.assertIn("ఎక్స్-ఓటో", spoken_text("XOTO కి స్వాగతం", "te"))
        self.assertIn("एक्स-ओटो", spoken_text("XOTO मा स्वागत छ", "ne"))
        self.assertEqual(spoken_text("XOTO'ya hoş geldiniz", "tr"), "Ex-oto'ya hoş geldiniz")
        self.assertEqual(spoken_text("Benvenuto in XOTO", "it"), "Benvenuto in Ex-oto")
        self.assertEqual(spoken_text("Welcome to XOTO", "xx"), "Welcome to Ex-oto")  # unknown code: default language

    def test_heard_forms_in_new_scripts(self):
        self.assertEqual(normalize_transcript("Что такое Ксото?"), "Что такое XOTO?")
        self.assertEqual(normalize_transcript("Расскажите про Экс-ото"), "Расскажите про XOTO")
        self.assertEqual(normalize_transcript("ઝોટો વિશે જણાવો"), "XOTO વિશે જણાવો")
        self.assertEqual(normalize_transcript("జోటో గురించి చెప్పండి"), "XOTO గురించి చెప్పండి")
        self.assertEqual(normalize_transcript("एक्स ओटो के बारे में"), "XOTO के बारे में")  # unchanged for Hindi and Nepali
        self.assertEqual(normalize_transcript("Зотов приедет завтра"), "Зотов приедет завтра")  # a surname is left alone
        # Heard live on 28 Oct 2026 when Gujarati and Telugu speakers said XOTO:
        self.assertEqual(normalize_transcript("X auto mortgage માટે શું આપે છે?"), "XOTO mortgage માટે શું આપે છે?")
        self.assertEqual(normalize_transcript("X ఆటో మార్ట్gage కోసం"), "XOTO మార్ట్gage కోసం")
        self.assertEqual(normalize_transcript("I parked my auto outside"), "I parked my auto outside")


if __name__ == "__main__":
    unittest.main()
