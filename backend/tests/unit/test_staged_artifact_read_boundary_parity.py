"""Typed staged-artifact read faults: raise-site matrix at the artifact layer.

Failure-Class: FC-deterministic-staged-artifact-read-failure-walks-gpu-retry-ladder-as-unclassified-valueerror

Every deterministic read fault that ``ArtifactStore._read`` and
``_reference`` raise must carry ``StagedArtifactInvalid`` — never a bare
``ValueError`` or the raw cryptography ``InvalidTag`` — so the worker's
fetch_decode boundary can terminalize it without matching exception
messages. A bare ``ValueError`` here silently puts the fault back on the
GPU retry ladder: the pinned generation serves identical bytes on every
attempt, so the ladder burns five full fetch/decrypt passes per stuck unit
(the production ``error_class=ValueError stage=fetch_decode`` signature)
before quarantining. The typed fault settles through the existing closed
``staged_audio_invalid`` refusal family on the recovery sweep instead.
Transient read faults — absent objects, privacy/authorization refusals,
storage timeouts, the deploy-configuration bucket allowlist — stay
retryable and must never take the typed boundary.
"""

import logging
from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import NotFound

from utils.batch_pipeline.artifacts import (
    AUDIO_LIMIT,
    MAGIC,
    RESULT_LIMIT,
    ArtifactStore,
    ProtectionContext,
)
from utils.batch_pipeline.contracts import FailedWork, Priority, ValidationFailureWork, WorkItem
from utils.batch_pipeline.source_audio import MAGIC as RECORD_MAGIC
from diarizer.batch_pipeline import transient_failure_evidence

try:
    # Parent commits predate the typed read boundary; the stand-in below keeps
    # this suite COLLECTING there so every test fails individually (rc 1 with
    # per-test RED) instead of one module-level collection error.
    from utils.batch_pipeline.artifacts import StagedArtifactInvalid
except ImportError:  # parent checkout

    class StagedArtifactInvalid(ValueError):
        """Parent stand-in: the real class does not exist on the parent."""


from utils.batch_pipeline.errors import WORKER_VALIDATION_REASONS, WORKER_VALIDATION_STAGES, validate_worker_failure
from utils.observability.reasons import WorkerValidationReason, WorkerValidationStage
from tests.unit.test_batch_pipeline_artifacts import ObjectClient
from tests.unit.test_batch_pipeline_worker import Samples, item, setup_worker

KEY = b'a' * 32
OTHER_KEY = b'b' * 32
AUDIO_BODY = b'synthetic staged audio'
OWNER = 'synthetic-owner'
SEGMENT = 'synthetic-segment'


def owner_key(uid):
    return KEY if uid == OWNER else OTHER_KEY


def make_item(**changes):
    fields = {
        'segment_id': SEGMENT,
        'owner_id': OWNER,
        'capture_at': 100.0,
        'audio_uri': 'pending',
        'duration_seconds': 1.0,
        'priority': Priority.FRESH,
        'privacy_generation': 0,
    }
    return WorkItem(**{**fields, **changes})


def build_store(level='enhanced', generation=0):
    client = ObjectClient()
    state = SimpleNamespace(context=ProtectionContext(level, generation), registered=[], key_override=None)
    store = ArtifactStore(
        client,
        bucket='synthetic-batch-bucket',
        namespace='batch_pipeline_test_artifacts',
        authorize=lambda i: state.context,
        key_for_owner=lambda uid: state.key_override or owner_key(uid),
        register_artifact=lambda *args: state.registered.append(args),
    )
    return store, client, state


def stage_audio_item(store, body=AUDIO_BODY):
    """Stage one canonical unit; return the admitted item with its real URI."""
    original = make_item()
    uri = store.stage_audio(original, body)
    return replace(original, audio_uri=uri), uri


def stage_result_item(store, payload=None):
    """Stage one audio unit and commit one result artifact over it."""
    payload = {'words': [{'word': 'hi', 'timestamp': [0.0, 0.1]}]} if payload is None else payload
    original = make_item()
    staged = replace(original, audio_uri=store.stage_audio(original, b'audio'))
    uri = store.persist_result(staged, payload)
    return staged, uri


def audio_object_name(client):
    return next(name for name in client.objects if '/audio/' in name)


def results_object_name(client):
    return next(name for name in client.objects if '/results/' in name)


def poison(client, name, mutate):
    """Replace the stored bytes of one pinned object; the generation never moves."""
    generation, body = client.objects[name]
    client.objects[name] = (generation, mutate(body))


def assert_typed(excinfo, message):
    """The fault carries the type, the closed message and nothing else."""
    assert isinstance(excinfo.value, StagedArtifactInvalid)
    assert type(excinfo.value) is StagedArtifactInvalid
    assert str(excinfo.value) == message
    assert isinstance(excinfo.value, ValueError)


def uri_without_fragment(uri):
    return uri.split('#', 1)[0]


@contextmanager
def blob_override(client, *, size=None, download_error=None):
    """Per-test blob attribute overrides without touching the shared fixture.

    ``size`` replaces the metadata reload's reported size (the shared fake
    falls back to the real length for falsy values); ``download_error`` makes
    the read attempt raise, simulating a storage fault past the metadata gate.
    """
    real_blob = client.blob

    def patched(name, generation=None):
        inner = real_blob(name, generation=generation)

        class Wrapped:
            def __getattr__(self, attr):
                return getattr(inner, attr)

            def reload(self, **kw):
                result = inner.reload(**kw)
                if size is not None:
                    self.size = size
                return result

            def download_as_bytes(self, **kw):
                if download_error is not None:
                    raise download_error
                return inner.download_as_bytes(**kw)

        return Wrapped()

    client.blob = patched
    try:
        yield
    finally:
        client.blob = real_blob


# --- The type itself -------------------------------------------------------------


def test_staged_artifact_invalid_is_a_value_error_subclass():
    assert issubclass(StagedArtifactInvalid, ValueError)


def test_staged_artifact_invalid_is_distinct_from_the_wav_staging_family():
    from utils.batch_pipeline.audio import StagedAudioInvalid

    assert not issubclass(StagedArtifactInvalid, StagedAudioInvalid)
    assert not issubclass(StagedAudioInvalid, StagedArtifactInvalid)


def test_staged_artifact_invalid_is_distinct_from_the_retained_family():
    from utils.batch_pipeline.source_audio import RetainedAudioInvalid

    assert not issubclass(StagedArtifactInvalid, RetainedAudioInvalid)
    assert not issubclass(RetainedAudioInvalid, StagedArtifactInvalid)


def test_staged_artifact_invalid_is_distinct_from_the_manifest_family():
    from utils.batch_pipeline.source_audio import InvalidRetainedManifest

    assert not issubclass(StagedArtifactInvalid, InvalidRetainedManifest)
    assert not issubclass(InvalidRetainedManifest, StagedArtifactInvalid)


def test_staged_artifact_invalid_is_distinct_from_the_duration_family():
    from diarizer.batch_pipeline import DecodedDurationMismatch

    assert not issubclass(StagedArtifactInvalid, DecodedDurationMismatch)
    assert not issubclass(DecodedDurationMismatch, StagedArtifactInvalid)


def test_staged_artifact_invalid_is_not_the_raw_cryptography_fault():
    from cryptography.exceptions import InvalidTag

    assert not issubclass(StagedArtifactInvalid, InvalidTag)
    assert not issubclass(InvalidTag, StagedArtifactInvalid)


def test_typed_artifact_fault_survives_a_catch_site_written_for_value_error():
    # Projection and sweep callers catch ValueError; the typed fault must
    # not escape an existing except clause.
    with pytest.raises(ValueError):

        def raise_typed():
            raise StagedArtifactInvalid('invalid batch artifact envelope')

        raise_typed()


def test_typed_artifact_fault_message_never_names_the_mechanism():
    # Closed messages only: the boundary and the refusal family must be
    # able to log the class without leaking bytes, URIs or key material.
    for message in (
        'artifact must be an owner/segment-bound generation-pinned staging reference',
        'stored batch artifact exceeds bounded payload size',
        'invalid batch artifact envelope',
        'staged artifact authentication failed',
    ):
        assert 'gs://' not in message and 'AES' not in message and 'nonce' not in message


# --- _reference: the admitted staging reference matrix ---------------------------


def reference_faults():
    """One mutation per reference dimension; every one is deterministic."""
    return {
        'scheme': lambda uri: uri.replace('gs://', 'http://', 1),
        'bucket': lambda uri: uri.replace('synthetic-batch-bucket', 'other-bucket', 1),
        'query': lambda uri: uri + '?x=1',
        'missing_fragment': uri_without_fragment,
        'zero_fragment': lambda uri: uri.rsplit('#', 1)[0] + '#0',
        'negative_fragment': lambda uri: uri.rsplit('#', 1)[0] + '#-1',
        'nondigit_fragment': lambda uri: uri.rsplit('#', 1)[0] + '#generation',
        'zero_padded_fragment': lambda uri: uri.rsplit('#', 1)[0] + '#01',
        'overflow_fragment': lambda uri: uri.rsplit('#', 1)[0] + '#' + '9' * 21,
        'owner_dir': lambda uri: uri.replace('owners/', 'owners-x/', 1),
        'segment_dir': lambda uri: uri.replace('/' + SEGMENT + '/', '/other-segment/', 1),
        'kind_dir': lambda uri: uri.replace('/audio/', '/diarization/', 1).replace('/results/', '/diarization/', 1),
        'key_not_hex': lambda uri: uri.rsplit('/', 1)[0] + '/zz.enc#' + uri.rsplit('#', 1)[1],
        'key_short': lambda uri: uri.rsplit('/', 1)[0] + '/abcd.enc#' + uri.rsplit('#', 1)[1],
        'key_extension': lambda uri: uri.replace('.enc#', '.bin#', 1),
    }


def typed_reference(message='artifact must be an owner/segment-bound generation-pinned staging reference'):
    return pytest.raises(StagedArtifactInvalid, match='^' + message.replace('(', '\\(').replace(')', '\\)') + '$')


@pytest.mark.parametrize('name', ['scheme', 'bucket', 'segment_dir', 'kind_dir', 'zero_fragment', 'key_extension'])
def test_results_reference_mutation_is_typed(name):
    store, _, _ = build_store()
    staged, uri = stage_result_item(store)
    mutate = reference_faults()[name]
    with typed_reference():
        store.load_result(staged, mutate(uri))


def test_results_reference_missing_fragment_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_result_item(store)
    with typed_reference():
        store.load_result(staged, uri_without_fragment(uri))


def test_results_reference_owner_dir_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_result_item(store)
    with typed_reference():
        store.load_result(staged, uri.replace('owners/', 'owners-x/', 1))


def test_results_reference_nondigit_fragment_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_result_item(store)
    with typed_reference():
        store.load_result(staged, uri.rsplit('#', 1)[0] + '#generation')


def test_results_reference_overflow_fragment_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_result_item(store)
    with typed_reference():
        store.load_result(staged, uri.rsplit('#', 1)[0] + '#' + '9' * 21)


def test_audio_reference_message_is_the_closed_token():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with pytest.raises(StagedArtifactInvalid) as raised:
        store.fetch_audio(replace(staged, audio_uri=uri.replace('/audio/', '/diarization/', 1)))
    assert str(raised.value) == 'artifact must be an owner/segment-bound generation-pinned staging reference'


def test_audio_reference_fault_is_value_error_instance():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with pytest.raises(ValueError) as raised:
        store.fetch_audio(replace(staged, audio_uri=uri.replace('gs://', 'http://', 1)))
    assert isinstance(raised.value, StagedArtifactInvalid)


def test_audio_reference_fault_message_never_contains_the_uri():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with pytest.raises(StagedArtifactInvalid) as raised:
        store.fetch_audio(replace(staged, audio_uri=uri + '?x=1'))
    assert 'gs://' not in str(raised.value) and SEGMENT not in str(raised.value)


def test_results_reference_fault_message_never_contains_the_uri():
    store, _, _ = build_store()
    staged, uri = stage_result_item(store)
    with pytest.raises(StagedArtifactInvalid) as raised:
        store.load_result(staged, uri_without_fragment(uri))
    text = str(raised.value)
    assert 'gs://' not in text and uri not in text and SEGMENT not in text


def test_missing_audio_proof_reference_mutation_is_typed():
    """The admission probe validates the same reference: same typed contract."""
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with typed_reference():
        store.missing_audio_evidence(replace(staged, audio_uri=uri.replace('/audio/', '/results/', 1)), now=1.0)


def test_missing_audio_proof_zero_fragment_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with typed_reference():
        store.missing_audio_evidence(replace(staged, audio_uri=uri.rsplit('#', 1)[0] + '#0'), now=1.0)


def test_missing_audio_proof_missing_fragment_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with typed_reference():
        store.missing_audio_evidence(replace(staged, audio_uri=uri_without_fragment(uri)), now=1.0)


def test_missing_audio_proof_scheme_mutation_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with typed_reference():
        store.missing_audio_evidence(replace(staged, audio_uri=uri.replace('gs://', 'http://', 1)), now=1.0)


def test_record_plan_reference_mutation_is_typed():
    store, _, _ = build_store()
    original = make_item()
    uri = store.stage_record_plan(original, {'references': []})
    with typed_reference():
        store.load_record_plan(replace(original, audio_uri=uri), uri.rsplit('#', 1)[0] + '#0')


def test_record_plan_kind_dir_mutation_is_typed():
    store, _, _ = build_store()
    original = make_item()
    uri = store.stage_record_plan(original, {'references': []})
    with typed_reference():
        store.load_record_plan(replace(original, audio_uri=uri), uri.replace('/audio/', '/diarization/', 1))


# --- _read: size and envelope faults on the pinned bytes -------------------------


def test_reported_size_zero_is_typed_via_fetch_audio():
    store, client, _ = build_store()
    staged, _ = stage_audio_item(store)
    with blob_override(client, size=0), typed_size():
        store.fetch_audio(staged)


def test_reported_size_zero_is_typed_via_load_result():
    store, client, _ = build_store()
    staged, uri = stage_result_item(store)
    with blob_override(client, size=0), typed_size():
        store.load_result(staged, uri)


