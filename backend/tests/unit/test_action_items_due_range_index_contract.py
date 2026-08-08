"""Every due-range action-item read must be served by a declared Firestore index.

``get_action_items`` orders ``due_at`` ascending whenever a due-date range is requested and
combines that order with whichever equality filters the caller asked for: ``completed``,
``conversation_id``, or both. Each combination is a distinct Firestore composite. Prod only
had (completed ASC, due_at DESC), which serves the reverse ordering and not this one, so every
due-range read -- the chat ``get_action_items`` tool and GET /v1/action-items with due filters --
failed with ``FailedPrecondition: 400 The query requires an index``; the ``conversation_id``
chains kept failing after (completed ASC, due_at ASC) was declared.

The query shapes are discovered by running the production function through the neutral storage
port (WP2/ADR-0028): ``get_action_items`` no longer touches a raw Firestore client, it issues
``store.query(path, filters=..., order_by=..., direction=...)`` calls. We record those port
calls and convert each to a Firestore index signature (equality fields, then the ordered field,
then ``__name__``). Firestore orders the equality prefix itself, so equality fields are compared
as a set. Adding an equality filter or changing the order direction without declaring the
matching index fails here instead of in prod.
"""

from datetime import datetime, timedelta, timezone

import pytest

import database.action_items as action_items
from database.firestore_index_registry import firebase_index_manifest

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


class _RecordingStore:
    """Storage-port stand-in that records every ``query`` composite the caller builds.

    ``get_action_items`` can issue more than one query per call (the incomplete bucket, the
    bounded legacy scan, and the completed bucket). Each ``query`` call is recorded as its
    ``filters``/``order_by``/``direction`` so the test can reconstruct the Firestore composite
    it maps to. Queries return no rows -- this test asserts on the query *shapes*, not results.
    """

    def __init__(self):
        self.queries: list[dict] = []

    def query(
        self,
        collection,
        *,
        filters=None,
        order_by=None,
        direction='asc',
        limit=None,
        offset=None,
        fields=None,
        start_after=None,
    ):
        self.queries.append(
            {
                'collection': collection,
                'filters': [tuple(f) for f in (filters or [])],
                'order_by': order_by,
                'direction': direction,
            }
        )
        return []


def _declared_action_item_signatures():
    signatures = set()
    for index in firebase_index_manifest()['indexes']:
        if index['collectionGroup'] != 'action_items' or index['queryScope'] != 'COLLECTION':
            continue
        fields = [(field['fieldPath'], field['order']) for field in index['fields']]
        signatures.add((frozenset(fields[:-2]), fields[-2], fields[-1]))
    return signatures


def _index_signature(recorded):
    """Firestore composite order: equality fields, then the ordered field, then __name__."""
    equalities = [(field, 'ASCENDING') for field, op, *_ in recorded['filters'] if op == '==']
    assert recorded['order_by'], 'due-range reads must order explicitly so a bounded prefix matches product sort'
    order = 'ASCENDING' if recorded['direction'] == 'asc' else 'DESCENDING'
    ordered = (recorded['order_by'], order)
    return (frozenset(equalities), ordered, ('__name__', order))


def _record_due_range_queries(monkeypatch, **filters):
    recorder = _RecordingStore()
    monkeypatch.setattr(action_items, '_store', lambda: recorder)
    action_items.get_action_items(
        'uid-under-test',
        due_start_date=BASE,
        due_end_date=BASE + timedelta(days=7),
        limit=50,
        **filters,
    )
    return recorder.queries


# Every filter combination GET /v1/action-items and the chat get_action_items tool accept
# alongside a due-date range.
DUE_RANGE_CALLS = [
    pytest.param({'completed': False}, id='completed'),
    pytest.param({'conversation_id': 'conv-under-test'}, id='conversation'),
    pytest.param({'conversation_id': 'conv-under-test', 'completed': False}, id='conversation+completed'),
    pytest.param({}, id='unfiltered'),
]


def test_due_range_read_filters_completed_and_orders_due_at_ascending(monkeypatch):
    (recorded,) = _record_due_range_queries(monkeypatch, completed=False)
    assert any(field == 'completed' and op == '==' for field, op, *_ in recorded['filters'])
    assert recorded['order_by'] == 'due_at'
    assert recorded['direction'] == 'asc'


def test_conversation_due_range_read_keeps_the_conversation_equality(monkeypatch):
    recorded = _record_due_range_queries(monkeypatch, conversation_id='conv-under-test')
    assert recorded, 'a conversation-scoped due-range read must issue at least one query'
    for query in recorded:
        assert any(field == 'conversation_id' and op == '==' for field, op, *_ in query['filters'])


@pytest.mark.parametrize('filters', DUE_RANGE_CALLS)
def test_due_range_composites_are_declared_in_the_firestore_index_manifest(monkeypatch, filters):
    declared = _declared_action_item_signatures()
    for query in _record_due_range_queries(monkeypatch, **filters):
        signature = _index_signature(query)
        if not signature[0]:
            # No equality filter: Firestore's automatic single-field index serves it.
            continue
        assert signature in declared, f'undeclared Firestore composite for {filters}: {signature}'
