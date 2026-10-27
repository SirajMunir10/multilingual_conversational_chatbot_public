"""Checks that a reply is written in its language's own script (PRD FR-1, FR-33).

Used after a confirmed language change: Punjabi must come back in Gurmukhi, not Urdu letters; Arabic must not carry
Urdu-only letters. Also tidies Arabic punctuation that sometimes slips into other scripts."""
import re

# The script each language must be written in (languages written in Latin letters are not checked).
_SCRIPT = {
    "pa": r"\u0A00-\u0A7F", "hi": r"\u0900-\u097F", "bn": r"\u0980-\u09FF", "ta": r"\u0B80-\u0BFF",
    "ml": r"\u0D00-\u0D7F", "or": r"\u0B00-\u0B7F", "zh": r"\u4E00-\u9FFF\u3400-\u4DBF",
    "ar": r"\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF", "ur": r"\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF",
    "fa": r"\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF",
}
_URDU_ONLY = re.compile(r"[ٹڈڑںےھۓ]")   # letters Arabic never uses
_PUNCTUATION = re.compile(r"[\u0964\u0965\u060C\u061B\u061F\u06D4]")  # danda, Arabic comma/semicolon/question mark, Urdu full stop


_ARABIC_SCRIPT = {"ar", "ur", "fa"}
_DANDA = {"hi", "pa", "bn", "or"}


def tidy_punctuation(text: str, language: str) -> str:
    """Replaces Arabic-script punctuation (، ؟ ۔) that sometimes slips into replies in other scripts."""
    if not text or language in _ARABIC_SCRIPT or not any(c in text for c in "،؟۔؛"):
        return text
    return (text.replace("،", ",").replace("؟", "?").replace("؛", ";")
            .replace("۔", "।" if language in _DANDA else "."))


def _letters(text: str):
    return [c for c in _PUNCTUATION.sub("", text or "") if c.isalpha()]


def foreign_script(text: str, language: str) -> bool:
    """True when a message contains words in an alphabet other than the language's own (e.g. Devanagari in an English
    conversation). Such turns are checked before the reply is shown."""
    letters = [c for c in _letters(text) if not c.isascii()]
    if len(letters) < 2:
        return False
    pattern = _SCRIPT.get(language)
    if not pattern:
        return True  # a Latin-script conversation with non-Latin words
    return any(not re.match(f"[{pattern}]", c) for c in letters)


def script_matches(text: str, language: str) -> bool:
    """True when a reply is written in the script of its language. Latin words such as XOTO or AED are ignored in
    non-Latin languages; a Latin-script language must be mostly Latin letters."""
    if not text:
        return True
    pattern = _SCRIPT.get(language)
    letters = _letters(text)
    if not pattern:
        return not letters or sum(1 for c in letters if c.isascii() or "\u00C0" <= c <= "\u024F") / len(letters) >= 0.85
    letters = [c for c in letters if not c.isascii()]
    if not letters:
        return True
    expected = sum(1 for c in letters if re.match(f"[{pattern}]", c))
    if language == "ar" and len(_URDU_ONLY.findall(text)) > 1:
        return False
    return expected / len(letters) >= 0.9
