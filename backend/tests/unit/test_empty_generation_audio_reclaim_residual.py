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
        raise ConnectionError('storage unavailable')

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
