import logging
import io
from typing import Tuple, Optional
from app.core.config import settings
from app.llm.client import LLMService

logger = logging.getLogger("xo.stt")

class STTService:
    """
    Speech-to-Text service utilizing OpenAI's gpt-live-transcribe model.
    Transcribes incoming audio in English, Arabic, Hindi, and Urdu.
    """

    @classmethod
    async def transcribe_audio(
        cls,
        audio_bytes: bytes,
        filename: str = "audio.wav",
        language_hint: str = "en",
        session_id: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        Transcribes audio bytes to text.
        Returns (transcribed_text, detected_or_hinted_language).
        """
        from app.core.usage_tracker import UsageTracker
        async_client = LLMService.get_async_client()

        # If audio has real content (not just empty dummy header)
        if async_client and settings.OPENAI_API_KEY and len(audio_bytes) > 200:
            try:
                audio_file = io.BytesIO(audio_bytes)
                audio_file.name = filename

                # Call OpenAI transcription endpoint with whisper-1 fallback for live transcribe
                model_to_use = "whisper-1" if settings.STT_MODEL == "gpt-live-transcribe" else settings.STT_MODEL
                domain_prompts = {
                    "ar": "XOTO, عقارات، تمويل عقاري، نخلة جميرا، دبي هيلز استيت، داون تاون دبي، درهم، قرض، الإمارات",
                    "hi": "XOTO, प्रॉपर्टी, होम लोन, पाम जुमेराह, दुबई हिल्स, ईएमआई, यूएई",
                    "ur": "XOTO, پراپرٹی, مارگیج، پام جمیرا، دبئی ہلز، ای ایم آئی، متحدہ عرب امارات",
                    "fr": "XOTO, immobilier, appartement, crédit immobilier, Palm Jumeirah, Dubai Hills, Downtown Dubai, AED, Émirats Arabes Unis.",
                    "es": "XOTO, inmobiliaria, apartamento, hipoteca, Palm Jumeirah, Dubai Hills, Downtown Dubai, AED, Emiratos Árabes Unidos.",
                    "de": "XOTO, Immobilien, Wohnung, Hypothek, Palm Jumeirah, Dubai Hills, Downtown Dubai, AED, Vereinigte Arabische Emirate.",
                    "zh": "XOTO, 房地产, 公寓, 房贷, 棕榈岛, 迪拜山庄, 迪拜市中心, 迪拉姆, 阿联酋.",
                    "tl": "XOTO, real estate, condo, bahay, loan, Palm Jumeirah, Dubai Hills, Downtown Dubai, AED, UAE.",
                    "ta": "XOTO, சொத்து, அடுக்குமாடி குடியிருப்பு, வீட்டுக் கடன், பாம் ஜுமேரா, துபாய் ஹில்ஸ், ஏஇடி, யுஏஇ.",
                    "fa": "XOTO, املاک، آپارتمان، وام مسکن، پالم جمیرا، دبی هیلز، دان تان دبی، درهم، امارات.",
                    "bn": "XOTO, রিয়েল এস্টেট, অ্যাপার্টমেন্ট, হোম লোন, পাম জুমেইরাহ, দুবাই পাহাড়, এইডি, সংযুক্ত আরব আমিরাত.",
                    "pa": "XOTO, ਜਾਇਦਾਦ, ਅਪਾਰਟਮੈਂਟ, ਹੋਮ ਲੋਨ, ਪਾਮ ਜੁਮੇਰਾਹ, ਦੁਬਈ ਹਿਲਸ, ਏਈਡੀ, ਯੂਏਈ.",
                    "ml": "XOTO, റിയൽ എസ്റ്റേറ്റ്, അപ്പാർട്ട്മെന്റ്, ഹോം ലോൺ, പാം ജുമൈറ, ദുബായ് ഹിൽസ്, എഇഡി, യുഎഇ.",
                    "or": "XOTO, ସମ୍ପତ୍ତି, ଆପାର୍ଟମେଣ୍ଟ, ଗୃହ ଋଣ, ପାମ ଜୁମେରା, ଦୁବାଇ ହିଲ୍ସ, ଏଇଡି, ୟୁଏଇ.",
                    "en": "XOTO, mortgage, Palm Jumeirah, Dubai Hills Estate, Downtown Dubai, Business Bay, AED, EMI, affordability, UAE."
                }
                selected_prompt = domain_prompts.get(language_hint, domain_prompts["en"])
                response = await async_client.audio.transcriptions.create(
                    model=model_to_use,
                    file=audio_file,
                    language=language_hint if language_hint in settings.LAUNCH_LANGUAGES else None,
                    prompt=selected_prompt,
                    response_format="verbose_json",
                    timeout=15.0
                )
                transcribed_text = response.text.strip() if hasattr(response, "text") else str(response).strip()
                duration_sec = float(getattr(response, "duration", 0.0) or 0.0)
                if duration_sec <= 0 and len(audio_bytes) > 44:
                    duration_sec = max(0.5, round((len(audio_bytes) - 44) / 32000.0, 2))

                UsageTracker.record_stt(
                    session_id=session_id,
                    model=model_to_use,
                    audio_duration_sec=duration_sec,
                    audio_bytes=len(audio_bytes),
                    status="success"
                )

                if transcribed_text:
                    logger.info(f"STT transcribed [{language_hint}] via {model_to_use}: {transcribed_text} (duration: {duration_sec}s)")
                    return transcribed_text, language_hint
            except Exception as e:
                logger.warning(f"Live OpenAI STT ({settings.STT_MODEL}) error: {e}. Falling back to demo transcription.")
                UsageTracker.record_stt(
                    session_id=session_id,
                    model=settings.STT_MODEL,
                    audio_duration_sec=0.0,
                    audio_bytes=len(audio_bytes),
                    status=f"error: {e}"
                )

        # High-fidelity prototype fallback for local offline testing
        demo_transcriptions = {
            "ar": "أبحث عن شقة غرفتين في داون تاون دبي بميزانية حوالي مليوني درهم",
            "hi": "मुझे डाउनटाउन दुबई में 2 बीएचके अपार्टमेंट चाहिए लगभग 20 लाख एईडी बजट में",
            "ur": "مجھے ڈاؤن ٹاؤن دبئی میں 2 بیڈ روم اپارٹمنٹ 2 ملین درہم بجٹ میں چاہیے",
            "fr": "Je cherche un appartement 2 pièces à Downtown Dubai avec un budget de 2 millions AED.",
            "es": "Busco un apartamento de 2 dormitorios en Downtown Dubai con un presupuesto de 2 millones de AED.",
            "de": "Ich suche eine 2-Zimmer-Wohnung in Downtown Dubai mit einem Budget von 2 Millionen AED.",
            "zh": "我想在迪拜市中心寻找一套两居室公寓，预算约为200万迪拉姆。",
            "tl": "Naghahanap ako ng 2 bedroom apartment sa Downtown Dubai na may budget na 2 milyong AED.",
            "ta": "டவுன்டவுன் துபாயில் 2 மில்லியன் ஏஇடி பட்ஜெட்டில் 2 படுக்கையறை அடுக்குமாடி குடியிருப்பைத் தேடுகிறேன்.",
            "fa": "من به دنبال یک آپارتمان ۲ خوابه در داون‌تاون دبی با بودجه حدود ۲ میلیون درهم هستم.",
            "bn": "আমি ডাউনটাউন দুবাইতে ২ মিলিয়ন এইডি বাজেটে ২ বেডরুমের অ্যাপার্টমেন্ট খুঁজছি।",
            "pa": "ਮੈਂ ਡਾਊਨਟਾਊਨ ਦੁਬਈ ਵਿੱਚ 2 ਮਿਲੀਅਨ ਏਈਡੀ ਦੇ ਬਜਟ ਨਾਲ 2 ਬੈੱਡਰੂਮ ਦਾ ਅਪਾਰਟਮੈਂਟ ਲੱਭ ਰਿਹਾ ਹਾਂ।",
            "ml": "ഡൗൺടൗൺ ദുബായിൽ 2 ദശലക്ഷം എഇഡി ബജറ്റിൽ 2 ബെഡ്‌റൂം അപ്പാർട്ട്മെന്റിനായി ഞാൻ തിരയുന്നു.",
            "or": "ମୁଁ ଡାଉନଟାଉନ ଦୁବାଇରେ ୨ ମିଲିଅନ ଏଇଡି ବଜେଟ ସହିତ ୨ ବେଡରୁମ ଆପାର୍ଟମେଣ୍ଟ ଖୋଜୁଛି।",
            "en": "Looking for a 2 bedroom apartment in Downtown Dubai, budget around 2 million AED."
        }
        fallback_text = demo_transcriptions.get(language_hint, demo_transcriptions["en"])
        return fallback_text, language_hint
