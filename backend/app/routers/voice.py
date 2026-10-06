import base64
from typing import Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Response
from app.voice.stt_service import STTService
from app.voice.tts_service import TTSService
from app.orchestrator.orchestrator import ConversationOrchestrator

router = APIRouter(prefix="/api/voice", tags=["Voice Layer (STT & TTS)"])

class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Text to synthesize")
    language: str = Field(default="en", description="Language: 'en', 'ar', 'hi', or 'ur'")

@router.post("/transcribe")
async def transcribe_audio_endpoint(
    audio: UploadFile = File(...),
    language_hint: str = Form("en")
):
    """
    Speech-to-Text endpoint using OpenAI's gpt-live-transcribe model.
    Transcribes audio in EN, AR, HI, UR.
    """
    audio_bytes = await audio.read()
    transcribed_text, detected_lang = await STTService.transcribe_audio(
        audio_bytes=audio_bytes,
        filename=audio.filename or "audio.wav",
        language_hint=language_hint
    )
    return {
        "text": transcribed_text,
        "language": detected_lang,
        "model": "gpt-live-transcribe"
    }

@router.post("/synthesize")
async def synthesize_speech_endpoint(payload: TTSRequest):
    """
    Text-to-Speech endpoint using OpenAI's gpt-4o-mini-tts model.
    Synthesizes speech in EN, AR, HI, UR.
    """
    audio_bytes = await TTSService.synthesize_speech(
        text=payload.text,
        language=payload.language
    )
    return Response(content=audio_bytes, media_type="audio/wav")

@router.post("/interact")
async def voice_interaction_pipeline(
    audio: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
    language_hint: Optional[str] = Form("en")
):
    """
    Composed Voice-to-Voice (V2V) Pipeline (Rule 7 & Confirmed Decision 1):
    Audio In → STT (gpt-live-transcribe) → Conversation Orchestrator → TTS (gpt-4o-mini-tts) → Audio Stream
    Uses the exact same business logic and conversation orchestrator as text.
    """
    audio_bytes = await audio.read()

    # Step 1: STT
    user_text, detected_lang = await STTService.transcribe_audio(
        audio_bytes=audio_bytes,
        filename=audio.filename or "audio.wav",
        language_hint=language_hint or "en"
    )

    # Step 2: Conversation Orchestration
    orchestration_result = await ConversationOrchestrator.process_user_turn(
        user_message=user_text,
        session_id=session_id,
        manual_language=detected_lang
    )

    # Step 3: TTS Synthesis
    bot_reply_text = orchestration_result["text"]
    reply_audio_bytes = await TTSService.synthesize_speech(
        text=bot_reply_text,
        language=orchestration_result["language"]
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
        "audio_base64": f"data:audio/wav;base64,{audio_base64}",
        "pipeline": "gpt-live-transcribe -> gpt-5-mini -> gpt-4o-mini-tts"
    }
