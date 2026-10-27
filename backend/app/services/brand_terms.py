"""The two names visitors say most: XO (the assistant) and XOTO (the company).

Speech recognition hears "XOTO" in many ways depending on accent ("Zoto", "Exoto", "X oto"), and text-to-speech
reads the bare word "XOTO" as "Zoto". `normalize_transcript` repairs what was heard; `spoken_text` tells the voice
how to say it. "XO" alone stays "XO": it is never turned into XOTO."""
import re

# Heard forms of XOTO. Each is a whole word, so ordinary words (e.g. "photo", "Soto" as a name) are untouched.
_XOTO_HEARD = re.compile(
    r"(?<![\w])(?:"
    r"x[\s.\-]?oto|ex[\s.\-]?oto|eks[\s.\-]?oto|ekso?to|exotto|xotto|zoto|zotto|ksoto|xoto"
    r"|ज़ोटो|जोटो|एक्सोटो|एक्स\s?ओटो|ایکسوٹو|ایکس\s?اوٹو|زوٹو|زوتو|اكسوتو|إكسوتو|اکسوتو|إكس\s?أوتو|اكس\s?اوتو"
    r")(?![\w])",
    re.IGNORECASE,
)
# Heard forms of XO when said on its own ("hey X O", "ex-oh"). Kept narrow: "so", "zoo" and "echo" are real words.
_XO_HEARD = re.compile(r"(?<![\w])(?:x\.\s?o\.?|x[\s\-]o|ex[\s\-]oh|ex-o|exo)(?![\w])", re.IGNORECASE)

# How the voice should say XOTO, per reply language (the written text keeps "XOTO").
_XOTO_SPOKEN = {
    "ar": "إكس-أوتو", "ur": "ایکس-اوٹو", "fa": "ایکس-اوتو", "hi": "एक्स-ओटो", "pa": "ਐਕਸ-ਓਟੋ", "bn": "এক্স-ওটো",
    "ta": "எக்ஸ்-ஓட்டோ", "ml": "എക്സ്-ഓട്ടോ", "or": "ଏକ୍ସ-ଓଟୋ", "zh": "Ex-oto",
}
_XOTO_DEFAULT = "Ex-oto"
_XOTO_WORD = re.compile(r"(?<![\w])XOTO(?![\w])", re.IGNORECASE)
# XO on its own is said "Ex-O" for the same reason (a leading X is otherwise often read as Z).
_XO_SPOKEN = {
    "ar": "إكس-أو", "ur": "ایکس-او", "fa": "ایکس-او", "hi": "एक्स-ओ", "pa": "ਐਕਸ-ਓ", "bn": "এক্স-ও",
    "ta": "எக்ஸ்-ஓ", "ml": "എക്സ്-ഓ", "or": "ଏକ୍ସ-ଓ",
}
_XO_DEFAULT = "Ex-O"
_XO_WORD = re.compile(r"(?<![\w])XO(?![\w])")


def normalize_transcript(text: str) -> str:
    """Writes the company and assistant names the way they are spelled, whatever the accent."""
    if not text:
        return text
    text = _XOTO_HEARD.sub("XOTO", text)
    return _XO_HEARD.sub("XO", text)


def spoken_text(text: str, language: str = "en") -> str:
    """Text for the voice engine: XOTO is said "X-oto" (never "Zoto") and XO "Ex-O"."""
    text = _XOTO_WORD.sub(_XOTO_SPOKEN.get(language, _XOTO_DEFAULT), text or "")
    return _XO_WORD.sub(_XO_SPOKEN.get(language, _XO_DEFAULT), text)
