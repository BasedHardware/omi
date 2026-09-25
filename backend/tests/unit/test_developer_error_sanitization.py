"""Hermetic unit and behavioral regression tests for error sanitization in developer API router.

Verifies that:
1. GET /v1/dev/user/memories catches ValueError during category parsing, logs
   error type safely, and returns generic HTTP 400 without leaking Enum exception text or input.
2. GET /v1/dev/user/conversations catches ValueError during category parsing, logs
   error type safely, and returns generic HTTP 400 without leaking Enum exception text or input.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys
from types import ModuleType
import unittest
from unittest.mock import MagicMock

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class _AutoMockModule(ModuleType):
    def __getattr__(self, name: str):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        mock = MagicMock()
        setattr(self, name, mock)
        return mock


_STUBS = [
    "redis",
    "cachetools",
    "prometheus_client",
    "google.cloud.tasks_v2",
    "ulid",
    "pinecone",
    "typesense",
    "opuslib",
    "pydub",
    "pusher",
    "modal",
    "database._client",
    "database.redis_db",
    "database.conversations",
    "database.memories",
    "database.action_items",
    "database.folders",
    "database.users",
    "database.user_usage",
    "database.vector_db",
    "database.chat",
    "database.apps",
    "database.goals",
    "database.notifications",
    "database.mem_db",
    "database.mcp_api_key",
    "database.daily_summaries",
    "database.fair_use",
    "database.auth",
    "database.knowledge_graph",
    "database.dev_api_key",
    "database.firestore_read_metrics",
    "firebase_admin",
    "firebase_admin.messaging",
    "firebase_admin.auth",
    "firebase_admin.credentials",
    "firebase_admin.firestore",
    "google.cloud.firestore",
    "google.cloud.firestore_v1",
    "utils.other.storage",
    "utils.stt.pre_recorded",
    "utils.stt.vad",
    "utils.fair_use",
    "utils.subscription",
    "utils.conversations.process_conversation",
    "utils.conversations.location",
    "utils.conversations.lifecycle",
    "utils.notifications",
    "utils.apps",
    "utils.llm.memories",
    "utils.llm.chat",
    "utils.llm.knowledge_graph",
]

DEVELOPER_SOURCE_FILE = BACKEND_DIR / "routers" / "developer.py"


def _get_endpoint_source(endpoint_name: str) -> str:
    source = DEVELOPER_SOURCE_FILE.read_text(encoding="utf-8")
    start = source.index(f"def {endpoint_name}(")
    match = re.search(r"\n(?:@router|def |async def )", source[start + 1 :])
    if match:
        return source[start : start + 1 + match.start()]
    return source[start:]


class DeveloperErrorSanitizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Stub dependencies within test lifecycle to avoid module-scope sys.modules mutation
        for mod_name in _STUBS:
            if mod_name not in sys.modules:
                sys.modules[mod_name] = _AutoMockModule(mod_name)
        sys.modules["firebase_admin.auth"].InvalidIdTokenError = type("InvalidIdTokenError", (Exception,), {})

        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from routers import developer

        app = FastAPI()
        app.include_router(developer.router)
        app.dependency_overrides[developer.get_developer_memory_default_memory_read_context] = lambda: MagicMock(
            uid="test-uid"
        )
        app.dependency_overrides[developer.get_auth_with_conversations_read] = lambda: MagicMock(uid="test-uid")
        cls.client = TestClient(app)

    # Labeled source tripwires
    def test_tripwire_get_memories_source_sanitized(self):
        source = _get_endpoint_source("get_memories")
        self.assertNotIn("detail=f\"Invalid category {str(e)}\"", source)
        self.assertNotIn("detail=str(e)", source)
        self.assertIn("type(e).__name__", source)
        self.assertIn('detail="Invalid category. Please provide a valid category."', source)

    def test_tripwire_get_conversations_source_sanitized(self):
        source = _get_endpoint_source("get_conversations")
        self.assertNotIn("detail=f\"Invalid category {str(e)}\"", source)
        self.assertNotIn("detail=str(e)", source)
        self.assertIn("type(e).__name__", source)
        self.assertIn('detail="Invalid category. Please provide a valid category."', source)

    # Behavioral regression tests
    def test_behavioral_get_memories_invalid_category_sanitized(self):
        bad_input = "not-a-real-category-secret-leak-12345"
        resp = self.client.get(f"/v1/dev/user/memories?categories={bad_input}")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json().get("detail"), "Invalid category. Please provide a valid category.")
        self.assertNotIn(bad_input, resp.text)

    def test_behavioral_get_conversations_invalid_category_sanitized(self):
        bad_input = "not-a-real-category-secret-leak-12345"
        resp = self.client.get(f"/v1/dev/user/conversations?categories={bad_input}")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json().get("detail"), "Invalid category. Please provide a valid category.")
        self.assertNotIn(bad_input, resp.text)


if __name__ == "__main__":
    unittest.main()
