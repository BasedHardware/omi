"""Live cap publication restarts a retired Firestore transaction instead of failing the socket.

An expired transaction id wrote nothing. Contention, a commit deadline, and
unavailable are the same class when the body re-reads before it increments.
"""

from __future__ import annotations

import asyncio
import copy
from contextlib import nullcontext
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import Mock
from threading import Barrier, Event, Lock, RLock, Thread
from types import SimpleNamespace

import pytest
import requests.exceptions
import urllib3.exceptions
from google.auth.exceptions import TransportError
from google.api_core.exceptions import RetryError
from google.api_core.exceptions import (
    Aborted,
    AlreadyExists,
    DeadlineExceeded,
    FailedPrecondition,
    InvalidArgument,
    NotFound,
    PreconditionFailed,
    ResourceExhausted,
    ServiceUnavailable,
)
from google.cloud.firestore_v1 import ReadAfterWriteError
from google.cloud.firestore_v1.transforms import Increment

from database._client import (
    firestore_failure_reason,
    is_retryable_firestore_transaction_error,
    run_transactional,
)
from database.firestore_transaction_retry import FirestoreContentionExhausted
from routers.listen.contracts import ListenSessionState
from routers.listen.receiver import ListenReceiver, mark_listen_internal_error
from utils.observability import held_content as held_metrics
from utils.sync import cap_hold, cap_hold_redrive, live_cap_manifest, live_cap_staging, live_cap_upload, live_cap_hold
from utils.sync.live_cap_publication import Publication
from utils.sync.live_cap_staging import late_hold_identity

EXPIRED = '400 The referenced transaction has expired or is no longer valid.'
REAL_UPLOAD = cap_hold.upload_held_audio
UID = 'synthetic'
FRAGMENT_PAYLOAD = b'fragment-bytes' * 4


def _counter(outcome: str) -> float:
    return sum(
        held_metrics.PUBLICATION_RETRY.labels(outcome=outcome, cause=cause)._value.get()
        for cause in held_metrics.PUBLICATION_RETRY_CAUSES
    )


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
    def __init__(self, data, update_time):
        self._data = data
        self.exists = data is not None
        self.update_time = update_time

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
        self.ops = []

    def _wait_for_peer_seal(self) -> None:
        barrier = self.client.seal_commit_barrier
        if barrier is None or self.client.seal_commit_barrier_passed:
            return
        if not any(op[0] == 'create' and 'stt_cap_fragment_claims' in op[1] for op in self.ops):
            return
        barrier.wait(timeout=5)
        self.client.seal_commit_barrier_passed = True

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
        self._wait_for_peer_seal()
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
        with self.client.lock:
            for op in self.ops:
                kind, key, payload = op[0], op[1], op[2]
                merge = kind == 'update' or (kind == 'set' and op[3])
                self.client.write(key, payload, merge=merge, create=kind == 'create', locked=True)
            self.client.applied += 1


class _Doc:
    def __init__(self, client: '_Client', key: str):
        self.client = client
        self.key = key
        self.path = key

    def collection(self, name: str) -> '_Collection':
        return _Collection(self.client, f'{self.key}/{name}')

    def get(self, transaction=None, timeout=None, retry=None):
        # The real client raises this before a read reaches the server once the
        # transaction has queued writes (get_transaction_id), so a transactional
        # body must finish its reads first.
        if transaction is not None and transaction.ops:
            raise ReadAfterWriteError('Attempted read after write in a transaction.')
        if self.key in self.client.fail_get_keys:
            self.client.fail_get_keys.discard(self.key)
            raise ResourceExhausted('429 Quota exceeded.')
        if self.client.read_errors:
            raise self.client.read_errors.pop(0)
        if self.client.fail_next_get:
            self.client.fail_next_get = False
            raise ResourceExhausted('429 Quota exceeded.')
        if (
            self.client.fail_read_after_rejections
            and self.client.reject_precondition == self.key
            and self.client.precondition_rejections >= 3
        ):
            if self.client.saw_reread_at_budget:
                raise ResourceExhausted('429 Quota exceeded.')
            self.client.saw_reread_at_budget = True
        if self.client.fail_get_after_plain_write and self.client.plain_writes and not self.client.verification_raised:
            self.client.verification_raised = True
            raise ResourceExhausted('429 Quota exceeded.')
        data = self.client.docs.get(self.key)
        return _Snap(data, self.client.versions.get(self.key, 0))

    def set(self, payload, merge: bool = False, timeout=None) -> None:
        self.client.write(self.key, copy.deepcopy(payload), merge=merge, create=False, plain=True)

    def create(self, payload, timeout=None, retry=None) -> None:
        if self.client.conflict_create == self.key:
            self.client.conflict_create = None
            if self.client.conflict_row is not None:
                self.client.docs[self.key] = copy.deepcopy(self.client.conflict_row)
                self.client.versions[self.key] = self.client.versions.get(self.key, 0) + 1
            self.client.fail_next_get = True
            raise AlreadyExists('exists')
        self.client.write(self.key, copy.deepcopy(payload), merge=False, create=True, plain=True)

    def update(self, payload, option=None, timeout=None) -> None:
        self.client.last_update_option = option
        if self.client.reject_precondition == self.key:
            self.client.precondition_rejections += 1
            raise FailedPrecondition('conditional append rejected')
        if self.client.land_fragment_on_update == self.key:
            # The attempt that already committed this fragment wins the version.
            self.client.land_fragment_on_update = None
            self.client.write(self.key, copy.deepcopy(payload), merge=False, create=False, plain=True)
            raise FailedPrecondition('ambiguous commit won the precondition')
        if self.client.seal_during_update == self.key:
            row = self.client.docs[self.key]
            row['state'] = 'sealing'
            self.client.versions[self.key] = self.client.versions.get(self.key, 0) + 1
            self.client.seal_during_update = None
            raise FailedPrecondition('stored version changed before the fallback write')
        expected = getattr(option, '_last_update_time', None) if option is not None else None
        current = self.client.versions.get(self.key, 0)
        if expected is not None and expected != current:
            raise FailedPrecondition('precondition failed')
        self.client.write(self.key, copy.deepcopy(payload), merge=True, create=False, plain=True)


