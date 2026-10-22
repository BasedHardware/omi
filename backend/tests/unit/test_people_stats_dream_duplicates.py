"""Regression: People stats scan counts Dream duplicate captures.

Dream's ``merge_conversations`` cleanup marks a duplicate capture with
``dream_duplicate_of`` pointing to the surviving capture. The row keeps
``discarded=False`` and ``status='completed'``.

The People-stats scan selects a field projection, ``PEOPLE_STATS_FIELD_PATHS``.
Previously, ``dream_duplicate_of`` was omitted from ``PEOPLE_STATS_FIELD_PATHS``.
As a result, projected snapshots lacked ``dream_duplicate_of``, causing
``is_visible_conversation(raw)`` to return True and count duplicate conversations
and duplicate talk time towards people stats.
"""

import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import List, Optional

import pytest
from google.cloud import firestore

from database import conversation_scan
from utils.other.list_budget import ListReadBudget
from utils.people_stats import aggregate_people_stats

UID = 'uid-people-stats-dream-dup'
T0 = datetime(2026, 6, 1, tzinfo=timezone.utc)


class _Snap:
    def __init__(self, path: str, data: Optional[dict]):
        self.reference = SimpleNamespace(path=path)
        self.id = path.rsplit('/', 1)[-1]
        self.exists = data is not None
        self.update_time = None
        self._data = data

    def to_dict(self) -> Optional[dict]:
        return dict(self._data) if self._data is not None else None


class _MockClient:
    def __init__(self, uid: str, docs: List[dict]):
        self.uid = uid
        self.snaps = [_Snap(f'users/{uid}/conversations/{doc["id"]}', doc) for doc in docs]

    def collection(self, name: str):
        assert name == 'users'
        return self

    def document(self, uid: str):
        assert uid == self.uid
        return _UserDoc(self)


class _UserDoc:
    def __init__(self, client: _MockClient):
        self._client = client

    def collection(self, name: str):
        assert name == 'conversations'
        return _MockQuery(self._client)


class _MockQuery:
    def __init__(
        self,
        client: _MockClient,
        filters: tuple = (),
        descending: bool = False,
        bound: Optional[int] = None,
        projection: Optional[tuple] = None,
        cursor: Optional[_Snap] = None,
    ):
        self._client = client
        self._filters = filters
        self._descending = descending
        self._bound = bound
        self._projection = projection
        self._cursor = cursor

    def _clone(self, **changes) -> '_MockQuery':
        state = {
            'filters': self._filters,
            'descending': self._descending,
            'bound': self._bound,
            'projection': self._projection,
            'cursor': self._cursor,
        }
        state.update(changes)
        return _MockQuery(self._client, **state)

    def where(self, *args, filter=None, **kwargs):
        assert filter is not None
        return self._clone(filters=self._filters + (filter,))

    def order_by(self, field_path: str, direction=None):
        return self._clone(descending=True)

    def select(self, field_paths):
        return self._clone(projection=tuple(field_paths))

    def limit(self, count: int):
        return self._clone(bound=count)

    def start_after(self, snapshot):
        return self._clone(cursor=snapshot)

    def _matches(self, snap: _Snap) -> bool:
        data = snap._data
        for node in self._filters:
            value = data.get(node.field_path)
            op = str(getattr(node.op_string, 'name', None) or node.op_string)
            if op == '==':
                if value != node.value:
                    return False
        return True

    def stream(self, **kwargs):
        rows = [snap for snap in self._client.snaps if self._matches(snap)]
        rows.sort(key=lambda snap: (snap._data['created_at'], snap.id), reverse=True)
        if self._cursor is not None:
            index = next(i for i, snap in enumerate(rows) if snap.id == self._cursor.id)
            rows = rows[index + 1 :]
        if self._bound is not None:
            rows = rows[: self._bound]
        if self._projection is None:
            return iter(rows)
        return iter([
            _Snap(snap.reference.path, {k: v for k, v in snap._data.items() if k in self._projection})
            for snap in rows
        ])


def _conv_row(conv_id: str, minute: int, person_id: str = 'p1', **extra):
    return {
        'id': conv_id,
        'created_at': T0 + timedelta(minutes=minute),
        'started_at': T0 + timedelta(minutes=minute),
        'discarded': False,
        'deleted': False,
        'is_locked': False,
        'transcript_segments': [
            {'person_id': person_id, 'start': 0.0, 'end': 10.0, 'text': 'Hello world'}
        ],
        **extra,
    }


def test_people_stats_field_paths_includes_dream_duplicate_of():
    assert 'dream_duplicate_of' in conversation_scan.PEOPLE_STATS_FIELD_PATHS


def test_people_stats_scan_filters_out_dream_duplicate():
    # c3 is original, c2 is a duplicate of c3 created by Dream, c1 is earlier original
    docs = [
        _conv_row('c3', 3),
        _conv_row('c2', 2, dream_duplicate_of='c3'),
        _conv_row('c1', 1),
    ]
    client = _MockClient(UID, docs)
    budget = ListReadBudget(deadline_monotonic=time.monotonic() + 10.0, max_documents=100)

    results = list(conversation_scan.people_stats_scan(UID, budget=budget, firestore_client=client))

    result_ids = [c['id'] for c in results]
    assert result_ids == ['c3', 'c1']
    assert 'c2' not in result_ids


def test_people_stats_aggregation_excludes_duplicate_counts_and_talk_time():
    docs = [
        _conv_row('c3', 3, person_id='p1'),
        _conv_row('c2', 2, person_id='p1', dream_duplicate_of='c3'),
        _conv_row('c1', 1, person_id='p1'),
    ]
    client = _MockClient(UID, docs)
    budget = ListReadBudget(deadline_monotonic=time.monotonic() + 10.0, max_documents=100)

    conversations = list(conversation_scan.people_stats_scan(UID, budget=budget, firestore_client=client))
    stats = aggregate_people_stats(conversations)

    # c2 must not be counted; only c3 and c1 (count = 2, talk_seconds = 20.0)
    assert stats['p1']['conversation_count'] == 2
    assert stats['p1']['talk_seconds'] == 20.0
