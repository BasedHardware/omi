"""Tests for goal ID fallback in database/goals.py.

Verifies that _goal_dict() correctly injects doc.id when the 'id' field
is missing from stored document data (issue #5671).

database.goals reads through the neutral storage port (``_store()``); the read-path tests bind a
``FakeDocumentStore`` to that seam and seed the user's goal collection directly.
"""

import os

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

import pytest

import database.goals as goals_module
from tests.store_fakes import FakeDocumentStore


@pytest.fixture
def goals(monkeypatch):
    """database.goals bound to an in-memory FakeDocumentStore through the ``_store()`` seam."""
    store = FakeDocumentStore()
    monkeypatch.setattr(goals_module, "_store", lambda: store)
    return goals_module


class FakeDoc:
    """Minimal Firestore document snapshot mock."""

    def __init__(self, doc_id: str, data: dict):
        self.id = doc_id
        self._data = data
        self.exists = True

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
# Read-path integration tests (FakeDocumentStore through the _store() seam)
# ---------------------------------------------------------------------------


def _seed_goals(goals, uid, docs):
    """Seed the user's goal collection with stored id-less rows (doc_id carried by the path)."""
    store = goals._store()
    for doc_id, data in docs:
        store.set(f"users/{uid}/goals/{doc_id}", dict(data))


class TestGetUserGoal:
    def test_returns_id_from_doc_id_when_missing(self, goals):
        _seed_goals(goals, "uid123", [("goal_rust_created", {"title": "Meditate", "is_active": True})])

        result = goals.get_user_goal("uid123")
        assert result is not None
        assert result["id"] == "goal_rust_created"


class TestGetUserGoals:
    def test_returns_ids_for_all_docs_when_missing(self, goals):
        _seed_goals(
            goals,
            "uid123",
            [
                ("goal_1", {"title": "A", "is_active": True, "created_at": "2026-01-01"}),
                ("goal_2", {"title": "B", "is_active": True, "created_at": "2026-01-02"}),
            ],
        )

        results = goals.get_user_goals("uid123", limit=3)
        assert len(results) == 2
        assert {r["id"] for r in results} == {"goal_1", "goal_2"}


class TestGetAllGoals:
    @pytest.mark.parametrize("include_inactive", [True, False])
    def test_returns_id_from_doc_id_when_missing(self, goals, include_inactive):
        _seed_goals(goals, "uid123", [("goal_no_id", {"title": "Read", "is_active": True, "created_at": "2026-01-01"})])

        results = goals.get_all_goals("uid123", include_inactive=include_inactive)
        assert len(results) == 1
        assert results[0]["id"] == "goal_no_id"


class TestQualitativeGoalAliases:
    def test_new_qualitative_goal_omits_fake_metric_aliases(self, goals):
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        payload = goals._new_goal_payload(
            {
                'title': 'Launch desktop',
                'desired_outcome': 'Ship a trustworthy release',
                'why_it_matters': 'Users rely on it',
                'success_criteria': ['Signed build ships'],
            },
            goal_id='goal_qualitative',
            now=now,
        )

        assert payload['metric'] is None
        assert 'goal_type' not in payload
        assert 'target_value' not in payload
        assert 'max_value' not in payload

    def test_normalize_qualitative_goal_preserves_metric_without_scale_projection(self, goals):
        normalized = goals.normalize_goal_storage(
            {
                'id': 'goal_qualitative',
                'title': 'Launch desktop',
                'desired_outcome': 'Ship a trustworthy release',
                'metric': None,
            },
            goal_id='goal_qualitative',
        )

        assert normalized['metric'] is None
        assert 'goal_type' not in normalized
        assert 'max_value' not in normalized
