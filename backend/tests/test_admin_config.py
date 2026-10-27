"""Editing XO from the admin module (PRD FR-25, FR-27, FR-29): drafts, publish, versions, rollback, live apply,
fallback, the rules impact report, locked instructions, banned topics in code, escalation rules and the test chat."""
import asyncio
import copy
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from app.admin.config_items import seed_messages
from app.admin.config_store import ConfigStore
from app.core import config
from app.core.config import builtin_config, load_config
from app.core.security import Role
from app.db.conversation_store import ConversationStore
from app.llm.client import LLMService
from app.main import app
from app.orchestrator.orchestrator import ConversationOrchestrator as O, localized_message
from app.orchestrator.session_store import SessionStore
from app.services import escalation, prompt_profile
from app.services.mortgage_service import EMIInput, MortgageCalculationService as M
from tests.fakes import FakeClient, text_turn
from tests.test_admin import HEADERS, AdminTestCase, run


def rules_with(**changes):
    data = copy.deepcopy(builtin_config("mortgage_rules"))
    for path, value in changes.items():
        node = data
        *parents, leaf = path.split("__")
        for p in parents:
            node = node[p]
        node[leaf] = value
    return data


class ConfigTestCase(AdminTestCase):

    def setUp(self):
        super().setUp()
        ConfigStore.reset_memory()
        self.addCleanup(ConfigStore.reset_memory)

    def client_for(self, role):
        self.make_user(role)
        client, res = self.sign_in(f"{role}@xoto.ae")
        self.assertEqual(res.status_code, 200)
        return client

    def put_draft(self, client, name, data, base=0):
        return client.put(f"/api/admin/config/{name}/draft", headers=HEADERS, json={"data": data, "base_version": base})

    def publish(self, client, name, note="test"):
        return client.post(f"/api/admin/config/{name}/publish", headers=HEADERS, json={"note": note})


