"""Chat and voice fixes (fix/chat-response-bugs): XO and XOTO names, explicit language requests, speech-to-text
settings, pronunciation, end-of-speech timing and connection warm-up."""
import json
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from app.core.config import load_config, settings
from app.gateways.grid_gateway import GridOffPlanGateway
from app.llm.client import LLMService
from app.main import app
from app.orchestrator.orchestrator import ConversationOrchestrator as O
from app.orchestrator.session_store import SessionStore
from app.services import warmup
from app.services.brand_terms import normalize_transcript, spoken_text
from app.voice import stt_service
from app.voice.tts_service import TTSService
from tests.fakes import FakeClient, listing, text_turn, tool_turn

LOCALES = load_config("locales")["locales"]


async def collect(gen):
    return [e async for e in gen]


class TestNames(unittest.TestCase):

    def test_xoto_heard_in_any_accent_is_written_xoto(self):
        for heard in ("Tell me about Zoto", "what is x oto", "what does exoto do", "Ex-oto fees", "زوتو کیا ہے", "एक्सोटो क्या है"):
            self.assertIn("XOTO", normalize_transcript(heard), heard)

    def test_xo_alone_stays_xo_and_ordinary_words_are_untouched(self):
        self.assertEqual(normalize_transcript("Hey X-O, what is XOTO?"), "Hey XO, what is XOTO?")
        for text in ("I like this photo", "Soto is my name", "so what", "an exotic villa"):
            self.assertEqual(normalize_transcript(text), text)

    def test_voice_says_x_oto_and_ex_o_in_each_language(self):
        self.assertEqual(spoken_text("Welcome to XOTO. I'm XO.", "en"), "Welcome to Ex-oto. I'm Ex-O.")
        self.assertIn("ایکس-اوٹو", spoken_text("XOTO میں خوش آمدید", "ur"))
        self.assertIn("एक्स-ओटो", spoken_text("XOTO के बारे में", "hi"))
        self.assertNotIn("XOTO", spoken_text("XOTO", "ar"))

    def test_tts_request_uses_the_spoken_form_and_display_text_is_unchanged(self):
        with mock.patch.object(settings, "ELEVENLABS_API_KEY", "k"):
            spoken, payload = TTSService._request("XOTO helps with mortgages.", "en")
        self.assertEqual(payload["text"], "Ex-oto helps with mortgages.")


