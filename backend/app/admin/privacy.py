"""Personal data in transcripts (PRD FR-22). Visitors sometimes type their phone number or email into the chat;
admins whose role does not include personal data see them masked."""
import re
from typing import Optional

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Digit runs (spaces, dots, dashes and brackets allowed between digits). A run is treated as a phone number when it
# starts with + or 0 and has 7+ digits (+971 50…, 050…), or has 9+ digits. Prices typed in chat ("2500000") stay
# readable for reviewers.
_DIGITS = re.compile(r"(?<!\w)\+?\d(?:[\s().-]?\d){6,}(?!\w)")


def _phone(match: "re.Match[str]") -> str:
    raw = match.group(0)
    digits = re.sub(r"\D", "", raw)
    if raw.startswith(("+", "0")) or len(digits) >= 9:
        return f"•••{digits[-3:]}"
    return raw


def mask_personal_data(text: Optional[str]) -> Optional[str]:
    if not text:
        return text
    return _DIGITS.sub(_phone, _EMAIL.sub("•••@•••", text))
