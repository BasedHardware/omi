"""`get_conversations_finished_after` serves duplicate-capture detection (#3244).

The read must carry the registered filter chain (status equality plus the
`finished_at` lower bound), order on the same activity clock so the bounded
page holds the rows nearest this recording's start, and decrypt nothing beyond
what `prepare_for_read` already does for every conversation read.
"""

from datetime import datetime, timedelta, timezone

from google.cloud.firestore_v1.base_query import FieldFilter

from database import conversations as conversations_db
from database.firestore_index_registry import (
    CONVERSATIONS_BY_STATUS_FINISHED_AFTER_QUERY,
    STALE_IN_PROGRESS_CONVERSATIONS_QUERY,
)


class _Document:
    def __init__(self, data: dict):
        self._data = data

    def to_dict(self):
        return dict(self._data)


class _Query:
    def __init__(self, documents):
        self.documents = documents
        self.filters = []
        self.ordering = None
        self.limit_value = None

    def where(self, *, filter):
        self.filters.append((filter.field_path, filter.op_string, filter.value))
        return self

    def order_by(self, field_path, direction):
        self.ordering = (field_path, direction)
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def stream(self):
        return iter(self.documents)


class _UserRef:
    def __init__(self, query):
        self.query = query

    def document(self, _uid):
        return self

    def collection(self, _name):
        return self.query


class _Client:
    """users/{uid}/conversations → the recording query."""

    def __init__(self, query):
        self.query = query

    def collection(self, _name):
        return _UserRef(self.query)


def test_query_carries_status_and_finished_at_lower_bound_ordered_by_activity_clock():
    started_at = datetime(2026, 9, 12, 15, 0, tzinfo=timezone.utc)
    query = _Query(
        [
            _Document({'id': 'mac', 'finished_at': started_at + timedelta(minutes=5)}),
            _Document({'id': 'later', 'finished_at': started_at + timedelta(hours=1)}),
        ]
    )
    client = _Client(query)

    rows = conversations_db.get_conversations_finished_after(
        'uid-1',
        status='completed',
        finished_after=started_at,
        limit=25,
        firestore_client=client,
    )

    assert [row['id'] for row in rows] == ['mac', 'later']
    assert query.filters == [('status', '==', 'completed'), ('finished_at', '>=', started_at)]
    assert query.ordering[0] == 'finished_at'
    assert query.limit_value == 25


def test_registered_spec_builds_the_same_filter_chain_and_reuses_the_stale_sweep_index():
    query = _Query([])
    built = CONVERSATIONS_BY_STATUS_FINISHED_AFTER_QUERY.build(
        query, {'status': 'processing', 'finished_after': 'T'}, field_filter_factory=FieldFilter
    )

    assert built is query
    assert query.filters == [('status', '==', 'processing'), ('finished_at', '>=', 'T')]
    assert (
        CONVERSATIONS_BY_STATUS_FINISHED_AFTER_QUERY.index_requirement.signature
        == STALE_IN_PROGRESS_CONVERSATIONS_QUERY.index_requirement.signature
    ), 'no new composite index: the manifest already provisions (status, finished_at)'
