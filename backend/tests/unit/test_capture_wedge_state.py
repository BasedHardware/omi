"""Hermetic unit tests for ``database.capture_wedge_state``."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from database import capture_wedge_state as state

BASE_UTC = datetime(2026, 7, 20, 12, 0, 0, tzinfo=timezone.utc)


class _FakeSnapshot:
    def __init__(self, data: dict[str, Any] | None):
        self._data = dict(data) if data is not None else None
        self.exists = data is not None

    def to_dict(self) -> dict[str, Any] | None:
        return dict(self._data) if self._data is not None else None


class _FakeDocRef:
    def __init__(self, store: dict[str, dict[str, Any]], doc_id: str):
        self._store = store
        self.id = doc_id

    def get(self, transaction: Any = None) -> _FakeSnapshot:
        return _FakeSnapshot(self._store.get(self.id))


class _FakeTransaction:
    def __init__(self, store: dict[str, dict[str, Any]]):
        self._store = store
        self._read_only = False
        self._id = b'fake-txn'
        self.in_progress = True
        self.writes: list[tuple[str, dict[str, Any], bool]] = []

    def _begin(self, retry_id: Any = None) -> None:
        self.in_progress = True

    def _commit(self) -> list[Any]:
        self.in_progress = False
        return []

    def _rollback(self) -> None:
        self.in_progress = False

    def _clean_up(self) -> None:
        self.in_progress = False

    def set(self, doc_ref: _FakeDocRef, payload: dict[str, Any], merge: bool = False) -> None:
        existing = dict(self._store.get(doc_ref.id, {})) if merge else {}
        existing.update(payload)
        self._store[doc_ref.id] = existing
        self.writes.append((doc_ref.id, dict(payload), merge))


class _FakeCollection:
    def __init__(self, store: dict[str, dict[str, Any]], name: str):
        self._store = store
        self.name = name
        self.requested_ids: list[str] = []

    def document(self, doc_id: str) -> _FakeDocRef:
        self.requested_ids.append(doc_id)
        return _FakeDocRef(self._store, doc_id)


class _FakeFirestoreClient:
    def __init__(self, initial: dict[str, dict[str, Any]] | None = None):
        self.store: dict[str, dict[str, Any]] = {k: dict(v) for k, v in (initial or {}).items()}
        self.collections: dict[str, _FakeCollection] = {}
        self.transactions: list[_FakeTransaction] = []

    def collection(self, name: str) -> _FakeCollection:
        col = self.collections.get(name)
        if col is None:
            col = _FakeCollection(self.store, name)
            self.collections[name] = col
        return col

    def transaction(self, **_kwargs: Any) -> _FakeTransaction:
        txn = _FakeTransaction(self.store)
        self.transactions.append(txn)
        return txn


@pytest.fixture(autouse=True)
def _passthrough_transactional(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(state.firestore, 'transactional', lambda fn: fn)


def test_claim_wedge_first_seen_claims_once_per_day_and_strips_inputs() -> None:
    client = _FakeFirestoreClient()
    naive_now = datetime(2026, 7, 20, 12, 0, 0)

    assert state.claim_wedge_first_seen('  user-1  ', ' 2026-07-20 ', now=naive_now, firestore_client=client) is True
    assert client.store['user-1'] == {
        'uid': 'user-1',
        'first_seen_day': '2026-07-20',
        'updated_at': BASE_UTC,
    }
    assert client.store['user-1']['updated_at'].tzinfo == timezone.utc

    # Duplicate claim on the same day (even with different whitespace padding) is rejected.
    later = BASE_UTC + timedelta(hours=2)
    assert state.claim_wedge_first_seen('user-1', '2026-07-20', now=later, firestore_client=client) is False
    assert client.store['user-1']['updated_at'] == BASE_UTC

    # Next UTC day succeeds and updates the record.
    next_day = BASE_UTC + timedelta(days=1)
    assert state.claim_wedge_first_seen('user-1', '2026-07-21', now=next_day, firestore_client=client) is True
    assert client.store['user-1']['first_seen_day'] == '2026-07-21'
    assert client.store['user-1']['updated_at'] == next_day


@pytest.mark.parametrize('bad_uid', [None, '', '   ', '\t\n', 123, [], {}])
@pytest.mark.parametrize('bad_day', [None, '', '   ', '\t\n', 456])
def test_claim_wedge_first_seen_rejects_invalid_or_blank_uid_and_day_without_touching_firestore(
    monkeypatch: pytest.MonkeyPatch,
    bad_uid: Any,
    bad_day: Any,
) -> None:
    monkeypatch.setattr(
        state,
        'get_firestore_client',
        lambda: (_ for _ in ()).throw(AssertionError('Firestore client must not be initialized on invalid inputs')),
    )
    assert state.claim_wedge_first_seen(bad_uid, '2026-07-20') is False
    assert state.claim_wedge_first_seen('valid-uid', bad_day) is False


def test_claim_wedge_nudge_cooldown_handles_naive_and_offset_aware_timestamps() -> None:
    # Stored timestamp is timezone-aware UTC; caller passes a naive datetime 12h later.
    client = _FakeFirestoreClient({'u1': {'uid': 'u1', 'last_nudge_at': BASE_UTC}})
    naive_within_cooldown = datetime(2026, 7, 21, 0, 0, 0)
    assert state.claim_wedge_nudge_cooldown('u1', now=naive_within_cooldown, firestore_client=client) is False
    assert client.store['u1']['last_nudge_at'] == BASE_UTC

    # Caller passes a naive datetime exactly 24h later -> succeeds and stores UTC-aware timestamp.
    naive_at_boundary = datetime(2026, 7, 21, 12, 0, 0)
    assert state.claim_wedge_nudge_cooldown('  u1 ', now=naive_at_boundary, firestore_client=client) is True
    assert client.store['u1']['last_nudge_at'] == datetime(2026, 7, 21, 12, 0, 0, tzinfo=timezone.utc)
    assert client.store['u1']['last_nudge_at'].tzinfo == timezone.utc

    # Stored timestamp is naive; caller passes non-UTC offset-aware datetime (+02:00) 23h later -> still in cooldown.
    client.store['u1']['last_nudge_at'] = datetime(2026, 7, 21, 12, 0, 0)
    tz_plus_2 = timezone(timedelta(hours=2))
    aware_plus_2_within = datetime(2026, 7, 22, 13, 0, 0, tzinfo=tz_plus_2)  # 11:00 UTC (23h elapsed)
    assert state.claim_wedge_nudge_cooldown('u1', now=aware_plus_2_within, firestore_client=client) is False

    aware_plus_2_ready = datetime(2026, 7, 22, 14, 0, 0, tzinfo=tz_plus_2)  # 12:00 UTC (24h elapsed)
    assert state.claim_wedge_nudge_cooldown('u1', now=aware_plus_2_ready, firestore_client=client) is True
    assert client.store['u1']['last_nudge_at'] == datetime(2026, 7, 22, 12, 0, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    'bad_cooldown',
    [
        timedelta(seconds=-1),
        timedelta(hours=-24),
        None,
        '24h',
        -100,
    ],
)
def test_claim_wedge_nudge_cooldown_clamps_negative_or_invalid_cooldown_to_default_24h(bad_cooldown: Any) -> None:
    client = _FakeFirestoreClient({'u1': {'uid': 'u1', 'last_nudge_at': BASE_UTC}})

    # 1 hour after last nudge must still be blocked when a negative/invalid cooldown is supplied.
    assert (
        state.claim_wedge_nudge_cooldown(
            'u1',
            cooldown=bad_cooldown,
            now=BASE_UTC + timedelta(hours=1),
            firestore_client=client,
        )
        is False
    )
    # 24 hours after last nudge succeeds under the clamped default cooldown.
    assert (
        state.claim_wedge_nudge_cooldown(
            'u1',
            cooldown=bad_cooldown,
            now=BASE_UTC + state.WEDGE_NUDGE_COOLDOWN,
            firestore_client=client,
        )
        is True
    )


@pytest.mark.parametrize('bad_uid', [None, '', '   ', '\n\t ', 999, []])
def test_claim_wedge_nudge_cooldown_rejects_invalid_uid_without_touching_firestore(
    monkeypatch: pytest.MonkeyPatch,
    bad_uid: Any,
) -> None:
    monkeypatch.setattr(
        state,
        'get_firestore_client',
        lambda: (_ for _ in ()).throw(AssertionError('Firestore client must not be initialized on invalid uid')),
    )
    assert state.claim_wedge_nudge_cooldown(bad_uid, now=BASE_UTC) is False


def test_claim_wedge_nudge_cooldown_overwrites_non_datetime_stored_stamp() -> None:
    client = _FakeFirestoreClient({'u1': {'uid': 'u1', 'last_nudge_at': 'corrupted-timestamp'}})
    assert state.claim_wedge_nudge_cooldown('u1', now=BASE_UTC, firestore_client=client) is True
    assert client.store['u1']['last_nudge_at'] == BASE_UTC
