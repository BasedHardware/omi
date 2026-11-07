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
    def __init__(self, store: dict[str, dict[str, Any]], doc_id: str, owner_client: _FakeFirestoreClient):
        self._store = store
        self.id = doc_id
        self._owner_client = owner_client

    def get(self, transaction: Any = None) -> _FakeSnapshot:
        if not isinstance(transaction, _FakeTransaction) or transaction._owner_client is not self._owner_client:
            raise AssertionError('Document read must be bound to an active transaction from the same Firestore client')
        if not transaction.in_progress:
            raise AssertionError('Cannot read document outside an active transaction')
        if transaction._staged_writes:
            raise AssertionError('Firestore transactions require all reads to execute before any writes')
        transaction.reads.append(self.id)
        return _FakeSnapshot(self._store.get(self.id))


class _FakeTransaction:
    def __init__(self, store: dict[str, dict[str, Any]], owner_client: _FakeFirestoreClient):
        self._store = store
        self._owner_client = owner_client
        self._read_only = False
        self._max_attempts = 1
        self._id: bytes | None = None
        self.in_progress = False
        self.committed = False
        self.rolled_back = False
        self.reads: list[str] = []
        self._staged_writes: list[tuple[str, dict[str, Any], bool]] = []
        self.writes: list[tuple[str, dict[str, Any], bool]] = []

    def _begin(self, retry_id: Any = None) -> None:
        self._id = b'fake-txn'
        self.in_progress = True
        self.reads.clear()
        self._staged_writes.clear()

    def _commit(self) -> list[Any]:
        if not self.in_progress:
            raise AssertionError('Cannot commit a transaction that is not in progress')
        for doc_id, payload, merge in self._staged_writes:
            existing = dict(self._store.get(doc_id, {})) if merge else {}
            existing.update(payload)
            self._store[doc_id] = existing
            self.writes.append((doc_id, dict(payload), merge))
        self._staged_writes.clear()
        self.in_progress = False
        self.committed = True
        return []

    def _rollback(self) -> None:
        self._staged_writes.clear()
        self.in_progress = False
        self.rolled_back = True

    def _clean_up(self) -> None:
        self._staged_writes.clear()
        self.in_progress = False
        self._id = None

    def set(self, doc_ref: _FakeDocRef, payload: dict[str, Any], merge: bool = False) -> None:
        if not self.in_progress:
            raise AssertionError('Cannot stage a write outside an active transaction')
        if doc_ref._owner_client is not self._owner_client:
            raise AssertionError('Document reference does not belong to this transaction client')
        if doc_ref.id not in self.reads:
            raise AssertionError('Claim transaction must read the target document before staging a write')
        self._staged_writes.append((doc_ref.id, dict(payload), merge))


class _FakeCollection:
    def __init__(self, store: dict[str, dict[str, Any]], name: str, owner_client: _FakeFirestoreClient):
        self._store = store
        self.name = name
        self._owner_client = owner_client
        self.requested_ids: list[str] = []

    def document(self, doc_id: str) -> _FakeDocRef:
        self.requested_ids.append(doc_id)
        return _FakeDocRef(self._store, doc_id, self._owner_client)


class _FakeFirestoreClient:
    def __init__(self, initial: dict[str, dict[str, Any]] | None = None):
        self.store: dict[str, dict[str, Any]] = {k: dict(v) for k, v in (initial or {}).items()}
        self.collections: dict[str, _FakeCollection] = {}
        self.transactions: list[_FakeTransaction] = []

    def collection(self, name: str) -> _FakeCollection:
        col = self.collections.get(name)
        if col is None:
            col = _FakeCollection(self.store, name, self)
            self.collections[name] = col
        return col

    def transaction(self, **_kwargs: Any) -> _FakeTransaction:
        txn = _FakeTransaction(self.store, self)
        self.transactions.append(txn)
        return txn


def test_claim_wedge_first_seen_claims_once_per_day_and_strips_inputs() -> None:
    client = _FakeFirestoreClient()
    naive_now = datetime(2026, 7, 20, 12, 0, 0)

    assert state.claim_wedge_first_seen('  user-1  ', ' 2026-07-20 ', now=naive_now, firestore_client=client) is True
    assert client.transactions[-1].committed is True
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


def test_legacy_padded_uid_state_is_respected_and_migrated() -> None:
    # A record created before UID trimming lived under the raw padded key '  user-legacy  '.
    client = _FakeFirestoreClient(
        {
            '  user-legacy  ': {
                'uid': '  user-legacy  ',
                'first_seen_day': '2026-07-20',
                'last_nudge_at': BASE_UTC,
            }
        }
    )

    # Calling with the padded UID on the same day must consult the legacy padded doc and reject duplicate claim.
    assert state.claim_wedge_first_seen('  user-legacy  ', '2026-07-20', now=BASE_UTC, firestore_client=client) is False
    assert (
        state.claim_wedge_nudge_cooldown(
            '  user-legacy  ',
            now=BASE_UTC + timedelta(hours=2),
            firestore_client=client,
        )
        is False
    )

    # On the next day / after cooldown expiry, claiming under the padded UID migrates state to the canonical key.
    next_day = BASE_UTC + timedelta(days=1)
    assert state.claim_wedge_first_seen('  user-legacy  ', '2026-07-21', now=next_day, firestore_client=client) is True
    assert client.store['user-legacy']['first_seen_day'] == '2026-07-21'
    assert client.store['user-legacy']['last_nudge_at'] == BASE_UTC


def test_strict_transaction_fake_enforces_ownership_ordering_and_deferred_commit() -> None:
    client = _FakeFirestoreClient()
    doc_ref = client.collection(state.CAPTURE_WEDGE_STATE_COLLECTION).document('u1')

    # Unbound read fails.
    with pytest.raises(AssertionError, match='bound to an active transaction'):
        doc_ref.get()

    txn = client.transaction()
    txn._begin()
    # Write before read fails.
    with pytest.raises(AssertionError, match='read the target document before staging a write'):
        txn.set(doc_ref, {'uid': 'u1'}, merge=True)

    # Read then stage write does not mutate store until _commit().
    doc_ref.get(transaction=txn)
    txn.set(doc_ref, {'uid': 'u1'}, merge=True)
    assert 'u1' not in client.store

    # Read after write in the same transaction fails.
    with pytest.raises(AssertionError, match='all reads to execute before any writes'):
        doc_ref.get(transaction=txn)

    txn._commit()
    assert client.store['u1'] == {'uid': 'u1'}


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
