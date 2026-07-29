"""Bounded serving-query contract for the memory review queue.

Migrated to the neutral storage port (WP2, ADR-0028): the persistence seam is the
``DocumentStore`` returned by ``review_queue._store()``, exercised through
``tests.store_fakes.FakeDocumentStore``. The former Firestore-shaped ranked-query,
rotating legacy-scan cursor, and ``memory_state`` cursor lanes are gone — a neutral
collection scan returns every row and a single repair pass self-heals stale/legacy rows,
so the tests assert returned values and stored state, not those retired internals.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence
from unittest.mock import patch

import pytest

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

from database import read_boundary, review_queue
from tests.store_fakes import FakeDocumentStore


class _RecordingStore(FakeDocumentStore):
    """Port fake that records batch source reads and can fail self-heal writes."""

    def __init__(self, *, backing: dict[str, dict[str, Any]] | None = None) -> None:
        super().__init__(backing=backing)
        self.batch_get_log: list[list[str]] = []
        self.fail_review_updates = False

    def get_many(self, collection: str, ids: Sequence[str]):
        self.batch_get_log.append(list(ids))
        return super().get_many(collection, ids)

    def update(self, path: str, data: dict[str, Any]) -> None:
        if self.fail_review_updates and '/memory_review_queue/' in path:
            raise RuntimeError('review self-heal failed')
        super().update(path, data)


def _review(
    review_id: str,
    *,
    impact: float,
    created_at: datetime,
    status: str = 'pending',
    canonical: bool = False,
):
    item = {
        'review_id': review_id,
        'fact_id': f'memory-{review_id}',
        'candidate': {'id': f'memory-{review_id}', 'content': review_id},
        'conflict_with': [],
        'status': status,
        'impact': impact,
        'created_at': created_at,
    }
    if canonical:
        item.update(
            {
                'authority': 'canonical_memory',
                'source_commit_id': f'commit-{review_id}',
                'source_item_revision': 1,
                'source_content_hash': f'hash-{review_id}',
            }
        )
    return item


def _seed(uid: str, items) -> _RecordingStore:
    store = _RecordingStore()
    for item in items:
        store.set(f'users/{uid}/memory_review_queue/{item["review_id"]}', item)
    return store


def test_list_review_conflicts_applies_status_order_and_limit(monkeypatch):
    uid = 'uid-bounded-review-list'
    now = datetime(2026, 7, 28, tzinfo=timezone.utc)
    store = _seed(
        uid,
        [
            _review('accepted', impact=1.0, created_at=now, status='accepted'),
            _review('high', impact=0.9, created_at=now - timedelta(minutes=2)),
            _review('middle', impact=0.5, created_at=now),
            _review('low', impact=0.1, created_at=now + timedelta(minutes=2)),
        ],
    )
    monkeypatch.setattr(review_queue, '_store', lambda: store)

    result = review_queue.list_review_conflicts(uid, status='pending', limit=2)

    # Status filter drops the accepted row; impact-descending order + the server-side limit
    # return the two highest-impact pending rows and never surface 'low'.
    assert [item['review_id'] for item in result] == ['high', 'middle']
    # No canonical rows -> the batched source lane is never touched.
    assert store.batch_get_log == []


def test_list_review_conflicts_fills_after_a_stale_canonical_page_with_one_batch_read(monkeypatch):
    uid = 'uid-stale-review-page'
    now = datetime(2026, 7, 28, tzinfo=timezone.utc)
    store = _seed(
        uid,
        [
            _review('stale-high', impact=1.0, created_at=now, canonical=True),
            _review('stale-next', impact=0.9, created_at=now, canonical=True),
            _review('valid-high', impact=0.8, created_at=now),
            _review('valid-next', impact=0.7, created_at=now),
        ],
    )
    monkeypatch.setattr(review_queue, '_store', lambda: store)

    result = review_queue.list_review_conflicts(uid, status='pending', limit=2)

    # The two canonical rows have no live source item -> they self-heal to tombstoned and drop
    # out of the pending page, so the valid rows fill it instead of leaving a short page.
    assert [item['review_id'] for item in result] == ['valid-high', 'valid-next']
    # Canonical source ownership is confirmed in a single batched read for the whole page.
    assert store.batch_get_log == [['memory-stale-high', 'memory-stale-next']]


def test_list_review_conflicts_tombstones_malformed_canonical_source_through_read_boundary(
    monkeypatch,
    caplog,
):
    uid = 'uid-malformed-canonical-review-source'
    now = datetime(2026, 7, 28, tzinfo=timezone.utc)
    secret = 'private malformed canonical memory content'
    review = _review('malformed-source', impact=1.0, created_at=now, canonical=True)
    store = _seed(uid, [review])
    store.set(
        f'users/{uid}/memory_items/memory-malformed-source',
        {'memory_id': 'memory-malformed-source', 'content': secret},
    )
    monkeypatch.setattr(review_queue, '_store', lambda: store)

    with patch.object(read_boundary, 'record_fallback') as fallback:
        result = review_queue.list_review_conflicts(uid, status='pending', limit=1)

    stored = store.get(f'users/{uid}/memory_review_queue/malformed-source').to_dict()
    assert result == []
    assert stored['status'] == 'tombstoned'
    assert stored['reason'] == 'canonical_review_source_invalid'
    assert stored['candidate'] == {'id': 'memory-malformed-source'}
    assert fallback.call_count == 1
    assert f'users/{uid}/memory_items/memory-malformed-source' in caplog.text
    assert secret not in caplog.text


def test_list_review_conflicts_self_heals_every_stale_canonical_row_in_one_pass(monkeypatch):
    uid = 'uid-stale-review-bound'
    now = datetime(2026, 7, 28, tzinfo=timezone.utc)
    stale_items = [
        _review(
            f'stale-{index:02d}',
            impact=1.0 - index / 100,
            created_at=now,
            canonical=True,
        )
        for index in range(3)
    ]
    valid = _review('valid-after-stale-prefix', impact=0.5, created_at=now)
    store = _seed(uid, [*stale_items, valid])
    monkeypatch.setattr(review_queue, '_store', lambda: store)

    result = review_queue.list_review_conflicts(uid, status='pending', limit=1)

    # A single neutral scan returns every row: the stale canonical rows self-heal and the valid
    # row is served immediately (no rotating-page allowance needed).
    assert [item['review_id'] for item in result] == ['valid-after-stale-prefix']
    assert all(
        store.get(f'users/{uid}/memory_review_queue/{item["review_id"]}').to_dict()['status'] == 'tombstoned'
        for item in stale_items
    )
    # The redaction strips the candidate content from every self-healed row.
    assert all(
        'content' not in store.get(f'users/{uid}/memory_review_queue/{item["review_id"]}').to_dict()['candidate']
        for item in stale_items
    )
    # One batched source read covers the whole scanned page.
    assert len(store.batch_get_log) == 1
    assert store.batch_get_log[0] == ['memory-stale-00', 'memory-stale-01', 'memory-stale-02']


def test_list_review_conflicts_keeps_legacy_rows_missing_rank_fields(monkeypatch):
    uid = 'uid-legacy-review-list'
    now = datetime(2026, 7, 28, tzinfo=timezone.utc)
    legacy = _review('legacy-high', impact=0.9, created_at=now)
    legacy.pop('created_at')
    store = _seed(
        uid,
        [
            legacy,
            _review('modern-low', impact=0.1, created_at=now),
        ],
    )
    monkeypatch.setattr(review_queue, '_store', lambda: store)

    result = review_queue.list_review_conflicts(uid, status='pending', limit=2)

    # A legacy row missing the ranked field is still served (the neutral scan does not drop it)
    # and outranks the low-impact modern row.
    assert [item['review_id'] for item in result] == ['legacy-high', 'modern-low']
    # The repair pass backfills the missing rank field so future reads sort deterministically.
    stored_legacy = store.get(f'users/{uid}/memory_review_queue/legacy-high').to_dict()
    assert stored_legacy['created_at'] == review_queue.REVIEW_LIST_LEGACY_CREATED_AT_SENTINEL


def test_list_review_conflicts_self_heal_failure_fails_closed(monkeypatch):
    uid = 'uid-stale-review-write-failure'
    now = datetime(2026, 7, 28, tzinfo=timezone.utc)
    stale = _review('stale-private', impact=1.0, created_at=now, canonical=True)
    store = _seed(uid, [stale])
    store.fail_review_updates = True
    monkeypatch.setattr(review_queue, '_store', lambda: store)

    with pytest.raises(RuntimeError, match='review self-heal failed'):
        review_queue.list_review_conflicts(uid, status='pending', limit=1)

    stored = store.get(f'users/{uid}/memory_review_queue/stale-private').to_dict()
    assert stored['status'] == 'pending'
    assert stored['candidate']['content'] == 'stale-private'
