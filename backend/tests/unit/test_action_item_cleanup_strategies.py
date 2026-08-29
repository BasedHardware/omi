"""
Tests for rule-based cleanup strategy functions in utils/action_item_cleanup.py.

Contract: strategies must correctly identify candidates for removal without
false-positives. A false deletion is worse than a missed stale task.

Heavy deps (Pinecone, Firebase, LangChain, database clients) are stubbed
before the module loads so no real infra is required.
"""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules

_BACKEND = Path(__file__).resolve().parents[2]


def _dt(days_ago: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days_ago)


def _item(id_, *, description="do something", due_at=None, created_at=None, conversation_id=None):
    return {
        "id": id_,
        "description": description,
        "completed": False,
        "due_at": due_at,
        "created_at": created_at if created_at is not None else _dt(0),
        "conversation_id": conversation_id,
    }


@pytest.fixture(scope="module")
def cleanup():
    """Load utils/action_item_cleanup.py fresh against faked heavy deps."""
    langchain_pkg = AutoMockModule("langchain_core")
    langchain_pkg.__path__ = []

    fakes = {
        "langchain_core": langchain_pkg,
        "langchain_core.prompts": AutoMockModule("langchain_core.prompts"),
        "database.action_items": AutoMockModule("database.action_items"),
        "database.conversations": AutoMockModule("database.conversations"),
        "database.vector_db": AutoMockModule("database.vector_db"),
        "utils.executors": AutoMockModule("utils.executors"),
        "utils.llm.clients": AutoMockModule("utils.llm.clients"),
    }
    with stub_modules(fakes):
        module = load_module_fresh(
            "utils.action_item_cleanup",
            os.path.join(str(_BACKEND), "utils", "action_item_cleanup.py"),
        )
        yield module


# ---------------------------------------------------------------------------
# _is_vague
# ---------------------------------------------------------------------------


class TestIsVague:
    def test_short_description_with_dangling_pronoun(self, cleanup):
        # "it" + "away" — unresolved referent
        assert cleanup._is_vague("put it away") is True

    def test_bare_demonstrative_pronoun(self, cleanup):
        assert cleanup._is_vague("fix those") is True

    def test_speaker_label_pattern(self, cleanup):
        assert cleanup._is_vague("Attend ultrasound with Speaker 1") is True

    def test_normal_task_not_vague(self, cleanup):
        assert cleanup._is_vague("Call the dentist to reschedule") is False

    def test_long_description_with_pronoun_not_vague(self, cleanup):
        # "it" appears in context — description is specific enough
        assert cleanup._is_vague("Review the Q3 budget report with Sarah before it closes") is False

    def test_two_word_dangling_task(self, cleanup):
        assert cleanup._is_vague("Send it") is True

    def test_empty_string_not_vague(self, cleanup):
        assert cleanup._is_vague("") is False

    @pytest.mark.parametrize(
        "description",
        [
            "Clean the kitchen",
            "Fix the sink",
            "Sort the laundry",
            "Change the oil",
            "Check the mail",
            "Return the library books",
        ],
    )
    def test_verb_plus_concrete_the_noun_not_vague(self, cleanup, description):
        # "the <noun>" names a concrete object — it's not a dangling reference like
        # "it"/"them"/"that", so these should not be flagged as vague.
        assert cleanup._is_vague(description) is False


def _mock_cleanup_page(cleanup, monkeypatch, items, next_cursor=None):
    monkeypatch.setattr(
        cleanup.action_items_db,
        "list_open_action_items_for_cleanup",
        lambda uid, cursor=None, limit=None: (items, next_cursor, len(items)),
    )


