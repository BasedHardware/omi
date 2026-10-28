"""A committed empty-generation delete must not be reclassified by its audio sweep.

Failure-Class: FC-post-commit-index-maintenance-terminal — work that runs after
the authoritative write has already committed is best-effort, and its failure
may not rewrite the committed outcome as a failure. The empty-generation
deletes the Firestore row first and reclaims its private-cloud audio second;
the reclaim's purge verifier raises
``RuntimeError('owner storage purge left N objects under ...')`` when one
object survives the verify re-list. That one observation proves nothing: an
object the first listing already saw can still answer one more read after its
delete committed (eventual propagation), and a same-key chunk upload admitted
between the listing and the deletes lands fresh under the prefix — the very
race the pipeline documents for buffered late audio. The raise then walked out
of ``_discard_unreferenced_audio``'s catch-all as a full ERROR traceback plus
an ``omi_fallback_total`` degradation event on every teardown, rollover-loser
cleanup and continuation adoption of that generation (prod backend-listen
2026-10-23: ``Failed to reclaim unreferenced audio`` ×16/30m, the
``owner storage purge left 1 objects`` shape confirmed live in the traceback).

Guards:
- the purge verifier settles one torn observation by re-attacking the residue
  once — an in-memory fake converges immediately, a persistently lost delete
  still fails closed on the second pass, so the account-wipe caller keeps its
  verify;
- the audio reclaim classifies the verifier's residual signal as the
  retained-audio path — INFO without a stack trace and without a degradation
  event — while a genuine storage fault (network refusal, permission error)
  keeps the failed-write classification with its traceback and event;
- a clean sweep still deletes, and a residual one still removes what it can
  (only the racing object survives), so the next reclamation attempt starts
  from a shorter prefix.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from google.api_core.exceptions import (
    BadGateway,
    BadRequest,
    Forbidden,
    GatewayTimeout,
    RetryError,
    ServiceUnavailable,
    TooManyRequests,
)
from google.cloud.exceptions import NotFound

from utils.conversations import lifecycle as lifecycle_service
from utils.other import storage as storage_mod


class _FlakyDeleteBlob:
    """Answer one read per delete with a write the listing had not seen."""

    def __init__(self, bucket: '_RaceBucket', name: str):
        self._bucket = bucket
        self.name = name

    def delete(self) -> None:
        self._bucket.pending_after_delete += 1
        self._bucket.names.discard(self.name)


class _RaceBucket:
    """In-memory bucket whose verify re-list still sees recently deleted objects."""

    def __init__(self, names: set[str], *, residue_after_first_delete: int):
        self.names = set(names)
        self.residue_after_first_delete = residue_after_first_delete
        self.pending_after_delete = 0
        self.delete_calls = 0

    def blob(self, name: str) -> _FlakyDeleteBlob:
        return _FlakyDeleteBlob(self, name)

    def list_blobs(self, *, prefix: str, **kwargs: Any) -> list[_FlakyDeleteBlob]:
        visible = sorted(name for name in self.names if name.startswith(prefix))
        blobs = [_FlakyDeleteBlob(self, name) for name in visible]
        for _ in range(self.pending_after_delete):
            self.pending_after_delete -= 1
            if self.residue_after_first_delete > 0:
                self.residue_after_first_delete -= 1
                ghosts = [_FlakyDeleteBlob(self, f'{prefix}late-writer-{self.residue_after_first_delete}.opus')]
                blobs = blobs + ghosts
        return blobs


class _LostDeleteBucket:
    """The delete calls never take effect: the residue is real."""

    def __init__(self, names: set[str]):
        self.names = set(names)
        self.delete_calls = 0

    def blob(self, name: str) -> Any:
        stuck = SimpleNamespace(name=name)

        def _delete() -> None:
            self.delete_calls += 1

        stuck.delete = _delete
        return stuck

    def list_blobs(self, *, prefix: str, **kwargs: Any) -> list[Any]:
        return [self.blob(name) for name in sorted(self.names) if name.startswith(prefix)]


class _FailingListBucket:
    """The storage itself is unavailable: every listing raises."""

    def list_blobs(self, *, prefix: str, **kwargs: Any) -> list[Any]:
        raise ConnectionError('storage unavailable')


class _ContendingStore:
    """Minimal Firestore fake: the empty generation exists and the delete commits."""

    def __init__(self) -> None:
        self.documents: dict = {}

    def collection(self, name: str) -> Any:
        return _StoreCollection(self, (name,))

    def transaction(self, *a: Any, **k: Any) -> Any:
        return _StoreTransaction(self)


class _StoreCollection:
    def __init__(self, store: _ContendingStore, path: tuple) -> None:
        self._store = store
        self._path = path

    def document(self, doc_id: str) -> Any:
        return _StoreDocument(self._store, self._path + (doc_id,))


class _StoreDocument:
    def __init__(self, store: _ContendingStore, path: tuple) -> None:
        self._store = store
        self._path = path

    def collection(self, name: str) -> Any:
        return _StoreCollection(self._store, self._path + (name,))

    def get(self, transaction: Any = None) -> Any:
        return _StoreSnapshot(self._store.documents.get(self._path))

    def delete(self) -> None:
        self._store.documents.pop(self._path, None)


class _StoreSnapshot:
    def __init__(self, data: Any) -> None:
        self._data = data

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self) -> Any:
        return dict(self._data) if self._data else {}


class _StoreTransaction:
    def __init__(self, store: _ContendingStore) -> None:
        self._store = store
        self._read_only = False
        self._max_attempts = 1
        self._id = b'test-txn'

    def _rollback(self) -> None:
        pass

    def _clean_up(self) -> None:
        pass

    def _commit(self) -> None:
        pass

    def _add_write_pb(self, *a: Any, **k: Any) -> None:
        pass

    def _reset(self) -> None:
        pass

    def _begin(self, **kwargs: Any) -> None:
        pass

    def get(self, ref: Any) -> Any:
        return ref.get()

    def delete(self, ref: Any) -> None:
        ref.delete()

    def update(self, ref: Any, data: dict) -> None:
        doc = self._store.documents.setdefault(ref._path, {})
        doc.update(data)


def test_purge_settles_one_torn_observation_without_raising():
    bucket = _RaceBucket({'chunks/uid/conv/a.opus'}, residue_after_first_delete=1)

    deleted = storage_mod._delete_owner_bucket_prefix(bucket, 'chunks/uid/conv/')

    assert deleted == 2  # the listed object plus the late writer on the re-attack
    assert bucket.names == set()


def test_purge_still_fails_closed_when_the_delete_is_never_applied():
    bucket = _LostDeleteBucket({'chunks/uid/conv/a.opus'})

    with pytest.raises(RuntimeError, match='owner storage purge left'):
        storage_mod._delete_owner_bucket_prefix(bucket, 'chunks/uid/conv/')

    assert bucket.delete_calls == 2  # the settle re-attack happened before giving up


def test_purge_storage_fault_keeps_raising():
    with pytest.raises(ConnectionError):
        storage_mod._delete_owner_bucket_prefix(_FailingListBucket(), 'chunks/uid/conv/')


@pytest.fixture()
def _generation_without_registered_audio(monkeypatch) -> dict[str, Any]:
    """``deleted_conversation`` snapshot with no ``audio_files`` key."""
    monkeypatch.setattr(
        lifecycle_service,
        'delete_conversation_audio_files',
        lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError('owner storage purge left 1 objects under chunks/uid/conv/'),
        ),
        raising=False,
    )
    return {}


def _fallback_spy(monkeypatch) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    monkeypatch.setattr(
        lifecycle_service,
        'record_fallback',
        lambda **kwargs: events.append(kwargs),
        raising=False,
    )
    return events


@pytest.fixture(autouse=True)
def _bounded_retry_stub(monkeypatch):
    """The deferral's retry stays a stub in this file: it pins the boundary's
    classification, not the retry mechanics — those live in the rate-limit
    file, and no test here may arm a real daemon thread."""
    monkeypatch.setattr(
        lifecycle_service,
        '_schedule_sweep_retry',
        lambda *a, **k: True,
        raising=False,
    )


def test_residual_sweep_keeps_the_committed_delete_classified_as_retained(
    monkeypatch, caplog, _generation_without_registered_audio
):
    fallbacks = _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        lifecycle_service._discard_unreferenced_audio('uid', 'conv', _generation_without_registered_audio)

    retained = [r for r in caplog.records if 'Retained unreferenced audio behind a late writer' in r.getMessage()]
    assert retained, 'the residual sweep must keep the retained-audio classification'
    assert all(r.levelno == 20 for r in retained), 'no ERROR, no traceback'
    assert all(r.exc_info is None for r in retained)
    assert not [r for r in caplog.records if r.levelno >= 40]
    assert fallbacks == [], 'a converging residue is not a degradation event'


def test_genuine_sweep_failure_keeps_the_failed_write_classification(
    monkeypatch, caplog, _generation_without_registered_audio
):
    def failing(*a, **k):
        raise PermissionError('bucket policy refuses the sweep')

    monkeypatch.setattr(lifecycle_service, 'delete_conversation_audio_files', failing, raising=False)
    fallbacks = _fallback_spy(monkeypatch)

    with caplog.at_level('ERROR'):
        lifecycle_service._discard_unreferenced_audio('uid', 'conv', _generation_without_registered_audio)

    failures = [r for r in caplog.records if 'Failed to reclaim unreferenced audio' in r.getMessage()]
    assert failures and failures[0].levelno >= 40 and failures[0].exc_info is not None
    assert fallbacks and fallbacks[0]['outcome'] == 'exhausted'


def test_registered_audio_is_still_retained_without_touching_storage(monkeypatch, caplog):
    touched: list[tuple] = []
    monkeypatch.setattr(
        lifecycle_service,
        'delete_conversation_audio_files',
        lambda *a, **k: touched.append(a),
        raising=False,
    )
    _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        lifecycle_service._discard_unreferenced_audio('uid', 'conv', {'audio_files': [{'path': 'chunks/x'}]})

    assert touched == []
    retained = [r for r in caplog.records if 'Retained registered audio for empty conversation' in r.getMessage()]
    assert retained


# ── D. The sweep stays exact about what it deleted ──────────────────────────


class _CountingBucket:
    """In-memory bucket that records every delete it observed."""

    def __init__(self, names: set[str]):
        self.names = set(names)
        self.deleted: list[str] = []

    def blob(self, name: str) -> Any:
        outer = self
        blob = SimpleNamespace(name=name)

        def _delete() -> None:
            outer.names.discard(name)
            outer.deleted.append(name)

        blob.delete = _delete
        return blob

    def list_blobs(self, *, prefix: str, **kwargs: Any) -> list[Any]:
        return [self.blob(name) for name in sorted(self.names) if name.startswith(prefix)]


def test_purge_returns_one_count_per_object_not_per_attempt():
    bucket = _CountingBucket({'chunks/uid/conv/a.opus', 'chunks/uid/conv/b.opus'})

    deleted = storage_mod._delete_owner_bucket_prefix(bucket, 'chunks/uid/conv/')

    assert deleted == 2, 'a settled re-attack must not double-count surviving accounting'
    assert bucket.names == set()


def test_purge_leaves_neighbouring_prefixes_untouched():
    bucket = _CountingBucket({'chunks/uid/conv/a.opus', 'chunks/uid/other/b.opus', 'audio/uid/conv/c.wav'})

    deleted = storage_mod._delete_owner_bucket_prefix(bucket, 'chunks/uid/conv/')

    assert deleted == 1
    assert bucket.names == {'chunks/uid/other/b.opus', 'audio/uid/conv/c.wav'}


def test_purge_empty_prefix_is_a_zero_delete_not_an_error():
    bucket = _CountingBucket(set())

    assert storage_mod._delete_owner_bucket_prefix(bucket, 'chunks/uid/conv/') == 0


# ── E. The fail-closed contract the account wipe depends on is preserved ────


def test_account_wipe_still_refuses_a_torn_purge():
    """The verifier's owner is the account wipe; its terminal verdict stays loud."""
    bucket = _LostDeleteBucket({'chunks/uid/conv/a.opus', 'chunks/uid/conv/b.opus'})

    with pytest.raises(RuntimeError, match='owner storage purge left 2 objects'):
        storage_mod._delete_owner_bucket_prefix(bucket, 'chunks/uid/conv/')