class TestLanguageSwitchInConversation(unittest.IsolatedAsyncioTestCase):
    """The visitor decides the language: XO offers, and switches only after a clear request or a yes to its offer."""

    async def asyncSetUp(self):
        SessionStore.clear_all()
        patcher = mock.patch.object(GridOffPlanGateway, "all", new=mock.AsyncMock(return_value=[listing()]))
        patcher.start()
        self.addCleanup(patcher.stop)

    def use(self, client):
        patcher = mock.patch.object(LLMService, "client", return_value=client)
        patcher.start()
        self.addCleanup(patcher.stop)

    def switch_check(self, verdict):
        return mock.patch("app.orchestrator.tools._confirm_language_switch", new=mock.AsyncMock(return_value=verdict))

    async def test_a_hindi_word_never_switches_without_the_visitor_agreeing(self):
        # The model tries to switch on "Yeah Okay अच्छा"; the intent check says no, so the reply stays in English.
        client = FakeClient([tool_turn([{"name": "set_language", "args": {"language": "hi"}}]),
                             text_turn("I'm here. Would you like to continue in Hindi?")])
        self.use(client)
        with self.switch_check(False):
            events = await collect(O.stream_turn("Yeah Okay अच्छा", channel="voice"))
        self.assertEqual(events[-1]["language"], "en")
        self.assertNotIn("language", [e["type"] for e in events])
        tool_result = json.loads(next(m["content"] for m in client.chat.completions.calls[1]["messages"] if m["role"] == "tool"))
        self.assertEqual(tool_result["status"], "not_switched")
        self.assertIn("ask whether they would like to continue in Hindi", tool_result["instruction"])

    async def test_yes_after_the_offer_switches_and_locks_the_language(self):
        client = FakeClient([tool_turn([{"name": "set_language", "args": {"language": "hi"}}]), text_turn("ज़रूर, अब हिंदी में बात करते हैं।")])
        self.use(client)
        with self.switch_check(True):
            events = await collect(O.stream_turn("yes please"))
        types = [e["type"] for e in events]
        self.assertLess(types.index("language"), types.index("token"))   # the voice uses Hindi for the answer
        self.assertEqual(events[-1]["language"], "hi")
        self.assertTrue(SessionStore.get(events[0]["session_id"]).language_locked)
        tool_result = json.loads(next(m["content"] for m in client.chat.completions.calls[1]["messages"] if m["role"] == "tool"))
        self.assertIn("Devanagari", tool_result["instruction"])          # the model is told the script to use

    async def test_intent_check_reads_xos_previous_message(self):
        self.use(FakeClient([text_turn("Yes, I speak Punjabi. Would you like to continue in Punjabi?")]))
        sid = (await collect(O.stream_turn("Can you speak Punjabi?")))[-1]["session_id"]
        client = FakeClient([tool_turn([{"name": "set_language", "args": {"language": "pa"}}]), text_turn("ਜ਼ਰੂਰ।")])
        self.use(client)
        await collect(O.stream_turn("haan ji", session_id=sid))
        check = next(c for c in client.chat.completions.calls if not c.get("stream"))
        sent = check["messages"][1]["content"]
        self.assertIn("Would you like to continue in Punjabi?", sent)
        self.assertIn("haan ji", sent)

    async def test_wrong_script_after_a_switch_is_rewritten_before_it_is_shown(self):
        client = FakeClient([tool_turn([{"name": "set_language", "args": {"language": "pa"}}]),
                             text_turn("ہاں جی، میں پنجابی وچ گل کراں گا۔"), text_turn("ਹਾਂ ਜੀ, ਮੈਂ ਪੰਜਾਬੀ ਵਿੱਚ ਗੱਲ ਕਰਾਂਗਾ।")])
        self.use(client)
        with self.switch_check(True):
            events = await collect(O.stream_turn("Let's talk in Punjabi"))
        tokens = [e["text"] for e in events if e["type"] == "token"]
        self.assertEqual(tokens, ["ਹਾਂ ਜੀ, ਮੈਂ ਪੰਜਾਬੀ ਵਿੱਚ ਗੱਲ ਕਰਾਂਗਾ।"])   # the Urdu-script draft is never shown
        self.assertIn("not written in Punjabi script", client.chat.completions.calls[-1]["messages"][-1]["content"])

    async def test_switched_language_holds_against_related_scripts(self):
        self.use(FakeClient([tool_turn([{"name": "set_language", "args": {"language": "pa"}}]), text_turn("ਜ਼ਰੂਰ।")]))
        with self.switch_check(True):
            sid = (await collect(O.stream_turn("Let's talk in Punjabi")))[-1]["session_id"]
        self.use(FakeClient([tool_turn([{"name": "set_language", "args": {"language": "hi"}}]), text_turn("ਠੀਕ ਹੈ।")]))
        with self.switch_check(False):   # Punjabi heard in Devanagari is not a request for Hindi
            final = (await collect(O.stream_turn("मैनूं दुबई मरीना विच घर चाहिदा", session_id=sid, channel="voice")))[-1]
        self.assertEqual(final["language"], "pa")

    async def test_intent_check_failure_never_switches(self):
        from app.orchestrator import tools as T
        session = SessionStore.get_or_create(None)
        session.current_user_text = "speak Hindi"
        with mock.patch.object(LLMService, "client", side_effect=RuntimeError("offline")):
            self.assertFalse(await T._confirm_language_switch(session, "hi"))

    def test_arabic_punctuation_is_tidied_in_other_scripts(self):
        from app.services.language_script import tidy_punctuation
        self.assertEqual(tidy_punctuation("ਬਿਲਕੁਲ، ਮਦਦ ਕਰਾਂ؟ ਠੀਕ۔", "pa"), "ਬਿਲਕੁਲ, ਮਦਦ ਕਰਾਂ? ਠੀਕ।")
        self.assertEqual(tidy_punctuation("بالتأكيد، كيف؟", "ar"), "بالتأكيد، كيف؟")

    def test_script_check(self):
        from app.services.language_script import script_matches
        self.assertTrue(script_matches("ਜ਼ਰੂਰ, ਹੁਣ ਮੈਂ ਪੰਜਾਬੀ ਵਿੱਚ ਗੱਲ ਕਰਾਂਗਾ। XOTO", "pa"))
        self.assertFalse(script_matches("ہاں جی، میں پنجابی وچ گل کراں گا۔", "pa"))
        self.assertFalse(script_matches("جی ہاں، میں آپ کی مدد کروں؟", "ar"))

    async def test_answer_with_a_refused_switch_is_not_repeated(self):
        # The model answers and also asks to switch; the switch is refused and its answer stands (no second pass).
        answer = "I'm here. Would you like to continue in Hindi?"
        chunks = text_turn(answer)[:-1] + tool_turn([{"name": "set_language", "args": {"language": "hi"}}])
        client = FakeClient([chunks, text_turn("Yes, I speak Hindi. Would you like to continue in Hindi?")])
        self.use(client)
        with self.switch_check(False):
            events = await collect(O.stream_turn("Yeah Okay अच्छा"))
        self.assertEqual(events[-1]["text"], answer)
        self.assertEqual(len([c for c in client.chat.completions.calls if c.get("stream")]), 1)

    async def test_reply_in_another_language_without_a_switch_is_rewritten(self):
        # English conversation, the visitor writes in Arabic, the model answers in Arabic: the visitor never sees that.
        client = FakeClient([text_turn("بالتأكيد، وجدت شقة في دبي مارينا."),
                             text_turn("I found a flat in Dubai Marina. Would you like to continue in Arabic?")])
        self.use(client)
        events = await collect(O.stream_turn("أريد شقة في دبي مارينا"))
        tokens = [e["text"] for e in events if e["type"] == "token"]
        self.assertEqual(tokens, ["I found a flat in Dubai Marina. Would you like to continue in Arabic?"])
        self.assertEqual(events[-1]["language"], "en")

    async def test_ordinary_turns_still_stream_word_by_word(self):
        self.use(FakeClient([text_turn("Here are three homes in JVC for you.")]))
        tokens = [e for e in await collect(O.stream_turn("show me homes in JVC")) if e["type"] == "token"]
        self.assertGreater(len(tokens), 3)

    def test_instructions_offer_in_the_current_language(self):
        prompt = LLMService.system_prompt("en", False)
        self.assertIn("in the session language: the offer to continue in that language", prompt)
        self.assertIn("Never for a few words", json.dumps(__import__("app.orchestrator.tools", fromlist=["x"]).tool_schemas()))

    async def test_typed_xoto_misspelling_reaches_the_model_corrected(self):
        client = FakeClient([text_turn("XOTO is a UAE property platform.")])
        self.use(client)
        await collect(O.stream_turn("what is zoto?"))
        self.assertEqual(client.chat.completions.calls[0]["messages"][-1]["content"], "what is XOTO?")

    def test_instructions_explain_xo_and_xoto(self):
        prompt = LLMService.system_prompt("en", False)
        self.assertIn('"XO" on its own always means you', prompt)
        self.assertIn("Small talk is welcome", prompt)


