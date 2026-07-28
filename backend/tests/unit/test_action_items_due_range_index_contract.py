"""The due-range action-item read must be served by a declared Firestore index.

``get_action_items`` filters ``completed`` for equality and orders ``due_at`` ascending
whenever a due-date range is requested, so Firestore needs a composite index on
(completed ASC, due_at ASC). Prod only had (completed ASC, due_at DESC), which serves the
reverse ordering and not this one, so every due-range read -- the chat ``get_action_items``
tool and GET /v1/action-items with due filters -- failed with
``FailedPrecondition: 400 The query requires an index``.

The query shape is discovered by running the production function through the sanctioned
``monkeypatch.setattr(action_items, 'db', ...)`` seam and is then converted to the Firestore
index signature (equality fields, then the ordered field, then ``__name__``). Changing the
order direction or adding an equality filter without declaring the matching index fails here
instead of in prod.
"""

from datetime import datetime, timedelta, timezone

import pytest

import database.action_items as action_items
from database.firestore_index_registry import firebase_index_manifest

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


class _RecordingQuery:
    """Firestore query stand-in that records the composite the caller builds."""

    def __init__(self, recorder):
        self._recorder = recorder

    def collection(self, _name):
        return self

    def document(self, _name):
        return self

    def where(self, *_args, **kwargs):
        filt = kwargs.get('filter')
        self._recorder.append(('where', getattr(filt, 'field_path', None), getattr(filt, 'op_string', None)))
        return self

    def order_by(self, field, direction=None):
        self._recorder.append(('order_by', field, direction))
        return self

    def offset(self, _n):
        return self

    def limit(self, _n):
        return self

    def stream(self):
        return iter(())


def _declared_action_item_signatures():
    return {
        tuple((field['fieldPath'], field['order']) for field in index['fields'])
        for index in firebase_index_manifest()['indexes']
        if index['collectionGroup'] == 'action_items' and index['queryScope'] == 'COLLECTION'
    }


def _index_signature(recorded):
    """Firestore composite order: equality fields, then the ordered field, then __name__."""
    equalities = [field for kind, field, op in recorded if kind == 'where' and op == '==']
    orders = [(field, direction) for kind, field, direction in recorded if kind == 'order_by']
    assert orders, 'due-range reads must order explicitly so a bounded prefix matches product sort'
    last_direction = orders[-1][1]
    return tuple([(field, 'ASCENDING') for field in equalities] + orders + [('__name__', last_direction)])


@pytest.fixture
def recorded_due_range_query(monkeypatch):
    recorder = []
    monkeypatch.setattr(action_items, 'db', _RecordingQuery(recorder))
    action_items.get_action_items(
        'uid-under-test',
        completed=False,
        due_start_date=BASE,
        due_end_date=BASE + timedelta(days=7),
        limit=50,
    )
    return recorder


def test_due_range_read_filters_completed_and_orders_due_at_ascending(recorded_due_range_query):
    assert ('where', 'completed', '==') in recorded_due_range_query
    assert ('order_by', 'due_at', action_items.firestore.Query.ASCENDING) in recorded_due_range_query


def test_due_range_composite_is_declared_in_the_firestore_index_manifest(recorded_due_range_query):
    assert _index_signature(recorded_due_range_query) in _declared_action_item_signatures()
