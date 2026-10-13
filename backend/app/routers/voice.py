import base64
from typing import Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, UploadFile, File, Form, Header, HTTPException, Response
from app.core.config import settings
from app.voice.stt_service import STTService
from app.voice.tts_service import TTSService
from app.orchestrator.orchestrator import ConversationOrchestrator

from app.core.usage_tracker import UsageTracker

router = APIRouter(prefix="/api/voice", tags=["Voice Layer (STT & TTS)"])

class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Text to synthesize")
    language: str = Field(default="en", description="Language: 'en', 'ar', 'hi', or 'ur'")
    session_id: Optional[str] = Field(default=None, description="Optional session correlation identifier")

@router.post("/transcribe")
async def transcribe_audio_endpoint(
    audio: UploadFile = File(...),
    language_hint: str = Form("en"),
    session_id: Optional[str] = Form(None)
):
    """
    Speech-to-Text endpoint using OpenAI's gpt-live-transcribe model.
    Transcribes audio in EN, AR, HI, UR.
    """
    audio_bytes = await audio.read()
    transcribed_text, detected_lang = await STTService.transcribe_audio(
        audio_bytes=audio_bytes,
        filename=audio.filename or "audio.wav",
        language_hint=language_hint,
        session_id=session_id
    )
    return {
        "text": transcribed_text,
        "language": detected_lang,
        "model": "gpt-live-transcribe"
    }

@router.post("/synthesize")
async def synthesize_speech_endpoint(payload: TTSRequest):
    """
    Text-to-Speech endpoint using ElevenLabs' eleven_flash_v2_5 model.
    Synthesizes speech in EN, AR, HI, UR.
    """
    audio_bytes = await TTSService.synthesize_speech(
        text=payload.text,
        language=payload.language,
        session_id=payload.session_id
    )
    return Response(content=audio_bytes, media_type="audio/mpeg")

@router.post("/interact")
async def voice_interaction_pipeline(
    audio: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
    language_hint: Optional[str] = Form("en"),
    transcribed_text: Optional[str] = Form(None),
    user_id: Optional[str] = Form(None),
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """
    Composed Voice-to-Voice (V2V) Pipeline (Rule 7 & Confirmed Decision 1):
    Audio In → STT (gpt-live-transcribe) → Conversation Orchestrator → TTS (eleven_flash_v2_5) → Audio Stream
    Uses the exact same business logic and conversation orchestrator as text.
    """
    active_session_id = session_id or x_session_id
    active_user_id = user_id or x_user_id
    audio_bytes = await audio.read()

    # Step 1: STT (Use client-side verified transcript if supplied, otherwise perform STT)
    if transcribed_text and transcribed_text.strip():
        user_text = transcribed_text.strip()
        detected_lang = language_hint or "en"
        # Also capture client-side STT duration if audio is present
        if len(audio_bytes) > 200:
            duration_sec = max(0.5, round((len(audio_bytes) - 44) / 32000.0, 2))
            UsageTracker.record_stt(
                session_id=active_session_id,
                model="web-speech-verified",
                audio_duration_sec=duration_sec,
                audio_bytes=len(audio_bytes),
                status="success"
            )
    else:
        user_text, detected_lang = await STTService.transcribe_audio(
            audio_bytes=audio_bytes,
            filename=audio.filename or "audio.wav",
            language_hint=language_hint or "en",
            session_id=active_session_id
        )

    # Step 2: Conversation Orchestration
    orchestration_result = await ConversationOrchestrator.process_user_turn(
        user_message=user_text,
        session_id=active_session_id,
        user_id=active_user_id,
        manual_language=detected_lang
    )

    # Step 3: TTS Synthesis (ElevenLabs Flash v2.5)
    bot_reply_text = orchestration_result["text"]
    reply_audio_bytes = await TTSService.synthesize_speech(
        text=bot_reply_text,
        language=orchestration_result["language"],
        session_id=orchestration_result["session_id"]
    )
    audio_base64 = base64.b64encode(reply_audio_bytes).decode("utf-8")

    return {
        "session_id": orchestration_result["session_id"],
        "transcribed_user_text": user_text,
        "detected_language": orchestration_result["language"],
        "intent": orchestration_result["intent"],
        "reply_text": bot_reply_text,
        "property_results": orchestration_result.get("property_results", []),
        "mortgage_result": orchestration_result.get("mortgage_result"),
        "saved_properties": orchestration_result.get("saved_properties", []),
        "application_status": orchestration_result.get("application_status"),
        "handoff_data": orchestration_result.get("handoff_data"),
        "handoff_offered": orchestration_result.get("handoff_offered", False),
        "audio_base64": f"data:audio/mpeg;base64,{audio_base64}",
        "pipeline": f"{settings.STT_MODEL} -> {settings.LLM_MODEL} -> {settings.TTS_MODEL}"
    }
