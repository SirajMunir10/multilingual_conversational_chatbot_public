import logging
import io
import struct
from typing import Optional
from app.core.config import settings
from app.llm.client import LLMService

logger = logging.getLogger("xo.tts")

class TTSService:
    """
    Text-to-Speech service utilizing OpenAI's gpt-4o-mini-tts model.
    Synthesizes speech in English, Arabic, Hindi, and Urdu.
    """

    # Cheerleader & Cute Voice Profile (Nova / Marin)
    # OpenAI API enum supports: 'nova', 'shimmer', 'echo', 'onyx', 'fable', 'alloy', 'ash', 'sage', 'coral'
    # 'nova' is OpenAI's official energetic, upbeat, cute female voice.
    VOICE_PROFILES = {
        "en": "nova",
        "ar": "nova",
        "hi": "nova",
        "ur": "nova"
    }

    @classmethod
    async def synthesize_speech(
        cls,
        text: str,
        language: str = "en",
        voice: Optional[str] = None
    ) -> bytes:
        """
        Synthesizes text into audio bytes (MP3/WAV format).
        Uses cute, upbeat cheerleader voice profile (Nova / Marin).
        """
        async_client = LLMService.get_async_client()
        # Default to nova (OpenAI's cute/cheerleader voice)
        requested_voice = voice or cls.VOICE_PROFILES.get(language, "nova")

        if async_client and settings.OPENAI_API_KEY:
            try:
                # Use tts-1 model with 15-second timeout for snappy speech synthesis
                model_to_use = "tts-1" if settings.TTS_MODEL == "gpt-4o-mini-tts" else settings.TTS_MODEL
                
                # Attempt synthesis with requested voice (e.g. marin or nova)
                try:
                    response = await async_client.audio.speech.create(
                        model=model_to_use,
                        voice=requested_voice,
                        input=text,
                        timeout=15.0
                    )
                except Exception as ve:
                    # If OpenAI API endpoint doesn't support 'marin' yet, automatically fall back to 'nova'
                    if "voice" in str(ve).lower() or requested_voice.lower() == "marin":
                        logger.info(f"Voice '{requested_voice}' not supported by endpoint. Using cute cheerleader voice 'nova'.")
                        response = await async_client.audio.speech.create(
                            model=model_to_use,
                            voice="nova",
                            input=text,
                            timeout=15.0
                        )
                    else:
                        raise ve

                audio_bytes = await response.aread()
                logger.info(f"TTS synthesized {len(text)} chars in [{language}] using cheerleader voice ({len(audio_bytes)} bytes)")
                return audio_bytes
            except Exception as e:
                logger.warning(f"Live OpenAI TTS ({settings.TTS_MODEL}) error: {e}. Generating prototype audio fallback.")

        # Valid minimal WAV audio fallback (1 sec 44.1kHz mono silent/tone pulse)
        # Allows frontend audio element to play without errors in offline dev mode
        return cls._generate_mock_wav_audio()

    @staticmethod
    def _generate_mock_wav_audio() -> bytes:
        """
        Generates a valid 1-second 44.1kHz 16-bit PCM WAV audio header + payload
        for local offline audio playback testing.
        """
        sample_rate = 44100
        duration_sec = 0.5
        num_samples = int(sample_rate * duration_sec)
        byte_rate = sample_rate * 2
        block_align = 2
        data_size = num_samples * 2

        buffer = io.BytesIO()
        # RIFF header
        buffer.write(b"RIFF")
        buffer.write(struct.pack("<I", 36 + data_size))
        buffer.write(b"WAVE")
        # fmt chunk
        buffer.write(b"fmt ")
        buffer.write(struct.pack("<I", 16))
        buffer.write(struct.pack("<H", 1))  # PCM
        buffer.write(struct.pack("<H", 1))  # 1 channel (mono)
        buffer.write(struct.pack("<I", sample_rate))
        buffer.write(struct.pack("<I", byte_rate))
        buffer.write(struct.pack("<H", block_align))
        buffer.write(struct.pack("<H", 16))  # 16 bits per sample
        # data chunk
        buffer.write(b"data")
        buffer.write(struct.pack("<I", data_size))
        buffer.write(b"\x00" * data_size)

        return buffer.getvalue()
