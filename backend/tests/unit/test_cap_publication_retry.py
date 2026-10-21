"""Live cap publication restarts a retired Firestore transaction instead of failing the socket.

An expired transaction id wrote nothing. Contention, a commit deadline, and
unavailable are the same class when the body re-reads before it increments.
"""

from __future__ import annotations

import copy
from contextlib import nullcontext
from threading import RLock
from types import SimpleNamespace

import pytest
from google.api_core.exceptions import (
    Aborted,
    AlreadyExists,
    DeadlineExceeded,
    InvalidArgument,
    ResourceExhausted,
    ServiceUnavailable,
)
from google.cloud.firestore_v1.transforms import Increment

from database._client import (
    firestore_failure_reason,
    is_retryable_firestore_transaction_error,
    run_transactional,
)
from database.firestore_transaction_retry import FirestoreContentionExhausted
from utils.observability import held_content as held_metrics
from utils.sync import cap_hold, cap_hold_redrive, live_cap_manifest, live_cap_staging
from utils.sync.live_cap_publication import Publication

EXPIRED = '400 The referenced transaction has expired or is no longer valid.'
UID = 'synthetic'


def _counter(outcome: str) -> float:
    return held_metrics.PUBLICATION_RETRY.labels(outcome=outcome)._value.get()


def test_failure_reason_classifies_commit_deadline_and_unavailable():
    assert firestore_failure_reason(DeadlineExceeded('deadline')) == 'deadline_exceeded'
    assert firestore_failure_reason(ServiceUnavailable('unavailable')) == 'unavailable'
    assert firestore_failure_reason(ResourceExhausted('429 Quota exceeded.')) == 'resource_exhausted'
    assert is_retryable_firestore_transaction_error(ResourceExhausted('429 Quota exceeded.'))
    assert is_retryable_firestore_transaction_error(InvalidArgument(EXPIRED))
    assert is_retryable_firestore_transaction_error(Aborted('Too much contention on these documents.'))
    assert is_retryable_firestore_transaction_error(DeadlineExceeded('deadline'))
    assert is_retryable_firestore_transaction_error(ServiceUnavailable('unavailable'))
    assert is_retryable_firestore_transaction_error(ValueError('Failed to commit transaction in 5 attempts.'))
    assert is_retryable_firestore_transaction_error(FirestoreContentionExhausted('exhausted'))
    assert not is_retryable_firestore_transaction_error(InvalidArgument('some other 400'))
    assert not is_retryable_firestore_transaction_error(
        InvalidArgument('the document exceeds the maximum allowed size')
    )


def test_default_run_transactional_does_not_retry_resource_exhausted():
    calls = []

    def operation(_tx):
        calls.append(1)
        raise ResourceExhausted('429 Quota exceeded.')

    client = SimpleNamespace(transaction=lambda: object())
    with pytest.raises(ResourceExhausted):
        run_transactional(client, operation, sleep=lambda _delay: (_ for _ in ()).throw(AssertionError('slept')))
    assert calls == [1]


def test_default_run_transactional_does_not_retry_contention_or_sleep():
    calls = []

    def operation(_tx):
        calls.append(1)
        raise Aborted('Too much contention on these documents.')

    client = SimpleNamespace(transaction=lambda: object())
    with pytest.raises(Aborted):
        run_transactional(client, operation, sleep=lambda _delay: (_ for _ in ()).throw(AssertionError('slept')))
    assert calls == [1]


@pytest.mark.parametrize('error', [DeadlineExceeded('deadline'), ServiceUnavailable('unavailable')])
def test_transient_run_transactional_uses_a_fresh_transaction(error):
    seen = []

    def operation(tx):
        seen.append(tx)
        if len(seen) == 1:
            raise error
        return 'ok'

    client = SimpleNamespace(transaction=lambda: object())
    assert run_transactional(client, operation, transient=True, sleep=lambda _delay: None) == 'ok'
    assert len(seen) == 2 and seen[0] is not seen[1]


class _Snap:
    def __init__(self, data):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return None if self._data is None else copy.deepcopy(self._data)


