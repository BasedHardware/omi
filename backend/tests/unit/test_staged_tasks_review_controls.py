"""Staged-task review controls: promote-by-id and clear-all.

Staged tasks are the buffer of AI-extracted task candidates a user reviews before they become
action items (Nik's #5079 "Task Detection Is Too Aggressive"). This adds the two missing review
verbs: promote a specific chosen candidate (POST /v1/staged-tasks/{task_id}/promote) and clear the
whole active queue in one call (DELETE /v1/staged-tasks).

- promote_staged_task now takes an optional task_id: when given it promotes that candidate through
  the same dedup/merge/create tail as the top-scored path (default task_id=None is unchanged).
- clear_staged_tasks batch-deletes only active (completed==False) staged tasks, preserving history.

Test isolation: the modules import cleanly, so they are imported normally and the collection is
faked via monkeypatch.setattr(staged_tasks_db, '_user_col'/'db') (no sys.modules mutation).
"""

import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from database import action_items as action_items_db
from database import staged_tasks as staged_tasks_db
import routers.staged_tasks as r


def _make_doc(doc_id, data):
    doc = MagicMock()
    doc.id = doc_id
    doc.to_dict.return_value = data
    return doc


def _stub_staged_by_id(monkeypatch, task_id, data):
    """Stub _user_col so document(task_id).get() returns a doc with `data` (exists=False if None)."""
    snap = MagicMock()
    snap.exists = data is not None
    snap.id = task_id
    snap.to_dict.return_value = data

    update_calls = {}
    ref = MagicMock()
    ref.get.return_value = snap
    ref.update.side_effect = lambda payload: update_calls.update(payload)

    fake_col = MagicMock()
    fake_col.document.return_value = ref
    monkeypatch.setattr(staged_tasks_db, "_user_col", lambda uid, name: fake_col)
    return fake_col, update_calls


def _stub_clear(monkeypatch, doc_ids):
    """Stub _user_col + db.batch for clear_staged_tasks."""
    fake_query = MagicMock()
    fake_query.select.return_value = fake_query
    fake_query.stream.return_value = iter([_make_doc(d, {}) for d in doc_ids])

    fake_col = MagicMock()
    fake_col.where.return_value = fake_query

    batch = MagicMock()
    monkeypatch.setattr(staged_tasks_db, "_user_col", lambda uid, name: fake_col)
    monkeypatch.setattr(staged_tasks_db, "db", MagicMock(batch=MagicMock(return_value=batch)))
    return fake_col, fake_query, batch


# --- promote_staged_task(task_id=...) ---


class TestPromoteById:
    def test_promotes_the_specified_candidate(self, monkeypatch):
        fake_col, update_calls = _stub_staged_by_id(
            monkeypatch, "staged-x", {"id": "staged-x", "description": "Unique task", "completed": False}
        )
        monkeypatch.setattr(action_items_db, "get_active_action_item_by_description", lambda uid, desc: None)
        monkeypatch.setattr(action_items_db, "create_action_item", lambda uid, data: "fresh-1")
        monkeypatch.setattr(
            action_items_db, "get_action_item", lambda uid, aid: {"id": aid, "description": "Unique task"}
        )

        result = staged_tasks_db.promote_staged_task("uid", task_id="staged-x")

        assert result == {"id": "fresh-1", "description": "Unique task"}
        fake_col.document.assert_any_call("staged-x")  # promoted the chosen doc, not a scored query
        assert update_calls.get("completed") is True

    def test_dedup_tail_still_applies_when_promoting_by_id(self, monkeypatch):
        _stub_staged_by_id(
            monkeypatch, "staged-y", {"id": "staged-y", "description": "Follow up on Volt", "completed": False}
        )
        existing = {"id": "existing-1", "description": "Follow up on Volt", "completed": False}
        monkeypatch.setattr(action_items_db, "get_active_action_item_by_description", lambda uid, desc: existing)
        create_called = []
        monkeypatch.setattr(
            action_items_db, "create_action_item", lambda uid, data: create_called.append(data) or "nope"
        )

        result = staged_tasks_db.promote_staged_task("uid", task_id="staged-y")

        assert result == existing
        assert create_called == []  # dedup guard fired instead of creating a duplicate

    def test_nonexistent_id_returns_none(self, monkeypatch):
        _stub_staged_by_id(monkeypatch, "ghost", None)  # snap.exists = False
        assert staged_tasks_db.promote_staged_task("uid", task_id="ghost") is None

    def test_already_completed_returns_none(self, monkeypatch):
        _stub_staged_by_id(monkeypatch, "done-1", {"id": "done-1", "description": "x", "completed": True})
        assert staged_tasks_db.promote_staged_task("uid", task_id="done-1") is None


# --- clear_staged_tasks ---


class TestClearStagedTasks:
    def test_deletes_active_and_returns_count(self, monkeypatch):
        fake_col, fake_query, batch = _stub_clear(monkeypatch, ["a", "b", "c"])
        count = staged_tasks_db.clear_staged_tasks("uid")
        assert count == 3
        assert batch.delete.call_count == 3
        batch.commit.assert_called_once()
        fake_col.where.assert_called_once()  # scoped, not an unfiltered wipe
        fake_query.select.assert_called_once()  # IDs-only projection

    def test_empty_queue_returns_zero_without_commit(self, monkeypatch):
        _fake_col, _fake_query, batch = _stub_clear(monkeypatch, [])
        assert staged_tasks_db.clear_staged_tasks("uid") == 0
        batch.delete.assert_not_called()
        batch.commit.assert_not_called()


# --- router handlers (called directly) ---


class TestRouterHandlers:
    def test_promote_by_id_success_shape(self, monkeypatch):
        monkeypatch.setattr(
            r.staged_tasks_db, "promote_staged_task", lambda uid, task_id: {"id": "a1", "description": "x"}
        )
        result = r.promote_staged_task_by_id("a1", uid="u1")
        assert result == {"promoted": True, "reason": None, "promoted_task": {"id": "a1", "description": "x"}}

    def test_promote_by_id_404_when_missing(self, monkeypatch):
        monkeypatch.setattr(r.staged_tasks_db, "promote_staged_task", lambda uid, task_id: None)
        with pytest.raises(HTTPException) as ei:
            r.promote_staged_task_by_id("ghost", uid="u1")
        assert ei.value.status_code == 404

    def test_clear_returns_deleted_count(self, monkeypatch):
        monkeypatch.setattr(r.staged_tasks_db, "clear_staged_tasks", lambda uid: 5)
        assert r.clear_staged_tasks(uid="u1") == {"status": "ok", "deleted_count": 5}
