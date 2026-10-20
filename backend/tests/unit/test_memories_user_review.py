"""
Tests for get_memories user_review filtering logic.
Regression test for issue #4498: KeyError when user_review field missing.

Also guards the decision to keep the filter in Python: Firestore cannot express
``user_review is not False`` without dropping legacy docs that omit the field.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import pytest

import database.memories as memories_db


class _FakeDoc:
    def __init__(self, data: Dict[str, Any]):
        self.id = data['id']
        self._data = dict(data)

    def to_dict(self):
        return dict(self._data)


class _RecordingQuery:
    def __init__(self, db: "_FakeDB", docs: List[_FakeDoc], filters: Optional[List] = None):
        self._db = db
        self._docs = docs
        self._filters = list(filters or [])
        self._limit = None
        self._offset = 0
        self._db.last_query = self

    @property
    def recorded_filters(self) -> List[Any]:
        return self._filters

    def where(self, *args, **kwargs):
        filt = kwargs.get('filter') or (args[0] if args else None)
        q = _RecordingQuery(self._db, self._docs, self._filters + [filt])
        q._limit = self._limit
        q._offset = self._offset
        return q

    def order_by(self, *args, **kwargs):
        return self

    def select(self, fields):
        return self

    def offset(self, n: int):
        q = _RecordingQuery(self._db, self._docs, self._filters)
        q._limit = self._limit
        q._offset = n
        return q

    def limit(self, n: int):
        q = _RecordingQuery(self._db, self._docs, self._filters)
        q._limit = n
        q._offset = self._offset
        return q

    def stream(self):
        docs = self._docs
        if self._offset:
            docs = docs[self._offset :]
        if self._limit is not None:
            docs = docs[: self._limit]
        for doc in docs:
            yield _FakeDoc({'id': doc.id, **doc._data})


class _FakeDB:
    def __init__(self, docs: List[_FakeDoc]):
        self._docs = docs
        self.last_query: Optional[_RecordingQuery] = None

    def collection(self, _name: str):
        return self

    def document(self, _uid: str):
        return SimpleNamespace(collection=self._user_collection)

    def _user_collection(self, _name: str):
        return _RecordingQuery(self, self._docs)


def _memory_row(memory_id: str, **fields: Any) -> Dict[str, Any]:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    row = {
        'id': memory_id,
        'content': memory_id,
        'category': 'interesting',
        'created_at': now,
        'updated_at': now,
        'scoring': 1.0,
    }
    row.update(fields)
    return row


class TestUserReviewFilterLogic:
    """
    Test the user_review filtering logic used in get_memories().

    The filter: memory.get('user_review') is not False

    Expected behavior:
    - Missing user_review field -> included (get returns None, None is not False)
    - user_review=None -> included (None is not False)
    - user_review=True -> included (True is not False)
    - user_review=False -> excluded (False is not False = False)
    """

    def filter_memories(self, memories: list) -> list:
        """Use the production list visibility helper."""
        return [
            memory
            for memory in memories
            if memories_db._memory_passes_list_visibility(memory, include_invalidated=False)
        ]

    def test_memory_without_user_review_field_included(self):
        """Memory without user_review field should be included (not crash with KeyError)."""
        memories = [{'id': '1', 'content': 'test memory'}]
        result = self.filter_memories(memories)
        assert len(result) == 1
        assert result[0]['id'] == '1'

    def test_memory_with_user_review_none_included(self):
        """Memory with user_review=None should be included."""
        memories = [{'id': '1', 'user_review': None}]
        result = self.filter_memories(memories)
        assert len(result) == 1

    def test_memory_with_user_review_false_excluded(self):
        """Memory with user_review=False should be excluded."""
        memories = [{'id': '1', 'user_review': False}]
        result = self.filter_memories(memories)
        assert len(result) == 0

    def test_memory_with_user_review_true_included(self):
        """Memory with user_review=True should be included."""
        memories = [{'id': '1', 'user_review': True}]
        result = self.filter_memories(memories)
        assert len(result) == 1

    def test_mixed_user_review_values(self):
        """Test filtering with mixed user_review values."""
        memories = [
            {'id': '1'},  # missing field - included
            {'id': '2', 'user_review': None},  # None - included
            {'id': '3', 'user_review': True},  # True - included
            {'id': '4', 'user_review': False},  # False - excluded
        ]
        result = self.filter_memories(memories)

        assert len(result) == 3
        result_ids = [m['id'] for m in result]
        assert '1' in result_ids
        assert '2' in result_ids
        assert '3' in result_ids
        assert '4' not in result_ids

    def test_invalid_at_excluded_unless_requested(self):
        memories = [
            {'id': 'active'},
            {'id': 'gone', 'invalid_at': datetime(2026, 1, 2, tzinfo=timezone.utc)},
        ]
        assert [m['id'] for m in self.filter_memories(memories)] == ['active']
        kept = [
            memory
            for memory in memories
            if memories_db._memory_passes_list_visibility(memory, include_invalidated=True)
        ]
        assert [m['id'] for m in kept] == ['active', 'gone']

    def test_old_behavior_would_keyerror(self):
        """
        Verify that the old behavior (direct dict access) would raise KeyError.
        This confirms the bug existed and our fix addresses it.
        """
        memories = [{'id': '1', 'content': 'test memory'}]  # no user_review field

        with pytest.raises(KeyError):
            # Old buggy code: memory['user_review']
            _ = [memory for memory in memories if memory['user_review'] is not False]


def test_get_memories_scoring_path_filters_user_review_in_python_not_firestore():
    """Scoring list omits a user_review FieldFilter; Python keeps missing-field rows.

    A Firestore ``!= False`` / ``not-in [False]`` would exclude docs that omit
    ``user_review``, changing GET /v3/memories results for legacy data (#4498).
    """
    docs = [
        _FakeDoc(_memory_row('keep-missing')),
        _FakeDoc(_memory_row('keep-none', user_review=None)),
        _FakeDoc(_memory_row('keep-true', user_review=True)),
        _FakeDoc(_memory_row('drop-false', user_review=False)),
        _FakeDoc(
            _memory_row(
                'drop-invalid',
                user_review=True,
                invalid_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            )
        ),
    ]
    fake_db = _FakeDB(docs)

    with patch.object(memories_db, '_prepare_memory_for_read', side_effect=lambda data, _uid: data):
        result = memories_db.get_memories(
            'uid-review', limit=10, offset=0, sort='scoring_desc', firestore_client=fake_db
        )

    assert [row['id'] for row in result] == ['keep-missing', 'keep-none', 'keep-true']
    assert fake_db.last_query is not None
    filter_fields = [
        getattr(filt, 'field_path', None) or getattr(filt, 'field', None)
        for filt in fake_db.last_query.recorded_filters
    ]
    assert 'user_review' not in filter_fields
    assert 'invalid_at' not in filter_fields


def test_merge_memory_list_index_docs_applies_same_visibility_helper():
    class _Doc:
        def __init__(self, payload):
            self.id = payload['id']
            self._payload = payload

        def to_dict(self):
            return dict(self._payload)

    docs = [
        _Doc(_memory_row('a', user_review=False)),
        _Doc(_memory_row('b')),
        _Doc(_memory_row('c', user_review=True, invalid_at=datetime(2026, 1, 3, tzinfo=timezone.utc))),
    ]
    merged = memories_db._merge_memory_list_index_docs(docs, include_invalidated=False)
    assert [row['id'] for row in merged] == ['b']


def _at_hour(hour: int) -> datetime:
    return datetime(2026, 1, 1, hour, tzinfo=timezone.utc)


def test_updated_or_created_index_fills_the_page_past_hidden_rows(monkeypatch):
    """Rejected or invalidated rows inside a candidate window must not shorten the page.

    MemoryService and HistoricalMemoryAdapter read a short index page as end-of-data,
    so the visible rows behind the hidden ones were never returned.
    """
    rows = [
        _memory_row('m1', created_at=_at_hour(6), updated_at=_at_hour(6)),
        _memory_row('m2', created_at=_at_hour(5), updated_at=_at_hour(5), user_review=False),
        _memory_row('m3', created_at=_at_hour(4), updated_at=_at_hour(4), invalid_at=_at_hour(7)),
        _memory_row('m4', created_at=_at_hour(3), updated_at=_at_hour(3)),
        # Legacy row without updated_at: only the created_at window can return it.
        _memory_row('m5', created_at=_at_hour(2), updated_at=None),
        _memory_row('m6', created_at=_at_hour(1), updated_at=_at_hour(1)),
    ]

    def fake_window(_memories_ref, order_field, candidate_limit, *, budget=None, cursor_snapshot=None):
        # Firestore order_by: newest first, rows missing the field excluded.
        ordered = sorted(
            (row for row in rows if row.get(order_field) is not None),
            key=lambda row: (row[order_field], row['id']),
            reverse=True,
        )
        if cursor_snapshot is not None:
            index = next(i for i, row in enumerate(ordered) if row['id'] == cursor_snapshot.id)
            ordered = ordered[index + 1 :]
        return [_FakeDoc(row) for row in ordered[:candidate_limit]]

    monkeypatch.setattr(memories_db, '_stream_memory_list_index_window', fake_window)

    def page_ids(limit: int, offset: int) -> List[str]:
        page = memories_db.list_memory_updated_or_created_index(
            'uid-review', limit=limit, offset=offset, firestore_client=_FakeDB([])
        )
        return [row['id'] for row in page]

    assert page_ids(3, 0) == ['m1', 'm4', 'm5']
    assert page_ids(2, 0) + page_ids(2, 2) == ['m1', 'm4', 'm5', 'm6']
