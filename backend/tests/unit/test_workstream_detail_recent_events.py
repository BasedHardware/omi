"""Workstream detail returns the newest journal events, not the oldest.

``get_workstream_detail`` filled ``recent_events`` from
``list_workstream_events`` with its defaults (``after_sequence=0``,
``limit=100``, ascending), so a thread past 100 events always served
sequences 1..100 and never its newest changes.
"""

from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock

import pytest

import database.workstreams as workstreams_db
from models.workstream import WorkstreamEventKind, WorkstreamSensitivity


class FakeSnapshot:
    def __init__(self, database, path, data=None):
        self.path = path
        self.id = path[-1]
        self._data = deepcopy(data)
        self.exists = data is not None

    def to_dict(self):
        return deepcopy(self._data)


class FakeRef:
    def __init__(self, database, path):
        self.database = database
        self.path = path
        self.id = path[-1]

    def collection(self, name):
        return FakeQuery(self.database, (*self.path, name))

    def get(self, transaction=None):
        return FakeSnapshot(self.database, self.path, self.database.rows.get(self.path))


class FakeQuery:
    def __init__(self, database, path, filters=None, order=None, limit_value=None):
        self.database = database
        self.path = path
        self.filters = list(filters or [])
        self.order = order
        self.limit_value = limit_value

    def document(self, name):
        return FakeRef(self.database, (*self.path, name))

    def where(self, filter):
        field, operator, value = filter.field_path, filter.op_string, filter.value
        return FakeQuery(
            self.database, self.path, [*self.filters, (field, operator, value)], self.order, self.limit_value
        )

    def order_by(self, field, direction=None):
        return FakeQuery(self.database, self.path, self.filters, (field, direction), self.limit_value)

    def limit(self, value):
        return FakeQuery(self.database, self.path, self.filters, self.order, value)

    def stream(self, transaction=None):
        rows = []
        expected_length = len(self.path) + 1
        for path, payload in self.database.rows.items():
            if len(path) != expected_length or path[:-1] != self.path:
                continue
            if all(self._matches(payload.get(field), operator, value) for field, operator, value in self.filters):
                rows.append(FakeSnapshot(self.database, path, payload))
        if self.order is not None:
            field, direction = self.order
            reverse = str(direction).endswith('DESCENDING')
            rows.sort(key=lambda snapshot: snapshot.to_dict().get(field, 0), reverse=reverse)
        return iter(rows[: self.limit_value] if self.limit_value is not None else rows)

    @staticmethod
    def _matches(actual, operator, expected):
        if operator == '==':
            return actual == expected
        if operator == '>':
            return actual is not None and actual > expected
        raise AssertionError(f'unsupported fake filter: {operator}')


class FakeDB:
    def __init__(self):
        self.rows = {}
        self.lock = RLock()

    def collection(self, name):
        return FakeQuery(self, (name,))


NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _seed(database, event_count):
    database.rows[('users', 'u1', 'workstreams', 'ws-1')] = {
        'workstream_id': 'ws-1',
        'title': 'Thread',
        'objective': 'Keep the newest changes visible',
        'status': 'open',
        'latest_event_sequence': event_count,
        'created_at': NOW,
        'updated_at': NOW,
    }
    for sequence in range(1, event_count + 1):
        database.rows[('users', 'u1', 'workstreams', 'ws-1', 'events', f'e{sequence}')] = {
            'event_id': f'e{sequence}',
            'workstream_id': 'ws-1',
            'sequence': sequence,
            'kind': WorkstreamEventKind.system.value,
            'summary': f'event {sequence}',
            'evidence_refs': [],
            'sensitivity': WorkstreamSensitivity.normal.value,
            'created_at': NOW,
        }


@pytest.fixture
def fake_db(monkeypatch):
    database = FakeDB()
    monkeypatch.setattr(workstreams_db, 'get_firestore_client', lambda: database)
    return database


def test_workstream_detail_returns_the_newest_events_past_the_page(fake_db):
    """105 events: the detail shows sequences 6..105, not the oldest 1..100."""
    _seed(fake_db, 105)

    detail = workstreams_db.get_workstream_detail('u1', 'ws-1', firestore_client=fake_db)

    sequences = [event.sequence for event in detail.recent_events]
    assert sequences == list(range(6, 106))
    assert sequences == sorted(sequences)


def test_workstream_detail_returns_every_event_of_a_short_thread(fake_db):
    _seed(fake_db, 3)

    detail = workstreams_db.get_workstream_detail('u1', 'ws-1', firestore_client=fake_db)

    assert [event.sequence for event in detail.recent_events] == [1, 2, 3]
