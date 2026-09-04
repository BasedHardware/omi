"""get_memories scoring_desc must fill `limit` with *visible* rows.

Firestore applies limit/offset before Python drops user-rejected
(``user_review is False``) and invalidated (``invalid_at`` set) rows. A hidden
row in the middle of a raw page therefore returns a short visible page and
leaves later visible memories unfetched — callers that stop after one page
(or treat len < limit as EOF) never see them.

Same failure class as chat ``get_messages`` reported pagination: raw page
limit before the visibility filter. This pins it against a fake that mirrors
Firestore offset+limit (broken) and start_after scan (fixed) semantics.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import database.memories as memories_db


class _FakeDoc:
    def __init__(self, data: Dict[str, Any]):
        self.id = data['id']
        self._data = dict(data)

    def to_dict(self):
        return dict(self._data)


class _FakeQuery:
    def __init__(
        self,
        docs: List[_FakeDoc],
        *,
        filters: Optional[List] = None,
        requested_offset: int = 0,
        requested_limit: Optional[int] = None,
    ):
        self._docs = docs
        self._filters = list(filters or [])
        self.requested_offset = requested_offset
        self.requested_limit = requested_limit

    def where(self, *args, **kwargs):
        filt = kwargs.get('filter') or (args[0] if args else None)
        return _FakeQuery(
            self._docs,
            filters=self._filters + [filt],
            requested_offset=self.requested_offset,
            requested_limit=self.requested_limit,
        )

    def order_by(self, *args, **kwargs):
        return self

    def select(self, fields):
        return self

    def offset(self, value: int):
        return _FakeQuery(
            self._docs,
            filters=self._filters,
            requested_offset=value,
            requested_limit=self.requested_limit,
        )

    def limit(self, value: int):
        return _FakeQuery(
            self._docs,
            filters=self._filters,
            requested_offset=self.requested_offset,
            requested_limit=value,
        )

    def start_after(self, document):
        start = next(i for i, row in enumerate(self._docs) if row.id == document.id) + 1
        return _FakeQuery(
            self._docs,
            filters=self._filters,
            requested_offset=start,
            requested_limit=self.requested_limit,
        )

    def stream(self):
        rows = self._docs
        start = self.requested_offset
        end = start + (self.requested_limit if self.requested_limit is not None else len(rows))
        for doc in rows[start:end]:
            yield _FakeDoc({'id': doc.id, **doc._data})


class _FakeDB:
    def __init__(self, docs: List[_FakeDoc]):
        self._docs = docs

    def collection(self, _name: str):
        return self

    def document(self, _uid: str):
        return SimpleNamespace(collection=self._user_collection)

    def _user_collection(self, _name: str):
        return _FakeQuery(self._docs)


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


def _call_scoring_page(docs: List[_FakeDoc], *, limit: int, offset: int = 0):
    fake_db = _FakeDB(docs)
    with patch.object(memories_db, '_prepare_memory_for_read', side_effect=lambda data, _uid: data):
        return memories_db.get_memories(
            'uid-scoring-vis',
            limit=limit,
            offset=offset,
            sort='scoring_desc',
            firestore_client=fake_db,
        )


def test_rejected_row_in_middle_of_page_does_not_shorten_visible_limit():
    """user_review=False in the raw page must not steal a visible slot.

    Scoring stream: visible-a, rejected, visible-b, visible-c.
    limit=2 must return [visible-a, visible-b], not a short [visible-a] that
    leaves visible-b unfetched for single-page / len<limit EOF callers.
    """
    docs = [
        _FakeDoc(_memory_row('visible-a')),
        _FakeDoc(_memory_row('rejected', user_review=False)),
        _FakeDoc(_memory_row('visible-b')),
        _FakeDoc(_memory_row('visible-c')),
    ]
    page = _call_scoring_page(docs, limit=2, offset=0)
    assert [row['id'] for row in page] == ['visible-a', 'visible-b']


def test_invalidated_row_in_middle_of_page_does_not_shorten_visible_limit():
    """invalid_at in the raw page must not steal a visible slot either."""
    docs = [
        _FakeDoc(_memory_row('visible-a')),
        _FakeDoc(_memory_row('gone', invalid_at=datetime(2026, 1, 2, tzinfo=timezone.utc))),
        _FakeDoc(_memory_row('visible-b')),
    ]
    page = _call_scoring_page(docs, limit=2, offset=0)
    assert [row['id'] for row in page] == ['visible-a', 'visible-b']


def test_offset_advances_by_visible_rows_not_raw_firestore_slots():
    """Page-2 offset must skip visible rows only, matching what page 1 returned.

    After a full visible page of 2, offset=2 must continue at visible-c — not
    jump past it because rejected/invalid rows inflated the raw Firestore offset.
    """
    docs = [
        _FakeDoc(_memory_row('visible-a')),
        _FakeDoc(_memory_row('rejected-1', user_review=False)),
        _FakeDoc(_memory_row('visible-b')),
        _FakeDoc(_memory_row('gone', invalid_at=datetime(2026, 1, 2, tzinfo=timezone.utc))),
        _FakeDoc(_memory_row('visible-c')),
        _FakeDoc(_memory_row('visible-d')),
    ]
    first = _call_scoring_page(docs, limit=2, offset=0)
    second = _call_scoring_page(docs, limit=2, offset=2)
    assert [row['id'] for row in first] == ['visible-a', 'visible-b']
    assert [row['id'] for row in second] == ['visible-c', 'visible-d']
