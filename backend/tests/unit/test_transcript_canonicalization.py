"""Storage-boundary transcript canonicalization and fail-closed binding.

Round 6 canonicalized one ingest path. Equal digests then implied identical
rendered attribution only for conversations that arrived that way. This
module is the rest of that contract:

- Every segment list that ``_prepare_conversation_for_write`` compresses is
  canonicalized first, so assign / sync / live capture / later writers cannot
  store a padded ``person_id`` the hasher would strip.
- A projection bound to a *stored* row is dropped when that row is not
  already canonical. ``transcript_sha256`` still strips (client helper).
  Binding uses ``transcript_sha256_for_binding``.

Red-proofs (one-line mutation that would make the named assertion pass wrongly):
- skip canonicalize in ``_prepare_conversation_for_write`` (assign then stores
  ``' alice '``, late-finalize matches the alice digest, render is Speaker 0)
- canonicalize only in a route, not at the storage boundary (sync write keeps
  the padded id)
- bind with ``transcript_sha256`` instead of ``transcript_sha256_for_binding``
  (legacy ``' alice '`` matches alice and still renders Speaker 0)
- drop empty-after-strip segments at the storage boundary (mutates the stored
  transcript so a trailing SPEAKER_07 disappears from both digest and render)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
import zlib
from pathlib import Path
from typing import Any, Dict, List

import pytest

from database import conversations as conversations_db
from models.other import Person
from models.transcript_segment import TranscriptSegment
from utils.conversations.transcript_hash import (
    canonicalize_transcript_segments_for_storage,
    stored_transcript_is_canonical,
    transcript_sha256,
    transcript_sha256_for_binding,
)

_BACKEND = Path(__file__).resolve().parents[2]
_AGREED = 'I agree'
_ALICE = Person(id='alice', name='Alice')
_PADDED_PERSON_ID = ' alice '
_CANONICAL_PERSON_ID = 'alice'


class _FakeSnapshot:
    def __init__(self, data: Dict[str, Any] | None):
        self._data = data
        self.exists = data is not None

    def to_dict(self) -> Dict[str, Any] | None:
        return dict(self._data) if self._data is not None else None


class _FakeDocumentReference:
    def __init__(self, client: '_FakeFirestoreClient'):
        self._client = client

    def get(self, transaction: Any = None) -> _FakeSnapshot:
        return _FakeSnapshot(self._client.document)

    def collection(self, _collection_id: str) -> '_FakeCollectionReference':
        return _FakeCollectionReference(self._client)


class _FakeCollectionReference:
    def __init__(self, client: '_FakeFirestoreClient'):
        self._client = client

    def document(self, _document_id: str) -> Any:
        return self._client.doc_ref

    def collection(self, _collection_id: str) -> '_FakeCollectionReference':
        return self


class _FakeTransaction:
    _max_attempts = 5
    _read_only = False

    def __init__(self, client: '_FakeFirestoreClient', index: int):
        self._client = client
        self._id = f'txn-{index}'.encode()
        self.payload: Dict[str, Any] | None = None
        self.rolled_back = False

    def _clean_up(self) -> None:
        pass

    def _begin(self, retry_id: Any = None) -> None:
        pass

    def _rollback(self) -> None:
        self.rolled_back = True

    def update(self, _doc_ref: Any, payload: Dict[str, Any]) -> None:
        self.payload = payload

    def _commit(self) -> None:
        self._client.commits.append(self.payload)
        if self.payload is not None:
            self._client.document = {**(self._client.document or {}), **self.payload}


class _FakeFirestoreClient:
    def __init__(self, document: Dict[str, Any] | None):
        self.document = document
        self.commits: List[Dict[str, Any] | None] = []
        self.transactions: List[_FakeTransaction] = []
        self.doc_ref = _FakeDocumentReference(self)

    def collection(self, _collection_id: str) -> _FakeCollectionReference:
        return _FakeCollectionReference(self)

    def transaction(self) -> _FakeTransaction:
        transaction = _FakeTransaction(self, len(self.transactions))
        self.transactions.append(transaction)
        return transaction


def _stored_segments(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    assert payload['transcript_segments_compressed'] is True
    return json.loads(zlib.decompress(payload['transcript_segments']).decode('utf-8'))


def _assign_segment_dump(person_id: str) -> dict[str, Any]:
    """The assign route writes ``model_dump()`` after setting ``person_id``."""
    segment = TranscriptSegment(
        text=_AGREED,
        speaker='SPEAKER_00',
        is_user=False,
        person_id=person_id,
        start=0.0,
        end=1.0,
    )
    return segment.model_dump()


def _write_segments(segments: List[dict[str, Any]]) -> List[dict[str, Any]]:
    client = _FakeFirestoreClient({'has_content': True, 'data_protection_level': 'standard'})
    written = conversations_db.update_conversation_segments(
        'uid-1',
        'conversation-1',
        segments,
        data_protection_level='standard',
        firestore_client=client,
    )
    assert written is True
    assert client.commits
    payload = client.commits[-1]
    assert payload is not None
    return _stored_segments(payload)


def _as_models(stored: List[dict[str, Any]]) -> List[TranscriptSegment]:
    return [TranscriptSegment.model_validate(segment) for segment in stored]


def _render(models: List[TranscriptSegment]) -> str:
    return TranscriptSegment.segments_as_string(models, user_name='You', people=[_ALICE])


def _late_finalize(stored: List[dict[str, Any]], client_digest: str) -> str | None:
    """Bind a late projection to the stored transcript, or drop it.

    Mirrors ``_accepted_client_projection``: schema is assumed valid here; the
    only question is whether the stored identity is trustworthy enough to
    compare digests. None means drop.
    """
    expected = transcript_sha256_for_binding(_as_models(stored))
    if expected is None or expected != client_digest:
        return None
    return expected


def test_assign_padded_person_id_stores_canonical_and_late_finalize_renders_alice() -> None:
    """Reviewer's reproduction: assign ``person_id=' alice '``, then late-finalize.

    red-proof: skip canonicalize in ``_prepare_conversation_for_write`` so
    the padded id is stored, ``transcript_sha256`` matches alice, render is
    Speaker 0.
    """
    assigned = _write_segments([_assign_segment_dump(_PADDED_PERSON_ID)])
    assert assigned[0]['person_id'] == _CANONICAL_PERSON_ID
    assert assigned[0]['person_id'] != _PADDED_PERSON_ID

    models = _as_models(assigned)
    assert models[0].person_id == _CANONICAL_PERSON_ID
    assert stored_transcript_is_canonical(models) is True
    assert _render(models) == 'Alice: I agree'
    assert 'Speaker 0:' not in _render(models)

    client_digest = transcript_sha256([{'text': _AGREED, 'person_id': _CANONICAL_PERSON_ID}])
    bound = _late_finalize(assigned, client_digest)
    assert bound == client_digest
    assert bound == transcript_sha256(models)


def test_sync_pipeline_write_canonicalizes_padded_person_id() -> None:
    """Sync writes dicts through ``update_conversation_segments``, not a route.

    red-proof: canonicalize only at from-segments ingest (or in a router)
    so this payload is stored raw.
    """
    sync_payload = [
        {
            'text': _AGREED,
            'speaker': 'SPEAKER_00',
            'speaker_id': 0,
            'is_user': False,
            'person_id': _PADDED_PERSON_ID,
            'start': 0.0,
            'end': 1.5,
        }
    ]
    stored = _write_segments(sync_payload)
    assert stored[0]['person_id'] == _CANONICAL_PERSON_ID
    assert stored[0]['start'] == 0.0
    assert stored[0]['end'] == 1.5
    models = _as_models(stored)
    assert _render(models) == 'Alice: I agree'
    assert transcript_sha256_for_binding(models) == transcript_sha256(
        [{'text': _AGREED, 'person_id': _CANONICAL_PERSON_ID}]
    )


def test_legacy_noncanonical_row_drops_the_projection() -> None:
    """Rows stored before the storage-boundary change keep the padded id.

    Hashing them would strip and match alice; rendering looks up the padded
    key and shows Speaker 0. Binding must drop, not trust.

    red-proof: ``return transcript_sha256(items)`` from
    ``transcript_sha256_for_binding`` without the canonicity gate.
    """
    legacy = TranscriptSegment(
        text=_AGREED,
        speaker='SPEAKER_00',
        is_user=False,
        person_id=_PADDED_PERSON_ID,
        start=0.0,
        end=1.0,
    )
    assert legacy.person_id == _PADDED_PERSON_ID
    assert stored_transcript_is_canonical([legacy]) is False
    assert transcript_sha256_for_binding([legacy]) is None
    # The trap: the client helper still strips, so a naive bind would accept.
    alice_digest = transcript_sha256([{'text': _AGREED, 'person_id': _CANONICAL_PERSON_ID}])
    assert transcript_sha256([legacy]) == alice_digest
    assert _render([legacy]) == 'Speaker 0: I agree'
    assert 'Alice:' not in _render([legacy])

    # Same outcome through the late-finalize helper on a decoded legacy dict.
    assert _late_finalize([legacy.model_dump()], alice_digest) is None


def test_legacy_whitespace_person_id_is_not_canonical() -> None:
    blank = TranscriptSegment(text=_AGREED, is_user=False, person_id='   ', start=0.0, end=1.0)
    assert stored_transcript_is_canonical([blank]) is False
    assert transcript_sha256_for_binding([blank]) is None


def test_canonical_stored_row_still_binds() -> None:
    clean = TranscriptSegment(
        text=_AGREED,
        speaker='SPEAKER_00',
        is_user=False,
        person_id=_CANONICAL_PERSON_ID,
        start=0.0,
        end=1.0,
    )
    assert stored_transcript_is_canonical([clean]) is True
    assert transcript_sha256_for_binding([clean]) == transcript_sha256([clean])


def test_client_helper_still_strips_padded_dicts() -> None:
    """The client-reproducible helper must keep stripping. Binding is separate."""
    padded = [{'text': _AGREED, 'person_id': _PADDED_PERSON_ID}]
    clean = [{'text': _AGREED, 'person_id': _CANONICAL_PERSON_ID}]
    assert transcript_sha256(padded) == transcript_sha256(clean)
    assert stored_transcript_is_canonical(padded) is False
    assert transcript_sha256_for_binding(padded) is None


def test_storage_canonicalization_preserves_omitted_identity_keys() -> None:
    """Live-capture / expiry writes omit identity keys; do not invent them.

    red-proof: always materialize speaker/speaker_id/is_user/person_id onto
    the stored dict (would break ``test_expired_transaction_is_restarted``).
    """
    sparse = [{'id': 'seg-1', 'text': 'hello', 'start': 0.0, 'end': 1.0}]
    stored = _write_segments(sparse)
    assert stored == sparse
    assert stored_transcript_is_canonical(stored) is True
    assert transcript_sha256_for_binding(stored) == transcript_sha256(sparse)


def test_encode_conversation_for_write_is_the_same_choke_point() -> None:
    encoded = conversations_db.encode_conversation_for_write(
        'uid-1',
        {
            'transcript_segments': [
                {'text': _AGREED, 'person_id': _PADDED_PERSON_ID, 'is_user': False},
            ]
        },
        'standard',
    )
    stored = _stored_segments(encoded)
    assert stored[0]['person_id'] == _CANONICAL_PERSON_ID
    assert stored[0]['is_user'] is False


def test_prepare_for_write_canonicalizes_before_compressing() -> None:
    """The choke point is the write helper, not a route.

    red-proof: call canonicalize after ``json.dumps``, or only in
    ``routers/conversations.py``.
    """
    source = (_BACKEND / 'database' / 'conversations.py').read_text()
    write_fn = source.split('def _prepare_conversation_for_write')[1].split('\ndef ')[0]
    assert 'canonicalize_transcript_segments_for_storage' in write_fn
    assert write_fn.index('canonicalize_transcript_segments_for_storage') < write_fn.index('json.dumps')
    assert 'canonicalize_transcript_segments_for_storage' in (_BACKEND / 'database' / 'conversations.py').read_text()


def test_canonicalize_does_not_drop_translations_or_ids() -> None:
    payload = [
        {
            'id': 'seg-keep',
            'text': '  hello  ',
            'person_id': _PADDED_PERSON_ID,
            'translations': [{'lang': 'es', 'text': 'hola'}],
            'start': 1.0,
            'end': 2.0,
        }
    ]
    stored = canonicalize_transcript_segments_for_storage(payload)
    assert stored[0]['id'] == 'seg-keep'
    assert stored[0]['text'] == 'hello'
    assert stored[0]['person_id'] == _CANONICAL_PERSON_ID
    assert stored[0]['translations'] == [{'lang': 'es', 'text': 'hola'}]
    assert stored[0]['start'] == 1.0


def test_empty_speaker_07_is_stored_hashed_and_rendered() -> None:
    """Storage keeps empty-after-strip rows; digest and renderer both see them.

    red-proof: skip empty-text in ``transcript_sha256``, or drop those rows in
    ``canonicalize_transcript_segments_for_storage`` -- then a client digest
    of ``['I agree']`` would bind this stored transcript while rendering adds
    ``Speaker 7:``.
    """
    payload = [
        {
            'text': _AGREED,
            'speaker': 'SPEAKER_00',
            'is_user': False,
            'start': 0.0,
            'end': 1.0,
        },
        {
            'text': '',
            'speaker': 'SPEAKER_07',
            'is_user': False,
            'start': 1.0,
            'end': 1.1,
        },
    ]
    stored = _write_segments(payload)
    assert len(stored) == 2
    assert stored[1]['text'] == ''
    assert stored[1]['speaker'] == 'SPEAKER_07'

    models = _as_models(stored)
    assert stored_transcript_is_canonical(models) is True
    without_empty = transcript_sha256([{'text': _AGREED}])
    bound = transcript_sha256_for_binding(models)
    assert bound is not None
    assert bound != without_empty
    assert 'Speaker 7:' in _render(models)
    assert 'Speaker 7:' not in _render(_as_models(stored[:1]))
    assert _late_finalize(stored, without_empty) is None
    assert _late_finalize(stored, bound) == bound


def test_empty_text_padded_person_id_drops_the_projection() -> None:
    """Empty-text identity is still checked; padded alice renders Speaker 0.

    red-proof: ``return True`` from ``_stored_segment_is_canonical`` when text is
    empty after strip -- then binding would trust a row that renders Speaker 0
    against a client digest of Alice.
    """
    legacy = TranscriptSegment(
        text='',
        speaker='SPEAKER_00',
        is_user=False,
        person_id=_PADDED_PERSON_ID,
        start=0.0,
        end=1.0,
    )
    assert legacy.person_id == _PADDED_PERSON_ID
    assert stored_transcript_is_canonical([legacy]) is False
    assert transcript_sha256_for_binding([legacy]) is None
    assert _render([legacy]) == 'Speaker 0:'
    assert 'Alice:' not in _render([legacy])
    alice_digest = transcript_sha256([{'text': '', 'person_id': _CANONICAL_PERSON_ID}])
    assert transcript_sha256([legacy]) == alice_digest
    assert _late_finalize([legacy.model_dump()], alice_digest) is None
    clean = TranscriptSegment(
        text='',
        speaker='SPEAKER_00',
        is_user=False,
        person_id=_CANONICAL_PERSON_ID,
        start=0.0,
        end=1.0,
    )
    assert stored_transcript_is_canonical([clean]) is True
    assert _render([clean]) == 'Alice:'


# Fixtures for the moved durable-admission tests.
_UID = 's4-durable-uid'
_CONV_ID = 's4-durable-conv'
_NOW = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
_SEGMENT_TEXT = 'Hello from the desktop capture'
_T2_TEXT = 'edited later after T1 was hashed'
PROJECTION_TITLE = 'Locally summarized standup'


def _t1_segment_dict() -> Dict[str, Any]:
    return {
        'id': 's1',
        'text': _SEGMENT_TEXT,
        'speaker': 'SPEAKER_00',
        'speaker_id': 0,
        'is_user': True,
        'start': 0.0,
        'end': 1.0,
    }


def _segment() -> TranscriptSegment:
    return TranscriptSegment(text=_SEGMENT_TEXT, speaker='SPEAKER_00', speaker_id=0, is_user=True, start=0.0, end=1.0)


def _t1_projection_dump() -> Dict[str, Any]:
    """A projection whose digest is over the T1 transcript."""
    return {
        'schema_version': 1,
        'transcript_sha256': transcript_sha256([_t1_segment_dict()]),
        'structure': {'title': PROJECTION_TITLE, 'overview': '', 'category': 'other', 'sections': []},
        'action_items': [],
        'provenance': {
            'model_id': 'local-test-model',
            'runtime': 'mlx',
            'device_class': 'apple_silicon',
            'generated_at': '2026-09-02T12:00:00+00:00',
        },
    }


def _t1_mutation() -> Dict[str, Any]:
    return {'client_processing': _t1_projection_dump()}


# Moved out of test_client_processing_finalize.py: these need the REAL
# database modules, and that file deliberately stubs the database layer to load
# the coordinator and router fresh. A test that needs production modules does not
# belong in a file whose fixtures replace them.
from database import conversation_finalization_jobs as jobs  # noqa: E402

# Import the real seed helper by module path, not by name: a neighbouring suite
# stubs `database._client.document_id_from_seed` to a constant, and a from-import
# would freeze whatever happened to be installed at collection time. These tests
# compute the SAME id the production code computes, so they must use the real one
# regardless of collection order.
import importlib.util as _importlib_util  # noqa: E402

_seed_spec = _importlib_util.spec_from_file_location(
    '_s4_real_database_client', str(_BACKEND / 'database' / '_client.py')
)
assert _seed_spec is not None and _seed_spec.loader is not None
_seed_module = _importlib_util.module_from_spec(_seed_spec)
_seed_spec.loader.exec_module(_seed_module)
document_id_from_seed = _seed_module.document_id_from_seed  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from typing import Optional  # noqa: E402


# red-proof: the durable outbox copies extra_updates['client_processing'] onto the T2 snapshot
def test_durable_admit_does_not_store_t1_projection_after_t2_segment_update() -> None:
    """Durable admission's outbox transaction is the same TOCTOU as claim.

    The route validated T1 and put the projection in extra_updates. The
    conversation snapshot inside the job txn is already T2. The generation
    still admits; the T1 projection is not stored.
    """

    t2_segments = [{**_t1_segment_dict(), 'text': _T2_TEXT}]
    conversation_data = {
        'status': 'in_progress',
        'transcript_segments': t2_segments,
        'structured': {'title': _SEGMENT_TEXT, 'overview': ''},
    }

    class _PhotoCollection:
        def limit(self, count: int):
            assert count == 1
            return self

        def stream(self, transaction=None):
            del transaction
            return iter([])

    class _Ref:
        def __init__(self, doc_id: str, data: dict[str, Any] | None):
            self.id = doc_id
            self.data = data

        def get(self, transaction=None):
            del transaction
            return SimpleNamespace(exists=self.data is not None, id=self.id, to_dict=lambda: self.data)

        def collection(self, name: str):
            assert name == 'photos'
            return _PhotoCollection()

    class _Collection:
        def __init__(self) -> None:
            self.refs: dict[str, _Ref] = {}

        def document(self, doc_id: str) -> _Ref:
            return self.refs.setdefault(doc_id, _Ref(doc_id, None))

    class _Txn:
        def __init__(self) -> None:
            self.updates: list[tuple[Any, dict[str, Any]]] = []
            self.sets: list[tuple[Any, dict[str, Any]]] = []

        def update(self, ref: Any, data: dict[str, Any]) -> None:
            self.updates.append((ref, data))

        def set(self, ref: Any, data: dict[str, Any], **_kwargs: Any) -> None:
            self.sets.append((ref, data))

    transaction = _Txn()
    conversation_ref = _Ref(_CONV_ID, conversation_data)
    extra = {
        'external_data': {'calendar_meeting_context': {'event_id': 'event-1'}},
        **_t1_mutation(),
    }
    assert extra['client_processing']['transcript_sha256'] == transcript_sha256([_segment()])
    assert extra['client_processing']['transcript_sha256'] != transcript_sha256(
        [TranscriptSegment(text=_T2_TEXT, speaker='SPEAKER_00', is_user=True, start=0.0, end=1.0)]
    )

    intent = jobs._create_or_get_finalization_intent_txn(
        transaction,
        conversation_ref,
        _Collection(),
        _UID,
        _CONV_ID,
        False,
        lambda _c: {'accepted': True, 'terminal': False, 'reason': 'accepted', 'fanout_key': 'fanout-key'},
        _NOW,
        extra_updates=extra,
    )

    assert intent['status'] == 'queued'
    assert intent['created'] is True
    assert transaction.updates
    written = transaction.updates[0][1]
    assert written['status'] == 'processing'
    assert written['external_data'] == {'calendar_meeting_context': {'event_id': 'event-1'}}
    assert 'client_processing' not in written


# red-proof: skip extra_updates_with_bound_client_processing in the durable outbox (matching T1 would be omitted)
def test_durable_admit_stores_when_transcript_is_still_t1() -> None:

    conversation_data = {
        'status': 'in_progress',
        'transcript_segments': [_t1_segment_dict()],
        'structured': {'title': _SEGMENT_TEXT, 'overview': ''},
    }

    class _PhotoCollection:
        def limit(self, count: int):
            return self

        def stream(self, transaction=None):
            del transaction
            return iter([])

    class _Ref:
        def __init__(self, doc_id: str, data: dict[str, Any] | None):
            self.id = doc_id
            self.data = data

        def get(self, transaction=None):
            del transaction
            return SimpleNamespace(exists=self.data is not None, id=self.id, to_dict=lambda: self.data)

        def collection(self, name: str):
            assert name == 'photos'
            return _PhotoCollection()

    class _Collection:
        def __init__(self) -> None:
            self.refs: dict[str, _Ref] = {}

        def document(self, doc_id: str) -> _Ref:
            return self.refs.setdefault(doc_id, _Ref(doc_id, None))

    class _Txn:
        def __init__(self) -> None:
            self.updates: list[tuple[Any, dict[str, Any]]] = []
            self.sets: list[tuple[Any, dict[str, Any]]] = []

        def update(self, ref: Any, data: dict[str, Any]) -> None:
            self.updates.append((ref, data))

        def set(self, ref: Any, data: dict[str, Any], **_kwargs: Any) -> None:
            self.sets.append((ref, data))

    transaction = _Txn()
    extra = _t1_mutation()
    intent = jobs._create_or_get_finalization_intent_txn(
        transaction,
        _Ref(_CONV_ID, conversation_data),
        _Collection(),
        _UID,
        _CONV_ID,
        False,
        lambda _c: {'accepted': True, 'terminal': False, 'reason': 'accepted', 'fanout_key': 'fanout-key'},
        _NOW,
        extra_updates=extra,
    )

    assert intent['created'] is True
    written = transaction.updates[0][1]
    assert written['status'] == 'processing'
    assert written['client_processing']['structure']['title'] == PROJECTION_TITLE


# red-proof: bind through transcript_sha256 instead of transcript_sha256_for_binding
# inside extra_updates_with_bound_client_processing — the padded row would match.


EXISTING_JOB_ID = 'job-already-created-by-a'
LATER_PROJECTION_TITLE = 'Later local summary of the same standup'


def _later_mutation() -> Dict[str, Any]:
    dump = _t1_projection_dump()
    dump['structure']['title'] = LATER_PROJECTION_TITLE
    return {
        'external_data': {'calendar_meeting_context': {'event_id': 'event-b'}},
        'client_processing': dump,
    }


def _queued_job() -> Dict[str, Any]:
    return {
        'status': 'queued',
        'dispatch_generation': 1,
        'requires_byok': False,
    }


def _existing_intent(job_id: str) -> Dict[str, Any]:
    return {
        'job_id': job_id,
        'status': 'queued',
        'dispatch_generation': 1,
        'requires_byok': False,
        'fanout_key': None,
        'created': False,
    }


def _accepted_admission(_conversation: Any) -> Dict[str, Any]:
    return {'accepted': True, 'terminal': False, 'reason': 'accepted', 'fanout_key': 'fanout-key'}


def _terminal_admission(_conversation: Any) -> Dict[str, Any]:
    return {'accepted': False, 'terminal': True, 'reason': 'terminal', 'fanout_key': None}


def _terminal_intent() -> Dict[str, Any]:
    return {
        'job_id': None,
        'status': 'terminal',
        'dispatch_generation': None,
        'requires_byok': False,
        'fanout_key': None,
        'created': False,
    }


def _durable_outbox_env(
    conversation_data: Dict[str, Any],
    *,
    existing_jobs: Optional[Dict[str, Dict[str, Any]]] = None,
) -> tuple[Any, Any, Any]:
    class _PhotoCollection:
        def limit(self, count: int):
            assert count == 1
            return self

        def stream(self, transaction=None):
            del transaction
            return iter([])

    class _Ref:
        def __init__(self, doc_id: str, data: dict[str, Any] | None):
            self.id = doc_id
            self.data = data

        def get(self, transaction=None):
            del transaction
            return SimpleNamespace(exists=self.data is not None, id=self.id, to_dict=lambda: self.data)

        def collection(self, name: str):
            assert name == 'photos'
            return _PhotoCollection()

    class _Collection:
        def __init__(self) -> None:
            self.refs: dict[str, _Ref] = {}

        def document(self, doc_id: str) -> _Ref:
            return self.refs.setdefault(doc_id, _Ref(doc_id, None))

    class _Txn:
        def __init__(self) -> None:
            self.updates: list[tuple[Any, dict[str, Any]]] = []
            self.sets: list[tuple[Any, dict[str, Any]]] = []

        def update(self, ref: Any, data: dict[str, Any]) -> None:
            self.updates.append((ref, data))

        def set(self, ref: Any, data: dict[str, Any], **_kwargs: Any) -> None:
            self.sets.append((ref, data))

    transaction = _Txn()
    conversation_ref = _Ref(_CONV_ID, conversation_data)
    collection = _Collection()
    for job_id, data in (existing_jobs or {}).items():
        collection.refs[job_id] = _Ref(job_id, data)
    return transaction, conversation_ref, collection


def _run_outbox_intent(
    conversation_data: Dict[str, Any],
    extra_updates: Dict[str, Any] | None,
    *,
    existing_jobs: Optional[Dict[str, Dict[str, Any]]] = None,
    finalization_admission: Any = _accepted_admission,
) -> tuple[Any, Any]:
    transaction, conversation_ref, collection = _durable_outbox_env(conversation_data, existing_jobs=existing_jobs)
    intent = jobs._create_or_get_finalization_intent_txn(
        transaction,
        conversation_ref,
        collection,
        _UID,
        _CONV_ID,
        False,
        finalization_admission,
        _NOW,
        extra_updates=extra_updates,
    )
    return intent, transaction


def _processing_with_existing_job(transcript_segments: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        'status': 'processing',
        'transcript_segments': transcript_segments,
        'structured': {'title': _SEGMENT_TEXT, 'overview': ''},
        'finalization_job_id': EXISTING_JOB_ID,
        'finalization_revision': 1,
    }


def _completed_after_worker(transcript_segments: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Snapshot a worker left after winning the race against a still-open request."""
    return {
        'status': 'completed',
        'transcript_segments': transcript_segments,
        'structured': {'title': _SEGMENT_TEXT, 'overview': ''},
        'finalization_job_id': EXISTING_JOB_ID,
        'finalization_revision': 1,
        'finalization_status': 'completed',
    }


