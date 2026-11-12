"""Regression: hidden rows in an MCP conversation offset window.

``get_conversations`` with ``offset > 0`` reads ``limit + 1`` stored rows at
that offset. Soft-deleted tombstones and legacy rule discards still match the
indexed ``discarded == False`` filter and are dropped in Python, so each one
used to cost the page a slot: the page came back short with ``has_more`` false
and no ``next_cursor``, and clients stopped paging while older conversations
were still stored.
"""

from datetime import datetime, timedelta, timezone

from database import mcp_conversation_pages
from utils.mcp_server.handlers import conversations as conversations_handler

UID = 'uid-offset-hidden'
T0 = datetime(2026, 6, 1, tzinfo=timezone.utc)
RULE_DISCARD = {'verdict': 'discard', 'decided_by': 'rule', 'reason': 'filler_only'}


class _Snapshot:
    update_time = None

    def __init__(self, row):
        self.id = row['id']
        self._row = row

    def to_dict(self):
        return dict(self._row)


class _Ref:
    def __init__(self, doc_id):
        self.id = doc_id


class _Query:
    """Immutable query fake in ``(created_at DESC, __name__ DESC)`` order.

    Honors equality filters, ``limit``, ``offset`` and a keyset
    ``start_after`` position, and records every streamed document id.
    """

    def __init__(self, rows, streamed, *, filters=(), limit=None, offset=0, after=None):
        self._rows = rows
        self._streamed = streamed
        self._filters = filters
        self._limit = limit
        self._offset = offset
        self._after = after

    def _with(self, **changes):
        state = {'filters': self._filters, 'limit': self._limit, 'offset': self._offset, 'after': self._after}
        state.update(changes)
        return _Query(self._rows, self._streamed, **state)

    def where(self, *, filter):
        assert filter.op_string == '=='
        return self._with(filters=self._filters + ((filter.field_path, filter.value),))

    def order_by(self, field_path, direction=None):
        return self

    def select(self, field_paths):
        return self

    def limit(self, count):
        return self._with(limit=count)

    def offset(self, num_to_skip):
        return self._with(offset=num_to_skip)

    def start_after(self, position):
        return self._with(after=(position['created_at'], position['__name__'].id))

    def document(self, doc_id):
        return _Ref(doc_id)

    def stream(self, **kwargs):
        rows = [row for row in self._rows if all(row.get(field) == value for field, value in self._filters)]
        rows.sort(key=lambda row: (row['created_at'], row['id']), reverse=True)
        if self._after is not None:
            rows = [row for row in rows if (row['created_at'], row['id']) < self._after]
        rows = rows[self._offset :][: self._limit]
        self._streamed.extend(row['id'] for row in rows)
        return iter([_Snapshot(row) for row in rows])


class _Client:
    def __init__(self, rows):
        self.streamed = []
        self._conversations = _Query(rows, self.streamed)

    def collection(self, name):
        assert name in {'users', 'conversations'}
        return self if name == 'users' else self._conversations

    def document(self, uid):
        assert uid == UID
        return self


def _row(minute, **extra):
    return {
        'id': f'c{minute}',
        'created_at': T0 + timedelta(minutes=minute),
        'discarded': False,
        'status': 'completed',
        'structured': {'title': f'Conversation {minute}'},
        **extra,
    }


def test_offset_page_fills_past_hidden_rows_and_resumes_at_the_next_visible_row(monkeypatch):
    client = _Client(
        [
            _row(8),
            _row(7),
            _row(6, deleted=True),
            _row(5),
            _row(4, relevance_decision=RULE_DISCARD),
            _row(3),
            _row(2),
            _row(1),
        ]
    )
    monkeypatch.setattr(conversations_handler.mcp_conversation_pages, 'get_firestore_client', lambda: client)

    first = conversations_handler.get_conversations(UID, {'limit': 3, 'offset': 1})

    # The four-row window after c8 holds a tombstone and a rule discard. The
    # page must still be full and must not report the end of the list.
    assert [card['id'] for card in first['conversations']] == ['c7', 'c5', 'c3']
    assert first['has_more'] is True

    second = conversations_handler.get_conversations(UID, {'limit': 3, 'cursor': first['next_cursor']})

    assert [card['id'] for card in second['conversations']] == ['c2', 'c1']
    assert second['has_more'] is False


def test_offset_read_past_hidden_rows_stops_at_the_scan_budget(monkeypatch):
    monkeypatch.setattr(mcp_conversation_pages, 'MCP_CARD_PAGE_SCAN_BUDGET', 4)
    client = _Client([_row(minute, deleted=True) for minute in range(2, 22)] + [_row(1)])

    page = mcp_conversation_pages.get_mcp_conversation_cards(UID, 3, 0, firestore_client=client)

    # A dense run of tombstones: the first three-row window, then whole windows
    # until the four-row budget is spent, never the rest of the collection.
    assert page == []
    assert client.streamed == [f'c{minute}' for minute in range(21, 12, -1)]
