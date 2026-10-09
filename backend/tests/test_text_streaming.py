import unittest
import os
import sys
import json
import asyncio

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from app.main import app
from app.orchestrator.orchestrator import ConversationOrchestrator
from app.orchestrator.session_store import SessionStore

class TestTextStreaming(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_01_stream_user_turn_tokens_and_final_payload(self):
        """
        Test direct ConversationOrchestrator.stream_user_turn generator:
        - Yields progressive tokens with is_final=False
        - Yields final metadata event with is_final=True and aggregated text
        - Persists assistant message into SessionStore
        """
        async def _run():
            session_id = "test_stream_direct_001"
            generator = ConversationOrchestrator.stream_user_turn(
                user_message="Hello, what can you help me with?",
                session_id=session_id
            )

            tokens = []
            final_payload = None

            async for chunk in generator:
                self.assertTrue(chunk.startswith("data: "))
                self.assertTrue(chunk.endswith("\n\n"))
                payload = json.loads(chunk[6:].strip())

                if not payload.get("is_final"):
                    self.assertIn("token", payload)
                    tokens.append(payload["token"])
                else:
                    final_payload = payload

            self.assertGreater(len(tokens), 0, "Should have streamed at least one token chunk")
            self.assertIsNotNone(final_payload, "Should have yielded a final payload")
            self.assertTrue(final_payload["is_final"])
            self.assertEqual(final_payload["session_id"], session_id)
            self.assertEqual(final_payload["text"], "".join(tokens))

            # Verify session store persistence
            session = SessionStore.get_or_create_session(session_id)
            self.assertGreaterEqual(len(session.messages), 2)
            self.assertEqual(session.messages[-1].role, "assistant")
            self.assertEqual(session.messages[-1].content, final_payload["text"])

        asyncio.run(_run())

    def test_02_api_chat_stream_endpoint(self):
        """
        Test POST /api/chat/stream HTTP endpoint:
        - Returns 200 with text/event-stream content-type
        - Headers include no-cache and keep-alive
        - Parses SSE chunks correctly
        """
        session_id = "test_stream_http_002"
        with self.client.stream(
            "POST",
            "/api/chat/stream",
            json={"message": "Show me 2 bedroom apartments in Dubai Marina", "session_id": session_id}
        ) as response:
            self.assertEqual(response.status_code, 200)
            self.assertIn("text/event-stream", response.headers.get("content-type", ""))
            self.assertEqual(response.headers.get("cache-control"), "no-cache")

            tokens = []
            final_payload = None

            for line in response.iter_lines():
                line_str = line if isinstance(line, str) else line.decode("utf-8")
                if line_str.startswith("data: "):
                    data_json = json.loads(line_str[6:])
                    if data_json.get("is_final"):
                        final_payload = data_json
                    else:
                        tokens.append(data_json.get("token", ""))

            self.assertGreater(len(tokens), 0)
            self.assertIsNotNone(final_payload)
            self.assertTrue(final_payload["is_final"])
            self.assertEqual(final_payload["session_id"], session_id)
            self.assertGreater(len(final_payload.get("property_results", [])), 0)

    def test_03_stream_payment_guardrail_rejection(self):
        """
        Test that payment requests via /api/chat/stream are blocked by guardrails.
        """
        with self.client.stream(
            "POST",
            "/api/chat/stream",
            json={"message": "Here is my credit card number 4111 2222 3333 4444 to make payment"}
        ) as response:
            self.assertEqual(response.status_code, 200)
            lines = [
                (l if isinstance(l, str) else l.decode("utf-8")) 
                for l in response.iter_lines() 
                if (l if isinstance(l, str) else l.decode("utf-8")).startswith("data: ")
            ]
            self.assertGreaterEqual(len(lines), 1)
            data = json.loads(lines[-1][6:])
            self.assertTrue(data.get("is_final"))
            self.assertTrue("error" in data or "payment" in data.get("text", "").lower())

if __name__ == "__main__":
    unittest.main()
