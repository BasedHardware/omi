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
        page = rows[start:end]
        # Firestore bills streamed documents, so the count is the cost this scan pays.
        self.collection.streamed += len(page)
        return page


class _FakeCollection:
    def __init__(self, rows):
        self.rows = rows
        self.streamed = 0

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


def test_a_clean_page_streams_no_more_documents_than_it_returns():
    """No reported rows means no slack: the read costs exactly what the page needs.

    The first version of this scan floored the budget at 100 and read a flat
    100-document first batch, so the chat-send path's limit=5 / limit=15 history
    reads streamed ~20x the documents the old raw query did. Slack must be paid
    only by a page that actually meets a reported row.
    """
    collection = _FakeCollection([_message(f'visible-{i}') for i in range(500)])
    with _patch_db(collection):
        page = chat_db.get_messages('uid', limit=5, offset=0)

    assert [row['id'] for row in page] == [f'visible-{i}' for i in range(5)]
    assert collection.streamed == 5


def test_a_deep_offset_is_still_serviced_rather_than_reported_as_end_of_results():
    """A deep offset must return its page, not an empty one.

    Capping the *total* scan (min(1000, ...)) meant offset + limit beyond the cap
    could never be reached, so the page came back empty. routers/chat.py reads an
    empty page as end-of-results, which is the same "later visible messages are
    never fetched" defect this scan exists to fix — reintroduced at depth. The
    budget therefore floors at the rows the page needs and bounds only the slack.
    """
    collection = _FakeCollection([_message(f'visible-{i}') for i in range(1300)])
    with _patch_db(collection):
        page = chat_db.get_messages('uid', limit=5, offset=1200)

    assert [row['id'] for row in page] == [f'visible-{i}' for i in range(1200, 1205)]


def test_slack_is_bounded_even_when_every_scanned_row_is_reported():
    """The scan still terminates on a page that can never be filled.

    Flooring the budget at the page size must not turn into an unbounded stream
    when reported rows are dense: the slack above the floor is what is capped.
    """
    collection = _FakeCollection([_message(f'reported-{i}', reported=True) for i in range(5000)])
    with _patch_db(collection):
        page = chat_db.get_messages('uid', limit=10, offset=0)

    assert page == []
    needed = 10
    assert collection.streamed <= needed + chat_db.CHAT_MESSAGES_VISIBLE_PAGE_SCAN_SLACK


def test_scan_continues_across_batches_through_a_dense_block_of_reported_rows():
    """A page must still fill across batches when many reported rows sit ahead of it.

    Scaling the slack with the page size gave limit=2 an allowance of six documents,
    so a run of reported rows longer than that returned an empty page — which
    routers/chat.py reads as end-of-results, the same defect this scan exists to fix.
    """
    rows = [_message(f'reported-{i}', reported=True) for i in range(150)]
    rows += [_message('visible-a'), _message('visible-b')]
    collection = _FakeCollection(rows)

    with _patch_db(collection):
        page = chat_db.get_messages('uid', limit=2, offset=0)

    assert [row['id'] for row in page] == ['visible-a', 'visible-b']
    assert collection.streamed > 2, 'the page must have required more than its own rows'