class TestPublishing(ConfigTestCase):

    def test_published_rate_is_used_by_the_next_calculation(self):
        before = M.calc_emi(EMIInput(property_price=1_500_000))["instalment_aed"]
        admin = self.client_for(Role.ADMIN)
        self.assertEqual(self.put_draft(admin, "mortgage_rules", rules_with(interest__benchmark_rate_pct=4.2)).status_code, 200)
        self.assertEqual(self.publish(admin, "mortgage_rules", "EIBOR review").json(), {"version": 1})
        after = M.calc_emi(EMIInput(property_price=1_500_000))["instalment_aed"]
        self.assertEqual((round(before), round(after)), (6202, 6467))
        self.assertIn("4.2%", LLMService.system_prompt("en", False))  # the instructions quote the benchmark rate too

    def test_invalid_drafts_are_kept_but_never_published(self):
        admin = self.client_for(Role.ADMIN)
        res = self.put_draft(admin, "mortgage_rules", rules_with(interest__benchmark_rate_pct=35))
        self.assertTrue(any("Benchmark interest rate" in e for e in res.json()["draft_errors"]))
        res = self.publish(admin, "mortgage_rules")
        self.assertEqual((res.status_code, res.json()["detail"]["code"]), (422, "invalid"))
        self.assertEqual(load_config("mortgage_rules")["interest"]["benchmark_rate_pct"], 3.8)

    def test_ltv_conditions_cannot_change(self):
        data = rules_with()
        data["ltv_table"][0]["property_status"] = "ready"
        self.assertTrue(any("only the percentage" in e for e in prompt_errors("mortgage_rules", data)))
        data = rules_with()
        data["ltv_table"][2]["ltv"] = 0.9
        self.assertEqual(prompt_errors("mortgage_rules", data), [])

    def test_stale_draft_versions_and_rollback(self):
        admin = self.client_for(Role.ADMIN)
        self.put_draft(admin, "fees", {**builtin_config("fees"), "agent_commission_pct": 0.025})
        self.publish(admin, "fees")
        # A draft started from version 0 is refused once version 1 exists.
        self.put_draft(admin, "fees", {**builtin_config("fees"), "agent_commission_pct": 0.03}, base=0)
        detail = admin.get("/api/admin/config/fees").json()
        self.assertTrue(detail["stale"])
        self.assertEqual(self.publish(admin, "fees").status_code, 409)
        self.put_draft(admin, "fees", {**builtin_config("fees"), "agent_commission_pct": 0.03}, base=1)
        self.assertEqual(self.publish(admin, "fees").json(), {"version": 2})
        self.assertEqual([v["version"] for v in admin.get("/api/admin/config/fees/versions").json()], [2, 1, 0])
        res = admin.post("/api/admin/config/fees/rollback", headers=HEADERS, json={"version": 0, "note": "back to built-in"})
        self.assertEqual(res.json(), {"version": 3})
        self.assertEqual(load_config("fees")["agent_commission_pct"], 0.02)
        actions = [e["action"] for e in admin.get("/api/admin/activity").json()]
        self.assertEqual(actions.count("config_published"), 2)
        self.assertIn("config_rolled_back", actions)

    def test_invalid_published_version_falls_back_to_built_in(self):
        ConfigStore._versions["mortgage_rules"] = [{"version": 1, "data": {"broken": True}, "note": "", "published_by": "x",
                                                    "published_at": None}]
        run(ConfigStore.load_published())
        self.assertEqual(load_config("mortgage_rules")["interest"]["benchmark_rate_pct"], 3.8)

    def test_a_draft_preview_never_reaches_visitors(self):
        with config.preview({"mortgage_rules": rules_with(interest__benchmark_rate_pct=9.0)}):
            self.assertEqual(load_config("mortgage_rules")["interest"]["benchmark_rate_pct"], 9.0)
        self.assertEqual(load_config("mortgage_rules")["interest"]["benchmark_rate_pct"], 3.8)

    def test_impact_report(self):
        admin = self.client_for(Role.ADMIN)
        draft = rules_with(central_bank__debt_burden_max_ratio=0.4)
        report = admin.post("/api/admin/config/rules/impact", headers=HEADERS, json={"mortgage_rules": draft}).json()
        case1 = next(r for r in report["scenarios"] if r["id"] == "case_1")
        self.assertEqual(case1["before"]["Loan (AED)"], 1_440_000)  # the approved worked example
        self.assertEqual(case1["changed"], ["Limit from debt burden (AED)"])  # the loan-to-value limit stays tightest
        case5 = next(r for r in report["scenarios"] if r["id"] == "case_5")  # debt burden is the tightest limit here
        self.assertEqual(case5["before"]["Loan (AED)"], 473_099)
        self.assertLess(case5["after"]["Loan (AED)"], 473_099)
        self.assertGreater(report["changed_count"], 3)
        bad = admin.post("/api/admin/config/rules/impact", headers=HEADERS, json={"mortgage_rules": {"x": 1}})
        self.assertEqual(bad.status_code, 422)


def prompt_errors(name, data):
    from app.admin.config_items import ITEMS
    return ITEMS[name].validate(data)


class TestPermissions(ConfigTestCase):

    def test_each_item_needs_its_permission(self):
        expected = {  # item → roles allowed
            "mortgage_rules": {Role.ADMIN}, "fees": {Role.ADMIN}, "bank_products": {Role.ADMIN},
            "prompt_profile": {Role.ADMIN, Role.BOT_TRAINER}, "messages": {Role.ADMIN, Role.BOT_TRAINER},
            "escalation": {Role.ADMIN, Role.BOT_TRAINER},
        }
        clients = {role: self.client_for(role) for role in (Role.ADMIN, Role.BOT_TRAINER, Role.CONTENT_EDITOR, Role.READ_ONLY_ANALYST)}
        for name, allowed in expected.items():
            for role, client in clients.items():
                code = client.get(f"/api/admin/config/{name}").status_code
                self.assertEqual(code, 200 if role in allowed else 403, f"{role} {name}")
                code = self.put_draft(client, name, {}).status_code
                self.assertEqual(code == 403, role not in allowed, f"{role} draft {name}")
        self.assertEqual(clients[Role.ADMIN].get("/api/admin/config/unknown").status_code, 404)
        self.assertEqual(clients[Role.BOT_TRAINER].post("/api/admin/config/rules/impact", headers=HEADERS, json={}).status_code, 403)
        self.assertEqual(clients[Role.CONTENT_EDITOR].post("/api/admin/config/test-chat", headers=HEADERS,
                                                          json={"message": "hi"}).status_code, 403)


