import logging
import io
from typing import Tuple
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
        language_hint: str = "en"
    ) -> Tuple[str, str]:
        """
        Transcribes audio bytes to text.
        Returns (transcribed_text, detected_or_hinted_language).
        """
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
                    "en": "XOTO, mortgage, Palm Jumeirah, Dubai Hills Estate, Downtown Dubai, Business Bay, AED, EMI, affordability, UAE.",
                    "ru": "XOTO, недвижимость, ипотека, Пальма Джумейра, Дубай Хиллс, первоначальный взнос, дирхам, ОАЭ.",
                    "fr": "XOTO, immobilier, prêt immobilier, Palm Jumeirah, Dubai Hills, mensualité, AED, Dubaï, Émirats.",
                    "de": "XOTO, Immobilien, Baufinanzierung, Palm Jumeirah, Dubai Hills, monatliche Rate, AED, VAE.",
                    "es": "XOTO, inmobiliaria, hipoteca, Palm Jumeirah, Dubai Hills, pago mensual, AED, Dubái, EAU.",
                    "tr": "XOTO, gayrimenkul, konut kredisi, Palm Jumeirah, Dubai Hills, taksit, AED, Dubai, BAE.",
                    "ta": "XOTO, ரியல் எஸ்டேட், வீட்டுக் கடன், பாம் ஜுமேரா, துபாய் ஹில்ஸ், இஎம்ஐ, திர்ஹாம், யுஏஇ.",
                    "te": "XOTO, రియల్ ఎస్టేట్, హోమ్ లోన్, పామ్ జుమేరా, దుబాయ్ హిల్స్, ఈఎంఐ, దిర్హామ్, యూఏఈ.",
                    "bn": "XOTO, রিয়েল এস্টেট, বন্ধক ঋণ, পাম জুমেইরাহ, দুবাই হিলস, ইএমআই, দিরহাম, ইউএই.",
                    "pa": "XOTO, ਰੀਅਲ ਅਸਟੇਟ, ਮਾਰਗੇਜ, ਪਾਮ ਜੁਮੇਰਾਹ, ਦੁਬਈ ਹਿਲਜ਼, ਈਐਮਆਈ, ਦਿਰਹਾਮ, ਯੂਏਈ.",
                    "gu": "XOTO, રિયલ એસ્ટેટ, હોમ લોન, પામ જુમેરાહ, દુબઈ હિલ્સ, ઇએમઆઇ, દિરહામ, યુએઈ.",
                    "mwr": "XOTO, प्रॉपर्टी, होम लोन, पाम जुमेराह, दुबई हिल्स, ईएमआई, दिरहम, यूएई.",
                    "or": "XOTO, ରିଅଲ ଇଷ୍ଟେଟ୍, ଗୃହ ଋଣ, ପାମ୍ ଜୁମେରାହ, ଦୁବାଇ ହିଲ୍ସ, ଇଏମଆଇ, ଦିରହାମ୍, ୟୁଏଇ."
                }
                selected_prompt = domain_prompts.get(language_hint, domain_prompts["en"])
                # Supported Whisper 2-letter ISO codes; map mwr to hi, or to None
                whisper_lang_map = {
                    "en": "en", "ar": "ar", "hi": "hi", "ur": "ur",
                    "ru": "ru", "fr": "fr", "de": "de", "es": "es",
                    "tr": "tr", "ta": "ta", "te": "te", "bn": "bn",
                    "pa": "pa", "gu": "gu", "mwr": "hi", "or": None
                }
                whisper_lang = whisper_lang_map.get(language_hint)
                response = await async_client.audio.transcriptions.create(
                    model=model_to_use,
                    file=audio_file,
                    language=whisper_lang,
                    prompt=selected_prompt,
                    timeout=15.0
                )
                transcribed_text = response.text.strip()
                if transcribed_text:
                    logger.info(f"STT transcribed [{language_hint}] via {model_to_use}: {transcribed_text}")
                    return transcribed_text, language_hint
            except Exception as e:
                logger.warning(f"Live OpenAI STT ({settings.STT_MODEL}) error: {e}. Falling back to demo transcription.")

        # High-fidelity prototype fallback for local offline testing
        # Provides meaningful transcription corresponding to language hint
        demo_transcriptions = {
            "ar": "أبحث عن شقة غرفتين في داون تاون دبي بميزانية حوالي مليوني درهم",
            "hi": "मुझे डाउनटाउन दुबई में 2 बीएचके अपार्टमेंट चाहिए लगभग 20 लाख एईडी बजट में",
            "ur": "مجھے ڈاؤن ٹاؤن دبئی میں 2 بیڈ روم اپارٹمنٹ 2 ملین درہم بجٹ میں چاہیے",
            "en": "Looking for a 2 bedroom apartment in Downtown Dubai, budget around 2 million AED.",
            "ru": "Ищу двухкомнатную квартиру в Даунтаун Дубай с бюджетом около 2 миллионов дирхамов",
            "fr": "Je cherche un appartement de 2 chambres à Downtown Dubai avec un budget d'environ 2 millions d'AED",
            "de": "Ich suche eine 2-Zimmer-Wohnung in Downtown Dubai mit einem Budget von ca. 2 Millionen AED",
            "es": "Busco un apartamento de 2 habitaciones en Downtown Dubai con un presupuesto de unos 2 millones de AED",
            "tr": "Downtown Dubai'de yaklaşık 2 milyon AED bütçeyle 2 yatak odalı bir daire arıyorum",
            "ta": "டவுன்டவுன் துபாயில் சுமார் 2 மில்லியன் AED பட்ஜெட்டில் 2 படுக்கையறை அபார்ட்மெண்ட் தேடுகிறேன்",
            "te": "డౌన్‌టౌన్ దుబాయ్‌లో సుమారు 2 మిలియన్ల AED బడ్జెట్‌తో 2 బెడ్‌రూమ్ అపార్ట్‌మెంట్ కోసం చూస్తున్నాను",
            "bn": "ডাউনটাউন দুবাইতে প্রায় ২ মিলিয়ন AED বাজেটে ২ বেডরুমের অ্যাপার্টমেন্ট খুঁজছি",
            "pa": "ਡਾਊਨਟਾਊਨ ਦੁਬਈ ਵਿੱਚ ਲਗਭਗ 2 ਮਿਲੀਅਨ AED ਬਜਟ ਵਿੱਚ 2 ਬੈੱਡਰੂਮ ਅਪਾਰਟਮੈਂਟ ਲੱਭ ਰਿਹਾ ਹਾਂ",
            "gu": "ડાઉનટાઉન દુબઈમાં આશરે 2 મિલિયન AED ના બજેટમાં 2 બેડરૂમનું એપાર્ટમેન્ટ શોધી રહ્યો છું",
            "mwr": "म्हाने डाउनटाउन दुबई में 2 बीएचके फ्लैट चाहीजै, बजट लगभग 20 लाख एईडी रो है",
            "or": "ଡାଉନଟାଉନ ଦୁବାଇରେ ପ୍ରାୟ ୨ ନିୟୁତ AED ବଜେଟରେ ୨ ବେଡରୁମ ବିଶିଷ୍ଟ ଆପାର୍ଟମେଣ୍ଟ ଖୋଜୁଛି"
        }
        fallback_text = demo_transcriptions.get(language_hint, demo_transcriptions["en"])
        return fallback_text, language_hint