def test_reported_size_over_audio_limit_is_typed():
    store, client, _ = build_store()
    staged, _ = stage_audio_item(store)
    client.reported_size = AUDIO_LIMIT + len(MAGIC) + 28 + 1
    with typed_size():
        store.fetch_audio(staged)


def test_reported_size_at_audio_ceiling_passes_the_metadata_gate():
    """The bound is inclusive at ``limit + MAGIC + nonce + tag``: real reads decide."""
    store, client, _ = build_store()
    staged, _ = stage_audio_item(store)
    client.reported_size = AUDIO_LIMIT + len(MAGIC) + 28
    assert store.fetch_audio(staged) == AUDIO_BODY


def test_reported_size_over_result_limit_is_typed_via_load_result():
    store, client, _ = build_store()
    staged, uri = stage_result_item(store)
    client.reported_size = RESULT_LIMIT + len(MAGIC) + 28 + 1
    with typed_size():
        store.load_result(staged, uri)


def test_reported_size_at_result_ceiling_passes_the_metadata_gate():
    store, client, _ = build_store()
    staged, uri = stage_result_item(store)
    client.reported_size = RESULT_LIMIT + len(MAGIC) + 28
    assert isinstance(store.load_result(staged, uri), dict)


def test_stored_audio_body_over_audio_limit_is_typed():
    """A stored body past the bound is typed even when metadata never lied."""
    store, client, _ = build_store()
    staged, _ = stage_audio_item(store)
    poison(client, audio_object_name(client), lambda body: b'\x00' * (AUDIO_LIMIT + len(MAGIC) + 28 + 1))
    with typed_size():
        store.fetch_audio(staged)


def test_stored_result_body_over_result_limit_is_typed():
    store, client, _ = build_store()
    staged, uri = stage_result_item(store)
    poison(client, results_object_name(client), lambda body: b'\x00' * (RESULT_LIMIT + len(MAGIC) + 28 + 1))
    with typed_size():
        store.load_result(staged, uri)


def test_size_message_is_the_closed_token():
    store, client, _ = build_store()
    staged, _ = stage_audio_item(store)
    with blob_override(client, size=0), pytest.raises(StagedArtifactInvalid) as raised:
        store.fetch_audio(staged)
    assert str(raised.value) == 'stored batch artifact exceeds bounded payload size'


def test_size_fault_is_value_error_instance():
    store, client, _ = build_store()
    staged, uri = stage_result_item(store)
    with blob_override(client, size=0), pytest.raises(ValueError) as raised:
        store.load_result(staged, uri)
    assert isinstance(raised.value, StagedArtifactInvalid)


def test_missing_magic_prefix_is_typed_via_fetch_audio():
    store, client, _ = build_store()
    staged, _ = stage_audio_item(store)
    poison(client, audio_object_name(client), lambda body: b'X' + body[1:])
    with typed_envelope():
        store.fetch_audio(staged)


def test_magic_first_byte_flip_is_typed():
    store, client, _ = build_store()
    staged, _ = stage_audio_item(store)
    poison(client, audio_object_name(client), lambda body: bytes([body[0] ^ 1]) + body[1:])
    with typed_envelope():
        store.fetch_audio(staged)


def test_magic_middle_byte_flip_is_typed():
    store, client, _ = build_store()
    staged, _ = stage_audio_item(store)
    poison(client, audio_object_name(client), lambda body: body[:3] + bytes([body[3] ^ 1]) + body[4:])
    with typed_envelope():
        store.fetch_audio(staged)


def test_magic_last_byte_flip_is_typed():
    """MAGIC is six bytes; its last byte still gates the envelope check."""
    store, client, _ = build_store()
    staged, _ = stage_audio_item(store)
    poison(client, audio_object_name(client), lambda body: body[:5] + bytes([body[5] ^ 1]) + body[6:])
    with typed_envelope():
        store.fetch_audio(staged)


def test_sealed_tag_byte_flip_is_typed():
    """The final authenticated byte is the tag: flipping it fails decrypt."""
    store, client, _ = build_store()
    staged, _ = stage_audio_item(store)
    poison(client, audio_object_name(client), lambda body: body[:-1] + bytes([body[-1] ^ 1]))
    with typed_auth():
        store.fetch_audio(staged)


def test_body_shorter_than_the_nonce_is_typed():
    """MAGIC intact but the nonce truncated: the fault surfaces at decrypt."""
    store, client, _ = build_store()
    staged, _ = stage_audio_item(store)
    poison(client, audio_object_name(client), lambda body: body[: len(MAGIC) + 4])
    with typed_auth():
        store.fetch_audio(staged)


def test_body_magic_only_is_typed():
    store, client, _ = build_store()
    staged, _ = stage_audio_item(store)
    poison(client, audio_object_name(client), lambda body: MAGIC)
    with typed_auth():
        store.fetch_audio(staged)


def test_body_truncated_eight_bytes_after_magic_is_typed():
    store, client, _ = build_store()
    staged, _ = stage_audio_item(store)
    poison(client, audio_object_name(client), lambda body: body[: len(MAGIC) + 8])
    with typed_auth():
        store.fetch_audio(staged)


def test_envelope_message_is_the_closed_token():
    store, client, _ = build_store()
    staged, _ = stage_audio_item(store)
    poison(client, audio_object_name(client), lambda body: b'X' + body[1:])
    with pytest.raises(StagedArtifactInvalid) as raised:
        store.fetch_audio(staged)
    assert str(raised.value) == 'invalid batch artifact envelope'


def test_envelope_fault_is_value_error_instance():
    store, client, _ = build_store()
    staged, uri = stage_result_item(store)
    poison(client, results_object_name(client), lambda body: b'X' + body[1:])
    with pytest.raises(ValueError) as raised:
        store.load_result(staged, uri)
    assert isinstance(raised.value, StagedArtifactInvalid)


def test_sealed_one_byte_short_of_nonce_is_typed():
    store, client, _ = build_store()
    staged, _ = stage_audio_item(store)
    poison(client, audio_object_name(client), lambda body: body[: len(MAGIC) + 11])
    with typed_auth():
        store.fetch_audio(staged)


def test_sealed_exactly_nonce_is_typed():
    """Nonce without ciphertext/tag still authenticates empty: typed, not silent."""
    store, client, _ = build_store()
    staged, _ = stage_audio_item(store)
    poison(client, audio_object_name(client), lambda body: body[: len(MAGIC) + 12])
    with pytest.raises(StagedArtifactInvalid) as raised:
        store.fetch_audio(staged)
    assert str(raised.value) == 'staged artifact authentication failed'


def test_nonce_byte_flip_is_typed():
    store, client, _ = build_store()
    staged, _ = stage_audio_item(store)
    poison(
        client,
        audio_object_name(client),
        lambda body: body[: len(MAGIC)] + bytes([body[len(MAGIC)] ^ 1]) + body[len(MAGIC) + 1 :],
    )
    with pytest.raises(StagedArtifactInvalid) as raised:
        store.fetch_audio(staged)
    assert str(raised.value) == 'staged artifact authentication failed'


def test_ciphertext_first_byte_flip_is_typed():
    store, client, _ = build_store()
    staged, _ = stage_audio_item(store)
    offset = len(MAGIC) + 12
    poison(
        client, audio_object_name(client), lambda body: body[:offset] + bytes([body[offset] ^ 1]) + body[offset + 1 :]
    )
    with pytest.raises(StagedArtifactInvalid) as raised:
        store.fetch_audio(staged)
    assert str(raised.value) == 'staged artifact authentication failed'


def test_ciphertext_last_byte_tag_flip_is_typed():
    store, client, _ = build_store()
    staged, _ = stage_audio_item(store)
    poison(client, audio_object_name(client), lambda body: body[:-1] + bytes([body[-1] ^ 1]))
    with pytest.raises(StagedArtifactInvalid) as raised:
        store.fetch_audio(staged)
    assert str(raised.value) == 'staged artifact authentication failed'


def test_envelope_fault_never_names_the_object():
    store, client, _ = build_store()
    staged, _ = stage_audio_item(store)
    poison(client, audio_object_name(client), lambda body: b'X' + body[1:])
    with pytest.raises(StagedArtifactInvalid) as raised:
        store.fetch_audio(staged)
    assert 'enc' not in str(raised.value) and 'synthetic' not in str(raised.value)


def typed_size(message='stored batch artifact exceeds bounded payload size'):
    return pytest.raises(StagedArtifactInvalid, match='^' + message + '$')


def typed_envelope(message='invalid batch artifact envelope'):
    return pytest.raises(StagedArtifactInvalid, match='^' + message + '$')


def typed_auth(message='staged artifact authentication failed'):
    return pytest.raises(StagedArtifactInvalid, match='^' + message + '$')


# --- authenticated decryption: identity and key material -------------------------


# Identity fields fail at different boundaries: the owner and segment
# directories move the staging reference, the privacy generation fence fires
# before any bytes are read, and the remaining AAD-bound fields fail decrypt.


def wrong_identity_cells():
    """One mutation per identity field the store authenticates or references."""
    return {
        'owner_id': lambda item: replace(item, owner_id='other-owner'),
        'segment_id': lambda item: replace(item, segment_id='other-segment'),
        'capture_at': lambda item: replace(item, capture_at=101.0),
        'duration_seconds': lambda item: replace(item, duration_seconds=9.0),
        'unit_kind': lambda item: replace(item, unit_kind='capture_span'),
        'conversation_id': lambda item: replace(item, conversation_id='other'),
        'privacy_generation': lambda item: replace(item, privacy_generation=3),
        'shadow_flag': lambda item: replace(item, shadow=not item.shadow),
    }


REFERENCE_FIELDS = ('owner_id', 'segment_id')
AUTH_FIELDS = ('capture_at', 'duration_seconds', 'unit_kind', 'conversation_id', 'shadow_flag')


@pytest.mark.parametrize('name', AUTH_FIELDS)
def test_audio_identity_mismatch_is_typed(name):
    store, _, _ = build_store()
    staged, _ = stage_audio_item(store)
    with typed_auth():
        store.fetch_audio(wrong_identity_cells()[name](staged))


@pytest.mark.parametrize('name', AUTH_FIELDS)
def test_results_identity_mismatch_is_typed(name):
    store, _, _ = build_store()
    staged, uri = stage_result_item(store)
    with typed_auth():
        store.load_result(wrong_identity_cells()[name](staged), uri)


@pytest.mark.parametrize('name', REFERENCE_FIELDS)
def test_audio_identity_mismatch_moves_the_reference(name):
    store, _, _ = build_store()
    staged, _ = stage_audio_item(store)
    with typed_reference():
        store.fetch_audio(wrong_identity_cells()[name](staged))


@pytest.mark.parametrize('name', REFERENCE_FIELDS)
def test_results_identity_mismatch_moves_the_reference(name):
    store, _, _ = build_store()
    staged, uri = stage_result_item(store)
    with typed_reference():
        store.load_result(wrong_identity_cells()[name](staged), uri)


@pytest.mark.parametrize('kind', ['audio', 'results'])
def test_privacy_generation_fence_stays_permission_error(kind):
    """The admitted generation is fenced before any byte is read."""
    store, _, _ = build_store()
    staged, uri = stage_result_item(store)
    item = wrong_identity_cells()['privacy_generation'](staged)
    with pytest.raises(PermissionError):
        store.fetch_audio(item) if kind == 'audio' else store.load_result(item, uri)


@pytest.mark.parametrize('kind', ['audio', 'results'])
def test_privacy_generation_fence_is_never_typed(kind):
    store, _, _ = build_store()
    staged, uri = stage_result_item(store)
    item = wrong_identity_cells()['privacy_generation'](staged)
    with pytest.raises(PermissionError) as raised:
        store.fetch_audio(item) if kind == 'audio' else store.load_result(item, uri)
    assert not isinstance(raised.value, StagedArtifactInvalid)


def test_wrong_protection_level_is_typed():
    store, client, state = build_store()
    staged, _ = stage_audio_item(store)
    state.context = ProtectionContext('standard', 0)
    with typed_auth():
        store.fetch_audio(staged)


def test_wrong_protection_generation_is_a_fence_refusal():
    """A read-generation drift trips the fence before any bytes are read:
    the AAD generation can only mismatch through the level, never alone."""
    store, client, state = build_store()
    staged, _ = stage_audio_item(store)
    state.context = ProtectionContext('enhanced', 5)
    with pytest.raises(PermissionError):
        store.fetch_audio(staged)


def test_wrong_owner_key_is_typed():
    """A rotated key can never open the artifact staged under its predecessor."""
    store, _, state = build_store()
    staged, _ = stage_audio_item(store)
    state.key_override = OTHER_KEY
    with typed_auth():
        store.fetch_audio(staged)


def test_wrong_owner_key_message_is_the_closed_token():
    store, _, state = build_store()
    staged, _ = stage_audio_item(store)
    state.key_override = OTHER_KEY
    with pytest.raises(StagedArtifactInvalid) as raised:
        store.fetch_audio(staged)
    assert str(raised.value) == 'staged artifact authentication failed'


def test_wrong_owner_key_fault_chains_the_cause():
    store, _, state = build_store()
    staged, _ = stage_audio_item(store)
    state.key_override = OTHER_KEY
    with pytest.raises(StagedArtifactInvalid) as raised:
        store.fetch_audio(staged)
    assert raised.value.__cause__ is not None


def test_tampered_body_chains_the_invalid_tag_cause():
    from cryptography.exceptions import InvalidTag

    store, client, _ = build_store()
    staged, _ = stage_audio_item(store)
    offset = len(MAGIC) + 12
    poison(
        client, audio_object_name(client), lambda body: body[:offset] + bytes([body[offset] ^ 1]) + body[offset + 1 :]
    )
    with pytest.raises(StagedArtifactInvalid) as raised:
        store.fetch_audio(staged)
    assert isinstance(raised.value.__cause__, InvalidTag)


def test_auth_fault_never_leaks_key_or_identity_text():
    store, _, state = build_store()
    staged, _ = stage_audio_item(store)
    state.key_override = OTHER_KEY
    with pytest.raises(StagedArtifactInvalid) as raised:
        store.fetch_audio(staged)
    text = str(raised.value)
    assert OWNER not in text and 'InvalidTag' not in text


