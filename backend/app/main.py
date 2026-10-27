import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.voice.tts_service import TTSService
from app.db.lead_store import LeadDatabaseService
from app.routers import admin, chat, handoff, health, mortgage, properties, voice
from app.services.vector_store import VectorDatabase
from app.services import warmup

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("xo.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s (%s) — LLM=%s STT=%s TTS=%s", settings.APP_NAME, settings.ENVIRONMENT,
                settings.LLM_MODEL, settings.STT_MODEL, settings.TTS_MODEL)
    VectorDatabase.load()
    await LeadDatabaseService.init_db()
    warmup.warm_in_background()  # the first visitor after a restart does not pay for new provider connections
    yield
    await LeadDatabaseService.close_db()
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


for r in (health.router, chat.router, voice.router, mortgage.router, properties.router, handoff.router, admin.router):
    app.include_router(r)


@app.get("/")
def root():
    return {"service": settings.APP_NAME, "status": "ok"}
