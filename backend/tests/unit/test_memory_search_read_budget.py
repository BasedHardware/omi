"""Product memory search must fail fast under read pressure (SCA-3795).

``GET /memory/search`` reads the authoritative ``memory_items`` collection
with no request budget or per-RPC deadline, so under read pressure it holds
to the 30s edge timeout and comes back as a bare 504 (four occurrences:
SCA-3797, SCA-4277, SCA-4823, SCA-5469). The approved design keeps the
authoritative read and the 5,000-item window and adds:

* a request-scoped deadline threaded into every Firestore RPC of the read,
* per-row charging so a scan that walks past its allowance stops,
* cancellation of the outstanding stream when the budget expires,
* a typed exhaustion that the route maps to its existing 503 contract --
  never a partial or empty window returned as a successful search.

These tests drive the real read path (``fetch_default_product_memory_search``
through ``MemoryService``) against a fake store, and cover normal load,
deadline exhaustion, document exhaustion, SDK deadline mapping, and a
saturating burst of concurrent searches.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
from google.api_core.exceptions import DeadlineExceeded as FirestoreDeadlineExceeded

import database.memories as memories_db
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.product_memory import (
    MemoryAccessPolicy,
    MemoryItem,
    MemoryItemStatus,
    MemoryTier,
    ProcessingState,
)
from utils.memory.product_memory_read_service import fetch_default_product_memory_search
from utils.memory.short_term_lifecycle import DEFAULT_SHORT_TERM_TTL_DAYS
from utils.other.list_budget import ListReadBudget, ListReadBudgetExhausted
from database.firestore_retry import FIRESTORE_NO_RETRY

_UID = 'u1'


@pytest.fixture(autouse=True)
def _empty_historical_store(monkeypatch):
    """This suite exercises the authoritative canonical read only."""
    monkeypatch.setattr(memories_db, 'get_memories', lambda *args, **kwargs: [])
    monkeypatch.setattr(memories_db, 'list_memory_updated_or_created_index', lambda *args, **kwargs: [])
    monkeypatch.setattr(memories_db, 'get_memories_by_ids', lambda *args, **kwargs: [])


class _Snapshot:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self.exists = True

    def to_dict(self):
        return dict(self._data)


class _Stream:
    """Firestore stream double that records how it was opened and closed."""

    def __init__(self, snapshots, *, per_row_seconds=0.0, fail_after=None):
        self._snapshots = list(snapshots)
        self._position = 0
        self._per_row_seconds = per_row_seconds
        self._fail_after = fail_after
        self.closed = False
        self.rows_yielded = 0

    def __iter__(self):
        return self

    def __next__(self):
        if self.closed:
            raise StopIteration
        if self._fail_after is not None and self.rows_yielded >= self._fail_after:
            raise FirestoreDeadlineExceeded('firestore rpc deadline exceeded')
        if self._position >= len(self._snapshots):
            raise StopIteration
        if self._per_row_seconds:
            time.sleep(self._per_row_seconds)
        snapshot = self._snapshots[self._position]
        self._position += 1
        self.rows_yielded += 1
        return snapshot

    def close(self):
        self.closed = True


class _Collection:
    def __init__(self, db):
        self._db = db

    def stream(self, **kwargs):
        self._db.stream_calls.append(kwargs)
        return self._db.next_stream()


class _FirestoreFake:
    def __init__(self, snapshots, *, accept_stream_kwargs=True, per_row_seconds=0.0, fail_after=None):
        self._snapshots = snapshots
        self._accept_stream_kwargs = accept_stream_kwargs
        self._per_row_seconds = per_row_seconds
        self._fail_after = fail_after
        self.stream_calls: list[dict] = []
        self.streams: list[_Stream] = []
        self.collection_paths: list[str] = []

    def collection(self, path):
        self.collection_paths.append(path)
        if not self._accept_stream_kwargs:
            return _LegacyCollection(self)
        return _Collection(self)

    def next_stream(self):
        stream = _Stream(
            self._snapshots,
            per_row_seconds=self._per_row_seconds,
            fail_after=self._fail_after,
        )
        self.streams.append(stream)
        return stream


class _LegacyCollection:
    """Stream double predating the budget seam (no timeout/retry kwargs)."""

    def __init__(self, db):
        self._db = db

    def stream(self):
        return self._db.next_stream()


def _evidence(source_id='conv1'):
    return MemoryEvidence(
        evidence_id=f'ev-{source_id}',
        source_id=source_id,
        source_type='conversation',
        source_version='v1',
        quote_refs=[{'text': 'User prefers concise product memory reads.'}],
        content_hash='hash1',
        source_state=SourceState.active,
        artifact_preservation=ArtifactPreservationState.preserved,
    )


def _stored_memory(memory_id: str, *, content=None, uid=_UID, now=None):
    captured_at = now or datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    item = MemoryItem(
        memory_id=memory_id,
        uid=uid,
        version=1,
        tier=MemoryTier.short_term,
        status=MemoryItemStatus.active,
        processing_state=ProcessingState.processed,
        content=content or f'{memory_id} coffee preference',
        evidence=[_evidence(f'{memory_id}-source')],
        source_state=SourceState.active,
        sensitivity_labels=[],
        visibility='private',
        user_asserted=False,
        captured_at=captured_at,
        updated_at=captured_at,
        expires_at=captured_at + timedelta(days=DEFAULT_SHORT_TERM_TTL_DAYS),
    )
    return item.model_dump(mode='json')


def _snapshots(count: int, *, matching: bool = True):
    return [
        _Snapshot(
            f'memory-{index:03d}',
            _stored_memory(
                f'memory-{index:03d}',
                content=f'coffee preference {index}' if matching else f'tea preference {index}',
            ),
        )
        for index in range(count)
    ]


def _policy():
    return MemoryAccessPolicy.for_omi_chat(archive_capability=False)


def _budget(*, seconds=24.0, max_documents=25_000):
    now = time.monotonic()
    return ListReadBudget(
        deadline_monotonic=now + seconds,
        max_documents=max_documents,
        route='memory-product-search',
        started_monotonic=now,
    )


# ---------------------------------------------------------------------------
# Normal load
# ---------------------------------------------------------------------------


def test_normal_load_search_is_unchanged_and_runs_under_one_budgeted_rpc():
    db = _FirestoreFake(_snapshots(5))
    budget = _budget()

    response = fetch_default_product_memory_search(
        _UID,
        'coffee',
        db_client=db,
        policy=_policy(),
        now=datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc),
        limit=10,
        budget=budget,
    )

    # Released ordering is newest-first by updated_at then memory_id; equal
    # timestamps keep memory_id ascending.
    assert [item['memory_id'] for item in response['items']] == [
        'memory-000',
        'memory-001',
        'memory-002',
        'memory-003',
        'memory-004',
    ]
    assert response['total_count'] == 5
    assert db.collection_paths == [f'users/{_UID}/memory_items']
    # The authoritative stream is opened once, with the budget's remaining
    # deadline as its RPC timeout and no SDK retry that would restart it.
    assert len(db.stream_calls) == 1
    assert 0 < db.stream_calls[0]['timeout'] <= 24.0
    assert db.stream_calls[0]['retry'] is FIRESTORE_NO_RETRY
    assert budget.docs_scanned == 5
    assert not budget.truncated
    assert db.streams[0].closed


def test_search_without_a_budget_keeps_the_released_unbounded_call():
    db = _FirestoreFake(_snapshots(2))

    response = fetch_default_product_memory_search(
        _UID,
        'coffee',
        db_client=db,
        policy=_policy(),
        limit=10,
    )

    assert response['total_count'] == 2
    assert db.stream_calls == [{}]
    assert not db.streams[0].closed


def test_budgeted_search_keeps_the_5000_item_window():
    # The approved design preserves the authoritative 5,000-item read; the
    # budget bounds its wall clock, it does not shrink the search window.
    from utils.memory.memory_service import HistoricalMemoryAdapter

    db = _FirestoreFake(_snapshots(3))
    fetch_default_product_memory_search(
        _UID,
        'coffee',
        db_client=db,
        policy=_policy(),
        limit=10,
        budget=_budget(seconds=5.0),
    )

    # read_canonical_memories slices to its requested window; the fake store
    # cannot tell us the window, so assert the reader was asked for the full
    # authoritative collection (unchanged cap) by counting streamed rows.
    assert db.streams[0].rows_yielded == 3
    assert HistoricalMemoryAdapter.MAX_COMPATIBILITY_WINDOW == 5000


# ---------------------------------------------------------------------------
# Deadline exhaustion
# ---------------------------------------------------------------------------


def test_deadline_exhaustion_raises_and_closes_the_outstanding_stream():
    db = _FirestoreFake(_snapshots(50), per_row_seconds=0.02)
    budget = _budget(seconds=0.3)

    started = time.monotonic()
    with pytest.raises(ListReadBudgetExhausted) as excinfo:
        fetch_default_product_memory_search(
            _UID,
            'coffee',
            db_client=db,
            policy=_policy(),
            limit=10,
            budget=budget,
        )
    elapsed = time.monotonic() - started

    assert excinfo.value.reason == 'deadline'
    assert budget.truncated
    # Fails fast well inside the 30s edge timeout instead of walking all 50 rows.
    assert elapsed < 2.0
    assert db.streams[0].rows_yielded < 50
    assert db.streams[0].closed
    assert budget.docs_scanned < 50


def test_sdk_rpc_deadline_becomes_the_typed_exhaustion_not_a_partial_result():
    db = _FirestoreFake(_snapshots(10), fail_after=3)
    budget = _budget()

    with pytest.raises(ListReadBudgetExhausted) as excinfo:
        fetch_default_product_memory_search(
            _UID,
            'coffee',
            db_client=db,
            policy=_policy(),
            limit=10,
            budget=budget,
        )

    assert excinfo.value.reason == 'deadline'
    assert db.streams[0].closed


def test_document_allowance_exhaustion_is_typed_and_never_a_partial_page():
    db = _FirestoreFake(_snapshots(10))
    budget = _budget(max_documents=3)

    with pytest.raises(ListReadBudgetExhausted) as excinfo:
        fetch_default_product_memory_search(
            _UID,
            'coffee',
            db_client=db,
            policy=_policy(),
            limit=10,
            budget=budget,
        )

    assert excinfo.value.reason == 'documents'
    assert budget.docs_scanned >= 3
    assert db.streams[0].closed


def test_legacy_stream_double_without_timeout_kwargs_still_stops_on_the_budget():
    db = _FirestoreFake(_snapshots(10), accept_stream_kwargs=False)
    budget = _budget(max_documents=2)

    with pytest.raises(ListReadBudgetExhausted) as excinfo:
        fetch_default_product_memory_search(
            _UID,
            'coffee',
            db_client=db,
            policy=_policy(),
            limit=10,
            budget=budget,
        )

    assert excinfo.value.reason == 'documents'
    assert db.streams[0].closed


# ---------------------------------------------------------------------------
# Saturation
# ---------------------------------------------------------------------------


def test_saturating_burst_of_searches_fails_fast_and_cancels_every_read(monkeypatch):
    """Concurrent pressure: each request either finishes or fails fast.

    Concurrent single-client bursts (2-8 parallel queries, retried ~30s later)
    are how the production incident presents. Under a saturating burst every
    request must stay inside its own budget, cancel the read it abandoned, and
    never surface an empty or partial page as a successful search.
    """
    from utils.memory import read_resilience

    # Isolate the read budget from the separate process-wide retry allowance
    # (covered by the admission-pressure test below) so this burst exercises
    # the deadline under contention.
    monkeypatch.setattr(read_resilience, '_retry_allowance', read_resilience.RetryAllowance())
    monkeypatch.setenv('OMI_MEMORY_READ_RETRY_BURST', '64')
    db = _FirestoreFake(_snapshots(200), per_row_seconds=0.005)
    outcomes: list[str] = []
    lock = threading.Lock()
    barrier = threading.Barrier(12)

    def _search() -> None:
        budget = _budget(seconds=0.15)
        barrier.wait()
        try:
            fetch_default_product_memory_search(
                _UID,
                'coffee',
                db_client=db,
                policy=_policy(),
                limit=10,
                budget=budget,
            )
        except ListReadBudgetExhausted as exc:
            outcome = f'exhausted:{exc.reason}'
        except Exception as exc:  # pragma: no cover - surfaced in the assertion
            outcome = f'error:{type(exc).__name__}'
        else:
            outcome = 'complete'
        with lock:
            outcomes.append(outcome)

    started = time.monotonic()
    threads = [threading.Thread(target=_search) for _ in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    elapsed = time.monotonic() - started

    assert len(outcomes) == 12
    assert all(outcome == 'exhausted:deadline' for outcome in outcomes), outcomes
    # Every abandoned read was cancelled; nothing was left streaming.
    assert len(db.streams) == 12
    assert all(stream.closed for stream in db.streams)
    assert elapsed < 10.0


def test_admission_pressure_fails_fast_with_the_existing_503_contract(monkeypatch):
    """When whole-operation admission is spent the request 503s, never hangs."""
    from fastapi import HTTPException

    from utils.memory import read_resilience

    monkeypatch.setattr(read_resilience, '_retry_allowance', read_resilience.RetryAllowance())
    monkeypatch.setenv('OMI_MEMORY_READ_RETRY_BURST', '1')
    db = _FirestoreFake(_snapshots(3))

    fetch_default_product_memory_search(_UID, 'coffee', db_client=db, policy=_policy(), limit=10, budget=_budget())

    started = time.monotonic()
    with pytest.raises(HTTPException) as excinfo:
        fetch_default_product_memory_search(
            _UID,
            'coffee',
            db_client=db,
            policy=_policy(),
            limit=10,
            budget=_budget(),
        )
    elapsed = time.monotonic() - started

    assert excinfo.value.status_code == 503
    assert excinfo.value.detail == 'Memory read admission exhausted'
    assert excinfo.value.headers == {'Retry-After': '1'}
    assert elapsed < 1.0
    # The denied request never opened a store read.
    assert len(db.streams) == 1
