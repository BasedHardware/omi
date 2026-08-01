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
client_stub.get_firestore_client = MagicMock(return_value=mock_db)
client_stub.document_id_from_seed = MagicMock(return_value="seed-id")

# Stub database.action_items (imported by staged_tasks)
_stub_module("database.action_items")

# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------
import database.staged_tasks as staged_tasks_mod
from tests.store_fakes import FakeDocumentStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _seed(monkeypatch, uid, rows):
    """Seed a FakeDocumentStore with staged tasks and wire the ``_store()`` seam.

    ``rows`` is a list of (id, completed, relevance_score) tuples.
    """
    store = FakeDocumentStore()
    for doc_id, completed, score in rows:
        store.set(
            f'users/{uid}/staged_tasks/{doc_id}',
            {'completed': completed, 'relevance_score': score},
        )
    monkeypatch.setattr(staged_tasks_mod, '_store', lambda: store)
    return store


def _score(store, uid, doc_id):
    return store.get(f'users/{uid}/staged_tasks/{doc_id}').to_dict()['relevance_score']


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestBatchUpdateStagedScores:
    """batch_update_staged_scores must skip IDs not present in the active set."""

    def test_skips_stale_ids(self, monkeypatch):
        """Only existing active IDs should be updated; stale IDs must be silently skipped."""
        # Server has task-1 and task-3 active; task-2 was deleted (absent).
        store = _seed(
            monkeypatch,
            "uid-123",
            [("task-1", False, 0.0), ("task-3", False, 0.0)],
        )

        scores = [
            {"id": "task-1", "relevance_score": 0.9},
            {"id": "task-2", "relevance_score": 0.5},  # stale
            {"id": "task-3", "relevance_score": 0.1},
        ]

        staged_tasks_mod.batch_update_staged_scores("uid-123", scores)

        # task-1 and task-3 got their new scores; the stale task-2 was never created.
        assert _score(store, "uid-123", "task-1") == 0.9
        assert _score(store, "uid-123", "task-3") == 0.1
        assert not store.exists("users/uid-123/staged_tasks/task-2")

    def test_empty_scores_no_writes(self, monkeypatch):
        """Empty scores list should return immediately without touching the store."""
        store = _seed(monkeypatch, "uid-123", [("task-1", False, 0.3)])

        staged_tasks_mod.batch_update_staged_scores("uid-123", [])

        # Untouched: the pre-existing score is unchanged.
        assert _score(store, "uid-123", "task-1") == 0.3

    def test_all_stale_ids_no_writes(self, monkeypatch):
        """If every ID in scores is stale, nothing is written."""
        store = _seed(monkeypatch, "uid-123", [])  # no active docs

        scores = [
            {"id": "gone-1", "relevance_score": 0.9},
            {"id": "gone-2", "relevance_score": 0.5},
        ]

        staged_tasks_mod.batch_update_staged_scores("uid-123", scores)

        assert store.list_ids("users/uid-123/staged_tasks") == []

    def test_all_valid_ids_updates_all(self, monkeypatch):
        """When all active IDs exist, all should be updated."""
        store = _seed(
            monkeypatch,
            "uid-456",
            [("t1", False, 0.0), ("t2", False, 0.0)],
        )

        scores = [
            {"id": "t1", "relevance_score": 0.8},
            {"id": "t2", "relevance_score": 0.2},
        ]

        staged_tasks_mod.batch_update_staged_scores("uid-456", scores)

        assert _score(store, "uid-456", "t1") == 0.8
        assert _score(store, "uid-456", "t2") == 0.2

    def test_skips_promoted_completed_ids(self, monkeypatch):
        """Promoted tasks (completed=True) should be excluded by the completed filter."""
        # task-1 is active; task-2 is promoted (completed=True) so the
        # completed==False query won't return it.
        store = _seed(
            monkeypatch,
            "uid-789",
            [("task-1", False, 0.0), ("task-2", True, 0.0)],
        )

        scores = [
            {"id": "task-1", "relevance_score": 0.9},
            {"id": "task-2", "relevance_score": 0.5},  # promoted, completed=True
        ]

        staged_tasks_mod.batch_update_staged_scores("uid-789", scores)

        # Only task-1 was updated; the completed task-2 kept its original score.
        assert _score(store, "uid-789", "task-1") == 0.9
        assert _score(store, "uid-789", "task-2") == 0.0
