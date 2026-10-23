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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("xo.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s (%s) — LLM=%s STT=%s TTS=%s", settings.APP_NAME, settings.ENVIRONMENT,
                settings.LLM_MODEL, settings.STT_MODEL, settings.TTS_MODEL)
    VectorDatabase.load()
    await Database.init()
    await LeadDatabaseService.init_db()
    await bootstrap_first_admin()
    await ConfigStore.load_published()  # versions published in the admin module (FR-25, FR-27, FR-29)
    try:
        logger.info("Knowledge base: %d entries live.", await KnowledgeStore.rebuild_index())  # FR-24 edits over the built-in KB
    except Exception as exc:  # keep the built-in index loaded above
        logger.error("Knowledge-base edits could not be loaded; using the built-in knowledge base: %s", exc)
    refreshers = [asyncio.create_task(ConfigStore.refresh_forever()), asyncio.create_task(KnowledgeStore.refresh_forever())]
    yield
    for task in refreshers:
        task.cancel()
    await ConversationStore.flush()
    await LeadDatabaseService.close_db()
    await Database.close()
    await TTSService.close()


app = FastAPI(title=settings.APP_NAME, version="2.0.0", lifespan=lifespan,
              docs_url="/docs" if settings.ENVIRONMENT != "production" else None, redoc_url=None)

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
