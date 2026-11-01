"""Deterministic reproduction test for Firestore 'in' query 30-element limit crash in database/apps.py.

Firestore imposes a strict maximum of 30 elements for 'in' and 'array-contains-any' query filters.
When more than 30 elements are provided, Firestore raises:
`google.api_core.exceptions.InvalidArgument: 'in' filters require a non-empty array with at most 30 elements.`

In database/apps.py:
1. `get_apps_for_tester_db` queries unapproved apps for a beta tester via `FieldFilter('id', 'in', apps)`.
   When a tester is assigned more than 30 apps, it fails to chunk the IDs, crashing GET /v1/apps for that tester.
   It also deduplicates IDs before chunking to prevent duplicate queries and cache entries.
2. `get_audio_apps_count` counts audio apps using `FieldFilter('id', 'in', app_ids)`.
   When more than 30 app IDs are passed, it fails to chunk the IDs, crashing audio apps counting.
   It also deduplicates IDs before chunking.

This test simulates Firestore's server-side 30-element limit and proves that unchunked queries
crash with InvalidArgument, while chunked queries succeed.
"""

import os
from typing import Any, List, Optional
from unittest.mock import MagicMock
from google.api_core.exceptions import InvalidArgument
from google.cloud.firestore_v1 import FieldFilter
from google.cloud.firestore_v1.base_query import BaseCompositeFilter

os.environ.setdefault('OPENAI_API_KEY', 'test-key')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

import database.apps as apps_db


class _FirestoreQueryLimitEnforcer:
    """Mock query that enforces Firestore's strict limit of <= 30 items in 'in' filters
    and returns only documents whose 'id' matches the chunk."""

    def __init__(self, collection_name: str, parent_db: "_FirestoreLimitEnforcingDB"):
        self.collection_name = collection_name
        self.parent_db = parent_db
        self.filters: List[Any] = []
        self.current_in_ids: Optional[set[str]] = None

    def where(self, filter: Any = None, *args: Any, **kwargs: Any):
        if filter is not None:
            self._validate_filter(filter)
            self.filters.append(filter)
        return self

    def _validate_filter(self, filter_obj: Any):
        if isinstance(filter_obj, BaseCompositeFilter):
            for subfilter in getattr(filter_obj, 'filters', []):
                self._validate_filter(subfilter)
        elif isinstance(filter_obj, FieldFilter):
            op = getattr(filter_obj, 'operator_string', None) or getattr(filter_obj, 'op_string', None)
            val = getattr(filter_obj, 'value', None)
            if op in ('in', 'not-in', 'array_contains_any') and isinstance(val, (list, tuple, set)):
                if len(val) > 30:
                    raise InvalidArgument(
                        f"'{op}' filters require a non-empty array with at most 30 elements, got {len(val)}"
                    )
                self.current_in_ids = set(val)

    def count(self):
        class _CountAggregation:
            def __init__(self, count_val: int):
                self.count_val = count_val

            def get(self):
                val_mock = MagicMock()
                val_mock.value = self.count_val
                return [[val_mock]]

        matching = [
            doc
            for doc in self.parent_db.sample_docs
            if self.current_in_ids is None or doc.to_dict().get('id') in self.current_in_ids
        ]
        return _CountAggregation(len(matching))

    def stream(self):
        if self.current_in_ids is None:
            return list(self.parent_db.sample_docs)
        return [doc for doc in self.parent_db.sample_docs if doc.to_dict().get('id') in self.current_in_ids]


class _FirestoreLimitEnforcingDB:
    def __init__(self, tester_apps: List[str], sample_docs: Optional[List[Any]] = None):
        self.tester_apps = tester_apps
        self.sample_docs = sample_docs or []

    def collection(self, name: str):
        if name == apps_db.testers_collection:
            doc_mock = MagicMock()
            snapshot_mock = MagicMock()
            snapshot_mock.exists = True
            snapshot_mock.to_dict.return_value = {'apps': self.tester_apps}
            doc_mock.get.return_value = snapshot_mock
            col_mock = MagicMock()
            col_mock.document.return_value = doc_mock
            return col_mock
        return _FirestoreQueryLimitEnforcer(name, self)


def test_get_apps_for_tester_db_handles_more_than_30_apps(monkeypatch):
    """When a tester has 35 apps, get_apps_for_tester_db must chunk queries into batches <= 30
    and return all 35 distinct apps without duplicate or dropped documents."""
    app_ids = [f'app_{i}' for i in range(35)]
    sample_docs = []
    for app_id in app_ids:
        doc = MagicMock()
        doc.to_dict.return_value = {'id': app_id, 'name': f'App {app_id}', 'approved': False}
        sample_docs.append(doc)

    fake_db = _FirestoreLimitEnforcingDB(tester_apps=app_ids, sample_docs=sample_docs)
    monkeypatch.setattr(apps_db, 'db', fake_db)

    results = apps_db.get_apps_for_tester_db('tester_uid_1')
    assert len(results) == 35
    assert len({r['id'] for r in results}) == 35
    assert [r['id'] for r in results] == app_ids


def test_get_apps_for_tester_db_deduplicates_apps_before_chunking(monkeypatch):
    """When a tester document contains duplicate app IDs crossing chunk boundaries,
    they must be deduplicated before chunking to prevent duplicate Firestore queries."""
    # 40 items total, but only 20 unique IDs
    app_ids = [f'app_{i % 20}' for i in range(40)]
    sample_docs = []
    for app_id in set(app_ids):
        doc = MagicMock()
        doc.to_dict.return_value = {'id': app_id, 'name': f'App {app_id}', 'approved': False}
        sample_docs.append(doc)

    fake_db = _FirestoreLimitEnforcingDB(tester_apps=app_ids, sample_docs=sample_docs)
    monkeypatch.setattr(apps_db, 'db', fake_db)

    results = apps_db.get_apps_for_tester_db('tester_uid_1')
    assert len(results) == 20
    assert len({r['id'] for r in results}) == 20


def test_get_audio_apps_count_handles_more_than_30_apps(monkeypatch):
    """When counting audio apps for 35 apps, queries must be chunked into batches <= 30
    and produce the exact total count."""
    app_ids = [f'audio_app_{i}' for i in range(35)]
    sample_docs = []
    for app_id in app_ids:
        doc = MagicMock()
        doc.to_dict.return_value = {'id': app_id, 'external_integration': {'triggers_on': 'audio_bytes'}}
        sample_docs.append(doc)

    fake_db = _FirestoreLimitEnforcingDB(tester_apps=[], sample_docs=sample_docs)
    monkeypatch.setattr(apps_db, 'db', fake_db)

    count = apps_db.get_audio_apps_count(app_ids)
    assert count == 35