def test_residual_signal_classifier_is_pinned_to_the_verifier_message():
    """The lifecycle arm recognizes the verifier's signal and nothing broader."""
    assert lifecycle_service._is_residual_audio_sweep(
        RuntimeError('owner storage purge left 1 objects under chunks/u/c/')
    )
    assert not lifecycle_service._is_residual_audio_sweep(RuntimeError('unrelated runtime failure'))
    assert not lifecycle_service._is_residual_audio_sweep(ConnectionError('owner storage purge left 1 objects'))
    assert not lifecycle_service._is_residual_audio_sweep(ValueError('owner storage purge left 9 objects'))


# ── F. The boundary keeps its committed outcome end to end ──────────────────


def test_empty_generation_delete_completes_when_only_the_sweep_races(
    monkeypatch, caplog, _generation_without_registered_audio
):
    """delete_empty_recording_conversation still reports the committed delete as True."""
    from database import conversations as conversations_db
    from utils.conversations import typesense_index

    store = _ContendingStore()
    store.documents[('users', 'uid', 'conversations', 'conv')] = conversations_db.encode_conversation_for_write(
        'uid', {'id': 'conv', 'status': 'in_progress', 'transcript_segments': []}, 'standard'
    )

    touched: list[str] = []
    monkeypatch.setattr(typesense_index, 'delete_conversation_index_doc', lambda *a, **k: touched.append('index'))
    monkeypatch.setattr(
        lifecycle_service.conversations_db,
        'delete_conversation_photos',
        lambda *a, **k: touched.append('photos'),
    )
    _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        deleted = lifecycle_service.delete_empty_recording_conversation(
            'uid',
            'conv',
            'session',
            firestore_client=store,
        )

    assert deleted is True
    assert touched == ['index', 'photos']
    assert not [r for r in caplog.records if r.levelno >= 40]


