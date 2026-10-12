import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.routers import health, gateways, chat, voice, mortgage, properties

# Configure root logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("xo.main")

app = FastAPI(
    title=settings.APP_NAME,
    description="XO — Conversational AI Assistant: Embedded Real Estate, Mortgage, & Knowledge Engine.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configure CORS for Vue 3 frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS + ["*"],  # Permissive for local dev prototype
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount core routers
app.include_router(health.router)
app.include_router(gateways.router)
app.include_router(chat.router)
app.include_router(voice.router)
app.include_router(mortgage.router)
app.include_router(properties.router)

@app.get("/")
def root():
    return {
        "message": f"Welcome to {settings.APP_NAME}",
        "status": "operational",
        "health_check": "/api/health",
        "api_docs": "/docs"
    }

@app.on_event("startup")
async def on_startup():
    logger.info(f"Starting {settings.APP_NAME}")
    logger.info(f"Active Models: LLM={settings.LLM_MODEL}, STT={settings.STT_MODEL}, TTS={settings.TTS_MODEL} (ElevenLabs Flash v2.5 - Voice: {settings.ELEVENLABS_VOICE_NAME} [{settings.ELEVENLABS_VOICE_ID}])")
    logger.info(f"Compliance Standard: {settings.REGULATORY_SCOPE} (Policy: {settings.COMPANY_RETENTION_POLICY_REF})")
    logger.info("Data Access Boundary: ZERO direct database connections enabled. All I/O scoped through API Gateways.")
