"""Orchestrator (PRD §6, FR-1–FR-6): streaming, tool loop, memory, language, failure handling — with a fake LLM."""
import json
import unittest
from unittest import mock

from app.gateways.grid_gateway import GridOffPlanGateway
from app.llm.client import LLMService
from app.orchestrator.orchestrator import ConversationOrchestrator as O, RepeatGuard, dedupe
from app.orchestrator.session_store import SessionStore
from tests.fakes import FakeClient, listing, text_turn, tool_turn


async def collect(gen):
    return [e async for e in gen]


class TestOrchestrator(unittest.IsolatedAsyncioTestCase):

    def use(self, client):
        patcher = mock.patch.object(LLMService, "client", return_value=client)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def asyncSetUp(self):
        SessionStore.clear_all()
        patcher = mock.patch.object(GridOffPlanGateway, "all", new=mock.AsyncMock(return_value=[listing()]))
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_streams_tokens_then_final(self):
        self.use(FakeClient([text_turn("Hello, how can I help with UAE property?")]))
        events = await collect(O.stream_turn("hi"))
        types = [e["type"] for e in events]
        self.assertEqual(types[0], "session")
        self.assertIn("token", types)
        self.assertEqual(types[-1], "final")
        self.assertEqual(events[-1]["text"], "Hello, how can I help with UAE property?")

    async def test_tool_loop_returns_cards_and_remembers_results(self):
        client = FakeClient([tool_turn([{"name": "search_properties", "args": {"location": "JVC"}}]), text_turn("1. Test Residence in JVC.")])
        self.use(client)
        events = await collect(O.stream_turn("show me JVC"))
        final = events[-1]
        self.assertIn({"type": "status", "tool": "search_properties"}, events)
        self.assertEqual(final["property_results"][0]["ref"], 1)
        # The tool result reached the model on the second call
        second_messages = client.chat.completions.calls[1]["messages"]
        self.assertEqual(second_messages[-1]["role"], "tool")
        self.assertIn("Test Residence", second_messages[-1]["content"])
        # …and is kept in session memory for follow-ups ("tell me about #1")
        session = SessionStore.get(final["session_id"])
        self.assertTrue(any(m.get("role") == "tool" for m in session.history))
        self.assertEqual(session.displayed_listings[0]["listing"]["title"], "Test Residence")

    async def test_follow_up_uses_listing_reference(self):
        self.use(FakeClient([tool_turn([{"name": "search_properties", "args": {"location": "JVC"}}]), text_turn("Here."),
                             tool_turn([{"name": "calc_emi", "args": {"property_price": 700000}}]), text_turn("About AED 2,894 a month.")]))
        first = (await collect(O.stream_turn("show me JVC")))[-1]
        second = (await collect(O.stream_turn("monthly payment on #1?", session_id=first["session_id"])))[-1]
        self.assertEqual(second["mortgage_result"]["calculation_type"], "emi")

    async def test_tool_errors_become_explanations_not_crashes(self):
        client = FakeClient([tool_turn([{"name": "calc_emi", "args": {"loan_amount": 1000000, "tenure_years": 40}}]), text_turn("Tenure can be at most 25 years.")])
        self.use(client)
        final = (await collect(O.stream_turn("EMI on 1M over 40 years")))[-1]
        self.assertEqual(final["type"], "final")
        tool_msg = client.chat.completions.calls[1]["messages"][-1]
        self.assertIn("invalid_input", tool_msg["content"])

    async def test_provider_failure_gives_localized_message(self):
        self.use(FakeClient([], fail=True))
        events = await collect(O.stream_turn("مرحبا", selected_language="ar"))
        self.assertEqual(events[-1]["type"], "error")
        self.assertIn("عذراً", events[-1]["message"])
        self.assertNotIn("provider down", events[-1]["message"])

    async def test_manual_language_selection_is_applied(self):
        client = FakeClient([text_turn("أهلاً")])
        self.use(client)
        final = (await collect(O.stream_turn("hello", selected_language="ar")))[-1]
        self.assertEqual(final["language"], "ar")
        self.assertIn("Arabic", client.chat.completions.calls[0]["messages"][0]["content"])

    async def test_language_switch_needs_real_evidence(self):
        client = FakeClient([tool_turn([{"name": "set_language", "args": {"language": "fr"}}]), text_turn("Fees are 4% DLD.")])
        self.use(client)
        final = (await collect(O.stream_turn("What are the fees for les apartments?")))[-1]
        self.assertEqual(final["language"], "en")       # classifier says the message is English

    async def test_confirmed_switch_emits_language_event_before_reply(self):
        client = FakeClient([tool_turn([{"name": "set_language", "args": {"language": "fr"}}]), text_turn("Bien sûr.")])
        self.use(client)
        with mock.patch("app.orchestrator.tools._confirm_language_switch", new=mock.AsyncMock(return_value=True)):
            events = await collect(O.stream_turn("Parle français, s'il te plaît"))
        types = [e["type"] for e in events]
        self.assertIn("language", types)                 # voice clients switch TTS language mid-reply
        self.assertLess(types.index("language"), types.index("token"))
        self.assertEqual(events[types.index("language")]["language"], "fr")

    async def test_payment_details_never_reach_the_model(self):
        client = FakeClient([text_turn("XO cannot take payments.")])
        self.use(client)
        await collect(O.stream_turn("pay with 4111 1111 1111 1111"))
        sent = json.dumps(client.chat.completions.calls[0]["messages"])
        self.assertNotIn("4111 1111", sent)

    async def test_calculation_runs_before_search_and_sets_budget(self):
        client = FakeClient([tool_turn([{"name": "search_properties", "args": {"location": "JVC"}},
                                        {"name": "calc_affordability", "args": {"monthly_income": 30000, "residency": "uae_resident", "age": 32, "employment_type": "salaried"}}]), text_turn("Done.")])
        self.use(client)
        await collect(O.stream_turn("what can I afford and show me JVC"))
        tool_msgs = [m for m in client.chat.completions.calls[1]["messages"] if m["role"] == "tool"]
        search_result = next(json.loads(m["content"]) for m in tool_msgs if "applied_filters" in m["content"])
        self.assertIn("budget_max", search_result["applied_filters"])

    async def test_placeholder_income_is_rejected(self):
        client = FakeClient([tool_turn([{"name": "calc_affordability", "args": {"monthly_income": 1, "residency": "uae_resident", "age": 32, "employment_type": "salaried"}}]), text_turn("What is your monthly income?")])
        self.use(client)
        final = (await collect(O.stream_turn("what can I afford?")))[-1]
        self.assertNotIn("mortgage_result", final)

    async def test_handoff_requires_consent(self):
        client = FakeClient([tool_turn([{"name": "request_human_handoff", "args": {"full_name": "A B", "phone": "+971501234567",
                                                                                  "preferred_language": "English", "consent_confirmed": False}}]),
                             text_turn("May I have your consent first?")])
        self.use(client)
        final = (await collect(O.stream_turn("call me")))[-1]
        self.assertNotIn("handoff_draft", final)

    async def test_handoff_shows_review_card_without_saving(self):
        client = FakeClient([tool_turn([{"name": "request_human_handoff", "args": {"full_name": "A B", "phone": "0501234567",
                                                                                  "consent_confirmed": True}}]),
                             text_turn("Please check the details and tap Confirm.")])
        self.use(client)
        final = (await collect(O.stream_turn("Aisha, 0501234567")))[-1]
        self.assertEqual(final["handoff_draft"]["phone"], "+971 50 123 4567")
        self.assertEqual(final["handoff_draft"]["status"], "review")
        self.assertNotIn("handoff_data", final)


class TestRepeatGuard(unittest.TestCase):

    def run_guard(self, text):
        g = RepeatGuard()
        streamed = "".join(g.feed(tok) for tok in [text[i:i + 3] for i in range(0, len(text), 3)])
        return streamed, g.final()

    def test_exact_duplicate_suppressed(self):
        a = "Would you like a mortgage advisor to contact you? You can stay anonymous."
        streamed, final = self.run_guard(a + "\n" + a)
        self.assertEqual(final, a)
        self.assertNotIn(a + "\n" + a[:30], streamed)

    def test_near_duplicate_suppressed(self):
        final = dedupe("I can arrange a mortgage advisor to contact you. Do you agree?\nI can arrange for a mortgage advisor to contact you. Do you agree?")
        self.assertEqual(final.count("Do you agree?"), 1)

    def test_normal_lists_untouched(self):
        text = "Here are two options:\n\n1. Marina Heights — AED 1,900,000\n2. JVC Studio Tower — from AED 700,000"
        streamed, final = self.run_guard(text)
        self.assertEqual(final, text)
        self.assertEqual(streamed, text)


if __name__ == "__main__":
    unittest.main()
