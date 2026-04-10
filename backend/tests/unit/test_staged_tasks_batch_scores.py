"""Tests for batch_update_staged_scores stale-ID resilience (issue #6468).

The desktop client can send score updates for staged tasks that have been
deleted or promoted server-side.  batch.update() on a non-existent Firestore
document raises NotFound, so the function must pre-filter to existing IDs.
"""

import os
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _stub_module(name):
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


def _stub_package(name):
    mod = types.ModuleType(name)
    mod.__path__ = []
    sys.modules[name] = mod
    return mod


# ---------------------------------------------------------------------------
# Stub heavy dependencies before any production imports
# ---------------------------------------------------------------------------
for mod_name in [
    "firebase_admin",
    "firebase_admin.firestore",
    "firebase_admin.auth",
    "firebase_admin.messaging",
    "firebase_admin.credentials",
    "google.cloud.firestore",
    "google.cloud.firestore_v1",
    "google.cloud.firestore_v1.base_query",
    "google.auth",
    "google.auth.transport",
    "google.auth.transport.requests",
    "google.cloud.storage",
    "opuslib",
    "sentry_sdk",
    "database.redis_db",
    "database.auth",
]:
    if mod_name not in sys.modules:
        _stub_module(mod_name)

# Stub google.cloud.firestore sentinels
firestore_stub = sys.modules["google.cloud.firestore"]
firestore_stub.Increment = lambda x: f"__increment_{x}__"
firestore_stub.Query = MagicMock()
firestore_stub.Query.ASCENDING = "ASCENDING"
firestore_stub.Query.DESCENDING = "DESCENDING"
firestore_stub.Client = MagicMock

# Stub FieldFilter
field_filter_stub = sys.modules["google.cloud.firestore_v1.base_query"]
field_filter_stub.FieldFilter = MagicMock()
sys.modules["google.cloud.firestore_v1"].FieldFilter = field_filter_stub.FieldFilter
sys.modules["google.cloud.firestore_v1"].transactional = lambda f: f

# Add backend dir to sys.path
sys.path.insert(0, str(BACKEND_DIR))

# Stub database package and _client
if "database" not in sys.modules:
    db_pkg = _stub_package("database")
    db_pkg.__path__ = [str(BACKEND_DIR / "database")]
else:
    db_mod = sys.modules["database"]
    if not hasattr(db_mod, '__path__'):
        db_mod.__path__ = [str(BACKEND_DIR / "database")]

client_stub = _stub_module("database._client")
mock_db = MagicMock()
client_stub.db = mock_db
client_stub.document_id_from_seed = MagicMock(return_value="seed-id")

# Stub database.action_items (imported by staged_tasks)
_stub_module("database.action_items")

# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------
import database.staged_tasks as staged_tasks_mod


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_mock():
    mock_db.reset_mock()
    yield


def _make_doc_snapshot(doc_id):
    """Create a minimal mock Firestore document snapshot with just .id."""
    snap = MagicMock()
    snap.id = doc_id
    return snap


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestBatchUpdateStagedScores:
    """batch_update_staged_scores must skip IDs not present in Firestore."""

    def test_skips_stale_ids(self):
        """Only existing active IDs should be updated; stale IDs must be silently skipped."""
        col_mock = MagicMock()
        mock_db.collection.return_value.document.return_value.collection.return_value = col_mock

        # .where(completed==False).select([]).stream() returns active docs only
        # Server has task-1 and task-3 active; task-2 was deleted
        col_mock.where.return_value.select.return_value.stream.return_value = [
            _make_doc_snapshot("task-1"),
            _make_doc_snapshot("task-3"),
        ]

        batch_mock = MagicMock()
        mock_db.batch.return_value = batch_mock

        scores = [
            {"id": "task-1", "relevance_score": 0.9},
            {"id": "task-2", "relevance_score": 0.5},  # stale
            {"id": "task-3", "relevance_score": 0.1},
        ]

        staged_tasks_mod.batch_update_staged_scores("uid-123", scores)

        # batch.update should have been called exactly twice (task-1, task-3)
        assert batch_mock.update.call_count == 2
        updated_ids = [c.args[0] for c in batch_mock.update.call_args_list]
        # Each ref is col_mock.document(id) — verify the document() calls
        col_mock.document.assert_any_call("task-1")
        col_mock.document.assert_any_call("task-3")
        # task-2 should NOT appear
        doc_calls = [c.args[0] for c in col_mock.document.call_args_list]
        assert "task-2" not in doc_calls

    def test_empty_scores_no_firestore_calls(self):
        """Empty scores list should return immediately without any Firestore reads."""
        staged_tasks_mod.batch_update_staged_scores("uid-123", [])

        mock_db.batch.assert_not_called()
        mock_db.collection.assert_not_called()

    def test_all_stale_ids_no_batch_commit(self):
        """If every ID in scores is stale, no batch operations should occur."""
        col_mock = MagicMock()
        mock_db.collection.return_value.document.return_value.collection.return_value = col_mock

        # Server has no active docs matching
        col_mock.where.return_value.select.return_value.stream.return_value = []

        batch_mock = MagicMock()
        mock_db.batch.return_value = batch_mock

        scores = [
            {"id": "gone-1", "relevance_score": 0.9},
            {"id": "gone-2", "relevance_score": 0.5},
        ]

        staged_tasks_mod.batch_update_staged_scores("uid-123", scores)

        # No batch should be created (early return before db.batch())
        mock_db.batch.assert_not_called()

    def test_all_valid_ids_updates_all(self):
        """When all active IDs exist, all should be updated."""
        col_mock = MagicMock()
        mock_db.collection.return_value.document.return_value.collection.return_value = col_mock

        col_mock.where.return_value.select.return_value.stream.return_value = [
            _make_doc_snapshot("t1"),
            _make_doc_snapshot("t2"),
        ]

        batch_mock = MagicMock()
        mock_db.batch.return_value = batch_mock

        scores = [
            {"id": "t1", "relevance_score": 0.8},
            {"id": "t2", "relevance_score": 0.2},
        ]

        staged_tasks_mod.batch_update_staged_scores("uid-456", scores)

        assert batch_mock.update.call_count == 2
        batch_mock.commit.assert_called_once()

    def test_skips_promoted_completed_ids(self):
        """Promoted tasks (completed=True) should be excluded by the where filter."""
        col_mock = MagicMock()
        mock_db.collection.return_value.document.return_value.collection.return_value = col_mock

        # Only task-1 is active; task-2 is promoted (completed=True) so the
        # where(completed==False) query won't return it
        col_mock.where.return_value.select.return_value.stream.return_value = [
            _make_doc_snapshot("task-1"),
        ]

        batch_mock = MagicMock()
        mock_db.batch.return_value = batch_mock

        scores = [
            {"id": "task-1", "relevance_score": 0.9},
            {"id": "task-2", "relevance_score": 0.5},  # promoted, completed=True
        ]

        staged_tasks_mod.batch_update_staged_scores("uid-789", scores)

        # Only task-1 should be updated
        assert batch_mock.update.call_count == 1
        col_mock.document.assert_called_once_with("task-1")
