import base64
import hashlib
import hmac
import json
import re
import time
from collections import defaultdict, deque
from typing import Any, Deque, Dict, Optional

from fastapi import Header, HTTPException, Request, status

from app.core.config import settings


class Role:
    CONTENT_EDITOR = "content_editor"
    BOT_TRAINER = "bot_trainer"
    ADMIN = "admin"
    READ_ONLY_ANALYST = "read_only_analyst"


# ---------------------------------------------------------------------------
# Authentication (PRD FR-21): identity comes only from a signed token,
# never from a client-supplied header or form field.
# ---------------------------------------------------------------------------

def _b64url_decode(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


# Admin sign-in tokens carry this audience, so they are never accepted as a visitor identity (and vice versa).
ADMIN_AUDIENCE = "xo-admin"


def issue_token(user_id: str, ttl_sec: int = 3600, audience: Optional[str] = None, claims: Optional[Dict[str, Any]] = None) -> str:
    """Issues an HS256 token. Used by the identity provider integration, the admin sign-in and tests."""
    if not settings.JWT_SECRET:
        raise RuntimeError("JWT_SECRET is not configured")
    body: Dict[str, Any] = {**(claims or {}), "sub": user_id, "exp": int(time.time()) + ttl_sec}
    if audience:
        body["aud"] = audience
    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url_encode(json.dumps(body).encode())
    signature = hmac.new(settings.JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64url_encode(signature)}"


def verify_claims(token: str, audience: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Returns the claims of a valid, unexpired HS256 token issued for exactly this audience, otherwise None."""
    if not token or not settings.JWT_SECRET:
        return None
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
        header = json.loads(_b64url_decode(header_b64))
        if header.get("alg") != "HS256":
            return None
        expected = hmac.new(settings.JWT_SECRET.encode(), f"{header_b64}.{payload_b64}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64url_decode(sig_b64)):
            return None
        payload = json.loads(_b64url_decode(payload_b64))
        if int(payload.get("exp", 0)) < time.time() or payload.get("aud") != audience or not payload.get("sub"):
            return None
        return payload
    except Exception:
        return None


def verify_token(token: str) -> Optional[str]:
    """Returns the visitor's user id for a valid, unexpired HS256 token, otherwise None. Admin tokens are rejected."""
    claims = verify_claims(token)
    return str(claims["sub"]) if claims else None


def optional_user(authorization: Optional[str] = Header(None)) -> Optional[str]:
    """FastAPI dependency: authenticated user id or None for anonymous visitors."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    return verify_token(authorization.split(" ", 1)[1].strip())


# ---------------------------------------------------------------------------
# Payment-data guard (PRD FR-23b): card and bank numbers never reach the LLM.
# ---------------------------------------------------------------------------

_CARD_CANDIDATE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){11,30}\b")
_CVV = re.compile(r"\b(cvv|cvc|security code)\s*[:#]?\s*\d{3,4}\b", re.IGNORECASE)


def _luhn_ok(digits: str) -> bool:
    total, parity = 0, len(digits) % 2
    for i, ch in enumerate(digits):
        d = int(ch)
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def redact_payment_data(text: str) -> str:
    """Replaces card numbers (Luhn-valid), IBANs and CVV codes with a placeholder."""
    def _card(match: "re.Match[str]") -> str:
        digits = re.sub(r"\D", "", match.group(0))
        return "[payment detail removed]" if 13 <= len(digits) <= 19 and _luhn_ok(digits) else match.group(0)

    text = _CARD_CANDIDATE.sub(_card, text)
    text = _IBAN.sub("[payment detail removed]", text)
    return _CVV.sub("[payment detail removed]", text)


# ---------------------------------------------------------------------------
# PII masking for logs and audit records (PRD FR-22).
# ---------------------------------------------------------------------------

def mask_phone(phone: Optional[str]) -> Optional[str]:
    if not phone:
        return phone
    digits = re.sub(r"\D", "", phone)
    return f"***{digits[-3:]}" if len(digits) >= 3 else "***"


def mask_name(name: Optional[str]) -> Optional[str]:
    if not name:
        return name
    return " ".join(part[0] + "." for part in name.split() if part)


# ---------------------------------------------------------------------------
# Rate limiting (cost-abuse protection, PRD §7 cost control).
# ---------------------------------------------------------------------------

class RateLimiter:
    def __init__(self) -> None:
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)

    def _recent(self, key: str, window_sec: float) -> Deque[float]:
        now = time.monotonic()
        bucket = self._hits[key]
        while bucket and now - bucket[0] > window_sec:
            bucket.popleft()
        return bucket

    def blocked(self, key: str, limit: int, window_sec: float) -> bool:
        """True once `limit` events were recorded for `key` within the window; records nothing itself."""
        return len(self._recent(key, window_sec)) >= limit

    def record(self, key: str) -> None:
        self._hits[key].append(time.monotonic())

    def allow(self, key: str, limit: int, window_sec: float = 60.0) -> bool:
        bucket = self._recent(key, window_sec)
        if len(bucket) >= limit:
            return False
        bucket.append(time.monotonic())
        if len(self._hits) > 20000:
            for stale in [k for k, v in self._hits.items() if not v]:
                self._hits.pop(stale, None)
        return True


rate_limiter = RateLimiter()


def client_ip(request: Any, direct: bool = False) -> str:
    """The visitor's address. Each trusted proxy appends the address it received the request from, so the entry
    TRUSTED_PROXY_HOPS from the right is the one our own proxies saw. Anything further left was sent by the visitor
    and could be made up, so it is never used. `direct` is for connections that skip the site's proxy (live voice
    connects straight to the API), which have one proxy fewer."""
    entries = [e.strip() for e in request.headers.get("x-forwarded-for", "").split(",") if e.strip()]
    hops = max(1, settings.TRUSTED_PROXY_HOPS - (1 if direct else 0))
    if entries:
        return entries[-hops] if len(entries) >= hops else entries[0]
    return request.client.host if request.client else "unknown"


def _too_many() -> HTTPException:
    return HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many requests. Please wait a moment.")


def allow_paid_call(key: str) -> bool:
    """Per-visitor limit plus a ceiling shared by everyone, for anything that spends AI or speech credit."""
    if not settings.RATE_LIMIT_ENABLED:
        return True
    if rate_limiter.blocked("paid:all", settings.GLOBAL_PAID_CALLS_PER_MINUTE, 60.0):
        return False
    if not rate_limiter.allow(key, settings.RATE_LIMIT_PER_MINUTE):
        return False
    rate_limiter.record("paid:all")
    return True


def enforce_rate_limit(request: Request) -> None:
    """FastAPI dependency for public endpoints (calculators, search, callbacks): a per-visitor limit."""
    if settings.RATE_LIMIT_ENABLED and not rate_limiter.allow(client_ip(request), settings.RATE_LIMIT_PER_MINUTE):
        raise _too_many()


def enforce_paid_limit(request: Request) -> None:
    """FastAPI dependency for endpoints that spend AI or speech credit (chat, speech)."""
    if not allow_paid_call(client_ip(request)):
        raise _too_many()


def enforce_light_rate_limit(request: Request) -> None:
    """For free but repeatable endpoints (warming connections): a visitor needs only a few a minute."""
    if settings.RATE_LIMIT_ENABLED and not rate_limiter.allow(f"light:{client_ip(request)}", 6):
        raise _too_many()