class _Transaction:
    _max_attempts = 5
    _read_only = False

    def __init__(self, client: '_Client'):
        self.client = client
        self._id = f'txn-{len(client.transactions)}'.encode()
        self.ops: list[tuple] = []

    def _clean_up(self) -> None:
        return None

    def _begin(self, retry_id=None) -> None:
        return None

    def _rollback(self) -> None:
        return None

    def create(self, ref, payload) -> None:
        self.ops.append(('create', ref.key, copy.deepcopy(payload)))

    def set(self, ref, payload, merge: bool = False) -> None:
        self.ops.append(('set', ref.key, copy.deepcopy(payload), merge))

    def update(self, ref, payload) -> None:
        self.ops.append(('update', ref.key, copy.deepcopy(payload)))

    def _commit(self) -> None:
        action = self.client.actions.pop(0) if self.client.actions else 'ok'
        if action == 'expire':
            raise InvalidArgument(EXPIRED)
        if action == 'deadline':
            self._apply()
            raise DeadlineExceeded('deadline exceeded before the commit reply')
        if action == 'permanent':
            raise InvalidArgument('some other 400')
        if action == 'throttle':
            raise ResourceExhausted('429 Quota exceeded.')
        self._apply()

    def _apply(self) -> None:
        for op in self.ops:
            kind, key, payload = op[0], op[1], op[2]
            merge = kind == 'update' or (kind == 'set' and op[3])
            self.client.write(key, payload, merge=merge, create=kind == 'create')
        self.client.applied += 1


class _Doc:
    def __init__(self, client: '_Client', key: str):
        self.client = client
        self.key = key
        self.path = key

    def get(self, transaction=None, timeout=None):
        if self.client.read_errors:
            raise self.client.read_errors.pop(0)
        return _Snap(self.client.docs.get(self.key))

    def set(self, payload, merge: bool = False, timeout=None) -> None:
        self.client.write(self.key, copy.deepcopy(payload), merge=merge, create=False)

    def create(self, payload) -> None:
        self.client.write(self.key, copy.deepcopy(payload), merge=False, create=True)

    def update(self, payload, timeout=None) -> None:
        self.client.write(self.key, copy.deepcopy(payload), merge=True, create=False)


class _Client:
    def __init__(self, actions: list[str] | None = None, read_errors: list | None = None):
        self.actions = list(actions or [])
        self.read_errors = list(read_errors or [])
        self.docs: dict[str, dict] = {}
        self.transactions: list[_Transaction] = []
        self.applied = 0
        self.increments: list[tuple[str, str, float]] = []
        self.deletes: list[str] = []

    def transaction(self) -> _Transaction:
        txn = _Transaction(self)
        self.transactions.append(txn)
        return txn

    def write(self, key: str, payload: dict, *, merge: bool, create: bool) -> None:
        if create and key in self.docs:
            raise AlreadyExists('exists')
        current = dict(self.docs.get(key) or {})
        applied = {}
        for field, value in payload.items():
            if isinstance(value, Increment):
                applied[field] = float(current.get(field) or 0) + float(value.value)
                self.increments.append((key, field, float(value.value)))
            else:
                applied[field] = value
        self.docs[key] = {**current, **applied} if merge else applied


class _Blob:
    def __init__(self, name: str, generation: int | None = None):
        self.name = name
        self.generation = generation or 1
        self.size = 64

    def reload(self, timeout=10, retry=None) -> None:
        self.generation = self.generation or 1

    def delete(self, if_generation_match=None, timeout=10, retry=None) -> None:
        return None

    def compose(self, sources, if_generation_match=0, timeout=10, retry=None) -> None:
        self.generation = 7


class _Bucket:
    def __init__(self, deletes: list[str]):
        self.deletes = deletes
        self.blobs: dict[str, _Blob] = {}

    def blob(self, name, generation=None):
        blob = self.blobs.setdefault(name, _Blob(name, generation))
        if generation:
            blob.generation = int(generation)
        blob.delete = self._delete(name, blob.delete)
        return blob

    def _delete(self, name, original):
        def delete(*args, **kwargs):
            self.deletes.append(name)
            return original(*args, **kwargs)

        return delete


class _TrackingLock:
    def __init__(self) -> None:
        self.depth = 0
        self._inner = RLock()

    def __enter__(self):
        self._inner.acquire()
        self.depth += 1
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.depth -= 1
        self._inner.release()