# The purge verifier classifies one more race the same way: a delete answered
# 404 NotFound. The empty-generation sweep, the rollover-loser cleanup, the
# merge cleanup and the account wipe can all be sweeping the same owner
# prefixes, so a listing entry can already be gone when the loop reaches it —
# the object is exactly where the delete wanted it, and one sweep's 404 must
# not reclassify the committed delete as a failed write.
#
# Failure-Class: FC-post-commit-index-maintenance-terminal — work that runs
# after the authoritative write has already committed is best-effort, and a
# bounded race or a momentary fault in it may not rewrite the committed
# outcome as a failure. Residue that survives a fresh delete of itself stays
# the fail-closed signal the account wipe depends on.


class _AlreadyGoneBlob:
    """A listing entry another sweep deleted between the list and the delete.

    The 404 confirms the object is gone, so the bucket stops listing it: the
    stale entry was the race, not the object.
    """

    def __init__(self, bucket: '_GoneRaceBucket', name: str):
        self._bucket = bucket
        self.name = name

    def delete(self) -> None:
        self._bucket.not_found += 1
        self._bucket.names.discard(self.name)
        raise NotFound(f'No such object: {self.name}')


class _GoneRaceBucket:
    """The listing still shows an object a concurrent sweep already removed."""

    def __init__(self, names: set[str]):
        self.names = set(names)
        self.not_found = 0

    def blob(self, name: str) -> _AlreadyGoneBlob:
        return _AlreadyGoneBlob(self, name)

    def list_blobs(self, *, prefix: str, **kwargs: Any) -> list[_AlreadyGoneBlob]:
        return [_AlreadyGoneBlob(self, name) for name in sorted(self.names) if name.startswith(prefix)]


