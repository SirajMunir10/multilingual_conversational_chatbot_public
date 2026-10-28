"""Checks that a reply is written in its language's own script (PRD FR-1, FR-33).

Used after a confirmed language change: Punjabi must come back in Gurmukhi, not Urdu letters; Arabic must not carry
Urdu-only letters. Also tidies Arabic punctuation that sometimes slips into other scripts. Each language declares its
script and full stop in locales.json, so adding a language needs no code change."""
import re
import unicodedata

from app.core.config import load_config

_URDU_ONLY = re.compile(r"[ٹڈڑںےھۓ]")   # letters Arabic never uses
_PUNCTUATION = re.compile(r"[।॥،؛؟۔]")  # danda, Arabic comma/semicolon/question mark, Urdu full stop


def _script(language: str) -> str:
    """The Unicode script a language is written in: "LATIN", "DEVANAGARI", "CYRILLIC", ..."""
    return (load_config("locales")["locales"].get(language) or {}).get("script", "LATIN")


def _in_script(char: str, script: str) -> bool:
    return unicodedata.name(char, "").startswith(script)


def tidy_punctuation(text: str, language: str) -> str:
    """Replaces Arabic-script punctuation (، ؟ ۔) that sometimes slips into replies in other scripts."""
    if not text or _script(language) == "ARABIC" or not any(c in text for c in "،؟۔؛"):
        return text
    full_stop = (load_config("locales")["locales"].get(language) or {}).get("full_stop", ".")
    return text.replace("،", ",").replace("؟", "?").replace("؛", ";").replace("۔", full_stop)


def _letters(text: str):
    return [c for c in _PUNCTUATION.sub("", text or "") if c.isalpha()]


def foreign_script(text: str, language: str) -> bool:
    """True when a message contains words in an alphabet other than the language's own (e.g. Devanagari in an English
    conversation). Such turns are checked before the reply is shown. Accented Latin letters (é, ü, ş) belong to the
    same alphabet as English, so a French or Turkish message is not foreign and its reply streams normally."""
    letters = [c for c in _letters(text) if not c.isascii()]
    if len(letters) < 2:
        return False
    script = _script(language)
    return any(not _in_script(c, script) for c in letters)


def script_matches(text: str, language: str) -> bool:
    """True when a reply is written in the script of its language. Latin names such as XOTO or AED are allowed in
    non-Latin languages, but a reply that is mostly English is not. Languages that share a script (Hindi and Nepali)
    are told apart by the writing instruction, not here."""
    if not text:
        return True
    script = _script(language)
    letters = _letters(text)
    if script == "LATIN":
        return not letters or sum(1 for c in letters if c.isascii() or _in_script(c, script)) / len(letters) >= 0.85
    if language == "ar" and len(_URDU_ONLY.findall(text)) > 1:
        return False
    latin = sum(1 for c in letters if c.isascii())
    letters = [c for c in letters if not c.isascii()]
    if len(letters) < latin:
        return False
    # A stray word in a third alphabet (a Georgian word in a Nepali reply) fails, however short the rest of the reply.
    return sum(1 for c in letters if not _in_script(c, script) and not _in_script(c, "LATIN")) < 3