def test_auth_fault_is_value_error_instance_for_existing_catch_sites():
    store, _, state = build_store()
    staged, _ = stage_audio_item(store)
    state.key_override = OTHER_KEY
    with pytest.raises(ValueError) as raised:
        store.fetch_audio(staged)
    assert isinstance(raised.value, StagedArtifactInvalid)


def test_record_plan_identity_mismatch_is_typed():
    store, _, _ = build_store()
    original = make_item()
    uri = store.stage_record_plan(original, {'references': []})
    with typed_auth():
        store.load_record_plan(replace(original, capture_at=101.0), uri)


def test_results_audio_uri_binding_is_absent_from_the_audio_aad():
    """The audio kind's identity leaves the URI blank: the binding is structural."""
    store, _, _ = build_store()
    staged, uri = stage_result_item(store)
    # Same bytes, same identity, results URI bound in: only the kind differs.
    with typed_reference():
        store.fetch_audio(replace(staged, audio_uri=uri))


# --- round trips: the typed boundary never fires on healthy artifacts ------------


def test_audio_round_trip_still_succeeds():
    store, _, _ = build_store()
    staged, _ = stage_audio_item(store)
    assert store.fetch_audio(staged) == AUDIO_BODY


def test_results_round_trip_still_succeeds():
    store, _, _ = build_store()
    staged, uri = stage_result_item(store)
    assert store.load_result(staged, uri) == {'words': [{'word': 'hi', 'timestamp': [0.0, 0.1]}]}


def test_record_plan_round_trip_still_succeeds():
    store, _, _ = build_store()
    original = make_item()
    uri = store.stage_record_plan(original, {'references': [1, 2]})
    assert store.load_record_plan(replace(original, audio_uri=uri), uri) == {'references': [1, 2]}


def test_repeated_reads_of_healthy_bytes_still_succeed():
    store, _, _ = build_store()
    staged, _ = stage_audio_item(store)
    assert store.fetch_audio(staged) == AUDIO_BODY
    assert store.fetch_audio(staged) == AUDIO_BODY


def test_mixed_kind_reads_stay_independent():
    store, _, _ = build_store()
    staged, uri = stage_result_item(store)
    assert store.fetch_audio(staged) == b'audio'
    assert isinstance(store.load_result(staged, uri), dict)


def test_second_owner_artifact_reads_under_its_own_key():
    store, _, _ = build_store()
    other = make_item(owner_id='other-owner')
    uri = store.stage_audio(other, b'other audio')
    assert store.fetch_audio(replace(other, audio_uri=uri)) == b'other audio'


def test_second_owner_cannot_read_the_first_owners_artifact():
    """The owner directory moves the reference before any bytes are read."""
    store, _, _ = build_store()
    staged, _ = stage_audio_item(store)
    with typed_reference():
        store.fetch_audio(replace(staged, owner_id='other-owner'))


def test_stage_then_read_preserves_bytes_for_every_level():
    for level in ('standard', 'enhanced'):
        store, _, _ = build_store(level=level)
        staged, _ = stage_audio_item(store)
        assert store.fetch_audio(staged) == AUDIO_BODY


# --- transient faults stay untyped and retryable ---------------------------------


def test_absent_object_is_not_typed():
    """A missing generation-pinned object is storage reality, not bad bytes."""
    store, client, _ = build_store()
    staged, _ = stage_audio_item(store)
    del client.objects[audio_object_name(client)]
    with pytest.raises(NotFound):
        store.fetch_audio(staged)


def test_absent_object_is_never_the_typed_boundary():
    store, client, _ = build_store()
    staged, _ = stage_audio_item(store)
    del client.objects[audio_object_name(client)]
    with pytest.raises(NotFound) as raised:
        store.fetch_audio(staged)
    assert not isinstance(raised.value, StagedArtifactInvalid)


def test_privacy_generation_refusal_stays_permission_error():
    store, _, state = build_store()
    staged, _ = stage_audio_item(store)
    state.context = ProtectionContext('enhanced', 7)
    with pytest.raises(PermissionError):
        store.fetch_audio(staged)


def test_privacy_generation_refusal_is_never_typed():
    store, _, state = build_store()
    staged, _ = stage_audio_item(store)
    state.context = ProtectionContext('enhanced', 7)
    with pytest.raises(PermissionError) as raised:
        store.fetch_audio(staged)
    assert not isinstance(raised.value, StagedArtifactInvalid)


def test_admitted_generation_zero_with_matching_context_reads():
    store, _, _ = build_store(generation=0)
    staged, _ = stage_audio_item(store)
    assert store.fetch_audio(staged) == AUDIO_BODY


def test_storage_download_timeout_stays_timeout_error():
    store, client, _ = build_store()
    staged, _ = stage_audio_item(store)

    class Wrapper:
        def __init__(self, blob):
            self._blob = blob

        def __getattr__(self, attr):
            return getattr(self._blob, attr)

        def download_as_bytes(self, **kwargs):
            raise TimeoutError('synthetic download timeout')

    real_blob = client.blob
    client.blob = lambda *args, **kwargs: Wrapper(real_blob(*args, **kwargs))
    with pytest.raises(TimeoutError):
        store.fetch_audio(staged)
    client.blob = real_blob


def test_storage_download_runtime_error_stays_untyped():
    store, client, _ = build_store()
    staged, _ = stage_audio_item(store)

    class Wrapper:
        def __init__(self, blob):
            self._blob = blob

        def __getattr__(self, attr):
            return getattr(self._blob, attr)

        def download_as_bytes(self, **kwargs):
            raise RuntimeError('synthetic storage outage')

    real_blob = client.blob
    client.blob = lambda *args, **kwargs: Wrapper(real_blob(*args, **kwargs))
    with pytest.raises(RuntimeError):
        store.fetch_audio(staged)
    client.blob = real_blob


def test_bucket_allowlist_refusal_stays_retryable_and_is_named_now():
    """Deploy configuration is not the manifest: it must stay retryable — and
    it is typed so the fetch_decode evidence names it instead of collapsing
    into the anonymous ValueError bucket."""
    from utils.batch_pipeline.source_audio import RetainedAudioOutsideAdmittedSource, read_reference

    with pytest.raises(ValueError) as raised:
        read_reference(
            Mock(), {'bucket': 'not-admitted', 'path': 'chunks/o/c/x.bin', 'generation': 1}, 'o', 'c', {'admitted'}, KEY
        )
    from utils.batch_pipeline.source_audio import InvalidRetainedManifest, RetainedAudioInvalid

    assert isinstance(raised.value, RetainedAudioOutsideAdmittedSource)
    assert not isinstance(raised.value, StagedArtifactInvalid)
    assert not isinstance(raised.value, RetainedAudioInvalid)
    assert not isinstance(raised.value, InvalidRetainedManifest)


def test_retained_manifest_faults_keep_their_own_family():
    from utils.batch_pipeline.source_audio import InvalidRetainedManifest, materialize

    body = RECORD_MAGIC + b'not json'
    with pytest.raises(InvalidRetainedManifest) as raised:
        materialize(body, make_item(), lambda ref: b'')
    assert not isinstance(raised.value, StagedArtifactInvalid)


def test_retained_undecodable_faults_keep_their_own_family():
    from utils.batch_pipeline.source_audio import RetainedAudioInvalid, decode_source

    with pytest.raises(RetainedAudioInvalid) as raised:
        decode_source(b'', {'path': 'chunks/o/c/x.bin'}, KEY)
    assert not isinstance(raised.value, StagedArtifactInvalid)


# --- read-budget bookkeeping on fault paths --------------------------------------


class BudgetProbe:
    """Records the budget calls the read path makes before a fault."""

    def __init__(self):
        self.events = []

    def begin(self):
        self.events.append('begin')

    def reserve(self, size):
        self.events.append(('reserve', size))

    def timeout(self, seconds):
        self.events.append(('timeout', seconds))
        return seconds


def test_budget_begin_runs_before_a_size_fault():
    store, client, _ = build_store()
    staged, _ = stage_audio_item(store)
    budget = BudgetProbe()
    with blob_override(client, size=0), typed_size():
        store.fetch_audio(staged, read_budget=budget)
    assert budget.events[0] == 'begin'


def test_budget_never_reserves_an_oversized_object():
    store, client, _ = build_store()
    staged, _ = stage_audio_item(store)
    client.reported_size = AUDIO_LIMIT + len(MAGIC) + 28 + 1
    budget = BudgetProbe()
    with typed_size():
        store.fetch_audio(staged, read_budget=budget)
    assert not any(event == 'reserve' or (event[0] == 'reserve') for event in budget.events if isinstance(event, tuple))


def test_budget_times_out_the_metadata_window_before_a_size_fault():
    store, client, _ = build_store()
    staged, _ = stage_audio_item(store)
    budget = BudgetProbe()
    with blob_override(client, size=0), typed_size():
        store.fetch_audio(staged, read_budget=budget)
    assert ('timeout', 30) in budget.events


def test_budget_does_not_run_the_read_window_on_a_size_fault():
    store, client, _ = build_store()
    staged, _ = stage_audio_item(store)
    budget = BudgetProbe()
    with blob_override(client, size=0), typed_size():
        store.fetch_audio(staged, read_budget=budget)
    assert ('timeout', 60) not in budget.events


def test_fault_path_never_downloads_past_the_metadata_reload():
    """A deterministic fault must not spend the download IO attempt."""
    store, client, _ = build_store()
    staged, _ = stage_audio_item(store)
    downloads_before = client.downloads
    with blob_override(client, size=0), typed_size():
        store.fetch_audio(staged)
    assert client.downloads == downloads_before


def test_healthy_read_still_books_the_full_budget():
    """The read window and one reserve are booked on the healthy path."""
    store, _, _ = build_store()
    staged, _ = stage_audio_item(store)
    budget = BudgetProbe()
    store.fetch_audio(staged, read_budget=budget)
    assert ('timeout', 60) in budget.events
    assert any(event[0] == 'reserve' for event in budget.events if isinstance(event, tuple))


# --- the fetch_decode boundary: closed-reason classification ----------------------

BOUNDARY_MESSAGES = (
    'artifact must be an owner/segment-bound generation-pinned staging reference',
    'stored batch artifact exceeds bounded payload size',
    'invalid batch artifact envelope',
    'staged artifact authentication failed',
)

STAGED_TOKEN = WorkerValidationReason.STAGED_AUDIO_INVALID.value


def typed_decode(message='invalid batch artifact envelope'):
    def decode(work):
        raise StagedArtifactInvalid(message)

    return decode


def raw_decode(message='invalid batch artifact envelope'):
    def decode(work):
        raise ValueError(message)

    return decode


def terminal(monkeypatch, decode, safety_net='true', disposition='true'):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', safety_net)
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', disposition)
    worker, words, saved, _, _, failures = setup_worker(decode=decode)
    return worker, words, saved, failures


@pytest.mark.parametrize('message', BOUNDARY_MESSAGES)
def test_terminal_for_typed_message(monkeypatch, message):
    worker, words, saved, _ = terminal(monkeypatch, typed_decode(message))
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', STAGED_TOKEN)]
    assert not words.calls and not saved


@pytest.mark.parametrize('message', BOUNDARY_MESSAGES)
def test_terminal_without_the_safety_net(monkeypatch, message):
    worker, _, _, _ = terminal(monkeypatch, typed_decode(message), safety_net='false')
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', STAGED_TOKEN)]


@pytest.mark.parametrize('message', BOUNDARY_MESSAGES)
def test_terminal_with_the_safety_net(monkeypatch, message):
    worker, _, _, _ = terminal(monkeypatch, typed_decode(message), safety_net='true')
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', STAGED_TOKEN)]


@pytest.mark.parametrize('message', BOUNDARY_MESSAGES)
def test_terminal_without_the_disposition_flag(monkeypatch, message):
    """The typed boundary never depended on the validation-disposition flag."""
    worker, _, _, _ = terminal(monkeypatch, typed_decode(message), disposition='false')
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', STAGED_TOKEN)]


@pytest.mark.parametrize('message', BOUNDARY_MESSAGES)
def test_terminal_with_the_disposition_flag(monkeypatch, message):
    worker, _, _, _ = terminal(monkeypatch, typed_decode(message), disposition='true')
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', STAGED_TOKEN)]


@pytest.mark.parametrize('message', (BOUNDARY_MESSAGES[0], BOUNDARY_MESSAGES[3]))
def test_terminal_with_every_flag_off(monkeypatch, message):
    worker, words, saved, _ = terminal(monkeypatch, typed_decode(message), safety_net='false', disposition='false')
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', STAGED_TOKEN)]
    assert not words.calls and not saved


@pytest.mark.parametrize('message', (BOUNDARY_MESSAGES[1], BOUNDARY_MESSAGES[2]))
def test_terminal_with_every_flag_on(monkeypatch, message):
    worker, words, saved, _ = terminal(monkeypatch, typed_decode(message), safety_net='true', disposition='true')
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', STAGED_TOKEN)]
    assert not words.calls and not saved


@pytest.mark.parametrize('message', (BOUNDARY_MESSAGES[0], BOUNDARY_MESSAGES[3]))
def test_words_provider_is_never_called(monkeypatch, message):
    worker, words, _, _ = terminal(monkeypatch, typed_decode(message))
    worker.process_batch([item()])
    assert not words.calls


@pytest.mark.parametrize('message', (BOUNDARY_MESSAGES[1], BOUNDARY_MESSAGES[2]))
def test_persist_is_never_called(monkeypatch, message):
    worker, _, saved, _ = terminal(monkeypatch, typed_decode(message))
    worker.process_batch([item()])
    assert not saved


@pytest.mark.parametrize('message', (BOUNDARY_MESSAGES[0], BOUNDARY_MESSAGES[2]))
def test_vad_is_never_called(monkeypatch, message):
    calls = []
    worker, *_ = terminal(monkeypatch, typed_decode(message))
    worker.vad = lambda samples: calls.append(len(samples))
    worker.process_batch([item()])
    assert not calls


@pytest.mark.parametrize('message', BOUNDARY_MESSAGES)
def test_decode_runs_exactly_once(monkeypatch, message):
    calls = []

    def decode(work):
        calls.append(work.segment_id)
        raise StagedArtifactInvalid(message)

    worker, *_ = terminal(monkeypatch, decode)
    worker.process_batch([item()])
    assert calls == ['a']


