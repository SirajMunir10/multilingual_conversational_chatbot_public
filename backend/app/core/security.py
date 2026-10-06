import re
from enum import Enum
from typing import Optional
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

class Role(str, Enum):
    CONTENT_EDITOR = "content_editor"
    BOT_TRAINER = "bot_trainer"
    ADMIN = "admin"
    READ_ONLY_ANALYST = "read_only_analyst"

# Strict payment blocking - XO has zero payment scope (FR-23b / Rule 8)
PAYMENT_KEYWORDS = [
    "credit card", "debit card", "cvv", "cvc", "expiry date",
    "card number", "bank account number", "iban", "swift", "wire transfer",
    "initiate payment", "process payment", "charge card", "make payment",
    "stripe_token", "payment_intent"
]

def assert_no_payment_intent(query_text: str) -> None:
    """
    Hard security check ensuring XO never collects, processes, or facilitates payments.
    """
    normalized = query_text.lower()
    for kw in PAYMENT_KEYWORDS:
        if kw in normalized:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="XO does not handle, collect, or process payments. Financial transactions are outside XO's scope."
            )

def sanitize_input_for_injection(text: str) -> str:
    """
    Defense against prompt injection attacks in user queries or external documents.
    Neutralizes system-level override attempts.
    """
    # Patterns attempting to override system prompts or role delimiters
    injection_patterns = [
        r"ignore (all )?previous instructions",
        r"you are now (an? )?unrestricted",
        r"system override",
        r"reveal (your )?system prompt",
        r"<\|im_start\|>",
        r"<\|im_end\|>",
        r"\[SYSTEM_PROMPT\]",
        r"execute (raw )?sql",
        r"drop table",
        r"select \* from"
    ]
    
    cleaned = text
    for pattern in injection_patterns:
        cleaned = re.sub(pattern, "[FILTERED_INPUT]", cleaned, flags=re.IGNORECASE)
    return cleaned

security_bearer = HTTPBearer(auto_error=False)

def verify_authenticated_user(credentials: Optional[HTTPAuthorizationCredentials] = Security(security_bearer)) -> str:
    """
    Validates token and returns current user ID.
    Rejects anonymous access for restricted account endpoints.
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to access user-scoped account records."
        )
    token = credentials.credentials
    # In prototype environment, user tokens map to user IDs (e.g. "usr_101", "usr_102")
    if token.startswith("user_"):
        return token
    if token == "mock_jwt_token_user_101":
        return "usr_101"
    return "usr_demo"