class _HalfGoneBucket:
    """One entry is already gone behind a 404, the neighbour is really there."""

    def __init__(self, names: set[str], gone: set[str]):
        self.names = set(names)
        self.gone = set(gone)
        self.deleted: list[str] = []

    def blob(self, name: str) -> Any:
        outer = self
        blob = SimpleNamespace(name=name)

        def _delete() -> None:
            if name in outer.gone:
                outer.names.discard(name)
                raise NotFound(f'No such object: {name}')
            outer.names.discard(name)
            outer.deleted.append(name)

        blob.delete = _delete
        return blob

    def list_blobs(self, *, prefix: str, **kwargs: Any) -> list[Any]:
        return [self.blob(name) for name in sorted(self.names) if name.startswith(prefix)]


def test_purge_treats_concurrent_404_as_success_and_verifies_clean():
    bucket = _GoneRaceBucket({'chunks/uid/conv/a.opus'})

    deleted = storage_mod._delete_owner_bucket_prefix(bucket, 'chunks/uid/conv/')

    assert bucket.not_found == 1, 'the 404 surfaced exactly once, on the first pass'
    assert deleted == 0, 'a deleted-by-another-sweep object is not this call\u2019s delete'
    assert bucket.names == set(), 'the 404 confirms gone: no residue for the verifier'