def _in_progress_without_job(transcript_segments: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        'status': 'in_progress',
        'transcript_segments': transcript_segments,
        'structured': {'title': _SEGMENT_TEXT, 'overview': ''},
    }


def _t2_segments() -> List[Dict[str, Any]]:
    return [{**_t1_segment_dict(), 'text': _T2_TEXT}]


# red-proof: return _intent_from_job(...) on the conversation-named existing job
# without applying extra_updates — B's later projection is discarded on a 200.
def test_existing_job_return_stores_later_bound_projection() -> None:
    """B read in_progress, A created the job, B's txn sees the existing intent.

    Section 1.7(c): B's valid later projection must still be stored. The
    existing-job return must not write calendar context or lifecycle fields.
    """
    extra = _later_mutation()
    intent, transaction = _run_outbox_intent(
        _processing_with_existing_job([_t1_segment_dict()]),
        extra,
        existing_jobs={EXISTING_JOB_ID: _queued_job()},
    )

    assert intent == _existing_intent(EXISTING_JOB_ID)
    assert transaction.sets == []
    assert len(transaction.updates) == 1
    written = transaction.updates[0][1]
    assert set(written) == {'client_processing'}
    assert written['client_processing']['structure']['title'] == LATER_PROJECTION_TITLE
    assert written['client_processing']['transcript_sha256'] == extra['client_processing']['transcript_sha256']
    assert 'external_data' not in written
    assert 'finalization_job_id' not in written
    assert 'finalization_revision' not in written
    assert 'finalization_status' not in written
    assert 'status' not in written
    assert 'dispatch_generation' not in written


