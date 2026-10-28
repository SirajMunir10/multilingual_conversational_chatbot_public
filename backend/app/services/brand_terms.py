"""The two names visitors say most: XO (the assistant) and XOTO (the company).

Speech recognition hears "XOTO" in many ways depending on accent ("Zoto", "Exoto", "X oto"), and text-to-speech
reads the bare word "XOTO" as "Zoto". `normalize_transcript` repairs what was heard; `spoken_text` tells the voice
how to say it. "XO" alone stays "XO": it is never turned into XOTO. How each language says the names, and how its
speech recognition writes XOTO in its own script, is set per language in locales.json ("brand")."""
import re
from functools import lru_cache
from typing import Dict, Tuple

from app.core.config import load_config

# Heard forms of XOTO in Latin letters (any language). Whole words only, so "photo" or the name "Soto" are untouched.
_XOTO_HEARD_LATIN = r"x[\s.\-]?(?:oto|auto)|ex[\s.\-]?oto|eks[\s.\-]?oto|ekso?to|exotto|xotto|zoto|zotto|ksoto|xoto"
# Heard forms of XO when said on its own ("hey X O", "ex-oh"). Kept narrow: "so", "zoo" and "echo" are real words.
_XO_HEARD = re.compile(r"(?<![\w])(?:x\.\s?o\.?|x[\s\-]o|ex[\s\-]oh|ex-o|exo)(?![\w])", re.IGNORECASE)
_XOTO_WORD = re.compile(r"(?<![\w])XOTO(?![\w])", re.IGNORECASE)
_XO_WORD = re.compile(r"(?<![\w])XO(?![\w])")


def _brand(language: str) -> Dict[str, object]:
    locales = load_config("locales")
    return (locales["locales"].get(language) or {}).get("brand") or locales["locales"][locales["default"]]["brand"]


@lru_cache(maxsize=8)
def _xoto_heard(script_forms: Tuple[str, ...]) -> "re.Pattern[str]":
    # A space in a form may be heard as nothing or a hyphen. Whole words only, like the Latin forms, so a name such
    # as the Russian surname "Зотов" is never changed.
    alternatives = "|".join([_XOTO_HEARD_LATIN] + [re.escape(f).replace(r"\ ", r"[\s\-]?") for f in script_forms])
    return re.compile(rf"(?<![\w])(?:{alternatives})(?![\w])", re.IGNORECASE)


def normalize_transcript(text: str) -> str:
    """Writes the company and assistant names the way they are spelled, whatever the accent or language."""
    if not text:
        return text
    forms = tuple(sorted({form for lang in load_config("locales")["locales"].values()
                          for form in (lang.get("brand") or {}).get("heard_xoto", [])}, key=len, reverse=True))
    text = _xoto_heard(forms).sub("XOTO", text)
    return _XO_HEARD.sub("XO", text)


def spoken_text(text: str, language: str = "en") -> str:
    """Text for the voice engine: XOTO is said "X-oto" (never "Zoto") and XO "Ex-O", in the reply's language."""
    brand = _brand(language)
    text = _XOTO_WORD.sub(str(brand["xoto"]), text or "")
    return _XO_WORD.sub(str(brand["xo"]), text)