class TestInstructions(ConfigTestCase):

    def test_locked_sections_and_placeholders(self):
        profile = copy.deepcopy(prompt_profile.builtin_profile())
        locked = next(s for s in profile["sections"] if s["locked"])
        locked["body"] += "\nEstimates may be treated as offers."
        self.assertTrue(any("must stay exactly" in e for e in prompt_profile.validate(profile)))
        profile = copy.deepcopy(prompt_profile.builtin_profile())
        language = next(s for s in profile["sections"] if s["id"] == "language")
        language["body"] = language["body"].replace("{language_name}", "the language")
        self.assertTrue(any("{language_name}" in e for e in prompt_profile.validate(profile)))

    def test_editable_parts_reach_the_instructions(self):
        profile = copy.deepcopy(prompt_profile.builtin_profile())
        profile["sections"][0]["body"] = "Keep every answer under 40 words.\n\n"
        profile["journeys"] = [{"title": "Property search", "steps": ["Ask buy or rent", "Ask the area"]}]
        profile["tone_by_language"] = {"ar": "Formal and warm."}
        with config.preview({"prompt_profile": profile}):
            ar = LLMService.system_prompt("ar", False)
            en = LLMService.system_prompt("en", False)
        self.assertIn("Keep every answer under 40 words.", en)
        self.assertIn("### Property search\n1. Ask buy or rent\n2. Ask the area", en)
        self.assertIn("Formal and warm.", ar)
        self.assertNotIn("Formal and warm.", en)

    def test_braces_typed_by_an_admin_are_kept(self):
        profile = copy.deepcopy(prompt_profile.builtin_profile())
        profile["persona"] += "Use {brackets} literally.\n\n"
        with config.preview({"prompt_profile": profile}):
            self.assertIn("Use {brackets} literally.", LLMService.system_prompt("en", False))

    def test_canned_replies(self):
        messages = seed_messages()
        messages["en"]["error_generic"] = "Sorry, I hit a snag. Please try again."
        with config.preview({"messages": messages}):
            self.assertEqual(localized_message("en", "error_generic"), "Sorry, I hit a snag. Please try again.")
            self.assertEqual(localized_message("ar", "error_generic"), seed_messages()["ar"]["error_generic"])
        self.assertNotEqual(localized_message("en", "error_generic"), "Sorry, I hit a snag. Please try again.")