def test_purge_survives_a_half_raced_prefix():
    bucket = _HalfGoneBucket(
        {'chunks/uid/conv/a.opus', 'chunks/uid/conv/b.opus'},
        gone={'chunks/uid/conv/a.opus'},
    )

    deleted = storage_mod._delete_owner_bucket_prefix(bucket, 'chunks/uid/conv/')

    assert deleted == 1, 'only the object this sweep actually removed'
    assert bucket.deleted == ['chunks/uid/conv/b.opus']


def test_account_wipe_keeps_failing_closed_without_404_masking_residue():
    """A lost delete is not a race: the residue verdict stays terminal."""
    bucket = _LostDeleteBucket({'chunks/uid/conv/a.opus'})

    with pytest.raises(RuntimeError, match='owner storage purge left'):
        storage_mod._delete_owner_bucket_prefix(bucket, 'chunks/uid/conv/')


# ── H. Linked originals: the same 404 race on the raw-sync loop ─────────────


class _LinkedOriginalBucket:
    """The raw-sync sweep races a delete of the same linked original."""

    def __init__(self, original_gone: bool):
        self.original_gone = original_gone
        self.deleted: list[str] = []
        blob = SimpleNamespace(
            name='raw-sync/uid/original.opus',
            metadata={'conversation_id': 'conv'},
        )

        def _delete() -> None:
            if self.original_gone:
                raise NotFound('No such object: raw-sync/uid/original.opus')
            self.deleted.append(blob.name)

        blob.delete = _delete
        self._blob = blob

    def list_blobs(self, *, prefix: str, **kwargs: Any) -> list[Any]:
        if self._blob.name.startswith(prefix):
            return [self._blob]
        return []


def _route_sweep_to_linked_bucket(monkeypatch, bucket: _LinkedOriginalBucket) -> None:
    """Serve ``delete_conversation_audio_files`` from the in-memory bucket."""

    monkeypatch.setattr(
        storage_mod,
        '_get_storage_client',
        lambda: SimpleNamespace(bucket=lambda name: bucket),
        raising=False,
    )
    monkeypatch.setattr(storage_mod, 'private_cloud_sync_bucket', 'private', raising=False)
    monkeypatch.setenv('BUCKET_AUDIO_DERIVED', '')


def test_linked_original_delete_absorbs_a_concurrent_404(monkeypatch):
    bucket = _LinkedOriginalBucket(original_gone=True)
    _route_sweep_to_linked_bucket(monkeypatch, bucket)

    # Must not raise: the linked original was already removed by the other
    # conversation's sweep.
    storage_mod.delete_conversation_audio_files('uid', 'conv')
    assert bucket.deleted == []


def test_linked_original_delete_still_removes_a_live_original(monkeypatch):
    bucket = _LinkedOriginalBucket(original_gone=False)
    _route_sweep_to_linked_bucket(monkeypatch, bucket)

    storage_mod.delete_conversation_audio_files('uid', 'conv')
    assert bucket.deleted == ['raw-sync/uid/original.opus']


# ── I. A momentary storage fault defers the sweep; the delete stays committed ──


def test_storage_blip_defers_the_sweep_without_reclassifying_the_delete(monkeypatch, caplog):
    def failing(*a: Any, **k: Any) -> None:
        raise ServiceUnavailable('blip')

    monkeypatch.setattr(lifecycle_service, 'delete_conversation_audio_files', failing, raising=False)
    fallbacks = _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        lifecycle_service._discard_unreferenced_audio('uid', 'conv', {})

    deferred = [r for r in caplog.records if 'Unreferenced audio sweep deferred' in r.getMessage()]
    assert deferred and deferred[0].levelno == 30, 'a deferral is a warning, not a traceback'
    assert deferred[0].exc_info is None
    assert not [r for r in caplog.records if r.levelno >= 40]
    assert fallbacks == [], 'a deferral is not an omi_fallback_total exhaustion'


