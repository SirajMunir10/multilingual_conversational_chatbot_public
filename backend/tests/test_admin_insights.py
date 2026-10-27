"""Admin insights (PRD FR-26, FR-31, §7): visitor thumbs, analytics figures, AI budget, conversation review with
personal data masked by role, the review queue and knowledge-base drafts."""
import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from fastapi.testclient import TestClient

from app.admin.analytics import build_report, report_range
from app.admin.privacy import mask_personal_data
from app.admin.reviews import ReviewStore
from app.admin.settings_store import SettingsStore
from app.core.security import Role
from app.db.conversation_store import ConversationStore
from app.main import app
from app.orchestrator.session_store import SessionStore
from tests.test_admin import HEADERS, AdminTestCase, run

PHONE_TEXT = "Please call me on +971 50 123 4567 about a 2 bedroom in JVC"


async def seed_conversation(text=PHONE_TEXT, reply="Sure, here are options.", tools=("search_properties",), turns=1,
                            channel="text", language="en", lead=False, fail_last=False, cost=0.002):
    session = SessionStore.get_or_create(None, language=language)
    turn_ids = []
    for i in range(turns):
        failed = fail_last and i == turns - 1
        turn_id = None if failed else f"{len(SessionStore._sessions):04x}{i:012x}"[-16:]
        if turn_id:
            session.turn_ids.append(turn_id)
            turn_ids.append(turn_id)
        await ConversationStore.record_turn(session.session_id, language=language, channel=channel, user_text=text,
                                            reply=None if failed else reply, tools=list(tools), latency_ms=900,
                                            cost_usd=cost * (i + 1), turn_id=turn_id)
    if lead:
        await ConversationStore.record_handoff(session.session_id, "XO-261021-ABC123")
    return session.session_id, turn_ids


class InsightsTestCase(AdminTestCase):

    def setUp(self):
        super().setUp()
        SessionStore.clear_all()
        ConversationStore.reset_memory()
        ReviewStore.reset_memory()
        SettingsStore.reset_memory()

    def client_for(self, role):
        self.make_user(role)
        client, res = self.sign_in(f"{role}@xoto.ae")
        self.assertEqual(res.status_code, 200)
        return client


class TestVisitorFeedback(InsightsTestCase):

    def test_thumbs_are_saved_changed_and_removed(self):
        sid, (turn,) = run(seed_conversation())
        client = TestClient(app)
        self.assertEqual(client.post("/api/chat/feedback", json={"session_id": sid, "turn_id": turn, "rating": "down"}).status_code, 200)
        self.assertEqual(run(ConversationStore.get(sid))["messages"][1]["rating"], -1)
        client.post("/api/chat/feedback", json={"session_id": sid, "turn_id": turn, "rating": "up"})
        self.assertEqual(run(ConversationStore.get(sid))["messages"][1]["rating"], 1)
        client.post("/api/chat/feedback", json={"session_id": sid, "turn_id": turn, "rating": None})
        self.assertIsNone(run(ConversationStore.get(sid))["messages"][1]["rating"])

    def test_only_real_replies_of_a_live_session_can_be_rated(self):
        sid, (turn,) = run(seed_conversation())
        other, _ = run(seed_conversation())
        client = TestClient(app)
        cases = [{"session_id": sid, "turn_id": "0123456789abcdef", "rating": "up"},      # made-up reply id
                 {"session_id": other, "turn_id": turn, "rating": "up"},                  # another visitor's reply
                 {"session_id": "sess_" + "x" * 24, "turn_id": turn, "rating": "up"}]     # unknown session
        for body in cases:
            self.assertEqual(client.post("/api/chat/feedback", json=body).status_code, 404, body)
        self.assertEqual(client.post("/api/chat/feedback", json={"session_id": sid, "turn_id": turn, "rating": "meh"}).status_code, 422)