class TestCandidatesStaleAge:
    def test_old_task_without_due_date_is_candidate(self, cleanup, monkeypatch):
        items = [_item("old-1", created_at=_dt(100))]
        _mock_cleanup_page(cleanup, monkeypatch, items)
        monkeypatch.setattr(cleanup.conversations_db, "get_conversation", lambda *a, **kw: None)

        result, _ = cleanup.candidates_stale_age("uid", age_days=90)

        assert [c["id"] for c in result] == ["old-1"]
        assert result[0]["strategy"] == "stale_age"

    def test_young_task_not_a_candidate(self, cleanup, monkeypatch):
        items = [_item("young-1", created_at=_dt(10))]
        _mock_cleanup_page(cleanup, monkeypatch, items)
        monkeypatch.setattr(cleanup.conversations_db, "get_conversation", lambda *a, **kw: None)

        result, _ = cleanup.candidates_stale_age("uid", age_days=90)

        assert result == []

    def test_old_task_with_due_date_skipped(self, cleanup, monkeypatch):
        # Tasks with a due date are actively scheduled — never stale-age candidates.
        items = [_item("old-due", created_at=_dt(100), due_at=_dt(-5))]
        _mock_cleanup_page(cleanup, monkeypatch, items)
        monkeypatch.setattr(cleanup.conversations_db, "get_conversation", lambda *a, **kw: None)

        result, _ = cleanup.candidates_stale_age("uid", age_days=90)

        assert result == []

    def test_uses_conversation_date_when_linked(self, cleanup, monkeypatch):
        # Task itself is recent but linked to an old conversation → candidate
        items = [_item("linked-1", created_at=_dt(5), conversation_id="conv-old")]
        conv = {"started_at": _dt(120)}
        _mock_cleanup_page(cleanup, monkeypatch, items)
        monkeypatch.setattr(
            cleanup.conversations_db,
            "get_conversation",
            lambda uid, cid: conv if cid == "conv-old" else None,
        )

        result, _ = cleanup.candidates_stale_age("uid", age_days=90)

        assert [c["id"] for c in result] == ["linked-1"]

    def test_young_conversation_suppresses_old_task(self, cleanup, monkeypatch):
        # Task itself is old but its conversation is recent → not a candidate
        items = [_item("linked-2", created_at=_dt(150), conversation_id="conv-new")]
        conv = {"started_at": _dt(5)}
        _mock_cleanup_page(cleanup, monkeypatch, items)
        monkeypatch.setattr(
            cleanup.conversations_db,
            "get_conversation",
            lambda uid, cid: conv if cid == "conv-new" else None,
        )

        result, _ = cleanup.candidates_stale_age("uid", age_days=90)

        assert result == []

    def test_task_with_none_created_at_skipped(self, cleanup, monkeypatch):
        item = _item("no-date")
        item["created_at"] = None
        _mock_cleanup_page(cleanup, monkeypatch, [item])
        monkeypatch.setattr(cleanup.conversations_db, "get_conversation", lambda *a, **kw: None)

        result, _ = cleanup.candidates_stale_age("uid", age_days=90)

        assert result == []


# ---------------------------------------------------------------------------
# candidates_overdue
# ---------------------------------------------------------------------------


class TestCandidatesOverdue:
    def test_overdue_task_is_candidate(self, cleanup, monkeypatch):
        items = [_item("overdue-1", due_at=_dt(45))]
        _mock_cleanup_page(cleanup, monkeypatch, items)

        result, _ = cleanup.candidates_overdue("uid", overdue_days=30)

        assert [c["id"] for c in result] == ["overdue-1"]
        assert result[0]["strategy"] == "overdue"

    def test_recent_due_date_not_candidate(self, cleanup, monkeypatch):
        items = [_item("recent-1", due_at=_dt(5))]
        _mock_cleanup_page(cleanup, monkeypatch, items)

        result, _ = cleanup.candidates_overdue("uid", overdue_days=30)

        assert result == []

    def test_task_without_due_at_skipped(self, cleanup, monkeypatch):
        items = [_item("no-due", due_at=None)]
        _mock_cleanup_page(cleanup, monkeypatch, items)

        result, _ = cleanup.candidates_overdue("uid", overdue_days=30)

        assert result == []

    def test_empty_list_returns_empty(self, cleanup, monkeypatch):
        _mock_cleanup_page(cleanup, monkeypatch, [])

        result, _ = cleanup.candidates_overdue("uid", overdue_days=30)

        assert result == []

    def test_locked_task_skipped(self, cleanup, monkeypatch):
        locked = _item("locked-1", due_at=_dt(45))
        locked["is_locked"] = True
        _mock_cleanup_page(cleanup, monkeypatch, [locked])

        result, _ = cleanup.candidates_overdue("uid", overdue_days=30)

        assert result == []