def test_drained_retry_envelope_defers_the_sweep_too(monkeypatch, caplog):
    def failing(*a: Any, **k: Any) -> None:
        raise RetryError('retry budget drained', ServiceUnavailable('blip'))

    monkeypatch.setattr(lifecycle_service, 'delete_conversation_audio_files', failing, raising=False)
    fallbacks = _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        lifecycle_service._discard_unreferenced_audio('uid', 'conv', {})

    deferred = [r for r in caplog.records if 'Unreferenced audio sweep deferred' in r.getMessage()]
    assert deferred, 'the SDK envelope around a blip is the same bounded transient'
    assert fallbacks == []


def test_unknown_storage_failure_keeps_the_failed_write_classification(monkeypatch, caplog):
    def failing(*a: Any, **k: Any) -> None:
        raise PermissionError('bucket policy refuses the delete')

    monkeypatch.setattr(lifecycle_service, 'delete_conversation_audio_files', failing, raising=False)
    fallbacks = _fallback_spy(monkeypatch)

    with caplog.at_level('ERROR'):
        lifecycle_service._discard_unreferenced_audio('uid', 'conv', {})

    failures = [r for r in caplog.records if 'Failed to reclaim unreferenced audio' in r.getMessage()]
    assert failures and failures[0].levelno >= 40 and failures[0].exc_info is not None
    assert fallbacks and fallbacks[0]['outcome'] == 'exhausted'


def test_classifier_draws_the_deferral_boundary_exactly():
    assert lifecycle_service._is_storage_blip(ServiceUnavailable('blip'))
    assert lifecycle_service._is_storage_blip(TooManyRequests('429: rate limited'))
    assert lifecycle_service._is_storage_blip(BadGateway('502: bad gateway'))
    assert lifecycle_service._is_storage_blip(GatewayTimeout('504: gateway timeout'))
    assert lifecycle_service._is_storage_blip(RetryError('drained', ServiceUnavailable('blip')))
    assert lifecycle_service._is_storage_blip(RetryError('drained', BadGateway('502')))
    assert not lifecycle_service._is_storage_blip(
        RetryError('drained', None)
    ), 'a cause-less envelope carries no transient evidence'
    assert not lifecycle_service._is_storage_blip(RetryError('drained', Forbidden('policy')))
    assert not lifecycle_service._is_storage_blip(Forbidden('policy')), 'a permanent refusal keeps the failed-write arm'
    assert not lifecycle_service._is_storage_blip(BadRequest('bad request'))
    assert not lifecycle_service._is_storage_blip(NotFound('gone')), 'a 404 is the delete\u2019s success, not a blip'
    assert not lifecycle_service._is_storage_blip(
        PermissionError('refused')
    ), 'a non-transport unknown keeps the failed-write arm'


# ── J. Convergence: the deferred residue is reclaimed by the next sweep ─────


class _LateWriterBucket:
    """A sweep that keeps surfacing one more late writer, then converges.

    The first call ends with residue (the verifier's fail-closed verdict), the
    second absorbs what is left — the deferred-reclamation promise.
    """

    def __init__(self, names: set[str]):
        self.names = set(names)
        # Enough late writers to outlive one call's settle budget (two passes),
        # then stop: the first call ends with residue, the second reclaims it.
        self._ghosts = 3

    def blob(self, name: str) -> Any:
        outer = self
        blob = SimpleNamespace(name=name)

        def _delete() -> None:
            outer.names.discard(name)
            if outer._ghosts:
                outer._ghosts -= 1
                outer.names.add(f'chunks/uid/conv/late-{outer._ghosts}.opus')

        blob.delete = _delete
        return blob

    def list_blobs(self, *, prefix: str, **kwargs: Any) -> list[Any]:
        return [self.blob(name) for name in sorted(self.names) if name.startswith(prefix)]


def test_second_sweep_after_a_torn_first_delete_finds_nothing_left():
    """The retention deferral's promise: one more pass of the same prefix
    reclaims the residue the first sweep's race left behind."""
    bucket = _LateWriterBucket({'chunks/uid/conv/a.opus', 'chunks/uid/conv/b.opus'})

    with pytest.raises(RuntimeError, match='owner storage purge left'):
        storage_mod._delete_owner_bucket_prefix(bucket, 'chunks/uid/conv/')

    second = storage_mod._delete_owner_bucket_prefix(bucket, 'chunks/uid/conv/')

    assert bucket.names == set(), 'the residue converges under the next reclamation'
    assert second == 1, 'only the late writer remained for the second pass'


