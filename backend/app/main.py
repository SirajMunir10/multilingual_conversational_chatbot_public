import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.admin.auth import bootstrap_first_admin
from app.admin.config_store import ConfigStore
from app.admin.knowledge import KnowledgeStore
from app.core.config import settings
from app.voice.tts_service import TTSService
from app.db.conversation_store import ConversationStore
from app.db.database import Database
from app.db.lead_store import LeadDatabaseService
from app.routers import admin, admin_config, admin_insights, admin_kb, chat, handoff, health, mortgage, properties, voice
from app.services.vector_store import VectorDatabase
from app.services import warmup

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("xo.main")


_PLACEHOLDERS = {"generate_a_long_random_value", "changeme", "change_me", "secret", "password", "admin"}


def _warn_weak_secrets() -> None:
    """Short or example secrets can be guessed; a guessed JWT_SECRET or ADMIN_API_KEY is full admin access."""
    for name, value, minimum in (("JWT_SECRET", settings.JWT_SECRET, 32), ("ADMIN_API_KEY", settings.ADMIN_API_KEY, 32)):
        if value and (len(value) < minimum or value.lower() in _PLACEHOLDERS):
            logger.error("%s is too weak (use at least %d random characters, e.g. `openssl rand -hex 32`).", name, minimum)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s (%s) — LLM=%s STT=%s TTS=%s", settings.APP_NAME, settings.ENVIRONMENT,
                settings.LLM_MODEL, settings.STT_MODEL, settings.TTS_MODEL)
    _warn_weak_secrets()
    VectorDatabase.load()
    await Database.init()
    await LeadDatabaseService.init_db()
    await bootstrap_first_admin()
    await ConfigStore.load_published()  # versions published in the admin module (FR-25, FR-27, FR-29)
    try:
        logger.info("Knowledge base: %d entries live.", await KnowledgeStore.rebuild_index())  # FR-24 edits over the built-in KB
    except Exception as exc:  # keep the built-in index loaded above
        logger.error("Knowledge-base edits could not be loaded; using the built-in knowledge base: %s", exc)
    warmup.warm_in_background()  # the first visitor after a restart does not pay for new provider connections
    refreshers = [asyncio.create_task(ConfigStore.refresh_forever()), asyncio.create_task(KnowledgeStore.refresh_forever())]
    yield
    for task in refreshers:
        task.cancel()
    await ConversationStore.flush()
    await LeadDatabaseService.close_db()
    await Database.close()
    await TTSService.close()


# The interactive API docs list every endpoint and field; they are off unless ENABLE_API_DOCS is set (local work).
app = FastAPI(title=settings.APP_NAME, version="2.0.0", lifespan=lifespan, redoc_url=None,
              docs_url="/docs" if settings.ENABLE_API_DOCS else None,
              openapi_url="/openapi.json" if settings.ENABLE_API_DOCS else None)

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-site",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}


class SecurityHeaders:
    """The API only returns data, never pages: browsers are told not to render, frame or sniff it. Written as plain
    ASGI so streamed replies (chat text, voice audio) pass through untouched."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        extra = dict(_SECURITY_HEADERS)
        if settings.ENVIRONMENT == "production":
            extra["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if scope["path"].startswith("/api/admin"):
            extra["Cache-Control"] = "no-store"  # personal data and transcripts are never cached

        async def with_headers(message):
            if message["type"] == "http.response.start":
                present = {k.lower() for k, _ in message.get("headers", [])}
                message["headers"] = [*message.get("headers", []),
                                      *((k.lower().encode(), v.encode()) for k, v in extra.items() if k.lower().encode() not in present)]
            await send(message)
        await self.app(scope, receive, with_headers)


class RequestSizeLimit:
    """Refuses request bodies over MAX_REQUEST_BYTES (uploads: MAX_UPLOAD_REQUEST_BYTES) with 413 before they are read
    into memory. A declared Content-Length is checked up front; a body sent without one is counted as it arrives."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = settings.MAX_UPLOAD_REQUEST_BYTES if scope["path"].endswith("/kb/upload") else settings.MAX_REQUEST_BYTES
        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None:
            if not declared.isdigit() or int(declared) > limit:
                return await self._too_large(scope, receive, send)
            return await self.app(scope, receive, send)
        body, more = b"", True
        while more:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body += message.get("body", b"")
            more = message.get("more_body", False)
            if len(body) > limit:
                return await self._too_large(scope, receive, send)
        replayed = False

        async def replay():
            nonlocal replayed
            if replayed:
                return await receive()  # later calls see the client disconnecting, as streamed replies expect
            replayed = True
            return {"type": "http.request", "body": body, "more_body": False}
        await self.app(scope, replay, send)

    @staticmethod
    async def _too_large(scope, receive, send):
        await JSONResponse(status_code=413, content={"detail": "request_too_large"})(scope, receive, send)


app.add_middleware(RequestSizeLimit)
app.add_middleware(SecurityHeaders)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Admin-Key"],
)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "internal_error"})


for r in (health.router, chat.router, voice.router, mortgage.router, properties.router, handoff.router, admin.router, admin_insights.router, admin_config.router,
          admin_kb.router):
    app.include_router(r)


@app.get("/")
def root():
    return {"service": settings.APP_NAME, "status": "ok"}