# red-proof: copy extra_updates['client_processing'] onto the existing-job
# conversation write without extra_updates_with_bound_client_processing.
def test_existing_job_return_drops_unbound_projection_and_keeps_existing_intent() -> None:
    extra = _later_mutation()
    assert extra['client_processing']['transcript_sha256'] == transcript_sha256([_segment()])
    intent, transaction = _run_outbox_intent(
        _processing_with_existing_job(_t2_segments()),
        extra,
        existing_jobs={EXISTING_JOB_ID: _queued_job()},
    )

    assert intent == _existing_intent(EXISTING_JOB_ID)
    assert transaction.sets == []
    assert transaction.updates == []


# red-proof: skip _apply_snapshot_bound_projection in the intent txn finally
# so a later bound projection is omitted from the attach write.
def test_computed_existing_job_return_stores_later_bound_projection() -> None:
    job_id = document_id_from_seed(f'listen-finalization:{_UID}:{_CONV_ID}:1')
    extra = _later_mutation()
    intent, transaction = _run_outbox_intent(
        _in_progress_without_job([_t1_segment_dict()]),
        extra,
        existing_jobs={job_id: _queued_job()},
    )

    assert intent == _existing_intent(job_id)
    assert transaction.sets == []
    assert len(transaction.updates) == 1
    written = transaction.updates[0][1]
    assert written['status'] == 'processing'
    assert written['finalization_job_id'] == job_id
    assert written['finalization_revision'] == 1
    assert written['finalization_status'] == 'queued'
    assert written['client_processing']['structure']['title'] == LATER_PROJECTION_TITLE
    assert 'external_data' not in written