class TestAnalyticsFigures(unittest.TestCase):

    def conv(self, **kw):
        base = {"session_id": "s", "started_at": datetime(2026, 10, 20, 9, tzinfo=timezone.utc), "updated_at": None,
                "language": "en", "channels": ["text"], "user_turns": 2, "failed_turns": 0, "tools": [], "handoff_ticket": None,
                "lead_saved": False, "cost_usd": 0.01, "first_question": "Hello", "last_tools": [], "last_role": "assistant",
                "thumbs_up": 0, "thumbs_down": 0, "flagged": 0, "reviewed_bad": 0, "reviewed_good": 0}
        return {**base, **kw}

    def test_report(self):
        start = datetime(2026, 10, 18, 20, tzinfo=timezone.utc)  # 19 Oct 00:00 Dubai
        end = datetime(2026, 10, 21, 8, tzinfo=timezone.utc)
        convs = [
            self.conv(tools=["search_properties"], last_tools=["search_properties"], thumbs_up=2, first_question="2BR in JVC?"),
            self.conv(tools=["calc_emi", "search_properties"], last_tools=["calc_emi"], thumbs_down=1, language="ar",
                      channels=["text", "voice"], first_question="2br in jvc"),
            self.conv(tools=["request_human_handoff"], handoff_ticket="XO-1", lead_saved=True, cost_usd=0.03),
            self.conv(user_turns=1, failed_turns=1, last_role="user", started_at=datetime(2026, 10, 19, 6, tzinfo=timezone.utc)),
        ]
        r = build_report(convs, start=start, end=end, month_cost_usd=8.5, budget={"monthly_usd": 10, "alert_pct": 80},
                         show_personal_data=True, previous=[self.conv(lead_saved=True, handoff_ticket="XO-0")])
        self.assertEqual(r["previous"], {"conversations": 1, "handled_by_xo_pct": 0.0, "lead_conversion_pct": 100.0,
                                         "satisfaction_pct": None, "cost_per_conversation_usd": 0.01})
        oct20 = next(d for d in r["daily"] if d["date"] == "2026-10-20")
        self.assertEqual((oct20["handled_by_xo"], oct20["leads"], oct20["thumbs_up"], oct20["thumbs_down"]), (2, 1, 2, 1))
        t = r["totals"]
        self.assertEqual((t["conversations"], t["user_messages"], t["leads"]), (4, 7, 1))
        self.assertEqual(t["handled_by_xo_pct"], 50.0)    # two of four: no handoff and at least one successful reply
        self.assertEqual(t["lead_conversion_pct"], 25.0)
        self.assertEqual(t["satisfaction_pct"], 66.7)     # 2 up, 1 down
        self.assertEqual((t["cost_usd"], t["cost_per_conversation_usd"]), (0.06, 0.015))
        self.assertEqual([d["date"] for d in r["daily"]], ["2026-10-19", "2026-10-20", "2026-10-21"])
        self.assertEqual([d["conversations"] for d in r["daily"]], [1, 3, 0])
        topics = {x["key"]: x["conversations"] for x in r["topics"]}
        self.assertEqual(topics, {"property": 2, "mortgage": 1, "advisor": 1, "general": 1})
        endings = {x["key"]: x["conversations"] for x in r["endings"]}
        self.assertEqual(endings, {"property": 1, "mortgage": 1, "lead": 1, "error": 1})
        self.assertEqual(r["top_questions"][0], {"question": "2BR in JVC?", "conversations": 2})
        self.assertEqual(r["channels"], {"text": 4, "voice": 1})
        self.assertEqual(r["budget"], {"monthly_usd": 10, "alert_pct": 80, "month_cost_usd": 8.5, "used_pct": 85.0, "alert": True})

    def test_empty_report_has_no_divisions_by_zero(self):
        rng = report_range(7)
        r = build_report([], start=rng["start"], end=rng["end"], month_cost_usd=0, budget={}, show_personal_data=False)
        self.assertEqual(r["totals"]["conversations"], 0)
        self.assertIsNone(r["totals"]["handled_by_xo_pct"])
        self.assertEqual(len(r["daily"]), 7)
        self.assertFalse(r["budget"]["alert"])


