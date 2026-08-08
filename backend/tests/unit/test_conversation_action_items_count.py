"""Unit tests for the per-conversation action-items count.

GET /v1/conversations/{conversation_id}/action-items/count returns a task-progress
summary (total / completed / incomplete) for one conversation via store count()
aggregation over the same conversation_id predicate the list uses. Soft-retired items
(``deleted: true``) are hidden from the list/read paths, so the count excludes them too.
These pin the arithmetic and the deleted-exclusion; the endpoint's ownership check and
passthrough are covered by the Public Developer API contract check.

The two count() aggregations are non-atomic, so a racing write can report completed > total.
The store cannot produce that from consistent data, so a tiny scripted store stands in for the
count() seam to exercise the clamp; the deleted-exclusion path uses real ``query`` results.
"""

import os
from types import SimpleNamespace

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

import database.action_items as ai_db  # noqa: E402


class _ScriptedCountStore:
    """Minimal DocumentStore stand-in for get_action_items_count_by_conversation.

    ``count`` returns the scripted total/completed aggregations (letting a test force the
    completed > total race the clamp guards against); ``query`` returns the scripted soft-retired
    docs the deleted-exclusion path streams.
    """

    def __init__(self, total, completed, deleted_docs):
        self._total = total
        self._completed = completed
        self._deleted_docs = deleted_docs

    def count(self, path, *, filters=None):
        filters = list(filters or [])
        if ('completed', '==', True) in filters:
            return self._completed
        return self._total

    def query(self, path, *, filters=None, **kwargs):
        return self._deleted_docs


def _deleted_doc(completed):
    return SimpleNamespace(to_dict=lambda: {"completed": completed, "deleted": True})


def test_count_by_conversation_arithmetic(monkeypatch):
    store = _ScriptedCountStore(total=3, completed=1, deleted_docs=[])
    monkeypatch.setattr(ai_db, "_store", lambda: store)

    result = ai_db.get_action_items_count_by_conversation("u1", "c1")

    assert result == {"total": 3, "completed": 1, "incomplete": 2}


def test_count_by_conversation_never_negative(monkeypatch):
    # completed's aggregation (4) exceeds total's (1) from a racing write; completed is capped to
    # total so the badge is self-consistent (completed <= total, total == completed + incomplete).
    store = _ScriptedCountStore(total=1, completed=4, deleted_docs=[])
    monkeypatch.setattr(ai_db, "_store", lambda: store)

    result = ai_db.get_action_items_count_by_conversation("u1", "c1")

    assert result == {"total": 1, "completed": 1, "incomplete": 0}


def test_count_by_conversation_excludes_soft_retired(monkeypatch):
    # Regression: deleted items in the conversation must not inflate the badge, matching the list
    # path which skips data.get('deleted').
    store = _ScriptedCountStore(
        total=4,  # 4 total, of which 2 are deleted
        completed=2,  # 2 completed, 1 deleted
        deleted_docs=[_deleted_doc(completed=True), _deleted_doc(completed=False)],
    )
    monkeypatch.setattr(ai_db, "_store", lambda: store)

    result = ai_db.get_action_items_count_by_conversation("u1", "c1")

    # visible total = 4 - 2 = 2; visible completed = 2 - 1 = 1; incomplete = 2 - 1 = 1
    assert result == {"total": 2, "completed": 1, "incomplete": 1}