# red-proof: merge extra_updates into the computed-id attach write without binding.
def test_computed_existing_job_return_drops_unbound_projection_and_keeps_existing_intent() -> None:
    job_id = document_id_from_seed(f'listen-finalization:{_UID}:{_CONV_ID}:1')
    extra = _later_mutation()
    intent, transaction = _run_outbox_intent(
        _in_progress_without_job(_t2_segments()),
        extra,
        existing_jobs={job_id: _queued_job()},
    )

    assert intent == _existing_intent(job_id)
    assert transaction.sets == []
    assert len(transaction.updates) == 1
    written = transaction.updates[0][1]
    assert written == {
        'status': 'processing',
        'finalization_job_id': job_id,
        'finalization_revision': 1,
        'finalization_status': 'queued',
    }
    assert 'client_processing' not in written
    assert 'external_data' not in written


# red-proof: return _no_finalization_intent(...) on a terminal snapshot without
# applying extra_updates — B's later projection is discarded, the router noop
# branch returns without retrying it, still 200.
def test_terminal_return_stores_later_bound_projection() -> None:
    """Request read in_progress; a worker completed first; txn hits terminal.

    Section 1.7(c): B's valid later projection must still be stored. The
    terminal return must not write calendar context or lifecycle fields, and
    must still report the same no-job terminal intent.
    """
    extra = _later_mutation()
    intent, transaction = _run_outbox_intent(
        _completed_after_worker([_t1_segment_dict()]),
        extra,
        existing_jobs={EXISTING_JOB_ID: _queued_job()},
        finalization_admission=_terminal_admission,
    )

    assert intent == _terminal_intent()
    assert transaction.sets == []
    assert len(transaction.updates) == 1
    written = transaction.updates[0][1]
    assert set(written) == {'client_processing'}
    assert written['client_processing']['structure']['title'] == LATER_PROJECTION_TITLE
    assert written['client_processing']['transcript_sha256'] == extra['client_processing']['transcript_sha256']
    assert 'external_data' not in written
    assert 'finalization_job_id' not in written
    assert 'finalization_revision' not in written
    assert 'finalization_status' not in written
    assert 'status' not in written
    assert 'dispatch_generation' not in written