def _track(publication: Publication, locks: list[_TrackingLock]) -> None:
    tracker = _TrackingLock()
    publication.lock = tracker
    locks.append(tracker)


@pytest.fixture
def delays(monkeypatch):
    slept: list[float] = []
    locks: list[_TrackingLock] = []

    def spy(delay: float) -> None:
        assert delay < 5
        assert all(lock.depth == 0 for lock in locks)
        slept.append(delay)

    monkeypatch.setattr('utils.sync.live_cap_publication.retry_sleep', spy)
    return slept, locks


@pytest.fixture
def store(monkeypatch):
    client = _Client()
    bucket = _Bucket(client.deletes)

    def holds(_uid):
        return SimpleNamespace(document=lambda identity: _Doc(client, identity))

    def summary(_uid):
        return _Doc(client, 'summary')

    def upload(_uid, _path, identity, metadata, immutable=False):
        return {
            'audio_path': f'chunks/{UID}/cap-held/{identity}.opus.enc',
            'audio_generation': 1,
            'audio_codec': 'ogg_opus',
            'sample_rate': metadata['sample_rate'],
            'source_frames': metadata['source_frames'],
            'metadata': 'encrypted',
        }

    for module in (live_cap_staging, live_cap_manifest):
        monkeypatch.setattr(module, 'get_firestore_client', lambda client=client: client)
        monkeypatch.setattr(module, 'external_write_fence', lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(cap_hold, 'holds', holds)
    monkeypatch.setattr(cap_hold, 'summary_ref', summary)
    monkeypatch.setattr(cap_hold, 'upload_held_audio', upload)
    monkeypatch.setattr(cap_hold, 'get_private_cloud_sync_bucket', lambda: bucket)
    monkeypatch.setattr(cap_hold, 'metadata', lambda _uid, _row: {'sample_rate': 16000})
    monkeypatch.setattr(live_cap_staging, 'encrypt', lambda payload, _uid: payload)
    monkeypatch.setattr(live_cap_staging, 'owner_storage_write_gate', lambda *args, **kwargs: nullcontext())
    return client


def _append(client: _Client, path: str, **scripts):
    client.actions = list(scripts.get('actions') or [])
    client.read_errors = list(scripts.get('read_errors') or [])
    group = Publication(UID)
    fragment = Publication(UID)
    row = live_cap_staging.append(
        UID,
        path,
        group,
        fragment,
        {'timestamp': 1_700_000_000, 'sample_rate': 16000, 'source_frames': 16000, 'audio_codec': 'ogg_opus'},
        1.0,
    )
    return group, fragment, row


def test_expired_transaction_retries_once_and_publishes_one_fragment(delays, store, tmp_path):
    slept, locks = delays
    path = tmp_path / 'fragment.opus'
    path.write_bytes(b'opus')
    group = Publication(UID)
    _track(group, locks)
    store.actions = ['expire', 'ok']
    fragment = Publication(UID)
    before_ok = _counter('retried_ok')
    row = live_cap_staging.append(
        UID,
        str(path),
        group,
        fragment,
        {'timestamp': 1_700_000_000, 'sample_rate': 16000, 'source_frames': 16000, 'audio_codec': 'ogg_opus'},
        1.0,
    )
    assert len(store.transactions) == 2
    assert store.transactions[0] is not store.transactions[1]
    assert store.applied == 1
    assert [part['id'] for part in row['stage_parts']] == [fragment.identity]
    assert _counter('retried_ok') == before_ok + 1
    assert len(slept) == 1 and sum(slept) < 5
    assert store.deletes == []


def test_aborted_read_retries_on_a_fresh_transaction(delays, store, tmp_path):
    path = tmp_path / 'fragment.opus'
    path.write_bytes(b'opus')
    before_ok = _counter('retried_ok')
    group, fragment, row = _append(
        store,
        str(path),
        read_errors=[Aborted('Too much contention on these documents.')],
    )
    assert len(store.transactions) == 2
    assert store.transactions[0]._id != store.transactions[1]._id
    assert [part['id'] for part in store.docs[group.identity]['stage_parts']] == [fragment.identity]
    assert row['state'] == 'staging'
    assert _counter('retried_ok') == before_ok + 1


def test_exhausted_retries_keep_the_fragment_staged_for_redrive(delays, store, tmp_path, monkeypatch):
    slept, locks = delays
    path = tmp_path / 'fragment.opus'
    path.write_bytes(b'opus')
    group = Publication(UID)
    _track(group, locks)
    fragment = Publication(UID)
    store.actions = ['expire', 'expire', 'expire']
    before_exhausted = _counter('exhausted')
    before_ok = _counter('retried_ok')
    row = live_cap_staging.append(
        UID,
        str(path),
        group,
        fragment,
        {'timestamp': 1_700_000_000, 'sample_rate': 16000, 'source_frames': 16000, 'audio_codec': 'ogg_opus'},
        1.0,
    )
    assert row['state'] == 'staging'
    assert [part['id'] for part in row['stage_parts']] == [fragment.identity]
    assert store.applied == 0  # No transactional commit landed.
    assert store.deletes == []
    assert _counter('exhausted') == before_exhausted + 1
    assert _counter('retried_ok') == before_ok
    assert len(slept) == 2 and sum(slept) < 5
    store.docs[group.identity]['writer_until'] = 0

    snap = SimpleNamespace(
        id=group.identity,
        reference=SimpleNamespace(path=f'users/{UID}/stt_cap_holds/{group.identity}'),
    )
    monkeypatch.setattr(cap_hold_redrive, 'enabled', lambda: True)
    monkeypatch.setattr(cap_hold_redrive, 'execution_admission_configured', lambda: False)
    monkeypatch.setattr(
        cap_hold_redrive.store,
        'fleet_snapshot',
        lambda firestore_client=None: {
            'pending_count': 1,
            'pending_seconds': 1.0,
            'oldest_listed_at': 1_700_000_000,
            'undated_pending': 0,
            'backlog_items': 0,
        },
    )
    monkeypatch.setattr(
        cap_hold_redrive.store,
        'discover',
        lambda kind: [snap] if kind == 'staging' else [],
    )
    assert __import__('asyncio').run(cap_hold_redrive.sweep())['sealed'] == 1
    assert store.docs['summary']['count'] == 1
    assert store.docs['summary']['seconds'] == 1
    assert store.docs[group.identity]['state'] == 'held'
    assert store.increments.count(('summary', 'count', 1.0)) == 1


def test_resource_exhausted_retries_once_and_publishes_one_fragment(delays, store, tmp_path):
    slept, locks = delays
    path = tmp_path / 'fragment.opus'
    path.write_bytes(b'opus')
    group = Publication(UID)
    _track(group, locks)
    store.actions = ['throttle', 'ok']
    fragment = Publication(UID)
    before_ok = _counter('retried_ok')
    row = live_cap_staging.append(
        UID,
        str(path),
        group,
        fragment,
        {'timestamp': 1_700_000_000, 'sample_rate': 16000, 'source_frames': 16000, 'audio_codec': 'ogg_opus'},
        1.0,
    )
    assert len(store.transactions) == 2
    assert store.transactions[0] is not store.transactions[1]
    assert store.applied == 1
    assert [part['id'] for part in row['stage_parts']] == [fragment.identity]
    assert _counter('retried_ok') == before_ok + 1
    assert len(slept) == 1 and sum(slept) < 5
    assert store.deletes == []


def test_resource_exhausted_past_the_budget_stays_staged_for_one_redrive(delays, store, tmp_path, monkeypatch):
    path = tmp_path / 'fragment.opus'
    path.write_bytes(b'opus')
    before_exhausted = _counter('exhausted')
    before_ok = _counter('retried_ok')
    group, fragment, row = _append(store, str(path), actions=['throttle', 'throttle', 'throttle'])
    assert _counter('exhausted') == before_exhausted + 1
    assert _counter('retried_ok') == before_ok
    assert len(delays[0]) == 2 and sum(delays[0]) < 5
    assert row['state'] == 'staging'
    assert [part['id'] for part in row['stage_parts']] == [fragment.identity]
    assert store.applied == 0
    assert store.deletes == []
    assert 'summary' not in store.docs
    store.docs[group.identity]['writer_until'] = 0
    store.actions = []
    snap = SimpleNamespace(
        id=group.identity,
        reference=SimpleNamespace(path=f'users/{UID}/stt_cap_holds/{group.identity}'),
    )
    monkeypatch.setattr(cap_hold_redrive, 'enabled', lambda: True)
    monkeypatch.setattr(cap_hold_redrive, 'execution_admission_configured', lambda: False)
    monkeypatch.setattr(
        cap_hold_redrive.store,
        'fleet_snapshot',
        lambda firestore_client=None: {
            'pending_count': 1,
            'pending_seconds': 1.0,
            'oldest_listed_at': 1_700_000_000,
            'undated_pending': 0,
            'backlog_items': 0,
        },
    )
    monkeypatch.setattr(
        cap_hold_redrive.store,
        'discover',
        lambda kind: [snap] if kind == 'staging' else [],
    )
    assert __import__('asyncio').run(cap_hold_redrive.sweep())['sealed'] == 1
    assert store.docs['summary']['count'] == 1
    assert store.docs['summary']['seconds'] == 1
    assert store.increments.count(('summary', 'count', 1.0)) == 1
    assert store.increments.count(('summary', 'seconds', 1.0)) == 1


def test_non_retryable_invalid_argument_is_not_retried(delays, store, tmp_path):
    path = tmp_path / 'fragment.opus'
    path.write_bytes(b'opus')
    before = _counter('exhausted')
    with pytest.raises(InvalidArgument, match='some other 400'):
        _append(store, str(path), read_errors=[InvalidArgument('some other 400')])
    assert len(store.transactions) == 1
    assert delays[0] == []
    assert _counter('exhausted') == before
    assert 'summary' not in store.docs


def test_ambiguous_commit_does_not_increment_usage_twice(delays, store, tmp_path):
    source = Publication(UID)
    _track(source, delays[1])
    store.actions = ['deadline']
    path = tmp_path / 'minute.opus'
    path.write_bytes(b'opus')
    before = _counter('retried_ok')
    live_cap_manifest.publish(
        UID,
        str(path),
        source,
        {'timestamp': 1_700_000_000, 'sample_rate': 16000, 'source_frames': 16000},
        60,
    )
    assert len(store.transactions) == 2
    assert store.docs['summary']['seconds'] == 60
    assert store.docs['summary']['count'] == 1
    assert store.increments.count(('summary', 'seconds', 60.0)) == 1
    assert store.increments.count(('summary', 'count', 1.0)) == 1
    assert _counter('retried_ok') == before + 1


def test_manifest_exhaustion_publishes_one_receipt_without_raising(delays, store, tmp_path):
    source = Publication(UID)
    _track(source, delays[1])
    path = tmp_path / 'minute.opus'
    path.write_bytes(b'opus')
    store.actions = ['expire', 'expire', 'expire']
    before = _counter('exhausted')
    live_cap_manifest.publish(
        UID,
        str(path),
        source,
        {'timestamp': 1_700_000_000, 'sample_rate': 16000, 'source_frames': 16000},
        60,
    )
    assert store.applied == 0
    assert store.deletes == []
    assert store.docs[source.identity]['state'] == 'held'
    assert store.docs['summary']['seconds'] == 60
    assert store.docs['summary']['count'] == 1
    assert store.increments.count(('summary', 'count', 1.0)) == 1
    assert _counter('exhausted') == before + 1


def test_seal_exhaustion_keeps_parts_until_a_later_seal(delays, store, tmp_path):
    path = tmp_path / 'fragment.opus'
    path.write_bytes(b'opus')
    group, fragment, _row = _append(store, str(path), actions=['expire', 'expire', 'expire'])
    assert store.docs[group.identity]['state'] == 'staging'
    store.actions = ['expire', 'expire', 'expire']
    assert live_cap_staging.seal(UID, group.identity) is False
    assert [part['id'] for part in store.docs[group.identity]['stage_parts']] == [fragment.identity]
    assert 'summary' not in store.docs
    store.docs[group.identity]['writer_until'] = 0
    store.actions = []
    assert live_cap_staging.seal(UID, group.identity, expired_only=True) is True
    assert store.docs['summary']['count'] == 1
    assert store.increments.count(('summary', 'count', 1.0)) == 1
