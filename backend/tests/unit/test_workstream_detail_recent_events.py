"""Regression: Workstream detail shows the newest 100 journal events in ascending order.

A workstream with more than 100 journal events previously showed sequences 1..100 as
"recent" events because ``get_workstream_detail`` called ``list_workstream_events``
with ascending order. Long threads therefore never showed their newest changes.

``get_workstream_detail`` now requests the newest events in descending order and
receives them reversed back to chronological ascending order, showing the latest 100 events.
"""

import os
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest
from google.cloud import firestore

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

import database.workstreams as workstreams_db
from models.workstream import (
    WorkstreamDetailProjection,
    WorkstreamEvent,
)

UID = 'uid-workstream-test'
WS_ID = 'ws-test-123'
T0 = datetime(2026, 6, 1, tzinfo=timezone.utc)


class _EventSnapshot:
    def __init__(self, sequence: int):
        self.id = f'wse-{sequence}'
        self.sequence = sequence

    def to_dict(self):
        return {
            'event_id': self.id,
            'workstream_id': WS_ID,
            'sequence': self.sequence,
            'kind': 'system',
            'summary': f'Event summary {self.sequence}',
            'evidence_refs': [],
            'sensitivity': 'normal',
            'created_at': T0,
        }


class _MockQuery:
    def __init__(self, snapshots: list[_EventSnapshot], filters=(), direction=firestore.Query.ASCENDING, limit_count=100):
        self.snapshots = snapshots
        self.filters = filters
        self.direction = direction
        self.limit_count = limit_count

    def where(self, *, filter):
        return _MockQuery(self.snapshots, self.filters + (filter,), self.direction, self.limit_count)

    def order_by(self, field, direction=firestore.Query.ASCENDING):
        return _MockQuery(self.snapshots, self.filters, direction, self.limit_count)

    def limit(self, count):
        return _MockQuery(self.snapshots, self.filters, self.direction, count)

    def stream(self):
        items = list(self.snapshots)
        for f in self.filters:
            if f.field_path == 'sequence' and f.op_string == '>':
                items = [it for it in items if it.sequence > f.value]
        if self.direction == firestore.Query.DESCENDING:
            items.sort(key=lambda it: it.sequence, reverse=True)
        else:
            items.sort(key=lambda it: it.sequence)
        return iter(items[: self.limit_count])


class _MockFirestore:
    def __init__(self, total_events: int = 150):
        self.total_events = total_events
        self.events_snapshots = [_EventSnapshot(i) for i in range(1, total_events + 1)]

    def collection(self, name):
        return _MockCollection(self, name)

    def document(self, path):
        return _MockDocRef(self, path)


class _MockCollection:
    def __init__(self, db: _MockFirestore, name: str, parent_doc: str = ''):
        self.db = db
        self.name = name
        self.parent_doc = parent_doc

    def document(self, doc_id: str):
        full_path = f'{self.parent_doc}/{self.name}/{doc_id}' if self.parent_doc else f'{self.name}/{doc_id}'
        return _MockDocRef(self.db, full_path)

    def where(self, *, filter):
        return self._as_query().where(filter=filter)

    def order_by(self, field, direction=firestore.Query.ASCENDING):
        return self._as_query().order_by(field, direction)

    def limit(self, count):
        return self._as_query().limit(count)

    def stream(self):
        return self._as_query().stream()

    def _as_query(self):
        if self.name == 'events':
            return _MockQuery(self.db.events_snapshots)
        # Empty stream for action_items, artifact_refs, etc.
        return _MockQuery([])


class _MockDocRef:
    def __init__(self, db: _MockFirestore, path: str):
        self.db = db
        self.path = path
        self.id = path.rsplit('/', 1)[-1]

    def collection(self, name: str):
        return _MockCollection(self.db, name, parent_doc=self.path)

    def get(self, transaction=None):
        snap = MagicMock()
        snap.exists = True
        snap.id = self.id
        if 'workstreams/' in self.path:
            snap.to_dict.return_value = {
                'workstream_id': self.id,
                'title': 'Test Workstream',
                'objective': 'Test Objective',
                'status': 'open',
                'current_state_summary': '',
                'latest_event_sequence': self.db.total_events,
                'created_at': T0,
                'updated_at': T0,
            }
        else:
            snap.to_dict.return_value = {}
        return snap


def test_list_workstream_events_descending_returns_newest_in_ascending_order():
    # 150 events in total: sequences 1 through 150
    db = _MockFirestore(total_events=150)
    events = workstreams_db.list_workstream_events(UID, WS_ID, limit=100, descending=True, firestore_client=db)

    # Must return exactly 100 events
    assert len(events) == 100
    # Must be the newest events (sequences 51 to 150)
    sequences = [e.sequence for e in events]
    assert sequences == list(range(51, 151))
    # Must be in chronological ascending order
    assert sequences[0] == 51
    assert sequences[-1] == 150


def test_list_workstream_events_default_returns_oldest_first():
    # 150 events in total: sequences 1 through 150
    db = _MockFirestore(total_events=150)
    events = workstreams_db.list_workstream_events(UID, WS_ID, limit=100, descending=False, firestore_client=db)

    assert len(events) == 100
    sequences = [e.sequence for e in events]
    assert sequences == list(range(1, 101))


def test_get_workstream_detail_contains_newest_events_in_ascending_order():
    # 150 events in total: sequences 1 through 150
    db = _MockFirestore(total_events=150)
    detail = workstreams_db.get_workstream_detail(UID, WS_ID, firestore_client=db)

    assert isinstance(detail, WorkstreamDetailProjection)
    recent = detail.recent_events
    assert len(recent) == 100
    sequences = [e.sequence for e in recent]
    # Verify newest events (51..150) in ascending order
    assert sequences == list(range(51, 151))