class TestAnalyticsAndBudgetEndpoints(InsightsTestCase):

    def test_analytics_from_saved_conversations(self):
        run(seed_conversation(turns=2))
        run(seed_conversation(tools=("calc_emi",), lead=True, channel="voice"))
        report = self.client_for(Role.READ_ONLY_ANALYST).get("/api/admin/analytics?days=7").json()
        self.assertEqual(report["totals"]["conversations"], 2)
        self.assertEqual(report["totals"]["leads"], 1)
        self.assertEqual(report["channels"], {"text": 1, "voice": 1})
        self.assertNotIn("4567", str(report["top_questions"]))  # analysts see phone numbers masked

    def test_only_admins_set_the_budget(self):
        analyst = self.client_for(Role.READ_ONLY_ANALYST)
        self.assertEqual(analyst.put("/api/admin/budget", json={"monthly_usd": 50, "alert_pct": 75}, headers=HEADERS).status_code, 403)
        admin = self.client_for(Role.ADMIN)
        res = admin.put("/api/admin/budget", json={"monthly_usd": 50, "alert_pct": 75}, headers=HEADERS)
        self.assertEqual(res.json(), {"monthly_usd": 50.0, "alert_pct": 75})
        self.assertEqual(analyst.get("/api/admin/budget").json()["monthly_usd"], 50.0)
        self.assertEqual(admin.put("/api/admin/budget", json={"monthly_usd": -1}, headers=HEADERS).status_code, 422)
        entry = next(e for e in admin.get("/api/admin/activity").json() if e["action"] == "budget_updated")
        self.assertEqual(entry["details"]["monthly_usd"], {"from": None, "to": 50.0})