class _Collection:
    def __init__(self, client: '_Client', prefix: str):
        self.client = client
        self.prefix = prefix

    def document(self, identity: str) -> _Doc:
        return _Doc(self.client, f'{self.prefix}/{identity}')


class _Client:
    def __init__(self, actions: list[str] | None = None, read_errors: list | None = None):
        self.actions = list(actions or [])
        self.read_errors = list(read_errors or [])
        self.docs: dict[str, dict] = {}
        self.versions: dict[str, int] = {}
        self.transactions: list[_Transaction] = []
        self.applied = 0
        self.increments: list[tuple[str, str, float]] = []
        self.deletes: list[str] = []
        self.plain_writes = 0
        self.fail_get_after_plain_write = False
        self.verification_raised = False
        self.seal_during_update: str | None = None
        self.land_fragment_on_update: str | None = None
        self.reject_precondition: str | None = None
        self.precondition_rejections = 0
        self.fail_read_after_rejections = False
        self.saw_reread_at_budget = False
        self.conflict_create: str | None = None
        self.conflict_row: dict | None = None
        self.fail_next_get = False
        self.fail_get_keys: set[str] = set()
        self.last_update_option = None
        self.lock = Lock()
        self.seal_commit_barrier: Barrier | None = None
        self.seal_commit_barrier_passed = False

    def collection(self, name: str) -> _Collection:
        return _Collection(self, name)

    def transaction(self) -> _Transaction:
        txn = _Transaction(self)
        self.transactions.append(txn)
        return txn

    def write(
        self, key: str, payload: dict, *, merge: bool, create: bool, plain: bool = False, locked: bool = False
    ) -> None:
        if locked:
            self._write(key, payload, merge=merge, create=create, plain=plain)
            return
        with self.lock:
            self._write(key, payload, merge=merge, create=create, plain=plain)

    def _write(self, key: str, payload: dict, *, merge: bool, create: bool, plain: bool) -> None:
        if create and key in self.docs:
            if 'stt_cap_fragment_claims' in key:
                raise Aborted('fragment claim lost')
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
        self.versions[key] = self.versions.get(key, 0) + 1
        if plain:
            self.plain_writes += 1


class _Stored:
    def __init__(self, name: str, generation: int, payload: bytes):
        self.name = name
        self.generation = generation
        self.payload = payload
        self.alive = True


class _Blob:
    def __init__(self, bucket: '_Bucket', name: str, generation: int | None = None):
        self.bucket = bucket
        self.name = name
        self.generation = generation
        self.size = 64

    def reload(self, timeout=10, retry=None) -> None:
        stored = self.bucket.objects.get(self.name)
        if stored is None or not stored.alive:
            raise NotFound(self.name)
        self.generation = stored.generation
        self.size = len(stored.payload)

    def delete(self, if_generation_match=None, timeout=10, retry=None) -> None:
        stored = self.bucket.objects.get(self.name)
        if stored is None or not stored.alive:
            raise NotFound(self.name)
        if if_generation_match is not None and int(if_generation_match) != stored.generation:
            raise PreconditionFailed('generation')
        stored.alive = False

    def compose(self, sources, if_generation_match=0, timeout=10, retry=None) -> None:
        stored = self.bucket.objects.get(self.name)
        if if_generation_match == 0 and stored is not None and stored.alive:
            raise PreconditionFailed('destination exists')
        payload = b''
        for source in sources:
            src = self.bucket.objects.get(source.name)
            if src is None or not src.alive:
                raise NotFound(source.name)
            payload += src.payload
        created = _Stored(self.name, 7, payload)
        self.bucket.objects[self.name] = created
        self.generation = 7
        self.size = len(payload)

    def download_as_bytes(self):
        stored = self.bucket.objects.get(self.name)
        if stored is None or not stored.alive:
            raise NotFound(self.name)
        return stored.payload