class TestSpeechToTextSettings(unittest.TestCase):

    def test_english_is_not_forced_other_languages_are_hinted(self):
        en = stt_service._session_update("en")["session"]["audio"]["input"]
        ur = stt_service._session_update("ur")["session"]["audio"]["input"]
        self.assertNotIn("languages", en["transcription"])   # a first turn in Urdu or Arabic is still heard
        self.assertEqual(ur["transcription"]["languages"], ["ur"])
        self.assertIn("XO", en["transcription"]["keywords"])
        self.assertIn("XOTO", en["transcription"]["prompt"])

    def test_noise_reduction_can_be_switched_off(self):
        on = stt_service._session_update("en")["session"]["audio"]["input"]
        off = stt_service._session_update("en", noise_reduction=False)["session"]["audio"]["input"]
        self.assertEqual(on["noise_reduction"], {"type": settings.STT_NOISE_REDUCTION})
        self.assertNotIn("noise_reduction", off)

    def test_end_of_speech_wait_is_one_second(self):
        self.assertEqual(settings.VOICE_SILENCE_SUBMIT_MS, 1000)
        self.assertEqual(TestClient(app).get("/api/config").json()["voice"]["silence_submit_ms"], 1000)


class TestWarmUp(unittest.IsolatedAsyncioTestCase):

    async def test_warm_up_runs_once_a_minute_and_survives_provider_errors(self):
        warmup._last = float("-inf")
        self.addCleanup(setattr, warmup, "_last", 0.0)
        calls = []

        async def ok():
            calls.append("openai")

        async def down():
            raise RuntimeError("offline")

        with mock.patch.object(warmup, "_openai", ok), mock.patch.object(warmup, "_elevenlabs", down):
            self.assertTrue(await warmup.warm())
            self.assertFalse(await warmup.warm())
        self.assertEqual(calls, ["openai"])

    def test_warm_endpoint_answers_at_once(self):
        with mock.patch.object(warmup, "warm_in_background") as started:
            res = TestClient(app).post("/api/warm")
        self.assertEqual(res.status_code, 204)
        started.assert_called_once()


if __name__ == "__main__":
    unittest.main()
