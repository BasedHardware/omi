"""HTTP-level proof that GET /memory/search fails fast instead of 504ing.

The production failure (SCA-3795, four occurrences) is a bare 30s middleware
504: the authoritative read outlives ``HTTP_GET_TIMEOUT`` and the edge cuts the
connection with no body. This test mounts the real product router on a real
FastAPI app, drives the read through a slow store, and asserts the client sees
a typed 503 with a retry hint well inside the edge timeout -- not a hung
request and not a 200 built from a partial window.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import database.memories as memories_db
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.product_memory import MemoryItem, MemoryItemStatus, MemoryTier, ProcessingState
from routers import memory_product
from utils.memory.short_term_lifecycle import DEFAULT_SHORT_TERM_TTL_DAYS

_UID = 'u1'


@pytest.fixture(autouse=True)
def _offline_read_path(monkeypatch):
    monkeypatch.setattr(memories_db, 'get_memories', lambda *args, **kwargs: [])
    monkeypatch.setattr(memories_db, 'list_memory_updated_or_created_index', lambda *args, **kwargs: [])
    monkeypatch.setattr(memories_db, 'get_memories_by_ids', lambda *args, **kwargs: [])


class _Snapshot:
    def __init__(self, doc_id, data, exists=True):
        self.id = doc_id
        self._data = data
        self.exists = exists

    def to_dict(self):
        return dict(self._data or {})


class _SlowStream:
    def __init__(self, snapshots, *, per_row_seconds):
        self._snapshots = list(snapshots)
        self._per_row_seconds = per_row_seconds
        self._position = 0
        self.closed = False

    def __iter__(self):
        return self

    def __next__(self):
        if self.closed or self._position >= len(self._snapshots):
            raise StopIteration
        time.sleep(self._per_row_seconds)
        snapshot = self._snapshots[self._position]
        self._position += 1
        return snapshot

    def close(self):
        self.closed = True


class _Collection:
    def __init__(self, db, path):
        self._db = db
        self.path = path

    def stream(self, **_kwargs):
        snapshots = []
        prefix = f'{self.path}/'
        for path, data in sorted(self._db.docs.items()):
            if path.startswith(prefix) and '/' not in path[len(prefix) :]:
                snapshots.append(_Snapshot(path[len(prefix) :], data))
        stream = _SlowStream(snapshots, per_row_seconds=self._db.per_row_seconds)
        self._db.streams.append(stream)
        return stream


class _DocumentRef:
    def __init__(self, db, path):
        self._db = db
        self.path = path

    def get(self, **_kwargs):
        data = self._db.docs.get(self.path)
        return _Snapshot(self.path.rsplit('/', 1)[-1], data, exists=data is not None)


class _FirestoreFake:
    def __init__(self, docs, *, per_row_seconds=0.0):
        self.docs = docs
        self.per_row_seconds = per_row_seconds
        self.streams: list[_SlowStream] = []

    def collection(self, path):
        return _Collection(self, path)

    def document(self, path):
        return _DocumentRef(self, path)


def _evidence():
    return MemoryEvidence(
        evidence_id='ev-1',
        source_id='conv1',
        source_type='conversation',
        source_version='v1',
        quote_refs=[{'text': 'User prefers concise product memory reads.'}],
        content_hash='hash1',
        source_state=SourceState.active,
        artifact_preservation=ArtifactPreservationState.preserved,
    )


def _stored_memory(memory_id: str):
    captured_at = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    return MemoryItem(
        memory_id=memory_id,
        uid=_UID,
        version=1,
        tier=MemoryTier.short_term,
        status=MemoryItemStatus.active,
        processing_state=ProcessingState.processed,
        content=f'coffee preference {memory_id}',
        evidence=[_evidence()],
        source_state=SourceState.active,
        sensitivity_labels=[],
        visibility='private',
        user_asserted=False,
        captured_at=captured_at,
        updated_at=captured_at,
        expires_at=captured_at + timedelta(days=DEFAULT_SHORT_TERM_TTL_DAYS),
    ).model_dump(mode='json')


def _docs(memory_count: int) -> dict:
    return {
        memory_product.GLOBAL_READ_GATE_PATH: {'memory_reads_enabled': True, 'kill_switch_active': False},
        f'users/{_UID}/memory_control/state': {
            'schema_version': 1,
            'uid': _UID,
            'mode': 'read',
            'fallback_projection_ready': True,
            'stage_gates': {'shadow': 'passed', 'write': 'passed', 'read': 'passed'},
            'grants': {'omi_chat': {'default_memory': True}},
        },
        **{
            f'users/{_UID}/memory_items/memory-{index:03d}': _stored_memory(f'memory-{index:03d}')
            for index in range(memory_count)
        },
    }


def _client(monkeypatch, db_client) -> TestClient:
    monkeypatch.setattr(memory_product, 'db', db_client)
    app = FastAPI()
    app.include_router(memory_product.router)
    app.dependency_overrides[memory_product.auth.get_current_user_uid] = lambda: _UID
    return TestClient(app)


def test_memory_search_returns_fast_503_when_the_read_budget_expires(monkeypatch):
    # ~0.02s per row over 60 rows would need ~1.2s; the budget allows 0.2s.
    monkeypatch.setenv('OMI_LIST_READ_BUDGET_SECONDS', '0.2')
    monkeypatch.setenv('OMI_MEMORY_READ_RETRY_BURST', '64')
    db_client = _FirestoreFake(_docs(60), per_row_seconds=0.02)

    started = time.monotonic()
    response = _client(monkeypatch, db_client).get('/memory/search', params={'query': 'coffee', 'limit': 10})
    elapsed = time.monotonic() - started

    assert response.status_code == 503
    assert response.headers['retry-after'] == '1'
    assert response.json()['detail'] == memory_product.MEMORY_SEARCH_UNAVAILABLE_DETAIL
    # Fails at the internal budget, not at the 30s edge timeout.
    assert elapsed < 5.0
    assert db_client.streams and db_client.streams[0].closed


def test_memory_search_still_answers_normally_within_the_budget(monkeypatch):
    monkeypatch.setenv('OMI_LIST_READ_BUDGET_SECONDS', '24')
    monkeypatch.setenv('OMI_MEMORY_READ_RETRY_BURST', '64')
    db_client = _FirestoreFake(_docs(5))

    response = _client(monkeypatch, db_client).get('/memory/search', params={'query': 'coffee', 'limit': 10})

    assert response.status_code == 200
    body = response.json()
    assert body['returned_count'] == 5
    assert [item['memory_id'] for item in body['items']] == [f'memory-{index:03d}' for index in range(5)]
    assert body['archive_default_visible'] is False