class _Bucket:
    def __init__(self, deletes: list[str]):
        self.deletes = deletes
        self.objects: dict[str, _Stored] = {}

    def put(self, name: str, payload: bytes, generation: int = 1) -> None:
        self.objects[name] = _Stored(name, generation, payload)

    def blob(self, name, generation=None):
        blob = _Blob(self, name, generation)
        original = blob.delete

        def delete(*args, **kwargs):
            self.deletes.append(name)
            return original(*args, **kwargs)

        blob.delete = delete
        return blob


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
        audio_path = f'chunks/{UID}/cap-held/{identity}.opus.enc'
        bucket.put(audio_path, FRAGMENT_PAYLOAD, generation=1)
        return {
            'audio_path': audio_path,
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
    client.bucket = bucket
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
    before_orphaned = _counter('source_orphaned')
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
    assert _counter('source_orphaned') == before_orphaned  # A staging row names the source.
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
    before_orphaned = _counter('source_orphaned')
    with pytest.raises(InvalidArgument, match='some other 400'):
        _append(store, str(path), read_errors=[InvalidArgument('some other 400')])
    assert len(store.transactions) == 1
    assert delays[0] == []
    assert _counter('exhausted') == before
    # The read failed before the upload, so there is no source to orphan.
    assert _counter('source_orphaned') == before_orphaned
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
    assert store.applied == 1  # The retired attempts wrote nothing; recovery committed once.
    assert store.deletes == []
    assert store.docs[source.identity]['state'] == 'held'
    assert store.docs['summary']['seconds'] == 60
    assert store.docs['summary']['count'] == 1
    assert store.docs[source.identity]['usage_applied'] is True
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


def _enable_redrive(monkeypatch, snaps: list) -> None:
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
    monkeypatch.setattr(cap_hold_redrive.store, 'discover', lambda kind: snaps if kind == 'staging' else [])


def _hold_snap(identity: str):
    return SimpleNamespace(
        id=identity,
        reference=SimpleNamespace(path=f'users/{UID}/stt_cap_holds/{identity}'),
    )


_METADATA = {
    'timestamp': 1_700_000_000,
    'sample_rate': 16000,
    'source_frames': 16000,
    'audio_codec': 'ogg_opus',
}


def test_fallback_does_not_clobber_a_row_the_sealer_moved(delays, store, tmp_path, monkeypatch):
    path = tmp_path / 'fragment.opus'
    path.write_bytes(b'opus')
    group = Publication(UID)
    fragment = Publication(UID)
    earlier = {
        'id': 'earlier',
        'audio_path': f'chunks/{UID}/cap-held/earlier.opus.enc',
        'audio_generation': 1,
        'bytes': 4,
        'frames': 1,
    }
    store.docs[group.identity] = {
        'state': 'staging',
        'stage_parts': [earlier],
        'seconds': 1.0,
        'writer_until': 10**12,
        'metadata': 'encrypted',
        'sample_rate': 16000,
        'started_at': 1_700_000_000,
        'created_at': 1.0,
        'listed_at': 1_700_000_000,
        'live_custody_version': 4,
    }
    store.versions[group.identity] = 1
    store.seal_during_update = group.identity
    store.actions = ['throttle', 'throttle', 'throttle']
    row = live_cap_staging.append(UID, str(path), group, fragment, _METADATA, 1.0)
    assert store.last_update_option._last_update_time == 1
    assert store.docs[group.identity]['state'] == 'sealing'
    assert [part['id'] for part in store.docs[group.identity]['stage_parts']] == ['earlier']
    late = late_hold_identity(fragment.identity)
    part_path = f'chunks/{UID}/cap-held/{fragment.identity}.opus.enc'
    assert row['state'] == 'staging'
    assert [part['id'] for part in row['stage_parts']] == [fragment.identity]
    assert store.docs[late]['writer_until'] == 0
    assert fragment.identity not in store.docs
    assert 'summary' not in store.docs
    store.actions = []
    _enable_redrive(monkeypatch, [_hold_snap(late)])
    assert __import__('asyncio').run(cap_hold_redrive.sweep())['sealed'] == 1
    sealed = store.docs[late]
    assert sealed['state'] == 'held'
    assert sealed['audio_path'] != part_path
    assert store.bucket.blob(sealed['audio_path']).download_as_bytes() == FRAGMENT_PAYLOAD
    assert part_path in store.deletes
    with pytest.raises(NotFound):
        store.bucket.blob(part_path).download_as_bytes()
    assert store.docs[group.identity]['state'] == 'sealing'
    assert [part['id'] for part in store.docs[group.identity]['stage_parts']] == ['earlier']
    assert store.docs['summary']['count'] == 1
    assert store.docs['summary']['seconds'] == 1
    assert store.increments.count(('summary', 'count', 1.0)) == 1
    assert store.increments.count(('summary', 'seconds', 1.0)) == 1
    assert __import__('asyncio').run(cap_hold_redrive.sweep())['sealed'] == 0
    assert store.increments.count(('summary', 'count', 1.0)) == 1
    assert store.increments.count(('summary', 'seconds', 1.0)) == 1
    assert store.bucket.blob(sealed['audio_path']).download_as_bytes() == FRAGMENT_PAYLOAD


def test_markerless_receipt_is_counted_exactly_once_on_both_paths(delays, store, tmp_path):
    source = Publication(UID)
    _track(source, delays[1])
    path = tmp_path / 'minute.opus'
    path.write_bytes(b'opus')
    # The writer deployed in production created the receipt and incremented the
    # summary in one transaction. Only the usage marker postdates that receipt.
    store.docs[source.identity] = {'state': 'held', 'seconds': 60, 'live_custody_version': 4}
    store.docs['summary'] = {'count': 1, 'seconds': 60}
    live_cap_manifest.publish(UID, str(path), source, _METADATA, 60)
    assert store.docs[source.identity]['usage_applied'] is True
    assert store.docs['summary'] == {'count': 1, 'seconds': 60}
    assert store.increments == []
    # Recovery: every publication attempt retires its transaction id, so the
    # receipt is reached through _publish_for_recovery instead of the commit.
    store.docs[source.identity].pop('usage_applied')
    store.actions = ['expire', 'expire', 'expire']
    live_cap_manifest.publish(UID, str(path), source, _METADATA, 60)
    assert store.docs[source.identity]['usage_applied'] is True
    assert store.docs['summary'] == {'count': 1, 'seconds': 60}
    assert store.increments == []


def test_read_after_a_staged_write_does_not_fail_the_socket(delays, store, tmp_path, monkeypatch):
    path = tmp_path / 'fragment.opus'
    path.write_bytes(b'opus')
    before = _counter('staged_unverified')
    store.fail_get_after_plain_write = True
    state = SimpleNamespace(close_code=None)
    try:
        group, fragment, row = _append(store, str(path), actions=['throttle', 'throttle', 'throttle'])
    except Exception:
        mark_listen_internal_error(state)
        raise
    assert state.close_code != 1011
    assert row['state'] == 'staging'
    assert [part['id'] for part in row['stage_parts']] == [fragment.identity]
    assert store.docs[group.identity]['state'] == 'staging'
    assert store.verification_raised is True
    assert _counter('staged_unverified') == before + 1
    assert 'summary' not in store.docs
    store.docs[group.identity]['writer_until'] = 0
    store.actions = []
    _enable_redrive(monkeypatch, [_hold_snap(group.identity)])
    assert __import__('asyncio').run(cap_hold_redrive.sweep())['sealed'] == 1
    assert store.docs['summary']['count'] == 1
    assert store.docs['summary']['seconds'] == 1
    assert store.increments.count(('summary', 'count', 1.0)) == 1
    assert store.increments.count(('summary', 'seconds', 1.0)) == 1


def test_precondition_loss_after_the_fragment_landed_seals_once(delays, store, tmp_path, monkeypatch):
    path = tmp_path / 'fragment.opus'
    path.write_bytes(b'opus')
    group = Publication(UID)
    fragment = Publication(UID)
    store.docs[group.identity] = {
        'state': 'staging',
        'stage_parts': [],
        'seconds': 0,
        'writer_until': 10**12,
        'metadata': 'encrypted',
        'sample_rate': 16000,
        'started_at': 1_700_000_000,
        'created_at': 1.0,
        'listed_at': 1_700_000_000,
        'live_custody_version': 4,
    }
    store.versions[group.identity] = 1
    store.land_fragment_on_update = group.identity
    store.actions = ['throttle', 'throttle', 'throttle']
    row = live_cap_staging.append(UID, str(path), group, fragment, _METADATA, 1.0)
    assert late_hold_identity(fragment.identity) not in store.docs
    assert [part['id'] for part in row['stage_parts']] == [fragment.identity]
    assert [part['id'] for part in store.docs[group.identity]['stage_parts']] == [fragment.identity]
    store.docs[group.identity]['writer_until'] = 0
    store.actions = []
    _enable_redrive(monkeypatch, [_hold_snap(group.identity)])
    assert __import__('asyncio').run(cap_hold_redrive.sweep())['sealed'] == 1
    assert store.docs['summary']['count'] == 1
    assert store.docs['summary']['seconds'] == 1
    assert store.increments.count(('summary', 'count', 1.0)) == 1
    assert store.increments.count(('summary', 'seconds', 1.0)) == 1
    assert __import__('asyncio').run(cap_hold_redrive.sweep())['sealed'] == 0
    assert store.increments.count(('summary', 'count', 1.0)) == 1


def _empty_staging_row() -> dict:
    return {
        'state': 'staging',
        'stage_parts': [],
        'seconds': 0,
        'writer_until': 10**12,
        'metadata': 'encrypted',
        'sample_rate': 16000,
        'started_at': 1_700_000_000,
        'created_at': 1.0,
        'listed_at': 1_700_000_000,
        'live_custody_version': 4,
    }


def _seal_late(monkeypatch, store, fragment) -> None:
    late = late_hold_identity(fragment.identity)
    store.actions = []
    _enable_redrive(monkeypatch, [_hold_snap(late)])
    assert __import__('asyncio').run(cap_hold_redrive.sweep())['sealed'] == 1
    assert store.docs[late]['state'] == 'held'
    assert store.docs['summary']['count'] == 1
    assert store.docs['summary']['seconds'] == 1
    assert store.increments.count(('summary', 'count', 1.0)) == 1
    assert store.increments.count(('summary', 'seconds', 1.0)) == 1
    assert __import__('asyncio').run(cap_hold_redrive.sweep())['sealed'] == 0
    assert store.increments.count(('summary', 'count', 1.0)) == 1


def test_exhausted_appends_open_a_late_row_when_the_group_omits_the_fragment(delays, store, tmp_path, monkeypatch):
    path = tmp_path / 'fragment.opus'
    path.write_bytes(b'opus')
    group = Publication(UID)
    fragment = Publication(UID)
    store.docs[group.identity] = _empty_staging_row()
    store.versions[group.identity] = 1
    store.reject_precondition = group.identity
    store.actions = ['throttle', 'throttle', 'throttle']
    row = live_cap_staging.append(UID, str(path), group, fragment, _METADATA, 1.0)
    late = late_hold_identity(fragment.identity)
    assert store.precondition_rejections == 3
    assert [part['id'] for part in store.docs[group.identity]['stage_parts']] == []
    assert store.docs[group.identity]['state'] == 'staging'
    assert [part['id'] for part in store.docs[late]['stage_parts']] == [fragment.identity]
    assert row['writer_until'] == 0
    assert [part['id'] for part in row['stage_parts']] == [fragment.identity]
    _seal_late(monkeypatch, store, fragment)


def test_final_read_failure_does_not_report_an_uncommitted_merge(delays, store, tmp_path, monkeypatch):
    path = tmp_path / 'fragment.opus'
    path.write_bytes(b'opus')
    group = Publication(UID)
    fragment = Publication(UID)
    store.docs[group.identity] = _empty_staging_row()
    store.versions[group.identity] = 1
    store.reject_precondition = group.identity
    store.fail_read_after_rejections = True
    store.actions = ['throttle', 'throttle', 'throttle']
    before = _counter('staged_unverified')
    row = live_cap_staging.append(UID, str(path), group, fragment, _METADATA, 1.0)
    late = late_hold_identity(fragment.identity)
    assert _counter('staged_unverified') == before + 1
    assert [part['id'] for part in store.docs[group.identity]['stage_parts']] == []
    assert [part['id'] for part in row['stage_parts']] == [fragment.identity]
    assert row['writer_until'] == 0
    assert late in store.docs
    _seal_late(monkeypatch, store, fragment)


def test_lost_create_race_without_the_fragment_opens_a_late_row(delays, store, tmp_path, monkeypatch):
    path = tmp_path / 'fragment.opus'
    path.write_bytes(b'opus')
    group = Publication(UID)
    fragment = Publication(UID)
    store.conflict_create = group.identity
    store.conflict_row = _empty_staging_row()
    store.actions = ['throttle', 'throttle', 'throttle']
    before = _counter('staged_unverified')
    row = live_cap_staging.append(UID, str(path), group, fragment, _METADATA, 1.0)
    late = late_hold_identity(fragment.identity)
    assert _counter('staged_unverified') == before + 1
    assert [part['id'] for part in store.docs[group.identity]['stage_parts']] == []
    assert [part['id'] for part in store.docs[late]['stage_parts']] == [fragment.identity]
    assert [part['id'] for part in row['stage_parts']] == [fragment.identity]
    assert row['writer_until'] == 0
    _seal_late(monkeypatch, store, fragment)


def _plant_fragment_row(store, identity: str, fragment_id: str) -> str:
    source = f'chunks/{UID}/cap-held/{fragment_id}.opus.enc'
    store.bucket.put(source, FRAGMENT_PAYLOAD, generation=1)
    store.docs[identity] = {
        'state': 'staging',
        'stage_parts': [
            {
                'id': fragment_id,
                'audio_path': source,
                'audio_generation': 1,
                'bytes': len(FRAGMENT_PAYLOAD) - 32,
                'frames': 16000,
            }
        ],
        'seconds': 1.0,
        'writer_until': 0,
        'metadata': 'encrypted',
        'sample_rate': 16000,
        'started_at': 1_700_000_000,
        'created_at': 1.0,
        'listed_at': 1_700_000_000,
        'live_custody_version': 4,
    }
    return source


def _plant_group_row(store, identity: str, fragment_ids: list[str]) -> dict[str, bytes]:
    """A staging row holding one distinct payload per fragment."""
    payloads: dict[str, bytes] = {}
    parts = []
    for fragment_id in fragment_ids:
        payload = f'fragment-{fragment_id[:8]}-'.encode() * 4
        source = f'chunks/{UID}/cap-held/{fragment_id}.opus.enc'
        store.bucket.put(source, payload, generation=1)
        payloads[fragment_id] = payload
        parts.append(
            {
                'id': fragment_id,
                'audio_path': source,
                'audio_generation': 1,
                'bytes': len(payload),
                'frames': 16000,
            }
        )
    store.docs[identity] = {
        'state': 'staging',
        'stage_parts': parts,
        'seconds': float(len(parts)),
        'writer_until': 0,
        'metadata': 'encrypted',
        'sample_rate': 16000,
        'started_at': 1_700_000_000,
        'created_at': 1.0,
        'listed_at': 1_700_000_000,
        'live_custody_version': 4,
    }
    return payloads


def _live_destinations(store, identity: str) -> list[str]:
    prefix = f'chunks/{UID}/cap-held/{identity}.'
    return sorted(name for name, stored in store.bucket.objects.items() if name.startswith(prefix) and stored.alive)


def _assert_one_claim(store, fragment_id: str, winner: str, loser: str) -> None:
    claim = f'users/{UID}/stt_cap_fragment_claims/{fragment_id}'
    assert [key for key in store.docs if 'stt_cap_fragment_claims' in key] == [claim]
    assert store.docs[claim] == {'hold_id': winner, 'fragment_id': fragment_id}
    assert store.docs[winner]['state'] == 'held'
    assert store.docs[loser]['state'] == 'superseded'
    assert store.docs[loser]['seconds'] == 0
    assert store.docs['summary']['count'] == 1
    assert store.docs['summary']['seconds'] == 1
    assert store.increments.count(('summary', 'count', 1.0)) == 1
    assert store.increments.count(('summary', 'seconds', 1.0)) == 1
    audio = store.docs[winner]['audio_path']
    assert store.bucket.blob(audio).download_as_bytes() == FRAGMENT_PAYLOAD
    source = f'chunks/{UID}/cap-held/{fragment_id}.opus.enc'
    with pytest.raises(NotFound):
        store.bucket.blob(source).download_as_bytes()
    assert store.bucket.blob(audio).download_as_bytes() == FRAGMENT_PAYLOAD
    assert _live_destinations(store, loser) == []


@pytest.mark.parametrize('first', ['group', 'late'])
def test_duplicate_rows_compose_and_count_the_fragment_once(store, first):
    group = Publication(UID).identity
    fragment_id = Publication(UID).identity
    late = late_hold_identity(fragment_id)
    _plant_fragment_row(store, group, fragment_id)
    store.docs[late] = copy.deepcopy(store.docs[group])
    order = [group, late] if first == 'group' else [late, group]
    assert live_cap_staging.seal(UID, order[0]) is True
    assert live_cap_staging.seal(UID, order[1]) is True
    _assert_one_claim(store, fragment_id, order[0], order[1])


def test_create_race_with_the_fragment_and_a_failed_read_counts_once(delays, store, tmp_path):
    path = tmp_path / 'fragment.opus'
    path.write_bytes(b'opus')
    group = Publication(UID)
    fragment = Publication(UID)
    source = f'chunks/{UID}/cap-held/{fragment.identity}.opus.enc'
    store.conflict_create = group.identity
    store.conflict_row = {
        'state': 'staging',
        'stage_parts': [
            {
                'id': fragment.identity,
                'audio_path': source,
                'audio_generation': 1,
                'bytes': 4,
                'frames': 16000,
            }
        ],
        'seconds': 1.0,
        'writer_until': 0,
        'metadata': 'encrypted',
        'sample_rate': 16000,
        'started_at': 1_700_000_000,
        'created_at': 1.0,
        'listed_at': 1_700_000_000,
        'live_custody_version': 4,
    }
    store.actions = ['throttle', 'throttle', 'throttle']
    before = _counter('staged_unverified')
    live_cap_staging.append(UID, str(path), group, fragment, _METADATA, 1.0)
    late = late_hold_identity(fragment.identity)
    assert _counter('staged_unverified') == before + 1
    assert late in store.docs
    assert [part['id'] for part in store.docs[group.identity]['stage_parts']] == [fragment.identity]
    assert [part['id'] for part in store.docs[late]['stage_parts']] == [fragment.identity]
    assert live_cap_staging.seal(UID, group.identity) is True
    assert live_cap_staging.seal(UID, late) is True
    _assert_one_claim(store, fragment.identity, group.identity, late)


def test_unconfirmed_late_create_keeps_the_source_and_fails(delays, store, tmp_path):
    path = tmp_path / 'fragment.opus'
    path.write_bytes(b'opus')
    group = Publication(UID)
    fragment = Publication(UID)
    store.docs[group.identity] = _empty_staging_row()
    store.versions[group.identity] = 1
    store.reject_precondition = group.identity
    late = late_hold_identity(fragment.identity)
    store.docs[late] = {'state': 'staging', 'stage_parts': [], 'seconds': 0, 'writer_until': 0}
    store.fail_get_keys.add(late)
    store.actions = ['throttle', 'throttle', 'throttle']
    source = f'chunks/{UID}/cap-held/{fragment.identity}.opus.enc'
    before = _counter('source_orphaned')
    with pytest.raises(ResourceExhausted):
        live_cap_staging.append(UID, str(path), group, fragment, _METADATA, 1.0)
    assert _counter('source_orphaned') == before + 1
    assert source not in store.deletes
    assert store.bucket.blob(source).download_as_bytes() == FRAGMENT_PAYLOAD
    assert [part['id'] for part in store.docs[group.identity]['stage_parts']] == []


def test_concurrent_seals_claim_the_fragment_once(store):
    group = Publication(UID).identity
    fragment_id = Publication(UID).identity
    late = late_hold_identity(fragment_id)
    _plant_fragment_row(store, group, fragment_id)
    store.docs[late] = copy.deepcopy(store.docs[group])
    store.seal_commit_barrier = Barrier(2)
    errors: list[BaseException] = []

    def _run(identity: str) -> None:
        try:
            assert live_cap_staging.seal(UID, identity) is True
        except BaseException as error:
            errors.append(error)

    threads = [Thread(target=_run, args=(identity,)) for identity in (group, late)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert errors == []
    assert all(not thread.is_alive() for thread in threads)
    winner = store.docs[f'users/{UID}/stt_cap_fragment_claims/{fragment_id}']['hold_id']
    loser = late if winner == group else group
    _assert_one_claim(store, fragment_id, winner, loser)


def test_fake_rejects_a_transactional_read_after_a_queued_write(store):
    tx = store.transaction()
    doc = _Doc(store, 'row')
    doc.get(transaction=tx)
    tx.set(doc, {'state': 'staging'})
    with pytest.raises(ReadAfterWriteError):
        doc.get(transaction=tx)
    assert doc.get().to_dict() is None  # A plain read is not transactional.


def test_multi_fragment_group_reads_every_claim_before_the_first_write(store):
    group = Publication(UID).identity
    fragments = [Publication(UID).identity for _ in range(3)]
    payloads = _plant_group_row(store, group, fragments)
    assert live_cap_staging.seal(UID, group) is True
    assert len(store.transactions) == 2  # freeze, then one commit without a restart
    row = store.docs[group]
    assert row['state'] == 'held'
    assert row['claimed_fragment_ids'] == fragments
    composed = store.bucket.blob(row['audio_path']).download_as_bytes()
    assert composed == b''.join(payloads[fragment_id] for fragment_id in fragments)
    assert [fragment['bytes'] for fragment in row['opus_fragments']] == [len(payloads[f]) for f in fragments]
    assert sum(fragment['bytes'] for fragment in row['opus_fragments']) == len(composed)
    assert store.docs['summary']['count'] == 1
    assert store.docs['summary']['seconds'] == 3
    assert store.increments.count(('summary', 'count', 1.0)) == 1
    for fragment_id in fragments:
        claim = store.docs[f'users/{UID}/stt_cap_fragment_claims/{fragment_id}']
        assert claim == {'hold_id': group, 'fragment_id': fragment_id}
        assert f'chunks/{UID}/cap-held/{fragment_id}.opus.enc' in store.deletes
    assert _live_destinations(store, group) == [row['audio_path']]


def test_retry_that_lost_a_fragment_composes_only_its_claimed_set(store, monkeypatch):
    group = Publication(UID).identity
    x, y = Publication(UID).identity, Publication(UID).identity
    payloads = _plant_group_row(store, group, [x, y])
    wide = live_cap_staging._compose_target(store.bucket, UID, group, [x, y]).name
    drops: list[tuple[str, int]] = []
    original_drop = live_cap_staging._drop_unpublished_targets

    def tracked_drop(bucket, uid, identity, part_ids, claimed_ids):
        # The stale-wider-composite deletion runs outside the seal transaction;
        # by the time it starts, this row's own commit is already applied.
        drops.append((store.docs[identity]['state'], store.applied))
        return original_drop(bucket, uid, identity, part_ids, claimed_ids)

    monkeypatch.setattr(live_cap_staging, '_drop_unpublished_targets', tracked_drop)
    # Freeze commits; every seal commit then retires its transaction id after
    # the X+Y composite is already in the bucket.
    store.actions = ['ok', 'expire', 'expire', 'expire']
    assert live_cap_staging.seal(UID, group) is False
    assert store.docs[group]['state'] == 'sealing'
    assert store.bucket.blob(wide).download_as_bytes() == payloads[x] + payloads[y]
    assert [key for key in store.docs if 'stt_cap_fragment_claims' in key] == []
    # Another row claims Y before this row is retried.
    late = late_hold_identity(y)
    store.docs[late] = {
        **copy.deepcopy(store.docs[group]),
        'state': 'staging',
        'stage_parts': [copy.deepcopy(store.docs[group]['stage_parts'][1])],
        'seconds': 1.0,
    }
    store.actions = []
    assert live_cap_staging.seal(UID, late) is True
    assert store.bucket.blob(store.docs[late]['audio_path']).download_as_bytes() == payloads[y]
    # The retry claims X only. It must compose X, not reuse the X+Y object.
    assert live_cap_staging.seal(UID, group) is True
    row = store.docs[group]
    assert row['state'] == 'held'
    assert row['claimed_fragment_ids'] == [x]
    assert row['audio_path'] != wide
    composed = store.bucket.blob(row['audio_path']).download_as_bytes()
    assert composed == payloads[x]
    assert [fragment['bytes'] for fragment in row['opus_fragments']] == [len(payloads[x])]
    assert sum(fragment['bytes'] for fragment in row['opus_fragments']) == len(composed)
    stale = store.bucket.objects.get(wide)
    assert stale is None or not stale.alive
    assert drops == [('held', store.applied)]
    assert _live_destinations(store, group) == [row['audio_path']]
    assert store.docs[f'users/{UID}/stt_cap_fragment_claims/{x}']['hold_id'] == group
    assert store.docs[f'users/{UID}/stt_cap_fragment_claims/{y}']['hold_id'] == late
    # X and Y are each counted once, by the row that claimed them.
    assert store.docs['summary']['count'] == 2
    assert store.docs['summary']['seconds'] == 2
    assert store.increments.count(('summary', 'count', 1.0)) == 2
    assert store.increments.count(('summary', 'seconds', 1.0)) == 2
    assert f'chunks/{UID}/cap-held/{x}.opus.enc' in store.deletes
    assert f'chunks/{UID}/cap-held/{y}.opus.enc' in store.deletes
    assert store.bucket.blob(store.docs[late]['audio_path']).download_as_bytes() == payloads[y]
    assert store.bucket.blob(row['audio_path']).download_as_bytes() == payloads[x]


def test_permanent_commit_failure_after_upload_counts_the_orphaned_source(delays, store, tmp_path):
    path = tmp_path / 'fragment.opus'
    path.write_bytes(b'opus')
    group = Publication(UID)
    fragment = Publication(UID)
    store.actions = ['permanent']
    before = _counter('source_orphaned')
    with pytest.raises(InvalidArgument, match='some other 400'):
        live_cap_staging.append(UID, str(path), group, fragment, _METADATA, 1.0)
    assert _counter('source_orphaned') == before + 1
    source = f'chunks/{UID}/cap-held/{fragment.identity}.opus.enc'
    assert source not in store.deletes
    assert store.bucket.blob(source).download_as_bytes() == FRAGMENT_PAYLOAD
    assert group.identity not in store.docs
    assert late_hold_identity(fragment.identity) not in store.docs


async def test_receive_data_close_code_follows_staging(delays, store, tmp_path):
    path = tmp_path / 'fragment.opus'
    path.write_bytes(b'opus')

    class _Socket:
        async def receive(self):
            raise asyncio.TimeoutError

    class _Hold:
        def __init__(self, actions, read_errors):
            self.actions = actions
            self.read_errors = read_errors
            self.row = None

        async def run_updates(self, receiver):
            await receiver._cap_hold_stop.wait()

        async def finish_updates(self, updates, stop):
            stop.set()
            if updates is not None:
                await updates
            _group, _fragment, self.row = _append(store, str(path), actions=self.actions, read_errors=self.read_errors)

    def spawn(coro, name=None):
        return asyncio.create_task(coro)

    async def turn(actions, read_errors):
        state = ListenSessionState()
        state.close_code = 1000
        hold = _Hold(actions, read_errors)
        host = SimpleNamespace(
            request=SimpleNamespace(websocket=_Socket(), uid=UID, codec='pcm16', sample_rate=16000),
            state=state,
            limits=SimpleNamespace(ws_receive_timeout=1.0),
            is_multi_channel=False,
            use_custom_stt=True,
            audio_bytes_send=None,
            transcripts=SimpleNamespace(enqueue=lambda segments: None),
            start_live_transcription=lambda: None,
            spawn=spawn,
        )
        receiver = ListenReceiver(host, [], {})
        receiver.live_hold = hold
        await receiver.receive_data()
        return state, hold.row

    staged, row = await turn(['throttle', 'throttle', 'throttle'], [])
    assert staged.close_code == 1000
    assert row['state'] == 'staging'
    failed, _row = await turn([], [InvalidArgument('some other 400')])
    assert failed.close_code == 1011


@pytest.mark.parametrize(
    'error',
    [
        requests.exceptions.ReadTimeout('read'),
        requests.exceptions.ConnectTimeout('connect'),
        requests.exceptions.ConnectionError('connection'),
        urllib3.exceptions.ProtocolError('protocol'),
        urllib3.exceptions.ReadTimeoutError(None, '/', 'read'),
        urllib3.exceptions.MaxRetryError(None, '/', requests.exceptions.ReadTimeout('wrapped')),
        TransportError('auth', requests.exceptions.ReadTimeout('wrapped')),
        RetryError('wrapped', requests.exceptions.ConnectionError('connection')),
    ],
)
async def test_only_upload_gets_one_transport_retry(error):
    source = Publication(UID)
    upload = Mock(side_effect=[error, {'audio_generation': 7, 'audio_size': 36}])
    cause = live_cap_upload.transport_cause(error)
    assert cause in ('timeout', 'connection')
    before = held_metrics.PUBLICATION_RETRY.labels(outcome='retried_ok', cause=cause)._value.get()
    await live_cap_upload.prepare(source, upload)
    assert upload.call_count == 2 and source.fields['audio_generation'] == 7
    assert held_metrics.PUBLICATION_RETRY.labels(outcome='retried_ok', cause=cause)._value.get() == before + 1
    await live_cap_upload.prepare(source, upload)
    assert upload.call_count == 2


async def test_second_upload_timeout_fails_without_a_third_attempt():
    source = Publication(UID)
    upload = Mock(side_effect=requests.exceptions.ReadTimeout('read'))
    before = held_metrics.PUBLICATION_RETRY.labels(outcome='exhausted', cause='timeout')._value.get()
    for _ in range(2):  # close/flush cannot reset the budget or the identity
        with pytest.raises(requests.exceptions.ReadTimeout):
            await live_cap_upload.prepare(source, upload)
    assert upload.call_count == 2 and len(source.upload_attempts) == 2
    assert source.put_started and not source.fields
    assert held_metrics.PUBLICATION_RETRY.labels(outcome='exhausted', cause='timeout')._value.get() == before + 1


@pytest.mark.parametrize(
    'error',
    [
        ValueError('permanent'),
        TimeoutError('caller signal'),
        RetryError('permanent', InvalidArgument('bad')),
        TransportError('no inner fault'),
    ],
)
async def test_upload_does_not_retry_api_or_permanent_errors(error):
    source = Publication(UID)
    upload = Mock(side_effect=error)
    with pytest.raises(type(error)):
        await live_cap_upload.prepare(source, upload)
    assert upload.call_count == 1


async def test_wall_deadline_retains_late_upload_and_never_commits(monkeypatch):
    entered, release = Event(), Event()
    source = Publication(UID)
    calls = []

    def stalled():
        calls.append(source.identity)
        entered.set()
        assert release.wait(2)
        return {'audio_generation': 7, 'audio_size': 36}

    monkeypatch.setattr(live_cap_upload, 'UPLOAD_ATTEMPT_SECONDS', 0.02)
    try:
        with pytest.raises(requests.exceptions.ReadTimeout):
            await live_cap_upload.prepare(source, stalled)
        assert entered.is_set() and calls == [source.identity, source.identity]
        assert not source.fields and len(source.upload_attempts) == 2
    finally:
        release.set()
        await asyncio.gather(*(asyncio.wrap_future(f) for f in source.upload_attempts))
    await live_cap_upload.prepare(source, stalled)
    assert source.fields['audio_generation'] == 7 and len(calls) == 2


async def test_live_upload_timeout_then_success_commits_once(delays, store, monkeypatch):

    monkeypatch.setattr(
        live_cap_hold.live_cap_codec, 'encode', lambda path, *args, **kw: Path(path).write_bytes(b'opus')
    )
    upload = Mock(
        side_effect=[
            requests.exceptions.ReadTimeout('read'),
            {
                'audio_path': 'chunks/synthetic/cap-held/source.opus.enc',
                'metadata': 'encrypted',
                'audio_generation': 1,
                'audio_size': 36,
            },
        ]
    )
    monkeypatch.setattr(cap_hold, 'upload_held_audio', upload)
    group, source = Publication(UID), Publication(UID)
    await live_cap_hold._publish_audio(UID, b'pcm', 16000, 100, group, source, _METADATA, 1)
    assert upload.call_count == 2 and len(store.transactions) == 1
    assert store.docs[group.identity]['stage_parts'][0]['id'] == source.identity
    assert upload.call_args.kwargs['rpc_timeout'] == 1.5


async def test_live_second_upload_timeout_hands_off_before_commit(store, monkeypatch):

    monkeypatch.setattr(
        live_cap_hold.live_cap_codec, 'encode', lambda path, *args, **kw: Path(path).write_bytes(b'opus')
    )
    upload = Mock(side_effect=requests.exceptions.ReadTimeout('read'))
    monkeypatch.setattr(cap_hold, 'upload_held_audio', upload)
    group, source = Publication(UID), Publication(UID)
    handoff = Mock()
    monkeypatch.setattr(live_cap_hold.live_cap_journal, 'defer', handoff)
    assert not await live_cap_hold._publish_audio(UID, b'pcm', 16000, 100, group, source, _METADATA, 1)
    assert upload.call_count == 2 and not store.transactions and not store.deletes
    assert handoff.call_count == 1


@pytest.mark.parametrize('mismatch', [None, 'capture', 'size', 'missing_metadata', 'generation'])
@pytest.mark.parametrize('failure', ['upload', 'reload'])
def test_ambiguous_upload_412_verifies_size_metadata_and_generation(tmp_path, monkeypatch, mismatch, failure):
    path = tmp_path / 'source.opus'
    path.write_bytes(b'opus')

    class Blob:
        generation = None
        stored = None
        reloads = 0

        def upload_from_file(self, stream, **kwargs):
            assert kwargs['if_generation_match'] == 0 and kwargs['retry'] is None
            assert kwargs['timeout'] == 1.5
            if self.stored is None:
                self.stored = (stream.read(), dict(self.metadata))
                if failure == 'upload':
                    raise requests.exceptions.ReadTimeout('upload landed, reply lost')
            raise PreconditionFailed('already landed')

        def reload(self, **kwargs):
            assert kwargs == {'timeout': 1.5, 'retry': None}
            self.reloads += 1
            if failure == 'reload' and self.reloads == 1:
                raise requests.exceptions.ReadTimeout('reload reply lost')
            payload, metadata = self.stored
            self.metadata = dict(metadata)
            self.size, self.generation = len(payload), 7
            if mismatch == 'capture':
                self.metadata['omi_live_capture'] = 'foreign'
            if mismatch == 'size':
                self.size += 1
            if mismatch == 'missing_metadata':
                self.metadata = {}
            if mismatch == 'generation':
                self.generation = None

    blob = Blob()
    monkeypatch.setattr(cap_hold, 'external_write_fence', lambda *a, **kw: nullcontext())
    monkeypatch.setattr(cap_hold, 'owner_storage_write_gate', lambda *a, **kw: nullcontext())
    monkeypatch.setattr(cap_hold, 'get_private_cloud_sync_bucket', lambda: SimpleNamespace(blob=lambda name: blob))
    args = (UID, str(path), 'stable-identity', _METADATA)
    kwargs = {'immutable': True, 'live_size_limit': 32768, 'rpc_timeout': 1.5}
    with pytest.raises(requests.exceptions.ReadTimeout):
        REAL_UPLOAD(*args, **kwargs)
    if mismatch:
        with pytest.raises(ValueError, match='provenance mismatch'):
            REAL_UPLOAD(*args, **kwargs)
    else:
        fields = REAL_UPLOAD(*args, **kwargs)
        assert fields['audio_generation'] == 7 and fields['audio_size'] == 36


def test_manifest_unknown_commit_preserves_source_generation(delays, store, tmp_path, monkeypatch):
    path = tmp_path / 'source.opus'
    path.write_bytes(b'opus')
    source = Publication(UID)
    store.actions = ['permanent']
    with pytest.raises(InvalidArgument):
        live_cap_manifest.publish(UID, str(path), source, _METADATA, 1)
    original = dict(source.fields)
    assert original['audio_generation'] == 1 and not store.deletes
    # Later upload/reload fails while the earlier commit's outcome is unresolved.
    # A known generation is reused; a failed put cannot erase it.
    monkeypatch.setattr(cap_hold, 'upload_held_audio', Mock(side_effect=requests.exceptions.ReadTimeout('late')))
    store.actions = ['permanent']
    with pytest.raises(InvalidArgument):
        live_cap_manifest.publish(UID, str(path), source, _METADATA, 1)
    assert source.fields == original and not store.deletes
    assert store.bucket.blob(original['audio_path']).download_as_bytes() == FRAGMENT_PAYLOAD


def test_requests_timeout_does_not_change_firestore_retry_semantics():
    client = Mock()
    call = Mock(side_effect=requests.exceptions.ReadTimeout('not a Firestore retry'))
    with pytest.raises(requests.exceptions.ReadTimeout):
        run_transactional(client, call, transient=True)
    assert call.call_count == 1


def test_late_manifest_commit_still_names_retained_audio(delays, store, tmp_path, monkeypatch):
    path = tmp_path / 'source.opus'
    path.write_bytes(b'opus')
    source = Publication(UID)
    pending = []

    def ambiguous(tx):
        pending.extend(copy.deepcopy(tx.ops))
        raise requests.exceptions.ReadTimeout('commit reply unknown')

    monkeypatch.setattr(_Transaction, '_commit', ambiguous)
    with pytest.raises(requests.exceptions.ReadTimeout):
        live_cap_manifest.publish(UID, str(path), source, _METADATA, 1)
    assert source.identity not in store.docs and source.fields['audio_generation'] == 1
    assert not store.deletes
    late = _Transaction(store)
    late.ops = pending
    late._apply()  # The server's old commit lands after recovery's absence read.
    assert store.docs[source.identity]['audio_path'] == source.fields['audio_path']
    assert store.bucket.blob(source.fields['audio_path']).download_as_bytes() == FRAGMENT_PAYLOAD


def test_retry_causes_are_a_closed_metric_set():
    before = _counter('retried_ok')
    held_metrics.record_publication_retry('retried_ok', 'unbounded-error-message')
    assert _counter('retried_ok') == before
    assert set(held_metrics.PUBLICATION_RETRY_CAUSES) == {'throttle', 'timeout', 'connection', 'other'}


async def test_cancelled_waiter_does_not_retry_an_upload_with_unknown_outcome():
    source = Publication(UID)
    previous = Future()
    source.upload_attempts.append(previous)
    upload = Mock()
    with pytest.raises(requests.exceptions.ReadTimeout, match='outcome unknown'):
        await live_cap_upload.prepare(source, upload)
    upload.assert_not_called()
    previous.set_result({'audio_generation': 7, 'audio_size': 36})
    await live_cap_upload.prepare(source, upload)
    assert source.fields['audio_generation'] == 7 and len(source.upload_attempts) == 1