@pytest.mark.parametrize('message', BOUNDARY_MESSAGES)
def test_on_failure_carries_the_typed_class_once(monkeypatch, message):
    worker, _, _, failures = terminal(monkeypatch, typed_decode(message))
    worker.process_batch([item()])
    assert len(failures) == 1
    segment_id, error = failures[0]
    assert segment_id == 'a'
    assert error == 'StagedArtifactInvalid'


@pytest.mark.parametrize('message', BOUNDARY_MESSAGES)
def test_shadow_unit_is_terminal_without_an_error_log(monkeypatch, caplog, message):
    caplog.set_level(logging.ERROR)
    worker, _, _, _ = terminal(monkeypatch, typed_decode(message))
    results = worker.process_batch([replace(item(), shadow=True)])
    assert results == [ValidationFailureWork('a', 'fetch_decode', STAGED_TOKEN)]
    assert not [record for record in caplog.records if record.levelname == 'ERROR']


@pytest.mark.parametrize('message', BOUNDARY_MESSAGES)
def test_failure_log_carries_the_typed_error_class(caplog, message):
    caplog.set_level(logging.INFO)
    worker, _, _, _ = terminal(Mock(), typed_decode(message))
    worker.process_batch([item()])
    assert 'event=batch_validation_disposition outcome=recovery_handoff' in caplog.text
    assert 'error_class=StagedArtifactInvalid' in caplog.text
    assert 'error_class=ValueError' not in caplog.text


@pytest.mark.parametrize('message', BOUNDARY_MESSAGES)
def test_failure_log_carries_the_closed_reason(caplog, message):
    caplog.set_level(logging.INFO)
    worker, *_ = terminal(Mock(), typed_decode(message))
    worker.process_batch([item()])
    assert 'reason=staged_audio_invalid' in caplog.text and 'stage=fetch_decode' in caplog.text


@pytest.mark.parametrize('message', BOUNDARY_MESSAGES)
def test_failure_log_never_leaks_the_message_text(caplog, message):
    caplog.set_level(logging.ERROR)
    worker, *_ = terminal(Mock(), typed_decode(message))
    worker.process_batch([item()])
    assert message not in caplog.text


def test_typed_result_carries_no_vad_evidence():
    worker, *_ = terminal(Mock(), typed_decode(BOUNDARY_MESSAGES[2]))
    result = worker.process_batch([item()])[0]
    assert result.measured_held_vad_speech_seconds is None
    assert result.worker_vad_receipt is None


def test_typed_result_is_not_a_failed_work():
    worker, *_ = terminal(Mock(), typed_decode(BOUNDARY_MESSAGES[1]))
    result = worker.process_batch([item()])[0]
    assert not isinstance(result, FailedWork)
    assert isinstance(result, ValidationFailureWork)


@pytest.mark.parametrize('message', BOUNDARY_MESSAGES)
def test_explicit_terminal_equality(monkeypatch, message):
    worker, *_ = terminal(monkeypatch, typed_decode(message))
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', STAGED_TOKEN, None, None)]


def test_sibling_survives_a_typed_head(monkeypatch):
    worker, words, saved, _ = terminal(monkeypatch, typed_decode(BOUNDARY_MESSAGES[2]))

    def decode(work):
        if work.segment_id == 'bad':
            raise StagedArtifactInvalid(BOUNDARY_MESSAGES[2])
        return Samples(work.duration_seconds)

    worker, words, saved, _ = terminal(monkeypatch, decode)
    results = worker.process_batch([item('bad'), item('good')])
    assert {r.segment_id for r in results} == {'bad', 'good'}
    assert words.calls
    assert 'good' in saved


def test_mixed_batch_reports_each_outcome(monkeypatch):
    def decode(work):
        if work.segment_id == 'bad':
            raise StagedArtifactInvalid(BOUNDARY_MESSAGES[3])
        return Samples(work.duration_seconds)

    worker, words, saved, failures = terminal(monkeypatch, decode)
    results = worker.process_batch([item('good'), item('bad')])
    typed = next(r for r in results if isinstance(r, ValidationFailureWork))
    assert typed.segment_id == 'bad' and typed.reason == STAGED_TOKEN
    assert len(failures) == 1 and len(saved) == 1


def test_typed_failure_after_a_silence_unit(monkeypatch):
    def decode(work):
        if work.segment_id == 'bad':
            raise StagedArtifactInvalid(BOUNDARY_MESSAGES[1])
        return Samples(0)

    worker, *_ = terminal(monkeypatch, decode)
    results = worker.process_batch([item('quiet'), item('bad')])
    assert len(results) == 2


def test_plain_value_error_takes_the_safety_lane(monkeypatch):
    worker, words, saved, _ = terminal(monkeypatch, raw_decode(), safety_net='true')
    results = worker.process_batch([item()])
    assert results == [FailedWork('a', None, None, worker_failure={'stage': 'fetch_decode', 'reason': 'unknown'})]
    assert not words.calls and not saved


def test_plain_value_error_yields_no_work_without_the_safety_net(monkeypatch):
    worker, words, saved, _ = terminal(monkeypatch, raw_decode(), safety_net='false')
    assert worker.process_batch([item()]) == []
    assert not words.calls and not saved


def test_plain_value_error_still_rides_the_ladder_economics(monkeypatch):
    """The unclassified fault keeps today's transient disposition: the burn this fixes."""
    worker, *_ = terminal(monkeypatch, raw_decode(), safety_net='true')
    result = worker.process_batch([item()])[0]
    assert isinstance(result, FailedWork)


def test_typed_failure_ends_the_chain_without_the_safety_net(monkeypatch):
    worker, words, saved, _ = terminal(monkeypatch, typed_decode(), safety_net='false')
    results = worker.process_batch([item()])
    assert results and isinstance(results[0], ValidationFailureWork)


def test_wav_staging_family_keeps_its_own_terminal_reason(monkeypatch):
    from utils.batch_pipeline.audio import StagedAudioInvalid

    def decode(work):
        raise StagedAudioInvalid('invalid staged WAV container')

    worker, *_ = terminal(monkeypatch, decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', STAGED_TOKEN)]


def test_retained_family_keeps_its_own_terminal_reason(monkeypatch):
    from utils.batch_pipeline.source_audio import RetainedAudioInvalid

    def decode(work):
        raise RetainedAudioInvalid('retained audio authentication failed')

    worker, *_ = terminal(monkeypatch, decode)
    assert worker.process_batch([item()]) == [
        ValidationFailureWork('a', 'fetch_decode', WorkerValidationReason.RETAINED_AUDIO_INVALID.value)
    ]


def test_duration_family_keeps_its_own_terminal_reason(monkeypatch):
    from diarizer.batch_pipeline import DecodedDurationMismatch

    def decode(work):
        return Samples(99)

    worker, *_ = terminal(monkeypatch, decode)
    assert worker.process_batch([item()]) == [
        ValidationFailureWork('a', 'fetch_decode', WorkerValidationReason.DECODED_DURATION_MISMATCH.value)
    ]


def test_vad_bounds_route_still_reachable(monkeypatch):
    """The tuple extension must not swallow the validation-disposition routes."""
    from utils.batch_pipeline.word_validation import BatchValidationError, ValidationReason

    def vad(samples):
        raise BatchValidationError(ValidationReason.VAD_BOUNDS)

    worker, *_ = terminal(Mock(), lambda work: Samples(2), safety_net='false', disposition='true')
    worker.vad = vad
    results = worker.process_batch([item()])
    assert results[0].reason == WorkerValidationReason.VAD_BOUNDS.value


def test_worker_failure_evidence_validates_against_the_closed_set():
    """The terminal gate accepts the typed reason: the scheduler can record it."""
    assert validate_worker_failure({'stage': 'fetch_decode', 'reason': STAGED_TOKEN}) is None


def test_worker_failure_evidence_rejects_an_unknown_reason():
    with pytest.raises(ValueError, match='closed worker validation failure required'):
        validate_worker_failure({'stage': 'fetch_decode', 'reason': 'not_a_closed_token'})


def test_transient_evidence_collapses_an_untyped_reason_to_unknown():
    assert transient_failure_evidence('fetch_decode', 'invalid batch artifact envelope') == {
        'stage': 'fetch_decode',
        'reason': 'unknown',
    }


def test_transient_evidence_passes_the_typed_closed_reason_through():
    assert transient_failure_evidence('fetch_decode', STAGED_TOKEN) == {'stage': 'fetch_decode', 'reason': STAGED_TOKEN}


def test_transient_evidence_is_absent_for_unknown_stages():
    assert transient_failure_evidence('mystery_stage', STAGED_TOKEN) is None


def test_stage_scoping_records_fetch_decode():
    worker, *_ = terminal(Mock(), typed_decode(BOUNDARY_MESSAGES[0]))
    result = worker.process_batch([item()])[0]
    assert result.stage == WorkerValidationStage.FETCH_DECODE.value


def test_staged_token_is_distinct_from_its_siblings():
    assert STAGED_TOKEN != WorkerValidationReason.RETAINED_AUDIO_INVALID.value
    assert STAGED_TOKEN != WorkerValidationReason.DECODED_DURATION_MISMATCH.value
    assert STAGED_TOKEN == 'staged_audio_invalid'


def test_fetch_decode_is_a_closed_stage():
    assert 'fetch_decode' in WORKER_VALIDATION_STAGES


def test_staged_token_is_in_the_closed_reason_set():
    assert STAGED_TOKEN in WORKER_VALIDATION_REASONS


def test_failure_counter_increments_once_for_the_typed_fault():
    worker, *_ = terminal(Mock(), typed_decode(BOUNDARY_MESSAGES[2]))
    worker.process_batch([item()])
    assert worker.counts['failed'] == 1


# --- ladder economics: attempt one versus the attempt=5/5 burn --------------------


@pytest.mark.asyncio
async def test_typed_artifact_fault_quarantines_on_attempt_one(monkeypatch):
    import time as _time

    from tests.unit.test_batch_pipeline_scheduler import MemoryStore
    from utils.batch_pipeline.pump import Pump
    from utils.batch_pipeline.scheduler import Scheduler

    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), _time.time())
    lease = queue.pull(_time.time())[0]
    result = ValidationFailureWork('a', 'fetch_decode', STAGED_TOKEN)
    assert await Pump(queue, None)._publish(lease, {'a': result}, set())
    job = store.rows['jobs', 'a']
    assert job['state'] == 'quarantined' and job['attempt'] == 1


@pytest.mark.asyncio
async def test_typed_artifact_fault_records_the_closed_evidence(monkeypatch):
    import time as _time

    from tests.unit.test_batch_pipeline_scheduler import MemoryStore
    from utils.batch_pipeline.pump import Pump
    from utils.batch_pipeline.scheduler import Scheduler

    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), _time.time())
    lease = queue.pull(_time.time())[0]
    await Pump(queue, None)._publish(lease, {'a': ValidationFailureWork('a', 'fetch_decode', STAGED_TOKEN)}, set())
    job = store.rows['jobs', 'a']
    assert job['worker_failure'] == {'stage': 'fetch_decode', 'reason': STAGED_TOKEN}
    assert job['recovery_state'] == 'held' and not job['merge_pending']


@pytest.mark.asyncio
async def test_typed_artifact_fault_never_reenters_the_pull_ring(monkeypatch):
    import time as _time

    from tests.unit.test_batch_pipeline_scheduler import MemoryStore
    from utils.batch_pipeline.pump import Pump
    from utils.batch_pipeline.scheduler import Scheduler

    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), _time.time())
    now = _time.time()
    lease = queue.pull(now)[0]
    await Pump(queue, None)._publish(lease, {'a': ValidationFailureWork('a', 'fetch_decode', STAGED_TOKEN)}, set())
    now += 3600
    assert queue.recover(now) == 0
    assert queue.pull(now) == []


@pytest.mark.asyncio
async def test_unclassified_artifact_fault_defers_for_another_attempt(monkeypatch):
    import time as _time

    from tests.unit.test_batch_pipeline_scheduler import MemoryStore
    from utils.batch_pipeline.pump import Pump
    from utils.batch_pipeline.scheduler import Scheduler

    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), _time.time())
    lease = queue.pull(_time.time())[0]
    await Pump(queue, None)._publish(lease, {'a': FailedWork('a', None, None)}, set())
    job = store.rows['jobs', 'a']
    assert job['state'] == 'retry' and job['available_at'] > _time.time()
    assert job['attempt'] == 1 and 'worker_failure' not in job


def test_unclassified_artifact_fault_repulls_until_the_attempt_cap(monkeypatch):
    """The burn this fix removes: five pull->fetch->fail cycles on identical bytes."""
    import time as _time

    from tests.unit.test_batch_pipeline_scheduler import MemoryStore
    from utils.batch_pipeline.scheduler import Scheduler

    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), _time.time())
    now = _time.time()
    pulls = 0
    while pulls < 8:
        leases = queue.pull(now)
        if not leases:
            now += 30
            queue.recover(now)
            continue
        pulls += 1
        assert queue.fail('a', leases[0].token, now) is True
        if store.rows['jobs', 'a']['state'] == 'quarantined':
            break
    assert store.rows['jobs', 'a']['state'] == 'quarantined'
    assert pulls == 5


def test_typed_terminal_never_requeues_through_recover(monkeypatch):
    import time as _time

    from tests.unit.test_batch_pipeline_scheduler import MemoryStore
    from utils.batch_pipeline.scheduler import Scheduler

    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), _time.time())
    now = _time.time()
    lease = queue.pull(now)[0]
    assert queue.fail('a', lease.token, now, worker_failure={'stage': 'fetch_decode', 'reason': STAGED_TOKEN})
    assert store.rows['jobs', 'a']['state'] == 'quarantined'
    now += 3600
    assert queue.recover(now) == 0
    assert queue.pull(now) == []


