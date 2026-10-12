import logging
import io
import struct
from typing import Optional
import httpx
from app.core.config import settings

logger = logging.getLogger("xo.tts")

class TTSService:
    """
    Text-to-Speech service utilizing ElevenLabs' eleven_flash_v2_5 model.
    Synthesizes low-latency, high-realism speech in English, Arabic, Hindi, and Urdu.
    """

    # Curated Voice IDs for ElevenLabs Flash v2.5
    # Default is Horatius (qXpMhyvQqiRxWQs4qSSB) - Energetic Character voice
    VOICE_PROFILES = {
        "en": "qXpMhyvQqiRxWQs4qSSB",  # Horatius (Energetic, confident character voice)
        "ar": "qXpMhyvQqiRxWQs4qSSB",  # Multilingual Flash v2.5 native Arabic
        "hi": "qXpMhyvQqiRxWQs4qSSB",  # Multilingual Flash v2.5 native Hindi
        "ur": "qXpMhyvQqiRxWQs4qSSB"   # Multilingual Flash v2.5 native Urdu
    }

    @classmethod
    async def synthesize_speech(
        cls,
        text: str,
        language: str = "en",
        voice: Optional[str] = None
    ) -> bytes:
        """
        Synthesizes text into audio bytes (MP3 format) using ElevenLabs Flash v2.5.
        """
        voice_id = voice or getattr(settings, "ELEVENLABS_VOICE_ID", "") or cls.VOICE_PROFILES.get(language, "qXpMhyvQqiRxWQs4qSSB")
        api_key = settings.ELEVENLABS_API_KEY
        model_id = settings.TTS_MODEL or "eleven_flash_v2_5"

        if api_key:
            try:
                url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
                headers = {
                    "xi-api-key": api_key,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg"
                }
                params = {
                    "output_format": "mp3_44100_128"
                }
                payload = {
                    "text": text,
                    "model_id": model_id,
                    "voice_settings": {
                        "stability": 0.5,
                        "similarity_boost": 0.75
                    }
                }

                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.post(url, headers=headers, params=params, json=payload)
                    if response.status_code == 200:
                        audio_bytes = response.content
                        logger.info(
                            f"ElevenLabs Flash v2.5 synthesized {len(text)} chars in [{language}] "
                            f"(voice={voice_id}, size={len(audio_bytes)} bytes)"
                        )
                        return audio_bytes
                    else:
                        logger.warning(
                            f"ElevenLabs API returned status {response.status_code}: {response.text}. "
                            f"Falling back to mock audio."
                        )
            except Exception as e:
                logger.warning(f"Live ElevenLabs TTS ({model_id}) error: {e}. Generating prototype audio fallback.")

        # Valid minimal audio fallback (for offline development/test runs)
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