# ---------------------------------------------------------------------------
# candidates_vague
# ---------------------------------------------------------------------------


class TestCandidatesVague:
    def test_vague_task_is_candidate(self, cleanup, monkeypatch):
        items = [_item("vague-1", description="put it away")]
        _mock_cleanup_page(cleanup, monkeypatch, items)

        result, _ = cleanup.candidates_vague("uid")

        assert [c["id"] for c in result] == ["vague-1"]
        assert result[0]["strategy"] == "vague"

    def test_clear_task_not_candidate(self, cleanup, monkeypatch):
        items = [_item("clear-1", description="Call the dentist to reschedule")]
        _mock_cleanup_page(cleanup, monkeypatch, items)

        result, _ = cleanup.candidates_vague("uid")

        assert result == []

    def test_empty_task_list(self, cleanup, monkeypatch):
        _mock_cleanup_page(cleanup, monkeypatch, [])

        result, _ = cleanup.candidates_vague("uid")

        assert result == []

    def test_mixed_list_filters_correctly(self, cleanup, monkeypatch):
        items = [
            _item("v1", description="fix those"),
            _item("c1", description="Schedule dentist for Monday"),
            _item("v2", description="Send it"),
        ]
        _mock_cleanup_page(cleanup, monkeypatch, items)

        result, _ = cleanup.candidates_vague("uid")

        assert {c["id"] for c in result} == {"v1", "v2"}


# ---------------------------------------------------------------------------
# merge_candidates
# ---------------------------------------------------------------------------


class TestMergeCandidates:
    def test_deduplicates_same_id_across_lists(self, cleanup):
        a = [{"id": "t1", "description": "x", "strategy": "stale_age"}]
        b = [{"id": "t1", "description": "x", "strategy": "vague"}]

        result = cleanup.merge_candidates([a, b])

        assert len(result) == 1
        assert result[0]["id"] == "t1"

    def test_preserves_order_across_lists(self, cleanup):
        a = [
            {"id": "t1", "description": "x", "strategy": "stale_age"},
            {"id": "t2", "description": "y", "strategy": "stale_age"},
        ]
        b = [{"id": "t3", "description": "z", "strategy": "vague"}]

        result = cleanup.merge_candidates([a, b])

        assert [c["id"] for c in result] == ["t1", "t2", "t3"]

    def test_empty_input_returns_empty(self, cleanup):
        assert cleanup.merge_candidates([]) == []

    def test_all_unique_ids_included(self, cleanup):
        a = [{"id": "t1", "description": "x", "strategy": "stale_age"}]
        b = [{"id": "t2", "description": "y", "strategy": "overdue"}]

        result = cleanup.merge_candidates([a, b])

        assert {c["id"] for c in result} == {"t1", "t2"}

    def test_later_list_duplicate_not_added(self, cleanup):
        a = [{"id": "t1", "description": "x", "strategy": "stale_age"}]
        b = [
            {"id": "t1", "description": "x", "strategy": "overdue"},
            {"id": "t2", "description": "y", "strategy": "overdue"},
        ]

        result = cleanup.merge_candidates([a, b])

        ids = [c["id"] for c in result]
        assert ids.count("t1") == 1
        assert "t2" in ids