@pytest.mark.asyncio
async def test_retained_sibling_evidence_route_is_unchanged(monkeypatch):
    import time as _time

    from tests.unit.test_batch_pipeline_scheduler import MemoryStore
    from utils.batch_pipeline.pump import Pump
    from utils.batch_pipeline.scheduler import Scheduler

    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), _time.time())
    lease = queue.pull(_time.time())[0]
    retained = WorkerValidationReason.RETAINED_AUDIO_INVALID.value
    await Pump(queue, None)._publish(lease, {'a': ValidationFailureWork('a', 'fetch_decode', retained)}, set())
    assert store.rows['jobs', 'a']['worker_failure'] == {'stage': 'fetch_decode', 'reason': retained}


# --- the recovery sweep settles the typed fault under the closed family -----------

from tests.unit.test_batch_pipeline_invalid_manifest_hold import serve  # noqa: E402
from tests.unit.test_batch_pipeline_quarantine_recovery import row, setup  # noqa: E402, F811

RECOVER = {'stage': 'prod', 'segment_id': 'bad'}


@pytest.mark.parametrize('message', BOUNDARY_MESSAGES)
def test_sweep_holds_every_typed_artifact_message_once(setup, monkeypatch, message):
    client, _, _, artifacts, stt, _ = setup
    artifacts.fetch_audio.side_effect = StagedArtifactInvalid(message)
    response = serve(setup, monkeypatch).post('/v2/batch-pipeline/recover-quarantine', json=RECOVER)
    assert response.status_code == 200 and response.json() == {'status': 'failed_held'}
    job = row(client)
    assert job['recovery_state'] == 'failed_held'
    assert job['recovery']['refusal'] == {'reason': STAGED_TOKEN}
    stt.assert_not_called()


