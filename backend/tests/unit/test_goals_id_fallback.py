"""Tests for goal ID fallback in database/goals.py.

Verifies that _goal_dict() correctly injects doc.id when the 'id' field
is missing from Firestore document data (issue #5671).
"""

import os
import sys
import types
from unittest.mock import MagicMock

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _stub_module(name: str) -> types.ModuleType:
    if name not in sys.modules:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return sys.modules[name]


# --- Stub the Firestore client chain to avoid GCP credential lookup ---
# Must happen before importing database.goals
_stub_module("google")
google_mod = sys.modules["google"]
if not hasattr(google_mod, "__path__"):
    google_mod.__path__ = []

_stub_module("google.cloud")
gc_mod = sys.modules["google.cloud"]
if not hasattr(gc_mod, "__path__"):
    gc_mod.__path__ = []

firestore_mod = _stub_module("google.cloud.firestore")
firestore_mod.Client = MagicMock()
firestore_mod.Query = MagicMock()

fv1_mod = _stub_module("google.cloud.firestore_v1")
fv1_mod.FieldFilter = MagicMock()

# Stub database package
database_mod = _stub_module("database")
if not hasattr(database_mod, "__path__"):
    database_mod.__path__ = []

# Stub database._client with a mock db
client_mod = _stub_module("database._client")
mock_db = MagicMock()
client_mod.db = mock_db

# Now import the real goals module
import importlib

if "database.goals" in sys.modules:
    del sys.modules["database.goals"]

# Manually load the real goals.py
import importlib.util

_goals_path = os.path.join(os.path.dirname(__file__), "..", "..", "database", "goals.py")
_goals_path = os.path.normpath(_goals_path)
spec = importlib.util.spec_from_file_location("database.goals", _goals_path,
                                                submodule_search_locations=[])
goals_mod = importlib.util.module_from_spec(spec)
sys.modules["database.goals"] = goals_mod
spec.loader.exec_module(goals_mod)

_goal_dict = goals_mod._goal_dict
get_user_goal = goals_mod.get_user_goal
get_user_goals = goals_mod.get_user_goals
get_all_goals = goals_mod.get_all_goals


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
    def test_injects_doc_id_when_id_missing(self):
        doc = FakeDoc("goal_abc123", {"title": "Run 5k", "is_active": True})
        result = _goal_dict(doc)
        assert result["id"] == "goal_abc123"

    def test_injects_doc_id_when_id_empty_string(self):
        doc = FakeDoc("goal_abc123", {"id": "", "title": "Run 5k"})
        result = _goal_dict(doc)
        assert result["id"] == "goal_abc123"

    def test_injects_doc_id_when_id_none(self):
        doc = FakeDoc("goal_abc123", {"id": None, "title": "Run 5k"})
        result = _goal_dict(doc)
        assert result["id"] == "goal_abc123"

    def test_preserves_existing_id(self):
        doc = FakeDoc("goal_abc123", {"id": "goal_existing", "title": "Run 5k"})
        result = _goal_dict(doc)
        assert result["id"] == "goal_existing"

    def test_handles_none_to_dict(self):
        """to_dict() returning None (empty snapshot) should not crash."""
        doc = FakeDoc("goal_abc123", {})
        doc.to_dict = lambda: None
        result = _goal_dict(doc)
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
    return col


def _setup_db_for_query(docs):
    """Wire mock_db chain: db.collection().document().collection() returns a mock collection."""
    mock_db.reset_mock()
    query = _mock_query(docs)
    col = _mock_collection(query)
    # Wire: db.collection('users').document(uid).collection('goals')
    user_doc = MagicMock()
    user_doc.collection.return_value = col
    users_col = MagicMock()
    users_col.document.return_value = user_doc
    mock_db.collection.return_value = users_col
    # Also set goals_mod.db to our mock (in case import cached a different ref)
    goals_mod.db = mock_db
    return col


class TestGetUserGoal:
    def test_returns_id_from_doc_id_when_missing(self):
        doc = FakeDoc("goal_rust_created", {"title": "Meditate", "is_active": True})
        _setup_db_for_query([doc])

        result = get_user_goal("uid123")
        assert result is not None
        assert result["id"] == "goal_rust_created"


class TestGetUserGoals:
    def test_returns_ids_for_all_docs_when_missing(self):
        docs = [
            FakeDoc("goal_1", {"title": "A", "is_active": True, "created_at": "2026-01-01"}),
            FakeDoc("goal_2", {"title": "B", "is_active": True, "created_at": "2026-01-02"}),
        ]
        _setup_db_for_query(docs)

        results = get_user_goals("uid123", limit=3)
        assert len(results) == 2
        assert results[0]["id"] == "goal_1"
        assert results[1]["id"] == "goal_2"


class TestGetAllGoals:
    @pytest.mark.parametrize("include_inactive", [True, False])
    def test_returns_id_from_doc_id_when_missing(self, include_inactive):
        doc = FakeDoc("goal_no_id", {"title": "Read", "is_active": True, "created_at": "2026-01-01"})
        _setup_db_for_query([doc])

        results = get_all_goals("uid123", include_inactive=include_inactive)
        assert len(results) == 1
        assert results[0]["id"] == "goal_no_id"