# red-proof: copy extra_updates['client_processing'] onto the terminal
# conversation write without extra_updates_with_bound_client_processing.
def test_terminal_return_drops_unbound_projection_and_keeps_terminal_intent() -> None:
    extra = _later_mutation()
    assert extra['client_processing']['transcript_sha256'] == transcript_sha256([_segment()])
    intent, transaction = _run_outbox_intent(
        _completed_after_worker(_t2_segments()),
        extra,
        existing_jobs={EXISTING_JOB_ID: _queued_job()},
        finalization_admission=_terminal_admission,
    )

    assert intent == _terminal_intent()
    assert transaction.sets == []
    assert transaction.updates == []


def _already_finalizing_admission(_conversation: Any) -> Dict[str, Any]:
    return {'accepted': False, 'terminal': False, 'reason': 'already_finalizing', 'fanout_key': None}


def _already_finalizing_intent() -> Dict[str, Any]:
    return {
        'job_id': None,
        'status': 'already_finalizing',
        'dispatch_generation': None,
        'requires_byok': False,
        'fanout_key': None,
        'created': False,
    }


def _no_content_intent() -> Dict[str, Any]:
    return {
        'job_id': None,
        'status': 'no_content',
        'dispatch_generation': None,
        'requires_byok': False,
        'fanout_key': None,
        'created': False,
    }