class _DerivedBucket:
    """One derived object whose delete answers 404: the other walker won."""

    def __init__(self, names: set[str]):
        self.names = set(names)

    def blob(self, name: str) -> Any:
        outer = self
        blob = SimpleNamespace(name=name)

        def _delete() -> None:
            outer.names.discard(name)
            raise NotFound(f'No such object: {name}')

        blob.delete = _delete
        return blob

    def list_blobs(self, *, prefix: str, **kwargs: Any) -> list[Any]:
        return [self.blob(name) for name in sorted(self.names) if name.startswith(prefix)]


def test_derived_bucket_sweep_absorbs_a_racing_404(monkeypatch):
    """The conversation sweep and the account wipe both walk the derived
    bucket's prefixes; a 404 from the other walker is absorbed and the
    verify re-list stays the only authority on what survived."""
    derived = _DerivedBucket({'merged/uid/conv/x.opus'})
    monkeypatch.setattr(
        storage_mod,
        '_get_storage_client',
        lambda: SimpleNamespace(bucket=lambda name: derived if name == 'derived' else _DerivedBucket(set())),
        raising=False,
    )
    monkeypatch.setattr(storage_mod, 'private_cloud_sync_bucket', 'private', raising=False)
    monkeypatch.setenv('BUCKET_AUDIO_DERIVED', 'derived')
    monkeypatch.delenv('BUCKET_CANONICAL_AUDIO', raising=False)

    # Must not raise: the object was already gone when this sweep reached it.
    storage_mod.delete_conversation_audio_files('uid', 'conv')
    assert derived.names == set()


def test_verifier_reports_true_residue_when_a_race_and_a_loss_coexist():
    """A 404 beside a lost delete: the verdict names only the real residue."""
    bucket = _HalfGoneBucket(
        {'chunks/uid/conv/gone.opus', 'chunks/uid/conv/stuck.opus'},
        gone={'chunks/uid/conv/gone.opus'},
    )
    original_list = bucket.list_blobs

    # Make the surviving object's delete a no-op: one 404 (the race), one
    # object no delete ever removes (the loss).
    def patched_list_blobs(*, prefix: str, **kwargs: Any) -> list[Any]:
        blobs = original_list(prefix=prefix, **kwargs)
        for blob in blobs:
            if blob.name == 'chunks/uid/conv/stuck.opus':
                blob.delete = lambda: None
        return blobs

    bucket.list_blobs = patched_list_blobs  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match='owner storage purge left 1 objects'):
        storage_mod._delete_owner_bucket_prefix(bucket, 'chunks/uid/conv/')


def test_empty_generation_delete_stays_committed_when_the_sweep_blips(monkeypatch, caplog):
    """End to end: the public delete returns True, logs one bounded deferral
    and emits no degradation event while the sweep behind it blips."""
    from database import conversations as conversations_db
    from utils.conversations import typesense_index

    store = _ContendingStore()
    store.documents[('users', 'uid', 'conversations', 'conv')] = conversations_db.encode_conversation_for_write(
        'uid', {'id': 'conv', 'status': 'in_progress', 'transcript_segments': []}, 'standard'
    )

    def blip(*a: Any, **k: Any) -> None:
        raise ServiceUnavailable('blip')

    monkeypatch.setattr(lifecycle_service, 'delete_conversation_audio_files', blip, raising=False)
    monkeypatch.setattr(typesense_index, 'delete_conversation_index_doc', lambda *a, **k: None)
    monkeypatch.setattr(lifecycle_service.conversations_db, 'delete_conversation_photos', lambda *a, **k: None)
    fallbacks = _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        deleted = lifecycle_service.delete_empty_recording_conversation(
            'uid',
            'conv',
            'session',
            firestore_client=store,
        )

    assert deleted is True, 'the committed delete keeps its outcome'
    assert any('Unreferenced audio sweep deferred' in r.getMessage() for r in caplog.records)
    assert not [r for r in caplog.records if r.levelno >= 40], 'no traceback, no ERROR'
    assert fallbacks == [], 'a deferral is not an omi_fallback_total exhaustion'
