"""Every due-range action-item read must be served by a declared Firestore index.

``get_action_items`` orders ``due_at`` ascending whenever a due-date range is requested and
combines that order with whichever equality filters the caller asked for: ``completed``,
``conversation_id``, or both. Each combination is a distinct Firestore composite. Prod only
had (completed ASC, due_at DESC), which serves the reverse ordering and not this one, so every
due-range read -- the chat ``get_action_items`` tool and GET /v1/action-items with due filters --
failed with ``FailedPrecondition: 400 The query requires an index``; the ``conversation_id``
chains kept failing after (completed ASC, due_at ASC) was declared.

The query shapes are discovered by running the production function through the sanctioned
``monkeypatch.setattr(action_items, 'db', ...)`` seam and are then converted to Firestore index
signatures (equality fields, then the ordered field, then ``__name__``). Firestore orders the
equality prefix itself, so equality fields are compared as a set. Adding an equality filter or
changing the order direction without declaring the matching index fails here instead of in prod.
"""

from datetime import datetime, timedelta, timezone

import pytest

import database.action_items as action_items
from database.firestore_index_registry import firebase_index_manifest

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


class _RecordingQuery:
    """Firestore query stand-in that records every composite the caller builds.

    ``get_action_items`` can build more than one query per call (the completed bucket and the
    bounded legacy scan), each starting from ``db.collection('users')``; that call opens a new
    recording.
    """

    def __init__(self):
        self.queries: list[list[tuple]] = []
        self._current: list[tuple] = []

    def collection(self, name):
        if name == 'users':
            self._current = []
            self.queries.append(self._current)
        return self

    def document(self, _name):
        return self

    def where(self, *_args, **kwargs):
        filt = kwargs.get('filter')
        self._current.append(('where', getattr(filt, 'field_path', None), getattr(filt, 'op_string', None)))
        return self

    def order_by(self, field, direction=None):
        self._current.append(('order_by', field, direction))
        return self

    def select(self, _fields):
        return self

    def offset(self, _n):
        return self

    def limit(self, _n):
        return self

    def stream(self):
        return iter(())


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
    equalities = [(field, 'ASCENDING') for kind, field, op in recorded if kind == 'where' and op == '==']
    orders = [(field, direction) for kind, field, direction in recorded if kind == 'order_by']
    assert orders, 'due-range reads must order explicitly so a bounded prefix matches product sort'
    ordered = orders[-1]
    return (frozenset(equalities), ordered, ('__name__', ordered[1]))


def _record_due_range_queries(monkeypatch, **filters):
    recorder = _RecordingQuery()
    monkeypatch.setattr(action_items, 'db', recorder)
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
    assert ('where', 'completed', '==') in recorded
    assert ('order_by', 'due_at', action_items.firestore.Query.ASCENDING) in recorded


def test_conversation_due_range_read_keeps_the_conversation_equality(monkeypatch):
    recorded = _record_due_range_queries(monkeypatch, conversation_id='conv-under-test')
    assert recorded, 'a conversation-scoped due-range read must issue at least one query'
    for query in recorded:
        assert ('where', 'conversation_id', '==') in query


@pytest.mark.parametrize('filters', DUE_RANGE_CALLS)
def test_due_range_composites_are_declared_in_the_firestore_index_manifest(monkeypatch, filters):
    declared = _declared_action_item_signatures()
    for query in _record_due_range_queries(monkeypatch, **filters):
        signature = _index_signature(query)
        if not signature[0]:
            # No equality filter: Firestore's automatic single-field index serves it.
            continue
        assert signature in declared, f'undeclared Firestore composite for {filters}: {signature}'