def _deferred_intent() -> Dict[str, Any]:
    return {
        'job_id': None,
        'status': 'deferred',
        'dispatch_generation': None,
        'requires_byok': False,
        'fanout_key': None,
        'created': False,
    }


def _bare_processing(transcript_segments: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Synchronous finalizer claimed the row without a durable job."""
    return {
        'status': 'processing',
        'transcript_segments': transcript_segments,
        'structured': {'title': _SEGMENT_TEXT, 'overview': ''},
    }


def _deferred_row(transcript_segments: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        'status': 'processing',
        'deferred': True,
        'transcript_segments': transcript_segments,
        'structured': {'title': _SEGMENT_TEXT, 'overview': ''},
    }


def _stored_empty_transcript_in_progress() -> Dict[str, Any]:
    encoded = conversations_db.encode_conversation_for_write(_UID, {'transcript_segments': []}, 'standard')
    return {
        'status': 'in_progress',
        'structured': {'title': _SEGMENT_TEXT, 'overview': ''},
        'data_protection_level': 'standard',
        **encoded,
    }


def _empty_digest_mutation() -> Dict[str, Any]:
    dump = _t1_projection_dump()
    dump['transcript_sha256'] = transcript_sha256([])
    dump['structure']['title'] = LATER_PROJECTION_TITLE
    return {
        'external_data': {'calendar_meeting_context': {'event_id': 'event-b'}},
        'client_processing': dump,
    }


def _assert_projection_only_write(transaction: Any, extra: Dict[str, Any]) -> None:
    assert transaction.sets == []
    assert len(transaction.updates) == 1
    written = transaction.updates[0][1]
    assert set(written) == {'client_processing'}
    assert written['client_processing']['structure']['title'] == LATER_PROJECTION_TITLE
    assert written['client_processing']['transcript_sha256'] == extra['client_processing']['transcript_sha256']
    assert 'external_data' not in written
    assert 'finalization_job_id' not in written
    assert 'finalization_revision' not in written
    assert 'finalization_status' not in written
    assert 'status' not in written
    assert 'dispatch_generation' not in written
    assert 'deferred' not in written


# red-proof: return _no_finalization_intent('already_finalizing') without the
# finally bind — the request is 200 and the valid later projection is gone.
def test_already_finalizing_return_stores_later_bound_projection() -> None:
    """Request read in_progress; a sync finalizer moved the row to bare processing.

    Admission is already_finalizing (no durable job). Section 1.7(c): B's
    valid later projection must still be stored. Lifecycle stays bare
    processing: no job identity, generation, or calendar write.
    """
    extra = _later_mutation()
    intent, transaction = _run_outbox_intent(
        _bare_processing([_t1_segment_dict()]),
        extra,
        finalization_admission=_already_finalizing_admission,
    )

    assert intent == _already_finalizing_intent()
    _assert_projection_only_write(transaction, extra)


# red-proof: copy extra_updates['client_processing'] onto the already_finalizing
# conversation write without extra_updates_with_bound_client_processing.
def test_already_finalizing_return_drops_unbound_projection() -> None:
    extra = _later_mutation()
    assert extra['client_processing']['transcript_sha256'] == transcript_sha256([_segment()])
    intent, transaction = _run_outbox_intent(
        _bare_processing(_t2_segments()),
        extra,
        finalization_admission=_already_finalizing_admission,
    )

    assert intent == _already_finalizing_intent()
    assert transaction.sets == []
    assert transaction.updates == []


# red-proof: return _no_finalization_intent('no_content') without the finally
# bind — an empty transcript is a real transcript that binds, and a 200 that
# discards its matching projection is the defect.
def test_no_content_return_stores_later_bound_empty_transcript_projection() -> None:
    """Stored, successfully decoded empty transcript reaches no_content.

    Round 9: empty is a real transcript; only an unreadable blob fails closed.
    The empty-transcript digest must bind. no_content lifecycle is unchanged.
    """
    extra = _empty_digest_mutation()
    assert extra['client_processing']['transcript_sha256'] == transcript_sha256([])
    intent, transaction = _run_outbox_intent(_stored_empty_transcript_in_progress(), extra)

    assert intent == _no_content_intent()
    _assert_projection_only_write(transaction, extra)


# red-proof: copy extra_updates['client_processing'] onto the no_content write
# without extra_updates_with_bound_client_processing.
def test_no_content_return_drops_unbound_projection() -> None:
    extra = _later_mutation()
    assert extra['client_processing']['transcript_sha256'] == transcript_sha256([_segment()])
    intent, transaction = _run_outbox_intent(_stored_empty_transcript_in_progress(), extra)

    assert intent == _no_content_intent()
    assert transaction.sets == []
    assert transaction.updates == []


# red-proof: return _no_finalization_intent('deferred') without the finally
# bind — another processor persisted deferred=True first, and the matching
# projection is discarded on a 200.
def test_deferred_return_stores_later_bound_projection_without_lifecycle_change() -> None:
    """Another processor persisted deferred=True first; the txn returns deferred.

    The matching projection is bound. deferred and processing stay as they
    were: this write does not claim or clear the deferred lane.
    """
    extra = _later_mutation()
    intent, transaction = _run_outbox_intent(_deferred_row([_t1_segment_dict()]), extra)

    assert intent == _deferred_intent()
    _assert_projection_only_write(transaction, extra)


# red-proof: copy extra_updates['client_processing'] onto the deferred write
# without extra_updates_with_bound_client_processing.
def test_deferred_return_drops_unbound_projection_and_keeps_deferred() -> None:
    extra = _later_mutation()
    assert extra['client_processing']['transcript_sha256'] == transcript_sha256([_segment()])
    intent, transaction = _run_outbox_intent(_deferred_row(_t2_segments()), extra)

    assert intent == _deferred_intent()
    assert transaction.sets == []
    assert transaction.updates == []


# red-proof: drop the sys.exc_info() guard from the finally and this fails —
# the bind runs while the transaction is aborting, and its own error replaces
# the traceback the caller needs.
def test_durable_intent_exception_propagates_without_a_projection_write() -> None:
    """An aborting transaction must not be written to, or have its error masked.

    The finally is the projection choke point for every *return*. It is not a
    handler: an exception aborts the Firestore transaction, so a write there
    can never commit, and a binding failure raised inside finally would
    replace the real traceback.
    """

    conversation_data = {
        'status': 'in_progress',
        'transcript_segments': [_t1_segment_dict()],
        'structured': {'title': _SEGMENT_TEXT, 'overview': ''},
    }

    class _PhotoCollection:
        def limit(self, count: int):
            del count
            return self

        def stream(self, transaction=None):
            del transaction
            return iter([])

    class _Ref:
        def __init__(self, doc_id: str, data: dict[str, Any] | None):
            self.id = doc_id
            self.data = data

        def get(self, transaction=None):
            del transaction
            return SimpleNamespace(exists=self.data is not None, id=self.id, to_dict=lambda: self.data)

        def collection(self, name: str):
            assert name == 'photos'
            return _PhotoCollection()

    class _Collection:
        def __init__(self) -> None:
            self.refs: dict[str, _Ref] = {}

        def document(self, doc_id: str) -> _Ref:
            return self.refs.setdefault(doc_id, _Ref(doc_id, None))

    class _Txn:
        def __init__(self) -> None:
            self.updates: list[tuple[Any, dict[str, Any]]] = []
            self.sets: list[tuple[Any, dict[str, Any]]] = []

        def update(self, ref: Any, data: dict[str, Any]) -> None:
            self.updates.append((ref, data))

        def set(self, ref: Any, data: dict[str, Any], **_kwargs: Any) -> None:
            self.sets.append((ref, data))

    class _AdmissionUnavailable(RuntimeError):
        pass

    def _raising_admission(_conversation: Any) -> Any:
        raise _AdmissionUnavailable('lifecycle service unavailable')

    transaction = _Txn()
    conversation_ref = _Ref(_CONV_ID, conversation_data)

    with pytest.raises(_AdmissionUnavailable):
        jobs._create_or_get_finalization_intent_txn(
            transaction,
            conversation_ref,
            _Collection(),
            _UID,
            _CONV_ID,
            False,
            _raising_admission,
            _NOW,
            extra_updates=_t1_mutation(),
        )

    assert transaction.updates == []
    assert transaction.sets == []


def _intent_txn_fakes(conversation_data: dict[str, Any]):
    """Transaction / ref / collection doubles for the durable intent txn."""

    class _PhotoCollection:
        def limit(self, count: int):
            del count
            return self

        def stream(self, transaction=None):
            del transaction
            return iter([])

    class _Ref:
        def __init__(self, doc_id: str, data: dict[str, Any] | None):
            self.id = doc_id
            self.data = data

        def get(self, transaction=None):
            del transaction
            return SimpleNamespace(exists=self.data is not None, id=self.id, to_dict=lambda: self.data)

        def collection(self, name: str):
            assert name == 'photos'
            return _PhotoCollection()

    class _Collection:
        def __init__(self) -> None:
            self.refs: dict[str, _Ref] = {}

        def document(self, doc_id: str) -> _Ref:
            return self.refs.setdefault(doc_id, _Ref(doc_id, None))

    class _Txn:
        def __init__(self) -> None:
            self.updates: list[tuple[Any, dict[str, Any]]] = []
            self.sets: list[tuple[Any, dict[str, Any]]] = []

        def update(self, ref: Any, data: dict[str, Any]) -> None:
            self.updates.append((ref, data))

        def set(self, ref: Any, data: dict[str, Any], **_kwargs: Any) -> None:
            self.sets.append((ref, data))

    return _Txn(), _Ref(_CONV_ID, conversation_data), _Collection()


def _accepting_admission(_conversation: Any) -> Any:
    return {'accepted': True, 'terminal': False, 'reason': 'accepted', 'fanout_key': 'fanout-key'}


# red-proof: guard the finally with ``sys.exc_info()[0] is None`` instead of this
# frame's own flag — the ambient exception makes the bind look like a failure,
# the job commits, and the conversation is written zero times.
def test_durable_intent_binds_when_called_from_inside_an_except_block() -> None:
    """An exception a CALLER is handling is not this transaction's failure.

    ``sys.exc_info()`` reports the exception being handled anywhere up the
    stack. Finalization invoked from an ``except`` (a fallback after a failed
    dispatch, for example) would then commit its job while silently skipping
    the conversation bind — the exact 200-and-discard this choke point exists
    to prevent.
    """

    conversation_data = {
        'status': 'in_progress',
        'transcript_segments': [_t1_segment_dict()],
        'structured': {'title': _SEGMENT_TEXT, 'overview': ''},
    }
    transaction, conversation_ref, collection = _intent_txn_fakes(conversation_data)

    try:
        raise RuntimeError('a caller is handling this')
    except RuntimeError:
        intent = jobs._create_or_get_finalization_intent_txn(
            transaction,
            conversation_ref,
            collection,
            _UID,
            _CONV_ID,
            False,
            _accepting_admission,
            _NOW,
            extra_updates=_t1_mutation(),
        )

    assert intent['created'] is True
    assert transaction.sets, 'the job document was created'
    assert transaction.updates, 'the conversation must still be written and bound'
    written = transaction.updates[0][1]
    assert written['status'] == 'processing'
    assert written['client_processing']['structure']['title'] == PROJECTION_TITLE


# red-proof: filter caller metadata by popping PROJECTION_FAMILY_FIELDS instead of
# allowlisting — the dotted key survives and Firestore writes it into the projection.
def test_durable_intent_drops_dotted_projection_field_paths() -> None:
    """Firestore reads ``a.b`` as a field path, so a denylist of names is not a filter.

    ``client_processing.title`` in extra_updates is a write *into* the stored
    projection that never passes the digest bind. Only allowlisted lifecycle
    metadata may ride along.
    """

    conversation_data = {
        'status': 'in_progress',
        'transcript_segments': [_t1_segment_dict()],
        'structured': {'title': _SEGMENT_TEXT, 'overview': ''},
    }
    transaction, conversation_ref, collection = _intent_txn_fakes(conversation_data)

    extra = {
        'external_data': {'calendar_meeting_context': {'event_id': 'event-1'}},
        'client_processing.title': 'unbound forgery',
        'client_processing.transcript_sha256': 'deadbeef',
        'status': 'completed',
        # Not a projection field and not allowlisted metadata: a caller cannot
        # smuggle lifecycle state this transaction did not decide.
        'deferred': True,
        'finalization_revision': 99,
        **_t1_mutation(),
    }

    jobs._create_or_get_finalization_intent_txn(
        transaction,
        conversation_ref,
        collection,
        _UID,
        _CONV_ID,
        False,
        _accepting_admission,
        _NOW,
        extra_updates=extra,
    )

    assert transaction.updates
    written = transaction.updates[0][1]
    assert not [key for key in written if '.' in key], f'field paths reached the write: {sorted(written)}'
    assert written['client_processing']['structure']['title'] == PROJECTION_TITLE
    # Caller metadata cannot override this transaction's own lifecycle keys,
    # nor add lifecycle state it never decided.
    assert written['status'] == 'processing'
    assert 'deferred' not in written
    assert written['finalization_revision'] == 1
    assert written['external_data'] == {'calendar_meeting_context': {'event_id': 'event-1'}}