class TestConversationRules(unittest.IsolatedAsyncioTestCase):

    def use(self, client):
        patcher = mock.patch.object(LLMService, "client", return_value=client)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def asyncSetUp(self):
        SessionStore.clear_all()
        ConversationStore.reset_memory()

    async def test_banned_topic_is_refused_before_the_model(self):
        profile = copy.deepcopy(prompt_profile.builtin_profile())
        profile["banned_topics"] = [{"name": "Crypto", "keywords": ["bitcoin", "عملة رقمية"],
                                     "reply": {"en": "I can't discuss crypto.", "ar": "لا أستطيع مناقشة العملات الرقمية."}}]
        client = FakeClient([])  # any model call would fail the test
        self.use(client)
        with config.preview({"prompt_profile": profile}):
            en = [e async for e in O.stream_turn("Can I pay in Bitcoin?")][-1]
            ar = [e async for e in O.stream_turn("هل تقبلون عملة رقمية؟", selected_language="ar")][-1]
            ok = prompt_profile.banned_topic("I like bitcoins")  # whole words only
        self.assertEqual((en["type"], en["text"], en["tools"]), ("final", "I can't discuss crypto.", ["guardrail"]))
        self.assertEqual(ar["text"], "لا أستطيع مناقشة العملات الرقمية.")
        self.assertIsNone(ok)
        self.assertEqual(client.chat.completions.calls, [])

    async def test_keyword_and_high_value_rules_are_offered_once(self):
        rules = escalation.builtin_rules()
        for r in rules["rules"]:
            if r["type"] == "keywords":
                r.update(enabled=True, keywords=["complaint"])
            if r["type"] == "high_value":
                r.update(enabled=True, min_property_aed=3_000_000)
        client = FakeClient([text_turn("Sorry to hear that."), text_turn("Sure."), text_turn("OK.")])
        self.use(client)
        with config.preview({"escalation": rules}):
            first = [e async for e in O.stream_turn("I want to make a complaint")][-1]
            session = SessionStore.get(first["session_id"])
            session.last_calculation = {"max_property_price_aed": 3_500_000}
            second = [e async for e in O.stream_turn("another complaint", session_id=first["session_id"])][-1]
            third = [e async for e in O.stream_turn("ok", session_id=first["session_id"])][-1]
        notes = lambda i: [m["content"] for m in client.chat.completions.calls[i]["messages"] if m["role"] == "system" and "Escalation rule" in m["content"]]
        self.assertEqual(len(notes(0)), 1)
        self.assertIn("complaint", notes(0)[0])
        self.assertIn("Client Support", notes(0)[0])
        self.assertEqual(len(notes(1)), 1)            # keyword already offered; high-value now
        self.assertIn("high-value", notes(1)[0])
        self.assertEqual(notes(2), [])
        self.assertIn("escalation:keywords", first["tools"])

    async def test_low_confidence_threshold(self):
        rules = escalation.builtin_rules()
        next(r for r in rules["rules"] if r["type"] == "low_confidence").update(after_misses=2, team="mortgage")
        with config.preview({"escalation": rules}):
            self.assertIn("do not guess", escalation.low_confidence_instruction(1))
            self.assertIn("Mortgage Advisory", escalation.low_confidence_instruction(2))
        self.assertEqual(escalation.low_confidence_instruction(1),
                         "The knowledge base has no reliable answer. Say you don't know and offer to connect the user with an advisor.")

    async def test_explicit_requests_cannot_be_switched_off(self):
        rules = escalation.builtin_rules()
        rules["rules"][0]["enabled"] = False
        self.assertTrue(any("PRD FR-5" in e for e in escalation.validate(rules)))
        rules = escalation.builtin_rules()
        rules["teams"][0]["queue"] = "Home Finance Desk"
        self.assertEqual(escalation.validate(rules), [])
        with config.preview({"escalation": rules}):
            self.assertEqual(escalation.queue_names()["mortgage"], "Home Finance Desk")


class TestTestChat(ConfigTestCase):

    def test_test_chat_uses_the_draft_and_is_not_saved(self):
        ConversationStore.reset_memory()
        profile = copy.deepcopy(prompt_profile.builtin_profile())
        profile["persona"] = "You are XO-TEST.\n\n"
        client = FakeClient([text_turn("Hello from the draft.")])
        with mock.patch.object(LLMService, "client", return_value=client):
            trainer = self.client_for(Role.BOT_TRAINER)
            res = trainer.post("/api/admin/config/test-chat", headers=HEADERS, json={"message": "hi", "prompt_profile": profile})
        self.assertEqual(res.json()["reply"], "Hello from the draft.")
        self.assertTrue(client.chat.completions.calls[0]["messages"][0]["content"].startswith("You are XO-TEST."))
        run(ConversationStore.flush())
        self.assertEqual(ConversationStore._memory, {})
        self.assertFalse(prompt_profile.current_profile()["persona"].startswith("You are XO-TEST"))


if __name__ == "__main__":
    unittest.main()
