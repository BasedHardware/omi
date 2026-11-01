"""Regression test for #20025: a tombstoned row with no ``created_at`` must not
crash ``get_mcp_conversation_cards_page`` with an unhandled ``ValueError``.

Before the fix, every raw doc in a scanned batch (visible or not) overwrote
``last_position`` with ``(raw.get('created_at'), doc.id)``. If the last doc in
a non-exhausted batch was a tombstone missing ``created_at``, the next scan
iteration unpacked ``last_position`` and raised
``ValueError('conversation keyset timestamp is invalid')`` -- an unhandled
crash from a single legitimate first-page request, no malformed external
cursor required.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from database import mcp_conversation_pages

T1 = datetime(2026, 6, 1, tzinfo=timezone.utc)
T0 = datetime(2026, 5, 1, tzinfo=timezone.utc)


class _FakeDoc:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self.update_time = None

    def to_dict(self):
        return dict(self._data)


def _self_returning_query():
    query = MagicMock()
    for method in ('where', 'order_by', 'select', 'limit', 'start_after'):
        getattr(query, method).return_value = query
    return query


def test_tombstone_without_created_at_stops_scan_instead_of_raising():
    client = MagicMock()
    query = _self_returning_query()
    client.collection.return_value.document.return_value.collection.return_value = query

    # One batch of limit+1 raw docs: a visible row, an invisible-but-timestamped
    # row, then a tombstone with no created_at. Not enough visible rows to stop
    # the scan on this batch alone, so the old code would advance last_position
    # to (None, 'conv-c') and raise on the next loop iteration.
    query.stream.return_value = [
        _FakeDoc('conv-a', {'id': 'conv-a', 'created_at': T1, 'discarded': False}),
        _FakeDoc('conv-b', {'id': 'conv-b', 'created_at': T0, 'discarded': True}),
        _FakeDoc('conv-c', {'id': 'conv-c', 'discarded': False}),
    ]

    page, resume = mcp_conversation_pages.get_mcp_conversation_cards_page(
        'u1',
        limit=2,
        firestore_client=client,
    )

    assert [conversation['id'] for conversation in page] == ['conv-a']
    # No valid keyset position survives the tombstone -- pagination ends safely
    # rather than handing back a cursor the next page would reject.
    assert resume is None
