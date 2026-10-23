"""Admin sign-in and permission checks (PRD FR-30, §7 security).

A signed-in admin carries an HttpOnly, SameSite=Strict session cookie naming the user, their `token_version` and a
server-side session. Signing out ends that one session; a password or role change or deactivation ends them all. Scripts can still
use the X-Admin-Key header, which acts as a full Admin."""
import hmac
import logging
from typing import Any, Callable, Dict, Optional

from fastapi import Depends, HTTPException, Request, Response, status

from app.admin.permissions import permissions_for
from app.admin.users import AdminUserError, AdminUserStore
from app.core.config import settings
from app.core.security import ADMIN_AUDIENCE, Role, issue_token, verify_claims

logger = logging.getLogger("xo.admin.auth")

COOKIE_NAME = "xo_admin"
COOKIE_PATH = "/api/admin"
# Browsers send this header only from our own pages; a cross-site form or image cannot add it (CSRF defence).
CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "xo-admin"
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

Actor = Dict[str, Any]


def _actor(user: Dict[str, Any], via: str) -> Actor:
    return {"id": user["id"], "email": user["email"], "name": user["name"], "role": user["role"],
            "permissions": sorted(permissions_for(user["role"])), "via": via}


_KEY_ACTOR = {"id": 0, "email": "admin-api-key", "name": "Admin API key", "role": Role.ADMIN}


def session_ttl_sec() -> int:
    return max(1, settings.ADMIN_SESSION_HOURS) * 3600


async def start_session(request: Request, response: Response, user: Dict[str, Any]) -> None:
    """Opens a new server-side session for this browser and sets its cookie."""
    session_id = await AdminUserStore.create_session(user["id"], session_ttl_sec())
    token = issue_token(str(user["id"]), ttl_sec=session_ttl_sec(), audience=ADMIN_AUDIENCE,
                        claims={"tv": user["token_version"], "sid": session_id})
    host = (request.url.hostname or "").lower()
    response.set_cookie(COOKIE_NAME, token, max_age=session_ttl_sec(), path=COOKIE_PATH, httponly=True,
                        samesite="strict", secure=host not in ("localhost", "127.0.0.1", "testserver"))


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path=COOKIE_PATH)


async def current_actor(request: Request) -> Actor:
    key = request.headers.get("x-admin-key")
    if key is not None:
        if settings.ADMIN_API_KEY and hmac.compare_digest(key, settings.ADMIN_API_KEY):
            return _actor(_KEY_ACTOR, "key")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin authentication required.")

    claims = verify_claims(request.cookies.get(COOKIE_NAME, ""), audience=ADMIN_AUDIENCE)
    if not claims:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin authentication required.")
    try:
        user = await AdminUserStore.get(int(claims["sub"]))
    except (TypeError, ValueError):
        user = None
    if (not user or not user["active"] or user["token_version"] != claims.get("tv")
            or not await AdminUserStore.session_active(str(claims.get("sid") or ""), user["id"])):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin authentication required.")
    if request.method not in _SAFE_METHODS and request.headers.get(CSRF_HEADER) != CSRF_VALUE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing request header.")
    return {**_actor(user, "session"), "session_id": claims["sid"]}


def require(permission: str) -> Callable[..., Any]:
    """FastAPI dependency: the signed-in actor, if their role grants `permission` (PRD FR-30)."""
    async def check(actor: Actor = Depends(current_actor)) -> Actor:
        if permission not in actor["permissions"]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your role does not allow this.")
        return actor
    return check


def require_any(*permissions: str) -> Callable[..., Any]:
    """FastAPI dependency: the signed-in actor, if their role grants at least one of `permissions`."""
    async def check(actor: Actor = Depends(current_actor)) -> Actor:
        if not any(p in actor["permissions"] for p in permissions):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your role does not allow this.")
        return actor
    return check


async def bootstrap_first_admin() -> Optional[Dict[str, Any]]:
    """Creates the first Admin from ADMIN_BOOTSTRAP_EMAIL / ADMIN_BOOTSTRAP_PASSWORD when no admin account exists."""
    if not (settings.ADMIN_BOOTSTRAP_EMAIL and settings.ADMIN_BOOTSTRAP_PASSWORD):
        return None
    if await AdminUserStore.count_active_admins() > 0:
        return None
    try:
        user = await AdminUserStore.create(settings.ADMIN_BOOTSTRAP_EMAIL, "Administrator", Role.ADMIN,
                                           settings.ADMIN_BOOTSTRAP_PASSWORD)
        logger.info("Created the first admin account (%s).", user["email"])
        return user
    except AdminUserError as exc:
        logger.error("Could not create the first admin account: %s", exc)
        return None