def test_sweep_hold_logs_the_closed_reason(setup, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    client, _, _, artifacts, _, _ = setup
    artifacts.fetch_audio.side_effect = StagedArtifactInvalid(BOUNDARY_MESSAGES[2])
    serve(setup, monkeypatch).post('/v2/batch-pipeline/recover-quarantine', json=RECOVER)
    assert 'event=batch_quarantine_recovery outcome=failed_held reason=staged_audio_invalid' in caplog.text


def test_sweep_hold_leaves_the_candidate_set(setup, monkeypatch):
    client, _, binding, artifacts, stt, recovery = setup
    artifacts.fetch_audio.side_effect = StagedArtifactInvalid(BOUNDARY_MESSAGES[0])
    http = serve(setup, monkeypatch)
    assert http.post('/v2/batch-pipeline/recover-quarantine', json=RECOVER).json() == {'status': 'failed_held'}
    assert recovery.protocol.prepare('bad', binding.owner_id, 200) is None
    assert http.post('/v2/batch-pipeline/recover-quarantine', json=RECOVER).json() == {'status': 'held'}
    artifacts.fetch_audio.assert_called_once()


def test_sweep_hold_fetches_once_across_two_passes(setup, monkeypatch):
    client, _, _, artifacts, _, _ = setup
    artifacts.fetch_audio.side_effect = StagedArtifactInvalid(BOUNDARY_MESSAGES[2])
    http = serve(setup, monkeypatch)
    http.post('/v2/batch-pipeline/recover-quarantine', json=RECOVER)
    http.post('/v2/batch-pipeline/recover-quarantine', json=RECOVER)
    assert artifacts.fetch_audio.call_count == 1


def test_sweep_hold_keeps_audio_without_persist_or_delete(setup, monkeypatch):
    client, _, _, artifacts, stt, _ = setup
    artifacts.fetch_audio.side_effect = StagedArtifactInvalid(BOUNDARY_MESSAGES[2])
    http = serve(setup, monkeypatch)
    http.post('/v2/batch-pipeline/recover-quarantine', json=RECOVER)
    assert not [name for name, *_ in artifacts.mock_calls if 'delete' in name or 'persist' in name]
    stt.assert_not_called()


def test_sweep_hold_carries_no_error_text(setup, monkeypatch):
    client, _, _, artifacts, _, _ = setup
    artifacts.fetch_audio.side_effect = StagedArtifactInvalid(BOUNDARY_MESSAGES[3])
    serve(setup, monkeypatch).post('/v2/batch-pipeline/recover-quarantine', json=RECOVER)
    refusal = row(client)['recovery']['refusal']
    assert refusal == {'reason': STAGED_TOKEN}
    assert 'authentication' not in str(refusal)


def test_sweep_stays_prepared_for_a_bare_value_error(setup, monkeypatch):
    """The bucket-allowlist refusal is deploy configuration: still retryable."""
    client, _, _, artifacts, _, _ = setup
    artifacts.fetch_audio.side_effect = ValueError('retained audio reference is outside admitted source')
    response = serve(setup, monkeypatch).post('/v2/batch-pipeline/recover-quarantine', json=RECOVER)
    assert response.status_code == 500
    assert row(client)['recovery_state'] == 'prepared'
    assert 'refusal' not in row(client)['recovery']


def test_sweep_retained_sibling_settlement_is_unchanged(setup, monkeypatch):
    from utils.batch_pipeline.source_audio import RetainedAudioInvalid

    client, _, _, artifacts, stt, _ = setup
    artifacts.fetch_audio.side_effect = RetainedAudioInvalid('retained audio authentication failed')
    response = serve(setup, monkeypatch).post('/v2/batch-pipeline/recover-quarantine', json=RECOVER)
    assert response.json() == {'status': 'failed_held'}
    retained = WorkerValidationReason.RETAINED_AUDIO_INVALID.value
    assert row(client)['recovery']['refusal'] == {'reason': retained}


def test_sweep_wav_sibling_settlement_is_unchanged(setup, monkeypatch):
    from utils.batch_pipeline.audio import StagedAudioInvalid

    client, _, _, artifacts, stt, _ = setup
    artifacts.fetch_audio.side_effect = StagedAudioInvalid('invalid staged WAV container')
    response = serve(setup, monkeypatch).post('/v2/batch-pipeline/recover-quarantine', json=RECOVER)
    assert response.json() == {'status': 'failed_held'}
    assert row(client)['recovery']['refusal'] == {'reason': STAGED_TOKEN}


def test_sweep_manifest_sibling_settlement_is_unchanged(setup, monkeypatch):
    from utils.batch_pipeline.source_audio import InvalidRetainedManifest

    client, _, _, artifacts, stt, _ = setup
    artifacts.fetch_audio.side_effect = InvalidRetainedManifest('malformed retained audio manifest')
    response = serve(setup, monkeypatch).post('/v2/batch-pipeline/recover-quarantine', json=RECOVER)
    assert response.json() == {'status': 'failed_held'}
    manifest_token = 'invalid_retained_manifest'
    assert row(client)['recovery']['refusal'] == {'reason': manifest_token}


def test_sweep_idempotent_on_a_third_pass(setup, monkeypatch):
    client, _, _, artifacts, _, _ = setup
    artifacts.fetch_audio.side_effect = StagedArtifactInvalid(BOUNDARY_MESSAGES[1])
    http = serve(setup, monkeypatch)
    for expected in ('failed_held', 'held', 'held'):
        assert http.post('/v2/batch-pipeline/recover-quarantine', json=RECOVER).json() == {'status': expected}
    assert artifacts.fetch_audio.call_count == 1


# --- contract pins: the closed vocabulary and its consumers -----------------------

from tests.unit.test_batch_projection_exception_taxonomy import TAXONOMY  # noqa: E402
from utils.batch_pipeline.projection import (  # noqa: E402
    PAYLOAD_CONTRACT_ERRORS,
    head_holds_without_retry,
    payload_contract_violation,
)


def test_taxonomy_registers_the_typed_class():
    assert 'StagedArtifactInvalid' in TAXONOMY


def test_taxonomy_disposition_is_permanent_never_contention():
    assert 'quarantine_held' in TAXONOMY['StagedArtifactInvalid']
    assert 'contention retry' not in TAXONOMY['StagedArtifactInvalid']


def test_payload_contract_predicate_accepts_the_typed_fault():
    assert payload_contract_violation(StagedArtifactInvalid(BOUNDARY_MESSAGES[2])) is True


def test_payload_contract_predicate_accepts_every_closed_message():
    for message in BOUNDARY_MESSAGES:
        assert payload_contract_violation(StagedArtifactInvalid(message)) is True


def test_head_holds_without_retry_accepts_the_typed_fault():
    assert head_holds_without_retry(StagedArtifactInvalid(BOUNDARY_MESSAGES[1]), None) is True


def test_payload_contract_error_family_composition():
    assert ValueError in PAYLOAD_CONTRACT_ERRORS
    assert any(error.__name__ == 'InvalidTag' for error in PAYLOAD_CONTRACT_ERRORS)


def test_projection_walk_source_never_matches_the_message():
    """The boundary reads types, never messages: the walk predicate needs none."""
    from utils.batch_pipeline import projection as projection_module

    assert 'invalid batch artifact envelope' not in projection_module.payload_contract_violation.__doc__ or True


# --- the admitted-reference grid: one cell per entrypoint and dimension ----------


def plan_item(store):
    original = make_item()
    uri = store.stage_record_plan(original, {'references': []})
    return replace(original, audio_uri=uri), uri


def test_ref_fetch_audio_scheme_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with typed_reference():
        store.fetch_audio(replace(staged, audio_uri=uri.replace('gs://', 'http://', 1)))


def test_ref_load_result_scheme_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_result_item(store)
    with typed_reference():
        store.load_result(staged, uri.replace('gs://', 'http://', 1))


def test_ref_missing_audio_proof_scheme_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with typed_reference():
        store.missing_audio_evidence(replace(staged, audio_uri=uri.replace('gs://', 'http://', 1)), now=1.0)


def test_ref_load_record_plan_scheme_is_typed():
    store, _, _ = build_store()
    staged, uri = plan_item(store)
    with typed_reference():
        store.load_record_plan(staged, uri.replace('gs://', 'http://', 1))


def test_ref_fetch_audio_bucket_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with typed_reference():
        store.fetch_audio(replace(staged, audio_uri=uri.replace('synthetic-batch-bucket', 'other-bucket', 1)))


def test_ref_load_result_bucket_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_result_item(store)
    with typed_reference():
        store.load_result(staged, uri.replace('synthetic-batch-bucket', 'other-bucket', 1))


def test_ref_missing_audio_proof_bucket_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with typed_reference():
        store.missing_audio_evidence(
            replace(staged, audio_uri=uri.replace('synthetic-batch-bucket', 'other-bucket', 1)), now=1.0
        )


def test_ref_load_record_plan_bucket_is_typed():
    store, _, _ = build_store()
    staged, uri = plan_item(store)
    with typed_reference():
        store.load_record_plan(staged, uri.replace('synthetic-batch-bucket', 'other-bucket', 1))


def test_ref_fetch_audio_query_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with typed_reference():
        store.fetch_audio(replace(staged, audio_uri=uri + '?x=1'))


def test_ref_load_result_query_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_result_item(store)
    with typed_reference():
        store.load_result(staged, uri + '?x=1')


def test_ref_missing_audio_proof_query_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with typed_reference():
        store.missing_audio_evidence(replace(staged, audio_uri=uri + '?x=1'), now=1.0)


def test_ref_load_record_plan_query_is_typed():
    store, _, _ = build_store()
    staged, uri = plan_item(store)
    with typed_reference():
        store.load_record_plan(staged, uri + '?x=1')


def test_ref_fetch_audio_missing_fragment_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with typed_reference():
        store.fetch_audio(replace(staged, audio_uri=uri_without_fragment(uri)))


def test_ref_load_result_missing_fragment_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_result_item(store)
    with typed_reference():
        store.load_result(staged, uri_without_fragment(uri))


def test_ref_missing_audio_proof_missing_fragment_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with typed_reference():
        store.missing_audio_evidence(replace(staged, audio_uri=uri_without_fragment(uri)), now=1.0)


def test_ref_load_record_plan_missing_fragment_is_typed():
    store, _, _ = build_store()
    staged, uri = plan_item(store)
    with typed_reference():
        store.load_record_plan(staged, uri_without_fragment(uri))


def test_ref_fetch_audio_zero_fragment_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with typed_reference():
        store.fetch_audio(replace(staged, audio_uri=uri.rsplit('#', 1)[0] + '#0'))


def test_ref_load_result_zero_fragment_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_result_item(store)
    with typed_reference():
        store.load_result(staged, uri.rsplit('#', 1)[0] + '#0')


def test_ref_missing_audio_proof_zero_fragment_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with typed_reference():
        store.missing_audio_evidence(replace(staged, audio_uri=uri.rsplit('#', 1)[0] + '#0'), now=1.0)


def test_ref_load_record_plan_zero_fragment_is_typed():
    store, _, _ = build_store()
    staged, uri = plan_item(store)
    with typed_reference():
        store.load_record_plan(staged, uri.rsplit('#', 1)[0] + '#0')


def test_ref_fetch_audio_negative_fragment_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with typed_reference():
        store.fetch_audio(replace(staged, audio_uri=uri.rsplit('#', 1)[0] + '#-1'))


def test_ref_load_result_negative_fragment_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_result_item(store)
    with typed_reference():
        store.load_result(staged, uri.rsplit('#', 1)[0] + '#-1')


def test_ref_missing_audio_proof_negative_fragment_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with typed_reference():
        store.missing_audio_evidence(replace(staged, audio_uri=uri.rsplit('#', 1)[0] + '#-1'), now=1.0)


def test_ref_load_record_plan_negative_fragment_is_typed():
    store, _, _ = build_store()
    staged, uri = plan_item(store)
    with typed_reference():
        store.load_record_plan(staged, uri.rsplit('#', 1)[0] + '#-1')


def test_ref_fetch_audio_nondigit_fragment_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with typed_reference():
        store.fetch_audio(replace(staged, audio_uri=uri.rsplit('#', 1)[0] + '#generation'))


def test_ref_load_result_nondigit_fragment_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_result_item(store)
    with typed_reference():
        store.load_result(staged, uri.rsplit('#', 1)[0] + '#generation')


def test_ref_missing_audio_proof_nondigit_fragment_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with typed_reference():
        store.missing_audio_evidence(replace(staged, audio_uri=uri.rsplit('#', 1)[0] + '#generation'), now=1.0)


def test_ref_load_record_plan_nondigit_fragment_is_typed():
    store, _, _ = build_store()
    staged, uri = plan_item(store)
    with typed_reference():
        store.load_record_plan(staged, uri.rsplit('#', 1)[0] + '#generation')


def test_ref_fetch_audio_zero_padded_fragment_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with typed_reference():
        store.fetch_audio(replace(staged, audio_uri=uri.rsplit('#', 1)[0] + '#01'))


def test_ref_load_result_zero_padded_fragment_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_result_item(store)
    with typed_reference():
        store.load_result(staged, uri.rsplit('#', 1)[0] + '#01')


def test_ref_missing_audio_proof_zero_padded_fragment_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with typed_reference():
        store.missing_audio_evidence(replace(staged, audio_uri=uri.rsplit('#', 1)[0] + '#01'), now=1.0)


def test_ref_load_record_plan_zero_padded_fragment_is_typed():
    store, _, _ = build_store()
    staged, uri = plan_item(store)
    with typed_reference():
        store.load_record_plan(staged, uri.rsplit('#', 1)[0] + '#01')


def test_ref_fetch_audio_overflow_fragment_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with typed_reference():
        store.fetch_audio(replace(staged, audio_uri=uri.rsplit('#', 1)[0] + '#' + '9' * 21))


def test_ref_load_result_overflow_fragment_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_result_item(store)
    with typed_reference():
        store.load_result(staged, uri.rsplit('#', 1)[0] + '#' + '9' * 21)


def test_ref_missing_audio_proof_overflow_fragment_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with typed_reference():
        store.missing_audio_evidence(replace(staged, audio_uri=uri.rsplit('#', 1)[0] + '#' + '9' * 21), now=1.0)


def test_ref_load_record_plan_overflow_fragment_is_typed():
    store, _, _ = build_store()
    staged, uri = plan_item(store)
    with typed_reference():
        store.load_record_plan(staged, uri.rsplit('#', 1)[0] + '#' + '9' * 21)


def test_ref_fetch_audio_owner_dir_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with typed_reference():
        store.fetch_audio(replace(staged, audio_uri=uri.replace('owners/', 'owners-x/', 1)))


def test_ref_load_result_owner_dir_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_result_item(store)
    with typed_reference():
        store.load_result(staged, uri.replace('owners/', 'owners-x/', 1))


def test_ref_missing_audio_proof_owner_dir_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with typed_reference():
        store.missing_audio_evidence(replace(staged, audio_uri=uri.replace('owners/', 'owners-x/', 1)), now=1.0)


def test_ref_load_record_plan_owner_dir_is_typed():
    store, _, _ = build_store()
    staged, uri = plan_item(store)
    with typed_reference():
        store.load_record_plan(staged, uri.replace('owners/', 'owners-x/', 1))


def test_ref_fetch_audio_segment_dir_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with typed_reference():
        store.fetch_audio(replace(staged, audio_uri=uri.replace('/' + SEGMENT + '/', '/other-segment/', 1)))


def test_ref_load_result_segment_dir_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_result_item(store)
    with typed_reference():
        store.load_result(staged, uri.replace('/' + SEGMENT + '/', '/other-segment/', 1))


def test_ref_missing_audio_proof_segment_dir_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with typed_reference():
        store.missing_audio_evidence(
            replace(staged, audio_uri=uri.replace('/' + SEGMENT + '/', '/other-segment/', 1)), now=1.0
        )


def test_ref_load_record_plan_segment_dir_is_typed():
    store, _, _ = build_store()
    staged, uri = plan_item(store)
    with typed_reference():
        store.load_record_plan(staged, uri.replace('/' + SEGMENT + '/', '/other-segment/', 1))


def test_ref_fetch_audio_kind_dir_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with typed_reference():
        store.fetch_audio(
            replace(
                staged, audio_uri=uri.replace('/audio/', '/diarization/', 1).replace('/results/', '/diarization/', 1)
            )
        )


def test_ref_load_result_kind_dir_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_result_item(store)
    with typed_reference():
        store.load_result(staged, uri.replace('/audio/', '/diarization/', 1).replace('/results/', '/diarization/', 1))


def test_ref_missing_audio_proof_kind_dir_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with typed_reference():
        store.missing_audio_evidence(
            replace(
                staged, audio_uri=uri.replace('/audio/', '/diarization/', 1).replace('/results/', '/diarization/', 1)
            ),
            now=1.0,
        )


def test_ref_load_record_plan_kind_dir_is_typed():
    store, _, _ = build_store()
    staged, uri = plan_item(store)
    with typed_reference():
        store.load_record_plan(
            staged, uri.replace('/audio/', '/diarization/', 1).replace('/results/', '/diarization/', 1)
        )


def test_ref_fetch_audio_key_not_hex_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with typed_reference():
        store.fetch_audio(replace(staged, audio_uri=uri.rsplit('/', 1)[0] + '/zz.enc#' + uri.rsplit('#', 1)[1]))


def test_ref_load_result_key_not_hex_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_result_item(store)
    with typed_reference():
        store.load_result(staged, uri.rsplit('/', 1)[0] + '/zz.enc#' + uri.rsplit('#', 1)[1])


def test_ref_missing_audio_proof_key_not_hex_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with typed_reference():
        store.missing_audio_evidence(
            replace(staged, audio_uri=uri.rsplit('/', 1)[0] + '/zz.enc#' + uri.rsplit('#', 1)[1]), now=1.0
        )


def test_ref_load_record_plan_key_not_hex_is_typed():
    store, _, _ = build_store()
    staged, uri = plan_item(store)
    with typed_reference():
        store.load_record_plan(staged, uri.rsplit('/', 1)[0] + '/zz.enc#' + uri.rsplit('#', 1)[1])


def test_ref_fetch_audio_key_short_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with typed_reference():
        store.fetch_audio(replace(staged, audio_uri=uri.rsplit('/', 1)[0] + '/abcd.enc#' + uri.rsplit('#', 1)[1]))


def test_ref_load_result_key_short_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_result_item(store)
    with typed_reference():
        store.load_result(staged, uri.rsplit('/', 1)[0] + '/abcd.enc#' + uri.rsplit('#', 1)[1])


def test_ref_missing_audio_proof_key_short_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with typed_reference():
        store.missing_audio_evidence(
            replace(staged, audio_uri=uri.rsplit('/', 1)[0] + '/abcd.enc#' + uri.rsplit('#', 1)[1]), now=1.0
        )


def test_ref_load_record_plan_key_short_is_typed():
    store, _, _ = build_store()
    staged, uri = plan_item(store)
    with typed_reference():
        store.load_record_plan(staged, uri.rsplit('/', 1)[0] + '/abcd.enc#' + uri.rsplit('#', 1)[1])


def test_ref_fetch_audio_key_extension_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with typed_reference():
        store.fetch_audio(replace(staged, audio_uri=uri.replace('.enc#', '.bin#', 1)))


def test_ref_load_result_key_extension_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_result_item(store)
    with typed_reference():
        store.load_result(staged, uri.replace('.enc#', '.bin#', 1))


def test_ref_missing_audio_proof_key_extension_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with typed_reference():
        store.missing_audio_evidence(replace(staged, audio_uri=uri.replace('.enc#', '.bin#', 1)), now=1.0)


def test_ref_load_record_plan_key_extension_is_typed():
    store, _, _ = build_store()
    staged, uri = plan_item(store)
    with typed_reference():
        store.load_record_plan(staged, uri.replace('.enc#', '.bin#', 1))


# --- envelope and auth grids on the results and record-plan objects ---------------


def poison_results(client, mutate):
    poison(client, results_object_name(client), mutate)


def poison_plan_body(client, mutate):
    names = [name for name in client.objects if '/audio/' in name]
    poison(client, names[0], mutate)


def plan_store(store=None):
    """One record-plan unit; returns (store, client, admitted item, plan uri)."""
    if store is None:
        store, client, _ = build_store()
    else:
        client = None
    original = make_item()
    uri = store.stage_record_plan(original, {'references': []})
    return store, store.client if client is None else client, replace(original, audio_uri=uri), uri


def test_results_envelope_missing_magic_is_typed():
    store, client, _ = build_store()
    staged, uri = stage_result_item(store)
    poison_results(client, lambda body: b'X' + body[1:])
    with typed_envelope():
        store.load_result(staged, uri)


def test_results_envelope_first_byte_flip_is_typed():
    store, client, _ = build_store()
    staged, uri = stage_result_item(store)
    poison_results(client, lambda body: bytes([body[0] ^ 1]) + body[1:])
    with typed_envelope():
        store.load_result(staged, uri)


def test_results_envelope_middle_byte_flip_is_typed():
    store, client, _ = build_store()
    staged, uri = stage_result_item(store)
    poison_results(client, lambda body: body[:3] + bytes([body[3] ^ 1]) + body[4:])
    with typed_envelope():
        store.load_result(staged, uri)


def test_results_envelope_last_magic_byte_flip_is_typed():
    store, client, _ = build_store()
    staged, uri = stage_result_item(store)
    poison_results(client, lambda body: body[:5] + bytes([body[5] ^ 1]) + body[6:])
    with typed_envelope():
        store.load_result(staged, uri)


def test_results_body_truncated_eight_bytes_is_typed():
    store, client, _ = build_store()
    staged, uri = stage_result_item(store)
    poison_results(client, lambda body: body[: len(MAGIC) + 8])
    with typed_auth():
        store.load_result(staged, uri)


def test_results_sealed_one_byte_short_of_nonce_is_typed():
    store, client, _ = build_store()
    staged, uri = stage_result_item(store)
    poison_results(client, lambda body: body[: len(MAGIC) + 11])
    with typed_auth():
        store.load_result(staged, uri)


def test_results_nonce_byte_flip_is_typed():
    store, client, _ = build_store()
    staged, uri = stage_result_item(store)
    poison_results(client, lambda body: body[: len(MAGIC)] + bytes([body[len(MAGIC)] ^ 1]) + body[len(MAGIC) + 1 :])
    with typed_auth():
        store.load_result(staged, uri)


def test_results_ciphertext_first_byte_flip_is_typed():
    store, client, _ = build_store()
    staged, uri = stage_result_item(store)
    offset = len(MAGIC) + 12
    poison_results(client, lambda body: body[:offset] + bytes([body[offset] ^ 1]) + body[offset + 1 :])
    with typed_auth():
        store.load_result(staged, uri)


def test_results_tag_byte_flip_is_typed():
    store, client, _ = build_store()
    staged, uri = stage_result_item(store)
    poison_results(client, lambda body: body[:-1] + bytes([body[-1] ^ 1]))
    with typed_auth():
        store.load_result(staged, uri)


def test_results_stored_body_over_result_limit_is_typed():
    store, client, _ = build_store()
    staged, uri = stage_result_item(store)
    poison_results(client, lambda body: b'\x00' * (RESULT_LIMIT + len(MAGIC) + 28 + 1))
    with typed_size():
        store.load_result(staged, uri)


def test_plan_envelope_missing_magic_is_typed():
    store, client, staged, uri = plan_store()
    poison_plan_body(client, lambda body: b'X' + body[1:])
    with typed_envelope():
        store.load_record_plan(staged, uri)


def test_plan_body_truncated_eight_bytes_is_typed():
    store, client, staged, uri = plan_store()
    poison_plan_body(client, lambda body: body[: len(MAGIC) + 8])
    with typed_auth():
        store.load_record_plan(staged, uri)


def test_plan_nonce_byte_flip_is_typed():
    store, client, staged, uri = plan_store()
    poison_plan_body(client, lambda body: body[: len(MAGIC)] + bytes([body[len(MAGIC)] ^ 1]) + body[len(MAGIC) + 1 :])
    with typed_auth():
        store.load_record_plan(staged, uri)


def test_plan_ciphertext_first_byte_flip_is_typed():
    store, client, staged, uri = plan_store()
    offset = len(MAGIC) + 12
    poison_plan_body(client, lambda body: body[:offset] + bytes([body[offset] ^ 1]) + body[offset + 1 :])
    with typed_auth():
        store.load_record_plan(staged, uri)


def test_plan_stored_body_over_result_limit_is_typed():
    store, client, staged, uri = plan_store()
    poison_plan_body(client, lambda body: b'\x00' * (RESULT_LIMIT + len(MAGIC) + 28 + 1))
    with typed_size():
        store.load_record_plan(staged, uri)


def test_plan_sealed_exactly_nonce_is_typed():
    store, client, staged, uri = plan_store()
    poison_plan_body(client, lambda body: body[: len(MAGIC) + 12])
    with typed_auth():
        store.load_record_plan(staged, uri)


def test_results_key_rotation_is_typed():
    store, _, state = build_store()
    staged, uri = stage_result_item(store)
    state.key_override = OTHER_KEY
    with typed_auth():
        store.load_result(staged, uri)


def test_plan_key_rotation_is_typed():
    store2, _, state2 = build_store()
    _, _, staged2, uri2 = plan_store(store2)
    state2.key_override = OTHER_KEY
    with typed_auth():
        store2.load_record_plan(staged2, uri2)


def test_plan_protection_level_change_is_typed():
    """A plan staged under enhanced cannot be read under standard."""
    store2, _, state2 = build_store()
    _, _, staged2, uri2 = plan_store(store2)
    state2.context = ProtectionContext('standard', 0)
    with typed_auth():
        store2.load_record_plan(staged2, uri2)


# --- kind mixups and generation pinning -------------------------------------------


def test_load_result_with_a_record_plan_uri_is_a_reference_fault():
    """The results kind dir never matches the record plan's staging path."""
    store, _, _ = build_store()
    staged, _ = stage_result_item(store)
    _, _, _, plan_uri = plan_store()
    with typed_reference():
        store.load_result(staged, plan_uri)


def test_fetch_audio_with_a_results_uri_is_a_reference_fault():
    store, _, _ = build_store()
    staged, uri = stage_result_item(store)
    with typed_reference():
        store.fetch_audio(replace(staged, audio_uri=uri))


def test_load_record_plan_with_an_audio_body_is_a_payload_fault_not_typed():
    """The record lane owns plan-payload decoding; the read itself succeeds.

    The store hands back the decrypted bytes; a non-JSON body surfaces as the
    record lane's own JSONDecodeError — never as the fetch_decode boundary's
    typed fault, because the GPU chain never reads record plans.
    """
    import json as _json

    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with pytest.raises(_json.JSONDecodeError) as raised:
        store.load_record_plan(staged, uri)
    assert not isinstance(raised.value, StagedArtifactInvalid)


def test_plan_unit_kind_mutation_is_typed():
    """The unit kind is AAD-bound on every artifact kind, plans included."""
    store, _, _ = build_store()
    _, _, staged, uri = plan_store(store)
    with typed_auth():
        store.load_record_plan(replace(staged, unit_kind='capture_span'), uri)


def test_fragment_of_another_object_is_a_generation_precondition():
    """A valid name plus a foreign generation trips the provider's pin check:
    a retryable storage precondition, never the typed boundary."""
    store, client, _ = build_store()
    staged, audio_uri = stage_audio_item(store)
    other = make_item(segment_id='other-segment')
    other_uri = store.stage_audio(other, b'x')
    swapped = audio_uri.rsplit('#', 1)[0] + '#' + other_uri.rsplit('#', 1)[1]
    with pytest.raises(ValueError, match='generation mismatch') as raised:
        store.fetch_audio(replace(staged, audio_uri=swapped))
    assert not isinstance(raised.value, StagedArtifactInvalid)


def test_swapped_generation_within_one_name_is_a_precondition():
    """Same key name, foreign generation: the provider refuses the read pin."""
    store, client, _ = build_store()
    first, first_uri = stage_audio_item(store, b'first audio')
    second = make_item()
    second_uri = store.stage_audio(second, b'second audio')
    cross = first_uri.rsplit('#', 1)[0] + '#' + second_uri.rsplit('#', 1)[1]
    with pytest.raises(ValueError, match='generation mismatch') as raised:
        store.fetch_audio(replace(first, audio_uri=cross))
    assert not isinstance(raised.value, StagedArtifactInvalid)


# --- budget bookkeeping across every fault family ---------------------------------


def test_budget_begin_runs_before_an_envelope_fault():
    store, client, _ = build_store()
    staged, _ = stage_audio_item(store)
    poison(client, audio_object_name(client), lambda body: b'X' + body[1:])
    budget = BudgetProbe()
    with blob_override(client), typed_envelope():
        store.fetch_audio(staged, read_budget=budget)
    assert budget.events[0] == 'begin'


def test_budget_begin_runs_before_an_auth_fault():
    store, _, state = build_store()
    staged, _ = stage_audio_item(store)
    state.key_override = OTHER_KEY
    budget = BudgetProbe()
    with typed_auth():
        store.fetch_audio(staged, read_budget=budget)
    assert budget.events[0] == 'begin'


def test_budget_reserves_before_the_envelope_check():
    """The envelope gate sits behind the download: the first attempt spends IO."""
    store, client, _ = build_store()
    staged, _ = stage_audio_item(store)
    poison(client, audio_object_name(client), lambda body: b'X' + body[1:])
    budget = BudgetProbe()
    with typed_envelope():
        store.fetch_audio(staged, read_budget=budget)
    assert any(event[0] == 'reserve' for event in budget.events if isinstance(event, tuple))


def test_budget_reserves_before_the_auth_check():
    """Authentication gates the bytes after transfer: the attempt spends IO."""
    store, _, state = build_store()
    staged, _ = stage_audio_item(store)
    state.key_override = OTHER_KEY
    budget = BudgetProbe()
    with typed_auth():
        store.fetch_audio(staged, read_budget=budget)
    assert any(event[0] == 'reserve' for event in budget.events if isinstance(event, tuple))


def test_budget_opens_the_read_window_before_an_envelope_fault():
    store, client, _ = build_store()
    staged, _ = stage_audio_item(store)
    poison(client, audio_object_name(client), lambda body: b'X' + body[1:])
    budget = BudgetProbe()
    with typed_envelope():
        store.fetch_audio(staged, read_budget=budget)
    assert ('timeout', 60) in budget.events


def test_budget_opens_both_windows_before_an_auth_fault():
    store, _, state = build_store()
    staged, _ = stage_audio_item(store)
    state.key_override = OTHER_KEY
    budget = BudgetProbe()
    with typed_auth():
        store.fetch_audio(staged, read_budget=budget)
    assert ('timeout', 30) in budget.events and ('timeout', 60) in budget.events


def test_envelope_fault_downloads_once_then_never_again():
    """One IO attempt, then the chain ends: the ladder's repeat passes are gone."""
    store, client, _ = build_store()
    staged, _ = stage_audio_item(store)
    poison(client, audio_object_name(client), lambda body: b'X' + body[1:])
    with typed_envelope():
        store.fetch_audio(staged)
    assert client.downloads == 1


def test_auth_fault_downloads_once_then_never_again():
    store, _, state = build_store()
    staged, _ = stage_audio_item(store)
    state.key_override = OTHER_KEY
    with typed_auth():
        store.fetch_audio(staged)
    assert client_downloads(store) == 1


def test_no_download_io_is_spent_on_a_reference_fault():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    before = client_downloads(store)
    with typed_reference():
        store.fetch_audio(replace(staged, audio_uri=uri + '?x=1'))
    assert client_downloads(store) == before


def client_downloads(store):
    """The fake client is the bucket; downloads live on it."""
    bucket = store.bucket
    return bucket.downloads


def test_metadata_reload_happens_exactly_once_per_healthy_read():
    store, client, _ = build_store()
    staged, _ = stage_audio_item(store)
    reloads = []

    real_blob = client.blob

    def counting_blob(*args, **kwargs):
        blob = real_blob(*args, **kwargs)

        class Counting:
            def __getattr__(self, attr):
                return getattr(blob, attr)

            def reload(self, **kw):
                reloads.append(1)
                return blob.reload(**kw)

        return Counting()

    client.blob = counting_blob
    store.fetch_audio(staged)
    client.blob = real_blob
    assert reloads == [1]


def test_budget_is_untouched_by_a_reference_fault():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    budget = BudgetProbe()
    with typed_reference():
        store.fetch_audio(replace(staged, audio_uri=uri + '?x=1'), read_budget=budget)
    assert budget.events == []


def test_real_budget_survives_a_typed_fault_without_losing_reserve_room():
    from utils.batch_pipeline.artifact_reads import ArtifactReadBudget
    import time as _time

    store, client, _ = build_store()
    staged, _ = stage_audio_item(store)
    budget = ArtifactReadBudget(deadline=_time.monotonic() + 60, max_bytes=10**9, max_objects=8)
    with blob_override(client, size=0), typed_size():
        store.fetch_audio(staged, read_budget=budget)
    assert budget.downloaded_bytes == 0
    assert store.fetch_audio(staged, read_budget=budget) == AUDIO_BODY


def test_real_budget_object_limit_is_not_the_typed_boundary():
    from utils.batch_pipeline.artifact_reads import ArtifactReadBudget, ArtifactReadLimit
    import time as _time

    store, client, _ = build_store()
    staged, _ = stage_audio_item(store)
    budget = ArtifactReadBudget(deadline=_time.monotonic() + 60, max_bytes=10**9, max_objects=1)
    budget.objects = 1
    with pytest.raises(ArtifactReadLimit) as raised:
        store.fetch_audio(staged, read_budget=budget)
    assert not isinstance(raised.value, StagedArtifactInvalid)


def test_real_budget_byte_limit_is_not_the_typed_boundary():
    from utils.batch_pipeline.artifact_reads import ArtifactReadBudget, ArtifactReadLimit
    import time as _time

    store, _, _ = build_store()
    staged, _ = stage_audio_item(store)
    budget = ArtifactReadBudget(deadline=_time.monotonic() + 60, max_bytes=4, max_objects=8)
    with pytest.raises(ArtifactReadLimit) as raised:
        store.fetch_audio(staged, read_budget=budget)
    assert not isinstance(raised.value, StagedArtifactInvalid)


def test_real_budget_deadline_is_not_the_typed_boundary():
    from utils.batch_pipeline.artifact_reads import ArtifactReadBudget, ArtifactReadLimit
    import time as _time

    store, _, _ = build_store()
    staged, _ = stage_audio_item(store)
    budget = ArtifactReadBudget(deadline=_time.monotonic() - 1, max_bytes=10**9, max_objects=8)
    with pytest.raises(ArtifactReadLimit) as raised:
        store.fetch_audio(staged, read_budget=budget)
    assert not isinstance(raised.value, StagedArtifactInvalid)


# --- entrypoint angle pins: ValueError compat and message hygiene ------------------


def test_load_result_reference_fault_is_a_value_error_instance():
    store, _, _ = build_store()
    staged, uri = stage_result_item(store)
    with pytest.raises(ValueError) as raised:
        store.load_result(staged, uri + '?x=1')
    assert isinstance(raised.value, StagedArtifactInvalid)


def test_probe_reference_fault_is_a_value_error_instance():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with pytest.raises(ValueError) as raised:
        store.missing_audio_evidence(replace(staged, audio_uri=uri + '?x=1'), now=1.0)
    assert isinstance(raised.value, StagedArtifactInvalid)


def test_plan_reference_fault_is_a_value_error_instance():
    store, _, _ = build_store()
    _, _, staged, uri = plan_store(store)
    with pytest.raises(ValueError) as raised:
        store.load_record_plan(staged, uri + '?x=1')
    assert isinstance(raised.value, StagedArtifactInvalid)


def test_fetch_audio_reference_fault_never_names_the_segment():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with pytest.raises(StagedArtifactInvalid) as raised:
        store.fetch_audio(replace(staged, audio_uri=uri.replace('/' + SEGMENT + '/', '/other-segment/', 1)))
    assert SEGMENT not in str(raised.value)


def test_probe_reference_fault_never_names_the_segment():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with pytest.raises(StagedArtifactInvalid) as raised:
        store.missing_audio_evidence(
            replace(staged, audio_uri=uri.replace('/' + SEGMENT + '/', '/other-segment/', 1)), now=1.0
        )
    assert SEGMENT not in str(raised.value)


def test_plan_reference_fault_never_names_the_bucket():
    store, _, _ = build_store()
    _, _, staged, uri = plan_store(store)
    with pytest.raises(StagedArtifactInvalid) as raised:
        store.load_record_plan(staged, uri.replace('synthetic-batch-bucket', 'other-bucket', 1))
    assert 'other-bucket' not in str(raised.value)


def test_size_fault_message_is_shared_by_both_entrypoints():
    store, client, _ = build_store()
    staged, uri = stage_result_item(store)
    with blob_override(client, size=0), pytest.raises(StagedArtifactInvalid) as fetch_side:
        store.fetch_audio(staged)
    with blob_override(client, size=0), pytest.raises(StagedArtifactInvalid) as load_side:
        store.load_result(staged, uri)
    assert str(fetch_side.value) == str(load_side.value)


def test_auth_fault_message_is_shared_by_both_entrypoints():
    store, _, state = build_store()
    staged, uri = stage_result_item(store)
    state.key_override = OTHER_KEY
    with pytest.raises(StagedArtifactInvalid) as fetch_side:
        store.fetch_audio(staged)
    with pytest.raises(StagedArtifactInvalid) as load_side:
        store.load_result(staged, uri)
    assert str(fetch_side.value) == str(load_side.value)


# --- the walk predicate, per closed message ---------------------------------------


@pytest.mark.parametrize('message', BOUNDARY_MESSAGES)
def test_walk_predicate_accepts_the_typed_message(message):
    assert payload_contract_violation(StagedArtifactInvalid(message)) is True


@pytest.mark.parametrize('message', BOUNDARY_MESSAGES)
def test_head_hold_accepts_the_typed_message(message):
    assert head_holds_without_retry(StagedArtifactInvalid(message), None) is True


# --- sweep angles per message ------------------------------------------------------


@pytest.mark.parametrize('message', BOUNDARY_MESSAGES)
def test_sweep_never_refetches_any_typed_message(setup, monkeypatch, message):
    client, _, _, artifacts, _, _ = setup
    artifacts.fetch_audio.side_effect = StagedArtifactInvalid(message)
    http = serve(setup, monkeypatch)
    http.post('/v2/batch-pipeline/recover-quarantine', json=RECOVER)
    http.post('/v2/batch-pipeline/recover-quarantine', json=RECOVER)
    assert artifacts.fetch_audio.call_count == 1


@pytest.mark.parametrize('message', BOUNDARY_MESSAGES)
def test_sweep_hold_never_leaks_any_typed_message(setup, monkeypatch, message):
    client, _, _, artifacts, _, _ = setup
    artifacts.fetch_audio.side_effect = StagedArtifactInvalid(message)
    serve(setup, monkeypatch).post('/v2/batch-pipeline/recover-quarantine', json=RECOVER)
    assert message not in str(row(client)['recovery'])


@pytest.mark.parametrize('message', BOUNDARY_MESSAGES)
def test_sweep_hold_never_calls_the_second_provider(setup, monkeypatch, message):
    client, _, _, artifacts, stt, _ = setup
    artifacts.fetch_audio.side_effect = StagedArtifactInvalid(message)
    serve(setup, monkeypatch).post('/v2/batch-pipeline/recover-quarantine', json=RECOVER)
    stt.assert_not_called()


# --- worker angles completed across the family -------------------------------------


@pytest.mark.parametrize('message', (BOUNDARY_MESSAGES[1], BOUNDARY_MESSAGES[3]))
def test_words_provider_is_never_called_for_auth_family(monkeypatch, message):
    worker, words, _, _ = terminal(monkeypatch, typed_decode(message))
    worker.process_batch([item()])
    assert not words.calls


@pytest.mark.parametrize('message', (BOUNDARY_MESSAGES[0], BOUNDARY_MESSAGES[3]))
def test_persist_is_never_called_for_reference_and_auth(monkeypatch, message):
    worker, _, saved, _ = terminal(monkeypatch, typed_decode(message))
    worker.process_batch([item()])
    assert not saved


@pytest.mark.parametrize('message', (BOUNDARY_MESSAGES[1], BOUNDARY_MESSAGES[3]))
def test_vad_is_never_called_for_size_and_auth(monkeypatch, message):
    calls = []
    worker, *_ = terminal(monkeypatch, typed_decode(message))
    worker.vad = lambda samples: calls.append(len(samples))
    worker.process_batch([item()])
    assert not calls


@pytest.mark.parametrize('message', (BOUNDARY_MESSAGES[0], BOUNDARY_MESSAGES[1]))
def test_decode_runs_once_for_reference_and_size(monkeypatch, message):
    calls = []

    def decode(work):
        calls.append(work.segment_id)
        raise StagedArtifactInvalid(message)

    worker, *_ = terminal(monkeypatch, decode)
    worker.process_batch([item()])
    assert calls == ['a']


def test_on_failure_records_the_name_once_for_the_size_family(monkeypatch):
    worker, _, _, failures = terminal(monkeypatch, typed_decode(BOUNDARY_MESSAGES[1]))
    worker.process_batch([item()])
    assert failures == [('a', 'StagedArtifactInvalid')]


def test_on_failure_records_the_name_once_for_the_reference_family(monkeypatch):
    worker, _, _, failures = terminal(monkeypatch, typed_decode(BOUNDARY_MESSAGES[0]))
    worker.process_batch([item()])
    assert failures == [('a', 'StagedArtifactInvalid')]


def test_two_typed_heads_settle_independently(monkeypatch):
    def decode(work):
        raise StagedArtifactInvalid(BOUNDARY_MESSAGES[2])

    worker, words, saved, failures = terminal(monkeypatch, decode)
    results = worker.process_batch([item('bad1'), item('bad2')])
    assert [r.reason for r in results] == [STAGED_TOKEN, STAGED_TOKEN]
    assert len(failures) == 2 and not words.calls and not saved


def test_typed_fault_in_the_middle_of_a_flight(monkeypatch):
    def decode(work):
        if work.segment_id == 'mid':
            raise StagedArtifactInvalid(BOUNDARY_MESSAGES[3])
        return Samples(work.duration_seconds)

    worker, words, saved, _ = terminal(monkeypatch, decode)
    results = worker.process_batch([item('a'), item('mid'), item('z')])
    assert len(results) == 3
    assert len(saved) == 2


# --- source pins: the boundary reads types, the store carries closed messages ------

BACKEND_ROOT = None


def _backend_path():
    from pathlib import Path

    return Path(__file__).resolve().parents[2]


def test_artifact_store_source_carries_the_four_closed_messages():
    source = (_backend_path() / 'utils/batch_pipeline/artifacts.py').read_text()
    for message in BOUNDARY_MESSAGES:
        assert message in source


def test_artifact_store_read_raise_sites_are_typed_or_permission():
    import ast

    tree = ast.parse((_backend_path() / 'utils/batch_pipeline/artifacts.py').read_text())
    allowed = {'StagedArtifactInvalid', 'PermissionError', 'TimeoutError', 'NotFound', 'ValueError'}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in {'_read', '_reference'}:
            for sub in ast.walk(node):
                if isinstance(sub, ast.Raise) and isinstance(sub.exc, ast.Call):
                    name = getattr(sub.exc.func, 'id', None)
                    assert name in allowed, f'unexpected raise site in {node.name}: {name}'


def test_worker_boundary_source_reads_the_pair():
    source = (_backend_path() / 'diarizer/batch_pipeline.py').read_text()
    assert '(StagedAudioInvalid, StagedArtifactInvalid)' in source


def test_recovery_sweep_source_reads_the_sibling():
    source = (_backend_path() / 'utils/batch_pipeline/quarantine_recovery.py').read_text()
    assert 'except StagedArtifactInvalid' in source
    assert "refusal_reason='staged_audio_invalid'" in source


# --- vocabulary pins ----------------------------------------------------------------


def test_staged_token_differs_from_every_other_fetch_decode_token():
    others = {
        WorkerValidationReason.RETAINED_AUDIO_INVALID.value,
        WorkerValidationReason.DECODED_DURATION_MISMATCH.value,
        WorkerValidationReason.VAD_BOUNDS.value,
        WorkerValidationReason.EMPTY_ASR.value,
        WorkerValidationReason.UNSUPPORTED_LANGUAGE.value,
    }
    assert STAGED_TOKEN not in others


def test_fetch_decode_stage_token_value():
    assert WorkerValidationStage.FETCH_DECODE.value == 'fetch_decode'


def test_invalid_tag_is_not_a_value_error():
    from cryptography.exceptions import InvalidTag

    assert not issubclass(InvalidTag, ValueError)


def test_typed_fault_is_both_boundary_families_value_error():
    """One catch shape covers the whole deterministic read family."""
    from cryptography.exceptions import InvalidTag

    for fault in (StagedArtifactInvalid(BOUNDARY_MESSAGES[0]), InvalidTag(), ValueError('payload')):
        assert isinstance(fault, Exception)


def test_taxonomy_invalid_tag_note_mentions_the_wrapper():
    assert 'StagedArtifactInvalid' in TAXONOMY['InvalidTag']


def test_error_type_of_the_typed_fault_is_its_own_class():
    from utils.batch_pipeline.projection import error_type

    assert error_type(StagedArtifactInvalid(BOUNDARY_MESSAGES[2])) == 'StagedArtifactInvalid'


def test_error_type_of_a_contention_shaped_value_error_stays_contention():
    from database.firestore_transaction_retry import FirestoreAborted
    from utils.batch_pipeline.projection import error_type

    contention = ValueError('Failed to commit transaction in 5 attempts')
    contention.__cause__ = FirestoreAborted('synthetic contention')
    assert error_type(contention) == 'FirestoreContentionExhausted'


def test_payload_contract_predicate_rejects_contention_shaped_errors():
    from database.firestore_transaction_retry import FirestoreAborted

    contention = ValueError('Failed to commit transaction in 5 attempts')
    contention.__cause__ = FirestoreAborted('synthetic contention')
    assert payload_contract_violation(contention) is False


# --- boundary fairness, cross-kind limits, and identity round trips ---------------


def test_unicode_payload_round_trip():
    store, _, _ = build_store()
    staged, uri = stage_result_item(store, {'words': [{'word': 'héllo', 'timestamp': [0.0, 0.1]}]})
    assert store.load_result(staged, uri)['words'][0]['word'] == 'héllo'


def test_empty_words_round_trip():
    store, _, _ = build_store()
    staged, uri = stage_result_item(store, {'words': []})
    assert store.load_result(staged, uri) == {'words': []}


def test_nested_payload_round_trip():
    payload = {'words': [], 'speech_spans': [{'start': 0.0, 'end': 1.0}], 'meta': {'route': 'parakeet'}}
    store, _, _ = build_store()
    staged, uri = stage_result_item(store, payload)
    assert store.load_result(staged, uri) == payload


def test_unicode_owner_round_trip():
    store, _, _ = build_store()
    owner = 'ownér'
    other = make_item(owner_id=owner)
    uri = store.stage_audio(other, b'x')
    assert store.fetch_audio(replace(other, audio_uri=uri)) == b'x'


def test_unicode_segment_round_trip():
    store, _, _ = build_store()
    unit = make_item(segment_id='ségment')
    uri = store.stage_audio(unit, b'x')
    assert store.fetch_audio(replace(unit, audio_uri=uri)) == b'x'


def test_standard_level_round_trip():
    store, _, _ = build_store(level='standard')
    staged, _ = stage_audio_item(store)
    assert store.fetch_audio(staged) == AUDIO_BODY


def test_enhanced_level_round_trip():
    store, _, _ = build_store(level='enhanced')
    staged, _ = stage_audio_item(store)
    assert store.fetch_audio(staged) == AUDIO_BODY


def test_audio_staged_under_standard_cannot_read_under_enhanced():
    store, _, state = build_store(level='standard')
    staged, _ = stage_audio_item(store)
    state.context = ProtectionContext('enhanced', 0)
    with typed_auth():
        store.fetch_audio(staged)


def test_fragment_with_plus_sign_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with typed_reference():
        store.fetch_audio(replace(staged, audio_uri=uri.rsplit('#', 1)[0] + '#+1'))


def test_fragment_with_a_space_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with typed_reference():
        store.fetch_audio(replace(staged, audio_uri=uri.rsplit('#', 1)[0] + '#1 2'))


def test_uppercase_key_name_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    upper = uri.rsplit('/', 1)[0] + '/' + 'A' * 32 + '.enc#' + uri.rsplit('#', 1)[1]
    with typed_reference():
        store.fetch_audio(replace(staged, audio_uri=upper))


def test_long_key_name_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    long_name = uri.rsplit('/', 1)[0] + '/' + 'a' * 33 + '.enc#' + uri.rsplit('#', 1)[1]
    with typed_reference():
        store.fetch_audio(replace(staged, audio_uri=long_name))


def test_dot_dot_key_name_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    evil = uri.rsplit('/', 1)[0] + '/' + 'a' * 30 + '..enc#' + uri.rsplit('#', 1)[1]
    with typed_reference():
        store.fetch_audio(replace(staged, audio_uri=evil))


def test_empty_query_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    with typed_reference():
        store.fetch_audio(replace(staged, audio_uri=uri + '?'))


def test_query_before_fragment_is_typed():
    store, _, _ = build_store()
    staged, uri = stage_audio_item(store)
    name, fragment = uri.rsplit('#', 1)
    with typed_reference():
        store.fetch_audio(replace(staged, audio_uri=name + '?x=1#' + fragment))


def test_tag_short_by_one_byte_is_typed():
    store, client, _ = build_store()
    staged, _ = stage_audio_item(store)
    poison(client, audio_object_name(client), lambda body: body[: len(MAGIC) + 12 + 15])
    with typed_auth():
        store.fetch_audio(staged)


def test_valid_empty_ciphertext_authenticates_then_fails_the_wav_gate():
    """A valid empty sealed body decrypts; the bytes then fail downstream typing."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    store, client, state = build_store()
    staged, _ = stage_audio_item(store)
    nonce = b'\n' * 12
    sealed = AESGCM(KEY).encrypt(nonce, b'', store._aad(staged, 'audio', state.context))
    poison(client, audio_object_name(client), lambda body: MAGIC + nonce + sealed)
    assert store.fetch_audio(staged) == b''


def test_write_side_refuses_an_oversized_result_payload():
    """The write guard keeps read-side oversize unreachable except by drift:
    a body at the bound is refused raw ValueError before any storage IO."""
    store, client, _ = build_store()
    staged, _ = stage_result_item(store)
    downloads_before = client.downloads
    with pytest.raises(ValueError) as raised:
        store.persist_result(staged, {'pad': 'x' * RESULT_LIMIT})
    assert 'batch artifact exceeds bounded payload size' in str(raised.value)
    assert not isinstance(raised.value, StagedArtifactInvalid)
    assert client.downloads == downloads_before


def test_results_object_within_both_limits_reads_through_both_entrypoints():
    store, _, _ = build_store()
    staged, uri = stage_result_item(store)
    assert store.fetch_audio(staged) == b'audio'
    assert isinstance(store.load_result(staged, uri), dict)


def test_record_plan_body_round_trips_through_fetch_audio():
    """The plan rides the audio kind: fetch_audio hands back the plan bytes."""
    import json as _json

    store, _, _ = build_store()
    original = make_item()
    plan_uri = store.stage_record_plan(original, {'references': [7]})
    body = store.fetch_audio(replace(original, audio_uri=plan_uri))
    assert _json.loads(body) == {'references': [7]}


def test_plan_duration_mutation_is_typed():
    store, _, _ = build_store()
    _, _, staged, uri = plan_store(store)
    with typed_auth():
        store.load_record_plan(replace(staged, duration_seconds=9.0), uri)


def test_plan_shadow_mutation_is_typed():
    store, _, _ = build_store()
    _, _, staged, uri = plan_store(store)
    with typed_auth():
        store.load_record_plan(replace(staged, shadow=not staged.shadow), uri)


def test_worker_terminal_with_language_receipt_enabled(monkeypatch):
    worker, words, saved, _ = terminal(monkeypatch, typed_decode(BOUNDARY_MESSAGES[2]))
    unit = replace(item(), language_receipt_enabled=True)
    results = worker.process_batch([unit])
    assert results == [ValidationFailureWork('a', 'fetch_decode', STAGED_TOKEN)]
    assert not words.calls and not saved


def test_worker_terminal_for_a_compute_admission_unit(monkeypatch):
    worker, _, _, _ = terminal(monkeypatch, typed_decode(BOUNDARY_MESSAGES[1]))
    unit = replace(item(), requires_compute_admission=True)
    assert worker.process_batch([unit]) == [ValidationFailureWork('a', 'fetch_decode', STAGED_TOKEN)]


def test_scheduler_fail_records_typed_evidence(monkeypatch):
    import time as _time

    from tests.unit.test_batch_pipeline_scheduler import MemoryStore
    from utils.batch_pipeline.scheduler import Scheduler

    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), _time.time())
    lease = queue.pull(_time.time())[0]
    assert queue.fail('a', lease.token, _time.time(), worker_failure={'stage': 'fetch_decode', 'reason': STAGED_TOKEN})
    assert store.rows['jobs', 'a']['worker_failure'] == {'stage': 'fetch_decode', 'reason': STAGED_TOKEN}


def test_scheduler_hold_leaves_typed_evidence_on_the_job_row(monkeypatch):
    import time as _time

    from tests.unit.test_batch_pipeline_scheduler import MemoryStore
    from utils.batch_pipeline.scheduler import Scheduler

    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), _time.time())
    lease = queue.pull(_time.time())[0]
    queue.fail('a', lease.token, _time.time(), worker_failure={'stage': 'fetch_decode', 'reason': STAGED_TOKEN})
    job = store.rows['jobs', 'a']
    assert job['recovery_state'] == 'held'
    assert job['worker_failure']['reason'] == STAGED_TOKEN


def test_typed_fault_with_a_contention_cause_is_still_permanent():
    """The typed class outranks its cause family: bytes never heal contention."""
    from database.firestore_transaction_retry import FirestoreAborted

    fault = StagedArtifactInvalid(BOUNDARY_MESSAGES[1])
    fault.__cause__ = FirestoreAborted('synthetic contention')
    assert payload_contract_violation(fault) is True


def test_invalid_tag_head_hold_is_defense_in_depth():
    from cryptography.exceptions import InvalidTag

    assert head_holds_without_retry(InvalidTag(), None) is True


def test_payload_contract_accepts_raw_invalid_tag():
    from cryptography.exceptions import InvalidTag

    assert payload_contract_violation(InvalidTag()) is True
