"""
Hermetic Unit Tests for Action Items Batch Boundary Resilience & Deduplication.
Tests Firestore 500-op limit chunking (501 items, L+1 boundary), duplicate ID
filtering, empty/whitespace ID rejection, and vector store exception resilience.
INV-MEM-5: Universal memory and task authority.
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch
from typing import Any, List

# Ensure backend root is on sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

mock_fa = MagicMock()
mock_fa.__path__ = []
sys.modules["firebase_admin"] = mock_fa
sys.modules["firebase_admin.auth"] = MagicMock()
sys.modules["firebase_admin.firestore"] = MagicMock()

# Hermetic test stubbing for environments without third-party cloud/cache packages
for mod_name in [
    "redis",
    "pinecone",
    "prometheus_client",
    "anthropic",
    "openai",
    "google.genai",
    "cachetools",
    "langchain",
    "langchain_core",
    "langchain_anthropic",
    "langchain_openai",
    "tiktoken",
    "utils.llm.clients",
    "utils.notifications",
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()

if "fastapi" not in sys.modules:
    mock_fastapi = MagicMock()

    def _route_decorator(*args, **kwargs):
        def _wrapper(fn):
            return fn
        return _wrapper

    class _MockRouter:
        def post(self, *a, **k):
            return _route_decorator()
        def get(self, *a, **k):
            return _route_decorator()
        def put(self, *a, **k):
            return _route_decorator()
        def delete(self, *a, **k):
            return _route_decorator()
        def patch(self, *a, **k):
            return _route_decorator()

    mock_fastapi.APIRouter = _MockRouter
    mock_fastapi.Depends = lambda x: x

    class MockHTTPException(Exception):
        def __init__(self, status_code: int = 500, detail: Any = None):
            self.status_code = status_code
            self.detail = detail
            super().__init__(f"HTTP {status_code}: {detail}")

    mock_fastapi.HTTPException = MockHTTPException
    mock_fastapi.Query = lambda *a, **k: None
    mock_fastapi.Request = MagicMock
    mock_fastapi.Response = MagicMock
    sys.modules["fastapi"] = mock_fastapi
    sys.modules["fastapi.responses"] = MagicMock()

mock_cloud = sys.modules.get("google.cloud", MagicMock())
mock_cloud.__path__ = []
mock_exceptions = MagicMock()
class MockNotFound(Exception):
    pass
mock_exceptions.NotFound = MockNotFound
mock_cloud.exceptions = mock_exceptions
sys.modules["google.cloud"] = mock_cloud
sys.modules["google.cloud.exceptions"] = mock_exceptions

if "google.cloud.firestore" not in sys.modules:
    mock_firestore = MagicMock()
    mock_cloud.firestore = mock_firestore
    sys.modules["google.cloud.firestore"] = mock_firestore
mock_firestore_v1 = MagicMock()
mock_firestore_v1.__path__ = []
mock_base_query = MagicMock()
mock_base_query.FieldFilter = lambda field, op, val: (field, op, val)
mock_firestore_v1.base_query = mock_base_query
mock_firestore_v1.FieldFilter = mock_base_query.FieldFilter
sys.modules["google.cloud.firestore_v1"] = mock_firestore_v1
sys.modules["google.cloud.firestore_v1.base_query"] = mock_base_query
sys.modules["google.cloud.firestore_v1.query"] = MagicMock()
sys.modules["database.firestore_document_probe"] = MagicMock()

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

import database.action_items as ai_db
import database.vector_db as vector_db
import routers.action_items as ai_router


class FakeDocRef:
    def __init__(self, doc_id: str, path: str = ""):
        self.id = doc_id
        self.path = f"{path}/{doc_id}" if path else doc_id


class FakeDoc:
    def __init__(self, doc_id: str, data: dict | None = None, exists: bool = True):
        self.id = doc_id
        self._data = data if data is not None else {"id": doc_id, "description": f"task {doc_id}", "completed": False}
        self.exists = exists
        self.reference = FakeDocRef(doc_id)

    def to_dict(self):
        return dict(self._data)


class FakeBatch:
    def __init__(self, recorder):
        self.recorder = recorder
        self.ops: List[tuple] = []

    def delete(self, ref):
        self.ops.append(("delete", getattr(ref, "id", str(ref))))

    def update(self, ref, data):
        self.ops.append(("update", getattr(ref, "id", str(ref)), data))

    def commit(self):
        self.recorder.commits.append(list(self.ops))
        self.ops = []


class FakeBatchRecorder:
    def __init__(self):
        self.commits: List[List[tuple]] = []

    def make_batch(self):
        return FakeBatch(self)


class TestActionItemsBatchBoundaryResilience(unittest.TestCase):
    def setUp(self):
        self.recorder = FakeBatchRecorder()

    @patch("database.action_items.bump_action_items_list_version")
    @patch("database.action_items.db")
    def test_delete_action_items_batch_boundary_chunking_501(self, mock_db, mock_bump):
        """Boundary stress test: 501 items (L+1) must split into 2 commits (499 + 2)."""
        mock_db.batch.side_effect = self.recorder.make_batch
        mock_col = MagicMock()
        mock_col.document.side_effect = lambda doc_id: FakeDocRef(doc_id)
        mock_db.collection.return_value.document.return_value.collection.return_value = mock_col

        ids_501 = [f"task-{i:04d}" for i in range(501)]
        deleted = ai_db.delete_action_items_batch("user-test-1", ids_501)

        self.assertEqual(len(deleted), 501)
        # 499 in first commit, 2 in second commit -> exactly 2 commits
        self.assertEqual(len(self.recorder.commits), 2)
        self.assertEqual(len(self.recorder.commits[0]), 499)
        self.assertEqual(len(self.recorder.commits[1]), 2)
        mock_bump.assert_called_once_with("user-test-1")

    @patch("database.action_items.bump_action_items_list_version")
    @patch("database.action_items.db")
    def test_delete_action_items_batch_deduplicates_and_cleans_ids(self, mock_db, mock_bump):
        """Duplicate IDs and whitespace/empty values must be sanitized to prevent Firestore single-commit crashes."""
        mock_db.batch.side_effect = self.recorder.make_batch
        mock_col = MagicMock()
        mock_col.document.side_effect = lambda doc_id: FakeDocRef(doc_id)
        mock_db.collection.return_value.document.return_value.collection.return_value = mock_col

        raw_ids = ["task-1", "task-1", "  task-2  ", "", "   ", "task-1", "task-3"]
        deleted = ai_db.delete_action_items_batch("user-test-1", raw_ids)

        self.assertEqual(deleted, ["task-1", "task-2", "task-3"])
        self.assertEqual(len(self.recorder.commits), 1)
        self.assertEqual(len(self.recorder.commits[0]), 3)

    def test_delete_action_items_batch_invalid_uid_raises(self):
        """Empty or whitespace UID must be rejected immediately."""
        with self.assertRaises(ValueError):
            ai_db.delete_action_items_batch("", ["task-1"])
        with self.assertRaises(ValueError):
            ai_db.delete_action_items_batch("   ", ["task-1"])

    @patch("database.action_items.bump_action_items_list_version")
    @patch("database.action_items.db")
    def test_delete_action_items_for_conversation_boundary_chunking_501(self, mock_db, mock_bump):
        """Conversations with >500 action items must not crash with batch limit exceptions."""
        mock_db.batch.side_effect = self.recorder.make_batch
        docs_501 = [FakeDoc(f"conv-task-{i:04d}") for i in range(501)]

        mock_query = MagicMock()
        mock_query.stream.return_value = iter(docs_501)
        mock_col = MagicMock()
        mock_col.where.return_value = mock_query
        mock_db.collection.return_value.document.return_value.collection.return_value = mock_col

        count = ai_db.delete_action_items_for_conversation("user-test-1", "conv-99")

        self.assertEqual(count, 501)
        self.assertEqual(len(self.recorder.commits), 2)
        self.assertEqual(len(self.recorder.commits[0]), 499)
        self.assertEqual(len(self.recorder.commits[1]), 2)
        mock_bump.assert_called_once_with("user-test-1")

    @patch("database.action_items.bump_action_items_list_version")
    @patch("database.action_items.db")
    def test_retire_action_items_for_conversation_boundary_chunking_501(self, mock_db, mock_bump):
        """Retiring >500 action items for conversation must be chunked safely."""
        mock_db.batch.side_effect = self.recorder.make_batch
        docs_501 = [FakeDoc(f"retire-task-{i:04d}") for i in range(501)]

        mock_query = MagicMock()
        mock_query.stream.return_value = iter(docs_501)
        mock_db.collection.return_value.document.return_value.collection.return_value.where.return_value = mock_query

        count = ai_db.retire_action_items_for_conversation(
            "user-test-1", "conv-99", active_ids=["retire-task-0000"]
        )

        # 501 total minus 1 active = 500 retired
        self.assertEqual(count, 500)
        self.assertEqual(len(self.recorder.commits), 2)
        self.assertEqual(len(self.recorder.commits[0]), 499)
        self.assertEqual(len(self.recorder.commits[1]), 1)
        mock_bump.assert_called_once_with("user-test-1")

    @patch("database.action_items.bump_action_items_list_version")
    @patch("database.action_items.db")
    def test_batch_set_sync_requested_chunking_and_deduplication(self, mock_db, mock_bump):
        """Sync requests with duplicate IDs and >500 items must be safely chunked and deduplicated."""
        mock_db.batch.side_effect = self.recorder.make_batch
        mock_col = MagicMock()
        mock_col.document.side_effect = lambda doc_id: FakeDocRef(doc_id)
        mock_db.collection.return_value.document.return_value.collection.return_value = mock_col

        items_501 = [f"sync-task-{i:04d}" for i in range(501)]
        # Add duplicate items
        items_with_dups = items_501 + ["sync-task-0000", "sync-task-0001", "   "]

        ai_db.batch_set_sync_requested("user-test-1", items_with_dups)

        # Unique count is exactly 501
        self.assertEqual(len(self.recorder.commits), 2)
        self.assertEqual(len(self.recorder.commits[0]), 499)
        self.assertEqual(len(self.recorder.commits[1]), 2)
        mock_bump.assert_called_once_with("user-test-1")

    @patch("database.action_items.prepare_action_item_for_read")
    @patch("database.action_items.typed_doc")
    @patch("database.action_items.db")
    def test_get_action_items_by_ids_chunking_and_order_preservation(self, mock_db, mock_typed, mock_prep):
        """get_action_items_by_ids chunks queries at 500 and preserves input order."""
        mock_typed.side_effect = lambda doc: doc.to_dict()
        mock_prep.side_effect = lambda d: d

        mock_db.collection.return_value.document.return_value.collection.return_value.document.side_effect = (
            lambda doc_id: FakeDocRef(doc_id)
        )

        def fake_get_all(refs):
            return [FakeDoc(ref.id) for ref in refs]

        mock_db.get_all.side_effect = fake_get_all

        ids_501 = [f"id-{i:04d}" for i in range(501)]
        result = ai_db.get_action_items_by_ids("user-test-1", ids_501)

        self.assertEqual(len(result), 501)
        self.assertEqual(result[0]["id"], "id-0000")
        self.assertEqual(result[500]["id"], "id-0500")
        # Assert get_all was called twice (500 + 1)
        self.assertEqual(mock_db.get_all.call_count, 2)

    @patch("database.vector_db.logger")
    @patch("database.vector_db.index")
    def test_delete_action_item_vectors_batch_handles_pinecone_failure_gracefully(self, mock_index, mock_logger):
        """Vector DB deletion failures must be logged as warnings, never raising HTTP 500 on callers."""
        mock_index.delete.side_effect = RuntimeError("Pinecone network timeout")

        # Must not raise
        vector_db.delete_action_item_vectors_batch("user-test-1", ["task-1", "task-2"])
        mock_logger.warning.assert_called_once()
        self.assertIn("Pinecone network timeout", str(mock_logger.warning.call_args))

    @patch("routers.action_items.record_product_event")
    @patch("routers.action_items.send_action_items_batch_deletion_message")
    @patch("routers.action_items.delete_action_item_vectors_batch")
    @patch("routers.action_items._wake_task_changes")
    @patch("routers.action_items.action_items_db")
    def test_router_batch_delete_deduplicates_and_protects_locked(
        self, mock_db, mock_wake, mock_vec, mock_fcm, mock_event
    ):
        """Router deduplicates IDs before preflight lock check and database batch delete."""
        mock_db.get_action_items_by_ids.return_value = [{"id": "t-1", "is_locked": False}]
        mock_db.delete_action_items_batch.return_value = ["t-1", "t-2"]

        req = ai_router.BatchDeleteActionItemsRequest(ids=["t-1", "t-1", "t-2", "   "])
        resp = ai_router.batch_delete_action_items(req, uid="user-test-1")

        self.assertEqual(resp["status"], "Ok")
        self.assertEqual(resp["deleted_count"], 2)
        # get_action_items_by_ids received deduplicated IDs
        mock_db.get_action_items_by_ids.assert_called_once_with("user-test-1", ["t-1", "t-2"])
        mock_db.delete_action_items_batch.assert_called_once_with("user-test-1", ["t-1", "t-2"])


if __name__ == "__main__":
    unittest.main()
