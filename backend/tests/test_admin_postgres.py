"""The admin stores against a real PostgreSQL (the production path on Render).

Runs only when TEST_DATABASE_URL points at a throwaway database; every test starts from empty tables."""
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from app.admin import users as users_module
from app.admin.activity import ActivityLog
from app.admin.config_store import ConfigError, ConfigStore
from app.admin.knowledge import KnowledgeError, KnowledgeStore
from app.admin.knowledge_web import WebSources
from app.core.config import builtin_config, load_config
from app.services.vector_store import VectorDatabase
from app.admin.reviews import ReviewStore
from app.admin.settings_store import SettingsStore
from app.admin.users import AdminUserError, AdminUserStore, verify_password
from app.core.config import settings
from app.core.security import Role
from app.db.conversation_store import ConversationStore
from app.db.database import Database
from app.db.lead_store import LeadDatabaseService

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")
TABLES = "config_versions, config_drafts, kb_versions, kb_sources, admin_settings, kb_drafts, message_reviews, message_feedback, admin_sessions, admin_users, admin_activity, conversation_messages, conversations, advisor_leads"


@unittest.skipUnless(TEST_DATABASE_URL, "set TEST_DATABASE_URL to run the PostgreSQL tests")
class TestAdminStoresOnPostgres(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        for p in (mock.patch.object(settings, "DATABASE_URL", TEST_DATABASE_URL),
                  mock.patch.object(users_module, "PBKDF2_ITERATIONS", 1000)):
            p.start()
            self.addCleanup(p.stop)
        self.assertTrue(await Database.init())
        self.assertTrue(await LeadDatabaseService.init_db())
        await Database.pool.execute(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE")

    async def asyncTearDown(self):
        await LeadDatabaseService.close_db()
        await Database.close()

    async def test_schema_is_safe_to_apply_twice(self):
        await Database.close()
        self.assertTrue(await Database.init())

    async def test_users(self):
        admin = await AdminUserStore.create("Owner@xoto.ae", "Owner", Role.ADMIN, "correct horse battery")
        self.assertEqual(admin["email"], "owner@xoto.ae")
        with self.assertRaises(AdminUserError):
            await AdminUserStore.create("owner@xoto.ae", "Again", Role.ADMIN, "correct horse battery")
        editor = await AdminUserStore.create("sara@xoto.ae", "Sara", Role.CONTENT_EDITOR, "correct horse battery")
        updated = await AdminUserStore.update(editor["id"], role=Role.BOT_TRAINER)
        self.assertEqual((updated["role"], updated["token_version"]), (Role.BOT_TRAINER, 1))
        with self.assertRaises(AdminUserError) as ctx:
            await AdminUserStore.update(admin["id"], active=False)
        self.assertEqual(str(ctx.exception), "last_admin")
        await AdminUserStore.set_password(editor["id"], "a brand new password")
        stored = await AdminUserStore.get_by_email("SARA@xoto.ae")
        self.assertTrue(verify_password("a brand new password", stored["password_hash"]))
        self.assertEqual(stored["token_version"], 2)
        await AdminUserStore.record_login(editor["id"])
        self.assertIsNotNone((await AdminUserStore.get(editor["id"]))["last_login_at"])
        self.assertEqual([u["email"] for u in await AdminUserStore.list()], ["owner@xoto.ae", "sara@xoto.ae"])
        self.assertEqual(await AdminUserStore.count_active_admins(), 1)

    async def test_sessions(self):
        user = await AdminUserStore.create("owner@xoto.ae", "Owner", Role.ADMIN, "correct horse battery")
        laptop = await AdminUserStore.create_session(user["id"], 3600)
        phone = await AdminUserStore.create_session(user["id"], 3600)
        expired = await AdminUserStore.create_session(user["id"], -10)
        await AdminUserStore.revoke_session(laptop)
        self.assertFalse(await AdminUserStore.session_active(laptop, user["id"]))
        self.assertTrue(await AdminUserStore.session_active(phone, user["id"]))
        self.assertFalse(await AdminUserStore.session_active(expired, user["id"]))
        self.assertFalse(await AdminUserStore.session_active(phone, user["id"] + 1))

    async def test_activity(self):
        actor = {"email": "owner@xoto.ae", "role": Role.ADMIN}
        await ActivityLog.record(actor, "user_created", "user:sara@xoto.ae", {"role": Role.CONTENT_EDITOR})
        await ActivityLog.record(actor, "config_reloaded", "config")
        entries = await ActivityLog.recent(10)
        self.assertEqual([e["action"] for e in entries], ["config_reloaded", "user_created"])
        self.assertEqual(entries[1]["details"], {"role": Role.CONTENT_EDITOR})
        self.assertEqual(len(await ActivityLog.recent(10, action="user_created")), 1)

    async def test_conversations(self):
        sid = "sess_postgres_test_000001"
        await ConversationStore.record_turn(sid, language="en", channel="voice", user_text="hi", reply="Hello!",
                                            tools=[], latency_ms=800, cost_usd=0.001)
        await ConversationStore.record_turn(sid, language="ar", channel="text", user_text="price?", reply=None,
                                            tools=["calc_emi"], latency_ms=None, cost_usd=0.002)
        await ConversationStore.record_handoff(sid, "XO-261021-ABC123")
        conv = await ConversationStore.get(sid)
        self.assertEqual((conv["user_turns"], conv["failed_turns"], conv["language"]), (2, 1, "ar"))
        self.assertEqual(sorted(conv["channels"]), ["text", "voice"])
        self.assertEqual(conv["tools"], ["calc_emi"])
        self.assertEqual((conv["handoff_ticket"], conv["lead_saved"], conv["cost_usd"]), ("XO-261021-ABC123", True, 0.002))
        self.assertEqual([(m["role"], m["content"]) for m in conv["messages"]], [("user", "hi"), ("assistant", "Hello!"), ("user", "price?")])

    async def test_feedback_reviews_queue_and_summaries(self):
        sid = "sess_postgres_test_000003"
        await ConversationStore.record_turn(sid, language="en", channel="text", user_text="Call me 0501234567 about JVC",
                                            reply="Here are options.", tools=["search_properties"], latency_ms=700,
                                            cost_usd=0.001, turn_id="00000000000000aa")
        await ConversationStore.update_cost(sid, 0.004)
        await ConversationStore.set_feedback(sid, "00000000000000aa", -1)
        conv = await ConversationStore.get(sid)
        reply = conv["messages"][1]
        self.assertEqual((reply["turn_id"], reply["rating"], conv["cost_usd"]), ("00000000000000aa", -1, 0.004))

        queue = await ReviewStore.queue()
        self.assertEqual([(q["message_id"], q["rating"], q["question"]) for q in queue],
                         [(reply["id"], -1, "Call me 0501234567 about JVC")])
        await ReviewStore.review(reply["id"], verdict="bad", flagged=False, note="wrong", reviewer="t@xoto.ae")
        self.assertEqual(await ReviewStore.queue(), [])
        await ReviewStore.review(reply["id"], verdict="bad", flagged=True, note="wrong", reviewer="t@xoto.ae")
        self.assertEqual(len(await ReviewStore.queue()), 1)
        self.assertEqual((await ReviewStore.reviews_for([reply["id"]]))[reply["id"]]["verdict"], "bad")

        now = datetime.now(timezone.utc)
        rows = await ConversationStore.summaries(now - timedelta(days=1), now + timedelta(minutes=1))
        row = rows[0]
        self.assertEqual((row["first_question"], row["last_tools"], row["last_role"]), ("Call me 0501234567 about JVC", ["search_properties"], "assistant"))
        self.assertEqual((row["thumbs_down"], row["flagged"], row["reviewed_bad"]), (1, 1, 1))
        self.assertEqual(len(await ConversationStore.summaries(now - timedelta(days=1), now + timedelta(minutes=1), search="jvc")), 1)
        self.assertEqual(len(await ConversationStore.summaries(now - timedelta(days=1), now + timedelta(minutes=1), search="villa")), 0)

        draft = await ReviewStore.create_draft(created_by="t@xoto.ae", source_message_id=reply["id"], language="en",
                                               title="JVC options", question="Q?", answer="A.")
        self.assertEqual([d["id"] for d in await ReviewStore.drafts()], [draft["id"]])
        await ConversationStore.set_feedback(sid, "00000000000000aa", None)
        self.assertIsNone((await ConversationStore.get(sid))["messages"][1]["rating"])

    async def test_settings(self):
        self.assertEqual(await SettingsStore.get("ai_budget", {"monthly_usd": None}), {"monthly_usd": None})
        await SettingsStore.set("ai_budget", {"monthly_usd": 50.0, "alert_pct": 75}, "owner@xoto.ae")
        await SettingsStore.set("ai_budget", {"monthly_usd": 60.0, "alert_pct": 75}, "owner@xoto.ae")
        self.assertEqual(await SettingsStore.get("ai_budget"), {"monthly_usd": 60.0, "alert_pct": 75})

    async def test_leads_use_the_shared_pool(self):
        result = await LeadDatabaseService.save_advisor_lead("sess_postgres_test_000002", "Test Person", "+971501234567", "English",
                                                             "Mortgage Advisory", {"ticket_id": "XO-1"}, ticket_id="XO-1")
        self.assertEqual(result, {"saved": True, "storage": "postgres"})
        self.assertEqual(len(await LeadDatabaseService.list_leads()), 1)

    async def test_config_versions_drafts_and_rollback(self):
        actor = {"email": "owner@xoto.ae", "role": Role.ADMIN}
        self.addCleanup(ConfigStore.reset_memory)
        rules = builtin_config("mortgage_rules")
        changed = {**rules, "interest": {**rules["interest"], "benchmark_rate_pct": 4.2}}
        await ConfigStore.save_draft("mortgage_rules", changed, 0, actor)
        self.assertEqual((await ConfigStore.draft("mortgage_rules"))["data"]["interest"]["benchmark_rate_pct"], 4.2)
        self.assertEqual(await ConfigStore.publish("mortgage_rules", "EIBOR review", actor), 1)
        self.assertIsNone(await ConfigStore.draft("mortgage_rules"))
        self.assertEqual(load_config("mortgage_rules")["interest"]["benchmark_rate_pct"], 4.2)
        await ConfigStore.save_draft("mortgage_rules", rules, 0, actor)  # started before version 1
        with self.assertRaises(ConfigError) as stale:
            await ConfigStore.publish("mortgage_rules", "late", actor)
        self.assertEqual(stale.exception.code, "stale_draft")
        await ConfigStore.discard_draft("mortgage_rules")
        self.assertEqual(await ConfigStore.rollback("mortgage_rules", 0, "back", actor), 2)
        self.assertEqual([v["version"] for v in await ConfigStore.versions("mortgage_rules")], [2, 1, 0])
        ConfigStore.reset_memory()
        await ConfigStore.load_published()  # a fresh instance reads the same live version
        self.assertEqual(load_config("mortgage_rules")["interest"]["benchmark_rate_pct"], rules["interest"]["benchmark_rate_pct"])

    async def test_knowledge_versions_index_and_sources(self):
        actor = {"email": "editor@xoto.ae", "role": Role.CONTENT_EDITOR}
        self.addCleanup(lambda: VectorDatabase.load(force_reload=True))

        async def embed(texts):
            return [[1.0] + [0.0] * 1535 for _ in texts]

        with mock.patch.object(KnowledgeStore, "_embed", embed):
            await KnowledgeStore.rebuild_index()
            self.assertEqual(VectorDatabase.get_document_count(), 75)
            entry = {"title": "Oqood", "short_answer": "The off-plan sales register in Dubai.", "type": "glossary"}
            saved = await KnowledgeStore.save("gloss_oqood", entry, actor, "new")
            self.assertEqual((saved["version"], VectorDatabase.get_document_count()), (1, 76))
            await KnowledgeStore.save("gloss_oqood", {**entry, "tags": ["dubai"]}, actor, "tag", base_version=1)
            with self.assertRaises(KnowledgeError):
                await KnowledgeStore.save("gloss_oqood", entry, actor, "late", base_version=1)
            await KnowledgeStore.retire("art_1", actor, "outdated")
            self.assertEqual(VectorDatabase.get_document_count(), 75)
            restored = await KnowledgeStore.restore("art_1", 0, actor, "")
            self.assertEqual((restored["version"], len((await KnowledgeStore.get("art_1"))["embedding"])), (2, 1536))
            self.assertEqual([v["action"] for v in await KnowledgeStore.versions("art_1")], ["restored", "retired", "builtin"])
            # Another instance publishes: this one notices on its next refresh.
            await Database.pool.execute(
                "INSERT INTO kb_versions (article_id, version, data, embedding, published_by) SELECT 'gloss_copy', 1, data, embedding, 'x' "
                "FROM kb_versions WHERE article_id = 'gloss_oqood' AND version = 2")
            self.assertTrue(await KnowledgeStore.refresh())
            self.assertEqual(VectorDatabase.get_document_count(), 77)

            page = "<html><head><title>Fees</title></head><body><h1>Transfer fee</h1><p>The DLD transfer fee in Dubai is 4% of the price, paid by the buyer.</p></body></html>"

            async def fetch(url):
                return page

            async def public(host):
                return None

            with mock.patch("app.admin.knowledge_web.fetch", fetch), mock.patch("app.admin.knowledge_web._public_address", public):
                source = await WebSources.add("https://xoto.ae/fees", actor)
                self.assertEqual(source["article_ids"], [f"web_{source['id']}_1"])
                self.assertEqual((await WebSources.refresh(source["id"]))["last_status"], "unchanged")
                await WebSources.remove(source["id"], actor)
            self.assertEqual(await WebSources.list(), [])
            self.assertEqual((await KnowledgeStore.get(f"web_{source['id']}_1"))["data"]["status"], "RETIRED")


if __name__ == "__main__":
    unittest.main()
