"""Tests for goal ID fallback in database/goals.py.

Verifies that _goal_dict() correctly injects doc.id when the 'id' field
is missing from Firestore document data (issue #5671).

database.goals binds ``db`` at import (``from database._client import db``), so the
fake ``database._client`` must be active before the module is exec'd. Sanctioned
Tier-2 "fake must precede import" pattern (see backend/docs/test_isolation.md and
testing/import_isolation.load_module_fresh).
"""

import os
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

_BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def goals():
    """Fresh database.goals against a stubbed database._client + firestore chain."""
    client_stub = ModuleType("database._client")
    client_stub.db = MagicMock(name="db")
    client_stub.document_id_from_seed = MagicMock(return_value="doc-id")

    firestore_stub = ModuleType("google.cloud.firestore")
    firestore_stub.Client = MagicMock()
    firestore_stub.Query = MagicMock()
    fv1_stub = ModuleType("google.cloud.firestore_v1")
    fv1_stub.FieldFilter = MagicMock()
    google_pkg = ModuleType("google")
    google_pkg.__path__ = []  # type: ignore[attr-defined]
    google_cloud_pkg = ModuleType("google.cloud")
    google_cloud_pkg.__path__ = []  # type: ignore[attr-defined]

    fakes = {
        "database._client": client_stub,
        "google": google_pkg,
        "google.cloud": google_cloud_pkg,
        "google.cloud.firestore": firestore_stub,
        "google.cloud.firestore_v1": fv1_stub,
    }
    with stub_modules(fakes):
        module = load_module_fresh(
            "database.goals",
            os.path.join(str(_BACKEND), "database", "goals.py"),
        )
        yield module


class FakeDoc:
    """Minimal Firestore document snapshot mock."""

    def __init__(self, doc_id: str, data: dict):
        self.id = doc_id
        self._data = data
        self.exists = True
        self.reference = MagicMock()

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


# ---------------------------------------------------------------------------
# _goal_dict unit tests
# ---------------------------------------------------------------------------


class TestGoalDict:
    def test_injects_doc_id_when_id_missing(self, goals):
        doc = FakeDoc("goal_abc123", {"title": "Run 5k", "is_active": True})
        result = goals._goal_dict(doc)
        assert result["id"] == "goal_abc123"

    def test_injects_doc_id_when_id_empty_string(self, goals):
        doc = FakeDoc("goal_abc123", {"id": "", "title": "Run 5k"})
        result = goals._goal_dict(doc)
        assert result["id"] == "goal_abc123"

    def test_injects_doc_id_when_id_none(self, goals):
        doc = FakeDoc("goal_abc123", {"id": None, "title": "Run 5k"})
        result = goals._goal_dict(doc)
        assert result["id"] == "goal_abc123"

    def test_preserves_existing_id(self, goals):
        doc = FakeDoc("goal_abc123", {"id": "goal_existing", "title": "Run 5k"})
        result = goals._goal_dict(doc)
        assert result["id"] == "goal_existing"

    def test_handles_none_to_dict(self, goals):
        """to_dict() returning None (empty snapshot) should not crash."""
        doc = FakeDoc("goal_abc123", {})
        doc.to_dict = lambda: None
        result = goals._goal_dict(doc)
        assert result["id"] == "goal_abc123"


# ---------------------------------------------------------------------------
# Read-path integration tests (mocked Firestore)
# ---------------------------------------------------------------------------


def _mock_query(docs):
    """Create a mock query that streams the given docs."""
    query = MagicMock()
    query.stream.return_value = iter(docs)
    query.limit.return_value = query
    return query


def _mock_collection(query):
    """Create a mock collection ref that returns query on .where()."""
    col = MagicMock()
    col.where.return_value = query
    col.order_by.return_value = query
    col.stream.side_effect = query.stream
    return col


def _setup_db_for_query(goals, docs):
    """Wire mock_db chain: db.collection().document().collection() returns a mock collection."""
    mock_db = goals.db
    mock_db.reset_mock()
    query = _mock_query(docs)
    col = _mock_collection(query)
    user_doc = MagicMock()
    user_doc.collection.return_value = col
    users_col = MagicMock()
    users_col.document.return_value = user_doc
    mock_db.collection.return_value = users_col
    return col


class TestGetUserGoal:
    def test_returns_id_from_doc_id_when_missing(self, goals):
        doc = FakeDoc("goal_rust_created", {"title": "Meditate", "is_active": True})
        _setup_db_for_query(goals, [doc])

        result = goals.get_user_goal("uid123")
        assert result is not None
        assert result["id"] == "goal_rust_created"


class TestGetUserGoals:
    def test_returns_ids_for_all_docs_when_missing(self, goals):
        docs = [
            FakeDoc("goal_1", {"title": "A", "is_active": True, "created_at": "2026-01-01"}),
            FakeDoc("goal_2", {"title": "B", "is_active": True, "created_at": "2026-01-02"}),
        ]
        _setup_db_for_query(goals, docs)

        results = goals.get_user_goals("uid123", limit=3)
        assert len(results) == 2
        assert results[0]["id"] == "goal_1"
        assert results[1]["id"] == "goal_2"


class TestGetAllGoals:
    @pytest.mark.parametrize("include_inactive", [True, False])
    def test_returns_id_from_doc_id_when_missing(self, goals, include_inactive):
        doc = FakeDoc("goal_no_id", {"title": "Read", "is_active": True, "created_at": "2026-01-01"})
        _setup_db_for_query(goals, [doc])

        results = goals.get_all_goals("uid123", include_inactive=include_inactive)
        assert len(results) == 1
        assert results[0]["id"] == "goal_no_id"
