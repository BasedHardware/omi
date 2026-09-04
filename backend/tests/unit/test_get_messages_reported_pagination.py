"""get_messages must fill `limit` with *visible* rows when reported rows sit in the page.

Firestore applies limit/offset before Python drops `reported is True`. A reported row
in the middle of a raw page therefore returns a short visible page and leaves
later visible messages unfetched — callers that stop after one page (or treat
len < limit as EOF) never see them.

This pins the failure class against a fake that mirrors Firestore offset+limit
semantics. It must fail on main before the scan-budget fix and pass after.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import database.chat as chat_db


class _FakeDocument:
    def __init__(self, document_id, data):
        self.id = document_id
        self._data = data

    def to_dict(self):
        return dict(self._data)


class _FakeQuery:
    def __init__(self, collection, *, requested_offset=0, requested_limit=None):
        self.collection = collection
        self.requested_offset = requested_offset
        self.requested_limit = requested_limit

    def where(self, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def offset(self, value):
        return _FakeQuery(self.collection, requested_offset=value, requested_limit=self.requested_limit)

    def limit(self, value):
        return _FakeQuery(self.collection, requested_offset=self.requested_offset, requested_limit=value)

    def start_after(self, document):
        # Keyset resume used by the scan-budget fix; rows stay newest-first.
        start = next(i for i, row in enumerate(self.collection.rows) if row.id == document.id) + 1
        return _FakeQuery(self.collection, requested_offset=start, requested_limit=self.requested_limit)

    def stream(self):
        rows = self.collection.rows
        start = self.requested_offset
        end = start + (self.requested_limit if self.requested_limit is not None else len(rows))
        return rows[start:end]


class _FakeCollection:
    def __init__(self, rows):
        self.rows = rows

    def where(self, **_kwargs):
        return _FakeQuery(self)

    def order_by(self, *_args, **_kwargs):
        return _FakeQuery(self)


def _message(document_id, *, reported=False):
    return _FakeDocument(
        document_id,
        {
            'id': document_id,
            'text': document_id,
            'sender': 'human',
            'type': 'text',
            'created_at': datetime.now(timezone.utc),
            'plugin_id': None,
            'app_id': None,
            'reported': reported,
            'memories_id': [],
            'files_id': [],
        },
    )


def _patch_db(collection):
    patched_db = MagicMock()
    patched_db.collection.return_value.document.return_value.collection.return_value = collection
    return patch.object(chat_db, 'db', patched_db)


def test_reported_row_in_middle_of_page_does_not_shorten_visible_limit():
    """Reported in the raw page must not steal a visible slot from later messages.

    Newest-first stream: visible-a, reported, visible-b, visible-c.
    limit=2 must return [visible-a, visible-b], not a short [visible-a] that
    leaves visible-b unfetched for single-page callers.
    """
    collection = _FakeCollection(
        [
            _message('visible-a'),
            _message('reported', reported=True),
            _message('visible-b'),
            _message('visible-c'),
        ]
    )
    with _patch_db(collection):
        page = chat_db.get_messages('uid', limit=2, offset=0)

    assert [row['id'] for row in page] == ['visible-a', 'visible-b']


def test_offset_advances_by_visible_rows_not_raw_firestore_slots():
    """Page-2 offset must skip visible rows only, matching what page 1 returned.

    After a full visible page of 2, offset=2 must continue at visible-c — not
    jump past it because reported rows inflated the raw Firestore offset.
    """
    collection = _FakeCollection(
        [
            _message('visible-a'),
            _message('reported-1', reported=True),
            _message('visible-b'),
            _message('reported-2', reported=True),
            _message('visible-c'),
            _message('visible-d'),
        ]
    )
    with _patch_db(collection):
        first = chat_db.get_messages('uid', limit=2, offset=0)
        second = chat_db.get_messages('uid', limit=2, offset=2)

    assert [row['id'] for row in first] == ['visible-a', 'visible-b']
    assert [row['id'] for row in second] == ['visible-c', 'visible-d']