class TestConversationReview(InsightsTestCase):

    def test_list_filters_and_pages(self):
        run(seed_conversation(text="Show me villas", language="en"))
        run(seed_conversation(text="أريد شقة", language="ar", channel="voice", lead=True))
        run(seed_conversation(text="EMI please", tools=("calc_emi",), fail_last=True, turns=2))
        client = self.client_for(Role.READ_ONLY_ANALYST)
        get = lambda qs: client.get(f"/api/admin/conversations?{qs}").json()
        self.assertEqual(get("")["total"], 3)
        self.assertEqual([i["language"] for i in get("language=ar")["items"]], ["ar"])
        self.assertEqual(get("channel=voice")["total"], 1)
        self.assertEqual(get("outcome=lead")["total"], 1)
        self.assertEqual(get("outcome=failed")["items"][0]["first_question"], "EMI please")
        self.assertEqual(get("q=villas")["total"], 1)
        page = get("page_size=5&page=1")
        self.assertEqual((page["page_size"], len(page["items"])), (5, 3))
        self.assertEqual(get("page=2&page_size=5")["items"], [])

    def test_personal_data_is_masked_for_roles_without_lead_access(self):
        sid, _ = run(seed_conversation())
        analyst = self.client_for(Role.READ_ONLY_ANALYST).get(f"/api/admin/conversations/{sid}").json()
        self.assertTrue(analyst["personal_data_masked"])
        self.assertIn("•••567", analyst["messages"][0]["content"])
        self.assertNotIn("123 4567", analyst["messages"][0]["content"])
        admin = self.client_for(Role.ADMIN).get(f"/api/admin/conversations/{sid}").json()
        self.assertIn("+971 50 123 4567", admin["messages"][0]["content"])
        self.assertEqual(self.client_for(Role.BOT_TRAINER).get("/api/admin/conversations/nope").status_code, 404)

    def test_review_queue_flow(self):
        sid, (turn,) = run(seed_conversation())
        TestClient(app).post("/api/chat/feedback", json={"session_id": sid, "turn_id": turn, "rating": "down"})
        trainer = self.client_for(Role.BOT_TRAINER)
        queue = trainer.get("/api/admin/review-queue").json()
        self.assertEqual(len(queue), 1)
        item = queue[0]
        self.assertEqual((item["rating"], item["reply"]), (-1, "Sure, here are options."))
        self.assertIn("•••567", item["question"])  # trainers do not see personal data either

        # Reviewing it (without a flag) takes it out of the queue; flagging puts it back.
        res = trainer.put(f"/api/admin/messages/{item['message_id']}/review", headers=HEADERS,
                          json={"verdict": "bad", "flagged": False, "note": "Missed the budget"})
        self.assertEqual((res.status_code, res.json()["reviewed_by"]), (200, "bot_trainer@xoto.ae"))
        self.assertEqual(trainer.get("/api/admin/review-queue").json(), [])
        trainer.put(f"/api/admin/messages/{item['message_id']}/review", headers=HEADERS, json={"verdict": "bad", "flagged": True})
        self.assertEqual(len(trainer.get("/api/admin/review-queue").json()), 1)

        detail = trainer.get(f"/api/admin/conversations/{sid}").json()
        reply = detail["messages"][1]
        self.assertEqual((reply["rating"], reply["review"]["verdict"], reply["review"]["flagged"]), (-1, "bad", True))
        listed = trainer.get("/api/admin/conversations?review=flagged").json()
        self.assertEqual((listed["total"], listed["items"][0]["thumbs_down"]), (1, 1))

    def test_review_rules(self):
        sid, _ = run(seed_conversation())
        user_message_id = run(ConversationStore.get(sid))["messages"][0]["id"]
        editor = self.client_for(Role.CONTENT_EDITOR)
        self.assertEqual(editor.put(f"/api/admin/messages/{user_message_id + 1}/review", headers=HEADERS, json={"verdict": "good"}).status_code, 403)
        trainer = self.client_for(Role.BOT_TRAINER)
        self.assertEqual(trainer.put(f"/api/admin/messages/{user_message_id}/review", headers=HEADERS, json={"verdict": "good"}).json()["detail"], "not_found")
        self.assertEqual(trainer.put("/api/admin/messages/999/review", headers=HEADERS, json={"verdict": "good"}).status_code, 404)
        self.assertEqual(trainer.put(f"/api/admin/messages/{user_message_id + 1}/review", headers=HEADERS, json={"verdict": "great"}).status_code, 422)

    def test_corrected_answer_becomes_a_kb_draft(self):
        sid, _ = run(seed_conversation())
        reply_id = run(ConversationStore.get(sid))["messages"][1]["id"]
        trainer = self.client_for(Role.BOT_TRAINER)
        body = {"source_message_id": reply_id, "language": "en", "title": "2-bedroom options in JVC",
                "question": "Do you have 2 bedrooms in JVC?", "answer": "Yes. Ask XO with your budget to see current listings."}
        res = trainer.post("/api/admin/kb-drafts", headers=HEADERS, json=body)
        self.assertEqual((res.status_code, res.json()["status"], res.json()["created_by"]), (201, "draft", "bot_trainer@xoto.ae"))
        self.assertEqual(trainer.post("/api/admin/kb-drafts", headers=HEADERS, json={**body, "title": " "}).json()["detail"], "title_required")
        self.assertEqual(trainer.post("/api/admin/kb-drafts", headers=HEADERS, json={**body, "source_message_id": 999}).status_code, 404)
        self.assertEqual([d["title"] for d in self.client_for(Role.CONTENT_EDITOR).get("/api/admin/kb-drafts").json()], [body["title"]])
        self.assertEqual(self.client_for(Role.READ_ONLY_ANALYST).get("/api/admin/kb-drafts").status_code, 403)


class TestPrivacyMask(unittest.TestCase):

    def test_phones_and_emails_masked_prices_kept(self):
        self.assertEqual(mask_personal_data("call +971 50 123 4567 or a.b@x.ae"), "call •••567 or •••@•••")
        self.assertEqual(mask_personal_data("my number 0501234567"), "my number •••567")
        for text in ("budget 2500000", "AED 1,500,000", "3.8% over 25 years", "ticket XO-261021-ABC123"):
            self.assertEqual(mask_personal_data(text), text)


if __name__ == "__main__":
    unittest.main()
