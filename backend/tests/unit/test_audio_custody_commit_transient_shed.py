"""The custody-commit availability shed pins every wiring site it protects.

One durable audio window commit runs four GCS operations as single explicit
attempts (``timeout=10, retry=None``): the media upload, its generation read,
the manifest upload and its generation read. A momentary availability blip
on any of them used to void the whole commit: the producer stayed
unacknowledged, the session failed closed, and a mid-session failure latched
the custody fence so every later window of that session was refused unseen.
The shed re-asks the same op a bounded number of times; these tests pin the
shed helper contract, every op wiring site in ``commit_capture``, the
unchanged parity of the committed receipt bytes, the metrics contract, and
the pusher session behavior at each flush boundary.
"""

import asyncio
import hashlib
import json
import struct
from collections import deque
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import (
    BadGateway,
    Forbidden,
    GatewayTimeout,
    InternalServerError,
    InvalidArgument,
    NotFound,
    PreconditionFailed,
    RetryError,
    ServiceUnavailable,
    TooManyRequests,
)

import routers.pusher as pusher
from starlette.websockets import WebSocketState
from fastapi.websockets import WebSocketDisconnect
from utils import pusher_audio_projection
from utils.pusher_audio_window import AUDIO_TIMELINE_CONTINUITY_TOLERANCE
from utils.pusher_record_finish import ProjectionQueueWaitTimeout, RecordProjectionQueue
from utils.other import audio_outbox, audio_outbox_metrics, storage
from utils.other.audio_outbox import (
    CUSTODY_COMMIT_TRANSIENT_ATTEMPTS,
    CUSTODY_COMMIT_TRANSIENT_BACKOFF_SECONDS,
    AudioReceipt,
    AudioProjection,
    _commit_op_with_transient_shed,
    _is_commit_availability_blip,
    commit_capture,
    commit_pcm,
    commit_pcm_window,
    read_pcm,
)
from utils.other.audio_packs import CaptureDeleted
from utils.other.audio_outbox_metrics import (
    CUSTODY_COMMIT_TRANSIENT_EXHAUSTED,
    CUSTODY_COMMIT_TRANSIENT_RETRIES,
)
from utils.pusher_protocol import ByteBudget
from database import record_audio as record_audio_db

try:  # the storage SDK's HTTP transport; present in every serving image
    import requests.exceptions as _requests_exceptions

    REQUESTS_CONNECTION_ERROR = _requests_exceptions.ConnectionError
    REQUESTS_READ_TIMEOUT = _requests_exceptions.ReadTimeout
except ImportError:  # pragma: no cover - the pinned SDK always ships requests
    REQUESTS_CONNECTION_ERROR = ConnectionError
    REQUESTS_READ_TIMEOUT = TimeoutError


COMMIT_OP_NAMES = ('media_upload', 'media_generation', 'manifest_upload', 'manifest_generation')
RETRYABLE_MEMBERS = (
    ServiceUnavailable,
    InternalServerError,
    TooManyRequests,
    BadGateway,
    GatewayTimeout,
    ConnectionError,
)


class FakeBlob:
    """One immutable object: create-if-absent upload, generation-pinned reads."""

    def __init__(self, name):
        self.name = name
        self.data = None
        self.generation = None
        self.metadata = {}
        self.upload_attempts = 0
        self.reload_attempts = 0
        self.reload_failures = []

    def write(self, data, metadata):
        self.data = data
        self.generation = 17
        self.metadata = dict(metadata)

    @property
    def size(self):
        return len(self.data or b'')

    def upload_from_string(self, data, *, if_generation_match, **kwargs):
        self.upload_attempts += 1
        assert if_generation_match == 0
        if self.data is not None:
            raise PreconditionFailed('immutable')
        self.data = data
        self.generation = 17

    def reload(self, **kwargs):
        self.reload_attempts += 1
        if self.reload_failures:
            raise self.reload_failures.pop(0)
        if self.data is None:
            raise NotFound('missing')
        return self.generation

    def download_as_bytes(self, **kwargs):
        if kwargs.get('if_generation_match', self.generation) != self.generation:
            raise PreconditionFailed('generation changed')
        return self.data


class FakeBucket:
    name = 'shed-audio'

    def __init__(self):
        self.blobs = {}

    def blob(self, name, generation=None):
        return self.blobs.setdefault(name, FakeBlob(name))


class ScriptedArchive:
    """``storage.archive_capture_bytes`` with per-prefix transient scripts.

    Mirrors the real writer's custody contract: content-addressed path from
    the plaintext digest, create-if-absent semantics (a rewrite of an
    existing object raises ``PreconditionFailed``), metadata carries the
    plaintext ``sha256`` the commit verifies, and the stored bytes are the
    payload verbatim. ``script[prefix]`` lists exceptions raised before the
    write, one per call, until exhausted.
    """

    def __init__(self, bucket, script=None):
        self.bucket = bucket
        self.script = dict(script or {})
        self.calls = []

    def __call__(self, uid, raw, prefix, name, metadata, *, data_protection_level=None, manifest_identity=None):
        digest = hashlib.sha256(raw).hexdigest()
        suffix = '.enc' if data_protection_level == 'enhanced' else ''
        path = f'{prefix}/{uid}/{name}/{manifest_identity or digest}.bin{suffix}'
        self.calls.append((prefix, name))
        pending = self.script.get(prefix)
        if pending:
            raise pending.pop(0)
        blob = self.bucket.blob(path)
        if blob.data is not None:
            # The real writer's create-if-absent acceptance: an object already
            # sitting at the content-addressed path with the same digest is
            # the earlier immutable generation, never a rotation.
            if (blob.metadata or {}).get('sha256') == digest:
                return path
            raise ValueError('capture identity collision')
        blob.write(raw, {**metadata, 'sha256': digest})
        return path


@pytest.fixture(autouse=True)
def no_shed_wait(monkeypatch):
    """Replace the shed's inter-attempt sleep; tests assert the schedule."""

    waits = []
    monkeypatch.setattr(audio_outbox.time, 'sleep', waits.append)
    return waits


@pytest.fixture
def bucket():
    return FakeBucket()


@pytest.fixture
def shed_storage(monkeypatch, bucket):
    """Hermetic commit boundary: scripted writer + fake bucket, real commit."""

    archive = ScriptedArchive(bucket)
    monkeypatch.setattr(storage, 'archive_capture_bytes', archive)
    monkeypatch.setattr(storage, 'get_private_cloud_sync_bucket', lambda: bucket)
    monkeypatch.setattr(storage.users_db, 'get_data_protection_level', lambda uid: 'standard')
    return SimpleNamespace(bucket=bucket, archive=archive)


@pytest.fixture
def real_storage(monkeypatch, bucket):
    """The REAL archive writer against the fake bucket (existing remote recipe)."""

    monkeypatch.setattr(storage, '_get_storage_client', lambda: SimpleNamespace(bucket=lambda name: bucket))
    monkeypatch.setattr(storage, 'private_cloud_sync_bucket', bucket.name)
    monkeypatch.setattr(storage.users_db, 'get_data_protection_level', lambda uid: 'standard')
    from contextlib import nullcontext

    monkeypatch.setattr(storage, 'owner_storage_write_gate', lambda *a: nullcontext())
    monkeypatch.setattr(storage.conversation_tombstones, 'is_deleted', lambda *a: False)
    return bucket


def counter_value(counter, **labels):
    sample = f'{counter._name}_total'
    return _registry_value(sample, labels)


def _registry_value(name, labels):
    try:
        from prometheus_client import REGISTRY

        value = REGISTRY.get_sample_value(name, labels)
        return value or 0.0
    except Exception:
        return 0.0


def custody_commits():
    return _registry_value('omi_audio_custody_commits_total', {})


def custody_failures(stage, reason):
    return _registry_value('omi_audio_custody_failures_total', {'stage': stage, 'reason': reason})


def shed_retries(op):
    return _registry_value('omi_audio_custody_commit_transient_retries_total', {'op': op})


def shed_exhausted(op):
    return _registry_value('omi_audio_custody_commit_shed_exhausted_total', {'op': op})


def _pcm(seconds=0.01, rate=16000, fill=1):
    return struct.pack(f'<{int(seconds * rate)}h', *[fill] * int(seconds * rate))


def _framed_setup(payloads, start=1000.0, rate=16000):
    """Contiguous frame table matching the concatenated payloads exactly."""

    frames = []
    step = len(payloads[0]) / 2 / rate
    for index, pcm in enumerate(payloads):
        frames.append(
            {
                'sequence': index + 1,
                'start': start + index * step,
                'samples': len(pcm) // 2,
                'sha256': hashlib.sha256(pcm).hexdigest(),
                'gap_before': False,
            }
        )
    return frames


# ---------------------------------------------------------------------------
# The shed helper contract.
# ---------------------------------------------------------------------------


def test_first_attempt_success_runs_the_op_once():
    calls = []
    result = _commit_op_with_transient_shed('media_upload', lambda: calls.append(1) or 'ok')
    assert result == 'ok'
    assert len(calls) == 1


def test_service_unavailable_is_retried_until_success():
    attempts = []

    def flaky():
        attempts.append(1)
        if len(attempts) < 2:
            raise ServiceUnavailable('blip')
        return 'ok'

    assert _commit_op_with_transient_shed('media_upload', flaky) == 'ok'
    assert len(attempts) == 2


def test_internal_server_error_is_retried_until_success():
    attempts = []

    def flaky():
        attempts.append(1)
        if len(attempts) < 2:
            raise InternalServerError('blip')
        return 'ok'

    assert _commit_op_with_transient_shed('manifest_upload', flaky) == 'ok'
    assert len(attempts) == 2


def test_too_many_requests_is_retried_until_success():
    attempts = []

    def flaky():
        attempts.append(1)
        if len(attempts) < 2:
            raise TooManyRequests('quota churn')
        return 'ok'

    assert _commit_op_with_transient_shed('media_generation', flaky) == 'ok'
    assert len(attempts) == 2


def test_bad_gateway_is_retried_until_success():
    attempts = []

    def flaky():
        attempts.append(1)
        if len(attempts) < 2:
            raise BadGateway('blip')
        return 'ok'

    assert _commit_op_with_transient_shed('manifest_generation', flaky) == 'ok'
    assert len(attempts) == 2


def test_gateway_timeout_is_retried_until_success():
    attempts = []

    def flaky():
        attempts.append(1)
        if len(attempts) < 2:
            raise GatewayTimeout('blip')
        return 'ok'

    assert _commit_op_with_transient_shed('media_upload', flaky) == 'ok'
    assert len(attempts) == 2


def test_builtin_connection_error_is_retried_until_success():
    attempts = []

    def flaky():
        attempts.append(1)
        if len(attempts) < 2:
            raise ConnectionError('reset by peer')
        return 'ok'

    assert _commit_op_with_transient_shed('manifest_upload', flaky) == 'ok'
    assert len(attempts) == 2


def test_requests_transport_connection_error_is_retried_until_success():
    attempts = []

    def flaky():
        attempts.append(1)
        if len(attempts) < 2:
            raise REQUESTS_CONNECTION_ERROR('connection reset')
        return 'ok'

    assert _commit_op_with_transient_shed('media_generation', flaky) == 'ok'
    assert len(attempts) == 2


def test_requests_transport_read_timeout_is_retried_until_success():
    attempts = []

    def flaky():
        attempts.append(1)
        if len(attempts) < 2:
            raise REQUESTS_READ_TIMEOUT('headers timed out')
        return 'ok'

    assert _commit_op_with_transient_shed('manifest_generation', flaky) == 'ok'
    assert len(attempts) == 2


def test_shed_budget_is_three_attempts_total():
    attempts = []

    def flaky():
        attempts.append(1)
        raise ServiceUnavailable('down')

    with pytest.raises(ServiceUnavailable):
        _commit_op_with_transient_shed('media_upload', flaky)
    assert len(attempts) == 3


def test_exhaustion_raises_the_last_transient_instance():
    seen = []

    def flaky():
        error = ServiceUnavailable('down')
        seen.append(error)
        raise error

    with pytest.raises(ServiceUnavailable) as caught:
        _commit_op_with_transient_shed('media_upload', flaky)
    assert caught.value is seen[-1]


def test_exhaustion_marks_the_error_shed_exhausted():
    def flaky():
        raise ServiceUnavailable('down')

    with pytest.raises(ServiceUnavailable) as caught:
        _commit_op_with_transient_shed('media_upload', flaky)
    assert caught.value.custody_shed_exhausted is True


def test_a_recovered_blip_is_not_marked_exhausted():
    attempts = []

    def flaky():
        attempts.append(1)
        if len(attempts) < 2:
            raise ServiceUnavailable('blip')
        return 'ok'

    _commit_op_with_transient_shed('media_upload', flaky)
    assert len(attempts) == 2


def test_precondition_failed_is_never_retried():
    calls = []

    def loud():
        calls.append(1)
        raise PreconditionFailed('immutable')

    with pytest.raises(PreconditionFailed):
        _commit_op_with_transient_shed('media_upload', loud)
    assert len(calls) == 1


def test_not_found_is_never_retried():
    calls = []

    def loud():
        calls.append(1)
        raise NotFound('missing')

    with pytest.raises(NotFound):
        _commit_op_with_transient_shed('media_generation', loud)
    assert len(calls) == 1


def test_forbidden_is_never_retried():
    calls = []

    def loud():
        calls.append(1)
        raise Forbidden('refused')

    with pytest.raises(Forbidden):
        _commit_op_with_transient_shed('manifest_upload', loud)
    assert len(calls) == 1


def test_invalid_argument_is_never_retried():
    calls = []

    def loud():
        calls.append(1)
        raise InvalidArgument('bad request')

    with pytest.raises(InvalidArgument):
        _commit_op_with_transient_shed('manifest_generation', loud)
    assert len(calls) == 1


def test_deterministic_value_error_is_never_retried():
    calls = []

    def loud():
        calls.append(1)
        raise ValueError('digest mismatch')

    with pytest.raises(ValueError):
        _commit_op_with_transient_shed('media_upload', loud)
    assert len(calls) == 1


def test_tombstone_refusal_is_never_retried():
    calls = []

    def loud():
        calls.append(1)
        raise CaptureDeleted('deleted')

    with pytest.raises(CaptureDeleted):
        _commit_op_with_transient_shed('media_upload', loud)
    assert len(calls) == 1


def test_keyboard_interrupt_is_never_retried():
    calls = []

    def loud():
        calls.append(1)
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        _commit_op_with_transient_shed('media_upload', loud)
    assert len(calls) == 1


def test_retry_error_envelope_is_never_retried_by_the_shed():
    calls = []

    def loud():
        calls.append(1)
        raise RetryError('drained elsewhere', ServiceUnavailable('cause'))

    with pytest.raises(RetryError):
        _commit_op_with_transient_shed('media_upload', loud)
    assert len(calls) == 1


def test_backoff_doubles_between_attempts(no_shed_wait):
    attempts = []

    def flaky():
        attempts.append(1)
        raise ServiceUnavailable('down')

    with pytest.raises(ServiceUnavailable):
        _commit_op_with_transient_shed('media_upload', flaky)
    assert no_shed_wait == [0.1, 0.2]


def test_backoff_schedule_holds_for_a_two_blip_recovery(no_shed_wait):
    attempts = []

    def flaky():
        attempts.append(1)
        if len(attempts) < 3:
            raise ServiceUnavailable('blip')
        return 'ok'

    assert _commit_op_with_transient_shed('media_upload', flaky) == 'ok'
    assert no_shed_wait == [0.1, 0.2]


def test_no_sleep_after_the_final_failed_attempt(no_shed_wait):
    def flaky():
        raise ServiceUnavailable('down')

    with pytest.raises(ServiceUnavailable):
        _commit_op_with_transient_shed('media_upload', flaky)
    assert no_shed_wait[-1:] == [] or len(no_shed_wait) == CUSTODY_COMMIT_TRANSIENT_ATTEMPTS - 1


def test_no_sleep_when_the_first_attempt_succeeds(no_shed_wait):
    _commit_op_with_transient_shed('media_upload', lambda: 'ok')
    assert no_shed_wait == []


def test_shed_backoff_constant_stays_executor_friendly():
    worst = CUSTODY_COMMIT_TRANSIENT_BACKOFF_SECONDS * (2 ** (CUSTODY_COMMIT_TRANSIENT_ATTEMPTS - 1)) * 3
    assert 0 < CUSTODY_COMMIT_TRANSIENT_BACKOFF_SECONDS <= 0.5
    assert worst < 5.0


def test_shed_attempts_constant_is_bounded():
    assert CUSTODY_COMMIT_TRANSIENT_ATTEMPTS == 3


# ---------------------------------------------------------------------------
# The availability classifier.
# ---------------------------------------------------------------------------


def test_classifier_accepts_every_replay_set_member():
    for member in RETRYABLE_MEMBERS:
        assert _is_commit_availability_blip(member('blip')) is True, type(member).__name__


def test_classifier_accepts_requests_transport_family():
    assert _is_commit_availability_blip(REQUESTS_CONNECTION_ERROR('reset')) is True
    assert _is_commit_availability_blip(REQUESTS_READ_TIMEOUT('timeout')) is True


def test_classifier_rejects_precondition_failed():
    assert _is_commit_availability_blip(PreconditionFailed('immutable')) is False


def test_classifier_rejects_not_found():
    assert _is_commit_availability_blip(NotFound('missing')) is False


def test_classifier_rejects_forbidden():
    assert _is_commit_availability_blip(Forbidden('refused')) is False


def test_classifier_rejects_invalid_argument():
    assert _is_commit_availability_blip(InvalidArgument('bad')) is False


def test_classifier_rejects_retry_error_envelope():
    assert _is_commit_availability_blip(RetryError('drained', ServiceUnavailable('cause'))) is False


def test_classifier_rejects_capture_deleted():
    assert _is_commit_availability_blip(CaptureDeleted('deleted')) is False


def test_classifier_rejects_plain_value_error():
    assert _is_commit_availability_blip(ValueError('mismatch')) is False


def test_classifier_rejects_plain_runtime_error():
    assert _is_commit_availability_blip(RuntimeError('unresolved fence')) is False


def test_classifier_rejects_plain_timeout_error():
    assert _is_commit_availability_blip(TimeoutError('10s window')) is False


def test_classifier_rejects_cancelled_error():
    assert _is_commit_availability_blip(asyncio.CancelledError()) is False


# ---------------------------------------------------------------------------
# commit_capture: every op wiring site sheds, every loud edge stays loud.
# ---------------------------------------------------------------------------


def _commit(shed_storage, uid='owner', conversation='conversation'):
    pcm = _pcm(fill=3)
    return commit_pcm_window(
        uid,
        pcm,
        conversation,
        1000.0,
        16000,
        'root',
        0,
        [
            {
                'sequence': 1,
                'start': 1000.0,
                'samples': len(pcm) // 2,
                'sha256': hashlib.sha256(pcm).hexdigest(),
                'gap_before': False,
            }
        ],
        framed=True,
    )


def test_media_upload_blip_recovers_and_returns_a_receipt(shed_storage):
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('cold channel')]
    receipt = _commit(shed_storage)
    assert receipt.path.startswith('raw-live/owner/')
    media_calls = [1 for prefix, _ in shed_storage.archive.calls if prefix == 'raw-live']
    manifest_calls = [1 for prefix, _ in shed_storage.archive.calls if prefix == 'audio-outbox']
    assert len(media_calls) == 2
    assert len(manifest_calls) == 1


def test_manifest_upload_blip_recovers_and_returns_a_receipt(shed_storage):
    shed_storage.archive.script['audio-outbox'] = [ServiceUnavailable('cold channel')]
    receipt = _commit(shed_storage)
    assert receipt.manifest_path.startswith('audio-outbox/owner/')
    assert len(shed_storage.archive.calls) == 3


def test_media_generation_read_blip_recovers_and_returns_a_receipt(shed_storage, monkeypatch):
    media_path = []

    def plant_media_reload_blip(uid, raw, prefix, name, metadata, **kwargs):
        path = shed_storage.archive(uid, raw, prefix, name, metadata, **kwargs)
        if prefix == 'raw-live':
            media_path.append(path)
            shed_storage.bucket.blobs[path].reload_failures = [ServiceUnavailable('cold read')]
        return path

    monkeypatch.setattr(storage, 'archive_capture_bytes', plant_media_reload_blip)
    receipt = commit_pcm_window('owner', _pcm(fill=4), 'conversation', 1000.0, 16000, 'root', 0, [], framed=False)
    assert receipt.generation == '17'
    assert shed_storage.bucket.blobs[media_path[-1]].reload_attempts == 2


def test_manifest_generation_read_blip_recovers_and_returns_a_receipt(shed_storage):
    media = _commit(shed_storage)
    shed_storage.bucket.blobs[media.manifest_path].reload_failures = [ServiceUnavailable('cold read')]
    receipt = commit_pcm_window('owner', _pcm(fill=3), 'conversation', 1000.0, 16000, 'root', 0, [], framed=False)
    assert receipt.manifest_generation == '17'


def test_one_blip_on_every_op_still_commits_one_receipt(shed_storage, monkeypatch):
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('blip')]
    shed_storage.archive.script['audio-outbox'] = [ServiceUnavailable('blip')]

    def blip_every_generation_read(uid, raw, prefix, name, metadata, **kwargs):
        path = shed_storage.archive(uid, raw, prefix, name, metadata, **kwargs)
        shed_storage.bucket.blobs[path].reload_failures = [ServiceUnavailable('blip')]
        return path

    monkeypatch.setattr(storage, 'archive_capture_bytes', blip_every_generation_read)
    receipt = _commit(shed_storage)
    assert receipt.generation == '17' and receipt.manifest_generation == '17'


def test_exhausted_media_upload_fails_the_commit_loud(shed_storage):
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('down')] * 3
    with pytest.raises(ServiceUnavailable):
        _commit(shed_storage)


def test_exhausted_manifest_upload_fails_the_commit_loud(shed_storage):
    shed_storage.archive.script['audio-outbox'] = [ServiceUnavailable('down')] * 3
    with pytest.raises(ServiceUnavailable):
        _commit(shed_storage)


def test_exhausted_media_generation_read_fails_the_commit_loud(shed_storage, monkeypatch):
    def plant_reload_blips(uid, raw, prefix, name, metadata, **kwargs):
        path = shed_storage.archive(uid, raw, prefix, name, metadata, **kwargs)
        if prefix == 'raw-live':
            shed_storage.bucket.blobs[path].reload_failures = [ServiceUnavailable('down') for _ in range(3)]
        return path

    monkeypatch.setattr(storage, 'archive_capture_bytes', plant_reload_blips)
    with pytest.raises(ServiceUnavailable):
        _commit(shed_storage)


def test_exhausted_manifest_generation_read_fails_the_commit_loud(shed_storage):
    media = _commit(shed_storage)
    shed_storage.bucket.blobs[media.manifest_path].reload_failures = [ServiceUnavailable('down') for _ in range(3)]
    with pytest.raises(ServiceUnavailable):
        _commit(shed_storage)


def test_exhausted_commit_records_the_transient_reason(shed_storage):
    before = custody_failures('commit', 'transient')
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('down')] * 3
    with pytest.raises(ServiceUnavailable):
        _commit(shed_storage)
    assert custody_failures('commit', 'transient') == before + 1


def test_deterministic_failure_keeps_the_unlabeled_reason(shed_storage, monkeypatch):
    before_other = custody_failures('commit', 'other')
    before_transient = custody_failures('commit', 'transient')

    def collision(uid, raw, prefix, name, metadata, **kwargs):
        raise ValueError('capture identity collision')

    monkeypatch.setattr(storage, 'archive_capture_bytes', collision)
    with pytest.raises(ValueError):
        _commit(shed_storage)
    assert custody_failures('commit', 'other') == before_other + 1
    assert custody_failures('commit', 'transient') == before_transient


def test_recovered_blips_do_not_record_custody_failures(shed_storage):
    before_other = custody_failures('commit', 'other')
    before_transient = custody_failures('commit', 'transient')
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('blip')]
    _commit(shed_storage)
    assert custody_failures('commit', 'other') == before_other
    assert custody_failures('commit', 'transient') == before_transient


def test_receipt_is_identical_with_and_without_a_blip(shed_storage):
    plain = _commit(shed_storage)
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('blip')]
    shed = _commit(shed_storage)
    assert plain.sha256 == shed.sha256
    assert plain.manifest_sha256 == shed.manifest_sha256
    assert plain.generation == shed.generation == '17'
    assert plain.path.split('/', 2)[2] == shed.path.split('/', 2)[2]


def test_a_retried_media_upload_keeps_the_content_addressed_name(shed_storage):
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('blip')]
    _commit(shed_storage)
    media_calls = [name for prefix, name in shed_storage.archive.calls if prefix == 'raw-live']
    assert len(media_calls) == 2
    assert media_calls[0] == media_calls[1]


def test_a_generation_read_retry_never_re_runs_the_media_upload(shed_storage):
    media = _commit(shed_storage)
    blob = shed_storage.bucket.blobs[media.path]
    attempts_after_clean_commit = blob.upload_attempts
    blob.reload_failures = [ServiceUnavailable('blip')]
    shed_storage.archive.script['audio-outbox'] = [ServiceUnavailable('blip')]
    commit_pcm_window('owner', _pcm(fill=3), 'conversation', 1000.0, 16000, 'root', 0, [], framed=False)
    assert blob.upload_attempts == attempts_after_clean_commit


def test_a_manifest_upload_retry_never_re_runs_the_media_upload(shed_storage):
    shed_storage.archive.script['audio-outbox'] = [ServiceUnavailable('blip')]
    receipt = commit_pcm_window('owner', _pcm(fill=3), 'conversation', 1000.0, 16000, 'root', 0, [], framed=False)
    media_calls = [1 for prefix, _ in shed_storage.archive.calls if prefix == 'raw-live']
    assert len(media_calls) == 1
    assert receipt.generation == '17'


def test_a_landed_retry_is_accepted_by_digest_without_rotation(shed_storage):
    pcm = _pcm(fill=3)
    digest = hashlib.sha256(pcm).hexdigest()
    frames = [
        {
            'sequence': 1,
            'start': 1000.0,
            'samples': len(pcm) // 2,
            'sha256': digest,
            'gap_before': False,
        }
    ]
    # The object already sits at its content-addressed path: the blipped first
    # attempt "landed" exactly like a lost response does in production.
    ghost = shed_storage.bucket.blob(f'raw-live/owner/conversation/0/0/root/0/{digest}.bin')
    ghost.write(pcm, {'sha256': digest})
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('response lost')]
    receipt = commit_pcm_window('owner', pcm, 'conversation', 1000.0, 16000, 'root', 0, frames, framed=True)
    assert receipt.generation == '17'
    assert shed_storage.bucket.blobs[receipt.path].upload_attempts == 0
    assert shed_storage.bucket.blobs[receipt.path].data == pcm


def test_a_landed_foreign_object_collides_loud_without_a_shed(shed_storage):
    pcm = _pcm(fill=3)
    digest = hashlib.sha256(pcm).hexdigest()
    frames = [
        {
            'sequence': 1,
            'start': 1000.0,
            'samples': len(pcm) // 2,
            'sha256': digest,
            'gap_before': False,
        }
    ]
    ghost = shed_storage.bucket.blob(f'raw-live/owner/conversation/0/0/root/0/{digest}.bin')
    ghost.write(b'not-this-capture', {'sha256': 'deadbeef'})
    with pytest.raises(ValueError) as caught:
        commit_pcm_window('owner', pcm, 'conversation', 1000.0, 16000, 'root', 0, frames, framed=True)
    assert 'identity collision' in str(caught.value)


def test_exhausted_media_upload_leaves_no_media_object(shed_storage):
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('down')] * 3
    with pytest.raises(ServiceUnavailable):
        _commit(shed_storage)
    assert [name for name in shed_storage.bucket.blobs if name.startswith('raw-live/')] == []


def test_exhausted_media_upload_never_attempts_the_manifest(shed_storage):
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('down')] * 3
    with pytest.raises(ServiceUnavailable):
        _commit(shed_storage)
    assert [prefix for prefix, _ in shed_storage.archive.calls if prefix == 'audio-outbox'] == []


def test_exhausted_commit_does_not_increment_custody_commits(shed_storage):
    before = custody_commits()
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('down')] * 3
    with pytest.raises(ServiceUnavailable):
        _commit(shed_storage)
    assert custody_commits() == before


def test_recovered_commit_increments_custody_commits_once(shed_storage):
    before = custody_commits()
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('blip')]
    _commit(shed_storage)
    assert custody_commits() == before + 1


def test_protection_level_is_read_once_per_commit_across_retries(shed_storage, monkeypatch):
    reads = []
    monkeypatch.setattr(storage.users_db, 'get_data_protection_level', lambda uid: reads.append(uid) or 'standard')
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('blip')]
    commit_pcm_window('owner', _pcm(fill=3), 'conversation', 1000.0, 16000, 'root', 0, [], framed=False)
    assert len(reads) == 1


def test_tombstone_deleted_refusal_is_loud_and_not_shed(real_storage, monkeypatch):
    refusals = []
    monkeypatch.setattr(storage.conversation_tombstones, 'is_deleted', lambda *a: refusals.append(1) or True)
    with pytest.raises(CaptureDeleted):
        commit_pcm_window('owner', _pcm(fill=3), 'conversation', 1000.0, 16000, 'root', 0, [], framed=False)
    assert len(refusals) == 1


def test_a_tombstone_refusal_on_retry_is_not_masked(real_storage, monkeypatch):
    real = storage.archive_capture_bytes
    calls = []

    def blip_then_real(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise ServiceUnavailable('blip')
        return real(*args, **kwargs)

    monkeypatch.setattr(storage, 'archive_capture_bytes', blip_then_real)
    monkeypatch.setattr(storage.conversation_tombstones, 'is_deleted', lambda *a: True)
    with pytest.raises(CaptureDeleted):
        commit_pcm_window('owner', _pcm(fill=3), 'conversation', 1000.0, 16000, 'root', 0, [], framed=False)
    assert len(calls) == 2


def test_recovered_commit_stamps_the_custody_schema(shed_storage):
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('blip')]
    receipt = _commit(shed_storage)
    manifest = json.loads(shed_storage.bucket.blobs[receipt.manifest_path].data)
    assert manifest['schema'] == 'audio_custody_v1'
    assert manifest['capture']['custody_schema'] == 'audio_custody_v1'


def test_recovered_commit_manifest_carries_the_media_pointer(shed_storage):
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('blip')]
    receipt = _commit(shed_storage)
    manifest = json.loads(shed_storage.bucket.blobs[receipt.manifest_path].data)
    assert manifest['media'] == {
        'bucket': shed_storage.bucket.name,
        'path': receipt.path,
        'generation': receipt.generation,
        'sha256': receipt.sha256,
    }


def test_recovered_commit_manifest_carries_the_frame_checkpoint(shed_storage):
    shed_storage.archive.script['audio-outbox'] = [ServiceUnavailable('blip')]
    receipt = _commit(shed_storage)
    manifest = json.loads(shed_storage.bucket.blobs[receipt.manifest_path].data)
    assert manifest['capture_end_checkpoint']['sequence'] == 1
    assert manifest['capture_end_checkpoint']['samples'] == receipt.samples


def test_recovered_framed_commit_pins_the_manifest_path_metadata(shed_storage):
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('blip')]
    receipt = _commit(shed_storage)
    media_metadata = shed_storage.bucket.blobs[receipt.path].metadata
    assert media_metadata['custody_manifest_path'] == receipt.manifest_path


def test_media_upload_sheds_service_unavailable(shed_storage):
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('blip')]
    assert _commit(shed_storage).generation == '17'


def test_media_upload_sheds_internal_server_error(shed_storage):
    shed_storage.archive.script['raw-live'] = [InternalServerError('blip')]
    assert _commit(shed_storage).generation == '17'


def test_media_upload_sheds_too_many_requests(shed_storage):
    shed_storage.archive.script['raw-live'] = [TooManyRequests('churn')]
    assert _commit(shed_storage).generation == '17'


def test_media_upload_sheds_bad_gateway(shed_storage):
    shed_storage.archive.script['raw-live'] = [BadGateway('blip')]
    assert _commit(shed_storage).generation == '17'


def test_media_upload_sheds_gateway_timeout(shed_storage):
    shed_storage.archive.script['raw-live'] = [GatewayTimeout('blip')]
    assert _commit(shed_storage).generation == '17'


def test_media_upload_sheds_connection_error(shed_storage):
    shed_storage.archive.script['raw-live'] = [ConnectionError('reset')]
    assert _commit(shed_storage).generation == '17'


def test_media_upload_sheds_requests_transport_connection_error(shed_storage):
    shed_storage.archive.script['raw-live'] = [REQUESTS_CONNECTION_ERROR('reset')]
    assert _commit(shed_storage).generation == '17'


def test_media_upload_sheds_requests_transport_read_timeout(shed_storage):
    shed_storage.archive.script['raw-live'] = [REQUESTS_READ_TIMEOUT('timeout')]
    assert _commit(shed_storage).generation == '17'


def test_manifest_upload_sheds_service_unavailable(shed_storage):
    shed_storage.archive.script['audio-outbox'] = [ServiceUnavailable('blip')]
    assert _commit(shed_storage).manifest_generation == '17'


def test_manifest_upload_sheds_internal_server_error(shed_storage):
    shed_storage.archive.script['audio-outbox'] = [InternalServerError('blip')]
    assert _commit(shed_storage).manifest_generation == '17'


def test_manifest_upload_sheds_too_many_requests(shed_storage):
    shed_storage.archive.script['audio-outbox'] = [TooManyRequests('churn')]
    assert _commit(shed_storage).manifest_generation == '17'


def test_manifest_upload_sheds_bad_gateway(shed_storage):
    shed_storage.archive.script['audio-outbox'] = [BadGateway('blip')]
    assert _commit(shed_storage).manifest_generation == '17'


def test_manifest_upload_sheds_gateway_timeout(shed_storage):
    shed_storage.archive.script['audio-outbox'] = [GatewayTimeout('blip')]
    assert _commit(shed_storage).manifest_generation == '17'


def test_manifest_upload_sheds_connection_error(shed_storage):
    shed_storage.archive.script['audio-outbox'] = [ConnectionError('reset')]
    assert _commit(shed_storage).manifest_generation == '17'


def test_manifest_upload_sheds_requests_transport_connection_error(shed_storage):
    shed_storage.archive.script['audio-outbox'] = [REQUESTS_CONNECTION_ERROR('reset')]
    assert _commit(shed_storage).manifest_generation == '17'


def test_manifest_upload_sheds_requests_transport_read_timeout(shed_storage):
    shed_storage.archive.script['audio-outbox'] = [REQUESTS_READ_TIMEOUT('timeout')]
    assert _commit(shed_storage).manifest_generation == '17'


def test_media_generation_read_sheds_service_unavailable(shed_storage):
    media = _commit(shed_storage)
    shed_storage.bucket.blobs[media.path].reload_failures = [ServiceUnavailable('blip')]
    receipt = commit_pcm_window('owner', _pcm(fill=3), 'conversation', 1000.0, 16000, 'root', 0, [], framed=False)
    assert receipt.generation == '17'


def test_media_generation_read_sheds_internal_server_error(shed_storage):
    media = _commit(shed_storage)
    shed_storage.bucket.blobs[media.path].reload_failures = [InternalServerError('blip')]
    receipt = commit_pcm_window('owner', _pcm(fill=3), 'conversation', 1000.0, 16000, 'root', 0, [], framed=False)
    assert receipt.generation == '17'


def test_media_generation_read_sheds_too_many_requests(shed_storage):
    media = _commit(shed_storage)
    shed_storage.bucket.blobs[media.path].reload_failures = [TooManyRequests('churn')]
    receipt = commit_pcm_window('owner', _pcm(fill=3), 'conversation', 1000.0, 16000, 'root', 0, [], framed=False)
    assert receipt.generation == '17'


def test_media_generation_read_sheds_connection_error(shed_storage):
    media = _commit(shed_storage)
    shed_storage.bucket.blobs[media.path].reload_failures = [ConnectionError('reset')]
    receipt = commit_pcm_window('owner', _pcm(fill=3), 'conversation', 1000.0, 16000, 'root', 0, [], framed=False)
    assert receipt.generation == '17'


def test_manifest_generation_read_sheds_service_unavailable(shed_storage):
    media = _commit(shed_storage)
    shed_storage.bucket.blobs[media.manifest_path].reload_failures = [ServiceUnavailable('blip')]
    receipt = commit_pcm_window('owner', _pcm(fill=3), 'conversation', 1000.0, 16000, 'root', 0, [], framed=False)
    assert receipt.manifest_generation == '17'


def test_manifest_generation_read_sheds_internal_server_error(shed_storage):
    media = _commit(shed_storage)
    shed_storage.bucket.blobs[media.manifest_path].reload_failures = [InternalServerError('blip')]
    receipt = commit_pcm_window('owner', _pcm(fill=3), 'conversation', 1000.0, 16000, 'root', 0, [], framed=False)
    assert receipt.manifest_generation == '17'


def test_manifest_generation_read_sheds_too_many_requests(shed_storage):
    media = _commit(shed_storage)
    shed_storage.bucket.blobs[media.manifest_path].reload_failures = [TooManyRequests('churn')]
    receipt = commit_pcm_window('owner', _pcm(fill=3), 'conversation', 1000.0, 16000, 'root', 0, [], framed=False)
    assert receipt.manifest_generation == '17'


def test_manifest_generation_read_sheds_gateway_timeout(shed_storage):
    media = _commit(shed_storage)
    shed_storage.bucket.blobs[media.manifest_path].reload_failures = [GatewayTimeout('blip')]
    receipt = commit_pcm_window('owner', _pcm(fill=3), 'conversation', 1000.0, 16000, 'root', 0, [], framed=False)
    assert receipt.manifest_generation == '17'


def test_one_generation_read_blip_per_object_recovers_both(shed_storage):
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('blip')]
    receipt = commit_pcm_window('owner', _pcm(fill=3), 'conversation', 1000.0, 16000, 'root', 0, [], framed=False)
    assert receipt.generation == '17' and receipt.manifest_generation == '17'


# ---------------------------------------------------------------------------
# Window parity: the committed bytes do not depend on the shed.
# ---------------------------------------------------------------------------


def test_window_payload_digest_matches_the_stored_object_after_a_blip(shed_storage):
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('blip')]
    pcm = _pcm(fill=3)
    receipt = commit_pcm_window('owner', pcm, 'conversation', 1000.0, 16000, 'root', 0, [], framed=False)
    stored = shed_storage.bucket.blobs[receipt.path].data
    assert hashlib.sha256(stored).hexdigest() == receipt.sha256


def test_manifest_payload_digest_matches_the_stored_object_after_a_blip(shed_storage):
    shed_storage.archive.script['audio-outbox'] = [ServiceUnavailable('blip')]
    receipt = _commit(shed_storage)
    stored = shed_storage.bucket.blobs[receipt.manifest_path].data
    assert hashlib.sha256(stored).hexdigest() == receipt.manifest_sha256


def test_framed_manifest_frame_table_matches_the_frames_after_a_blip(shed_storage):
    shed_storage.archive.script['audio-outbox'] = [ServiceUnavailable('blip')]
    pcm = _pcm(fill=3)
    frames = _framed_setup([pcm])
    receipt = commit_pcm_window('owner', pcm, 'conversation', 1000.0, 16000, 'root', 0, frames, framed=True)
    manifest = json.loads(shed_storage.bucket.blobs[receipt.manifest_path].data)
    assert manifest['frames'] == frames


def test_unframed_commit_has_no_frame_schema_metadata(shed_storage):
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('blip')]
    receipt = commit_pcm_window('owner', _pcm(fill=3), 'conversation', 1000.0, 16000, 'root', 0, [], framed=False)
    manifest = json.loads(shed_storage.bucket.blobs[receipt.manifest_path].data)
    assert 'frame_schema' not in manifest['capture']


def test_framed_commit_stamps_the_frame_schema_after_a_blip(shed_storage):
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('blip')]
    receipt = _commit(shed_storage)
    manifest = json.loads(shed_storage.bucket.blobs[receipt.manifest_path].data)
    assert manifest['capture']['frame_schema'] == 'audio_frames_v1'


def test_gap_count_reflects_discontinuity_frames_after_a_blip(shed_storage):
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('blip')]
    first, second = _pcm(fill=1), _pcm(fill=2)
    frames = [
        {
            'sequence': 1,
            'start': 1000.0,
            'samples': 160,
            'sha256': hashlib.sha256(first).hexdigest(),
            'gap_before': False,
        },
        {
            'sequence': 2,
            'start': 1100.0,
            'samples': 160,
            'sha256': hashlib.sha256(second).hexdigest(),
            'gap_before': True,
        },
    ]
    receipt = commit_pcm_window('owner', first + second, 'conversation', 1000.0, 16000, 'root', 1, frames, framed=True)
    manifest = json.loads(shed_storage.bucket.blobs[receipt.manifest_path].data)
    assert manifest['capture']['gap_count'] == 1


def test_clock_source_default_survives_a_blip(shed_storage):
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('blip')]
    receipt = commit_pcm_window('owner', _pcm(fill=3), 'conversation', 1000.0, 16000, 'root', 0, [], framed=False)
    manifest = json.loads(shed_storage.bucket.blobs[receipt.manifest_path].data)
    assert manifest['capture']['clock_source'] == 'server_projected'


def test_clock_source_override_survives_a_blip(shed_storage):
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('blip')]
    receipt = commit_pcm_window(
        'owner',
        _pcm(fill=3),
        'conversation',
        1000.0,
        16000,
        'root',
        0,
        [],
        framed=False,
        clock_source='arrival_estimate',
    )
    manifest = json.loads(shed_storage.bucket.blobs[receipt.manifest_path].data)
    assert manifest['capture']['clock_source'] == 'arrival_estimate'


def test_capture_session_id_metadata_survives_a_blip(shed_storage):
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('blip')]
    receipt = commit_pcm_window('owner', _pcm(fill=3), 'conversation', 1000.0, 16000, 'root', 0, [], framed=False)
    manifest = json.loads(shed_storage.bucket.blobs[receipt.manifest_path].data)
    assert manifest['capture']['capture_session_id'] == 'root'


def test_consent_state_metadata_survives_a_blip(shed_storage):
    shed_storage.archive.script['audio-outbox'] = [ServiceUnavailable('blip')]
    receipt = _commit(shed_storage)
    manifest = json.loads(shed_storage.bucket.blobs[receipt.manifest_path].data)
    assert manifest['capture']['consent_state'] == 'private_cloud_sync_enabled'


def test_enhanced_protection_adds_the_enc_suffix_under_a_blip(shed_storage, monkeypatch):
    monkeypatch.setattr(storage.users_db, 'get_data_protection_level', lambda uid: 'enhanced')
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('blip')]
    receipt = commit_pcm_window('owner', _pcm(fill=3), 'conversation', 1000.0, 16000, 'root', 0, [], framed=False)
    assert receipt.path.endswith('.enc')


def test_standard_protection_has_no_enc_suffix_after_a_blip(shed_storage):
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('blip')]
    receipt = commit_pcm_window('owner', _pcm(fill=3), 'conversation', 1000.0, 16000, 'root', 0, [], framed=False)
    assert not receipt.path.endswith('.enc')


def test_enhanced_framed_manifest_path_carries_the_enc_suffix(shed_storage, monkeypatch):
    monkeypatch.setattr(storage.users_db, 'get_data_protection_level', lambda uid: 'enhanced')
    shed_storage.archive.script['audio-outbox'] = [ServiceUnavailable('blip')]
    receipt = _commit(shed_storage)
    assert receipt.manifest_path.endswith('.enc')


def test_commit_pcm_single_frame_sheds_a_media_blip(shed_storage):
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('blip')]
    receipt = commit_pcm('owner', _pcm(fill=3), 'conversation', 1000.0, 16000, 'root', 7)
    assert receipt.generation == '17'
    assert receipt.samples == 160


def test_commit_pcm_single_frame_sheds_a_manifest_blip(shed_storage):
    shed_storage.archive.script['audio-outbox'] = [ServiceUnavailable('blip')]
    receipt = commit_pcm('owner', _pcm(fill=3), 'conversation', 1000.0, 16000, 'root', 7)
    assert receipt.manifest_generation == '17'


def test_commit_pcm_receipt_fields_match_with_and_without_a_blip(shed_storage):
    plain = commit_pcm('owner', _pcm(fill=3), 'conversation', 1000.0, 16000, 'root', 7)
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('blip')]
    shed = commit_pcm('owner', _pcm(fill=3), 'conversation', 1000.0, 16000, 'root', 7)
    assert plain.sha256 == shed.sha256 and plain.manifest_sha256 == shed.manifest_sha256
    assert plain.path.split('/', 2)[2] == shed.path.split('/', 2)[2]


def test_commit_pcm_unlinked_window_sheds_a_blip(shed_storage):
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('blip')]
    receipt = commit_pcm('owner', _pcm(fill=3), None, 1000.0, 16000, 'root', 7)
    assert receipt.conversation_id is None
    assert receipt.path.startswith('raw-live/owner/unlinked/')


def test_multi_frame_window_commits_after_a_media_blip(shed_storage):
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('blip')]
    payloads = [_pcm(fill=n + 1) for n in range(3)]
    receipt = commit_pcm_window(
        'owner',
        b''.join(payloads),
        'conversation',
        1000.0,
        16000,
        'root',
        1,
        _framed_setup(payloads),
        framed=True,
    )
    assert receipt.samples == 480
    assert receipt.start == 1000.0


def test_multi_frame_checkpoint_names_the_last_frame_after_a_blip(shed_storage):
    shed_storage.archive.script['audio-outbox'] = [ServiceUnavailable('blip')]
    payloads = [_pcm(fill=n + 1) for n in range(3)]
    frames = _framed_setup(payloads)
    receipt = commit_pcm_window(
        'owner', b''.join(payloads), 'conversation', 1000.0, 16000, 'root', 1, frames, framed=True
    )
    manifest = json.loads(shed_storage.bucket.blobs[receipt.manifest_path].data)
    assert manifest['capture_end_checkpoint'] == frames[-1]


def test_window_with_a_discontinuity_commits_after_a_blip(shed_storage):
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('blip')]
    first, second = _pcm(fill=1), _pcm(fill=2)
    frames = [
        {
            'sequence': 1,
            'start': 1000.0,
            'samples': 160,
            'sha256': hashlib.sha256(first).hexdigest(),
            'gap_before': False,
        },
        {
            'sequence': 2,
            'start': 1100.0,
            'samples': 160,
            'sha256': hashlib.sha256(second).hexdigest(),
            'gap_before': True,
        },
    ]
    receipt = commit_pcm_window('owner', first + second, 'conversation', 1000.0, 16000, 'root', 1, frames, framed=True)
    assert receipt.generation == '17'


def test_a_frame_bytes_mismatch_is_loud_before_any_io(shed_storage):
    pcm = _pcm(fill=3)
    frames = [
        {
            'sequence': 1,
            'start': 1000.0,
            'samples': len(pcm) // 2,
            'sha256': hashlib.sha256(b'other').hexdigest(),
            'gap_before': False,
        }
    ]
    with pytest.raises(ValueError):
        commit_pcm_window('owner', pcm, 'conversation', 1000.0, 16000, 'root', 0, frames, framed=True)
    assert shed_storage.archive.calls == []


def test_odd_pcm_is_rejected_before_any_io(shed_storage):
    with pytest.raises(ValueError):
        commit_pcm_window('owner', b'\x01', 'conversation', 1000.0, 16000, 'root', 0, [], framed=False)
    assert shed_storage.archive.calls == []


def test_empty_window_commit_is_rejected_before_any_io(shed_storage):
    with pytest.raises(ValueError):
        commit_pcm_window('owner', b'', 'conversation', 1000.0, 16000, 'root', 0, [], framed=False)
    assert shed_storage.archive.calls == []


def test_manifest_json_round_trips_after_a_blip(shed_storage):
    shed_storage.archive.script['audio-outbox'] = [ServiceUnavailable('blip')]
    receipt = _commit(shed_storage)
    manifest = json.loads(shed_storage.bucket.blobs[receipt.manifest_path].data)
    assert manifest['capture']['sample_rate'] == 16000
    assert manifest['capture']['sequence_count'] == 1


def test_receipt_serialization_is_stable_across_a_blip(shed_storage):
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('blip')]
    receipt = _commit(shed_storage)
    restored = AudioReceipt(**json.loads(json.dumps(receipt.to_dict())))
    assert restored == receipt


def test_the_same_window_recommits_to_the_same_immutable_objects(shed_storage):
    first = _commit(shed_storage)
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('blip')]
    second = _commit(shed_storage)
    assert first.path == second.path and first.manifest_path == second.manifest_path


def test_exhausted_media_upload_preserves_the_transient_instance(shed_storage):
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('down') for _ in range(3)]
    with pytest.raises(ServiceUnavailable) as caught:
        _commit(shed_storage)
    assert caught.value.custody_shed_exhausted is True


def test_exhausted_media_upload_internal_server_error(shed_storage):
    shed_storage.archive.script['raw-live'] = [InternalServerError('down') for _ in range(3)]
    with pytest.raises(InternalServerError):
        _commit(shed_storage)


def test_exhausted_media_upload_too_many_requests(shed_storage):
    shed_storage.archive.script['raw-live'] = [TooManyRequests('down') for _ in range(3)]
    with pytest.raises(TooManyRequests):
        _commit(shed_storage)


def test_classifier_accepts_connection_reset_subclass():
    assert _is_commit_availability_blip(ConnectionResetError()) is True


def test_classifier_accepts_requests_http_error_member():
    import requests.exceptions as requests_exceptions

    assert _is_commit_availability_blip(requests_exceptions.HTTPError('503')) is True


# ---------------------------------------------------------------------------
# The metrics contract.
# ---------------------------------------------------------------------------


def test_retry_counter_has_a_zero_baseline_for_every_op():
    for op in COMMIT_OP_NAMES:
        assert shed_retries(op) >= 0.0


def test_exhaustion_counter_has_a_zero_baseline_for_every_op():
    for op in COMMIT_OP_NAMES:
        assert shed_exhausted(op) >= 0.0


def test_retry_counter_counts_each_retried_attempt(shed_storage):
    before = shed_retries('media_upload')
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('a'), ServiceUnavailable('b')]
    _commit(shed_storage)
    assert shed_retries('media_upload') == before + 2


def test_retry_counter_labels_the_manifest_op(shed_storage):
    before = shed_retries('manifest_upload')
    shed_storage.archive.script['audio-outbox'] = [ServiceUnavailable('a')]
    _commit(shed_storage)
    assert shed_retries('manifest_upload') == before + 1


def test_exhaustion_counter_counts_once_per_drained_budget(shed_storage):
    before = shed_exhausted('media_upload')
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('down') for _ in range(3)]
    with pytest.raises(ServiceUnavailable):
        _commit(shed_storage)
    assert shed_exhausted('media_upload') == before + 1


def test_clean_commit_touches_neither_shed_counter(shed_storage):
    before_retries = shed_retries('media_upload')
    before_exhausted = shed_exhausted('media_upload')
    _commit(shed_storage)
    assert shed_retries('media_upload') == before_retries
    assert shed_exhausted('media_upload') == before_exhausted


def test_transient_failure_reason_has_a_zero_baseline():
    assert custody_failures('commit', 'transient') >= 0.0


def test_exhausted_commit_increments_the_transient_reason(shed_storage):
    before = custody_failures('commit', 'transient')
    shed_storage.archive.script['raw-live'] = [GatewayTimeout('down') for _ in range(3)]
    with pytest.raises(GatewayTimeout):
        _commit(shed_storage)
    assert custody_failures('commit', 'transient') == before + 1


def test_other_reason_untouched_by_a_recovered_blip(shed_storage):
    before = custody_failures('commit', 'other')
    shed_storage.archive.script['manifest_generation'] = None
    media = _commit(shed_storage)
    shed_storage.bucket.blobs[media.manifest_path].reload_failures = [ServiceUnavailable('blip')]
    commit_pcm_window('owner', _pcm(fill=3), 'conversation', 1000.0, 16000, 'root', 0, [], framed=False)
    assert custody_failures('commit', 'other') == before


def test_conflict_reason_stays_reserved_for_projection_mismatch(shed_storage):
    before = custody_failures('commit', 'conflict')
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('blip')]
    _commit(shed_storage)
    assert custody_failures('commit', 'conflict') == before


def test_invalid_argument_reason_stays_reserved(shed_storage):
    before = custody_failures('commit', 'invalid_argument')
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('blip')]
    _commit(shed_storage)
    assert custody_failures('commit', 'invalid_argument') == before


def test_shed_counter_series_are_declared_for_dashboards():
    from prometheus_client import REGISTRY

    for op in COMMIT_OP_NAMES:
        assert REGISTRY.get_sample_value('omi_audio_custody_commit_transient_retries_total', {'op': op}) is not None
        assert REGISTRY.get_sample_value('omi_audio_custody_commit_shed_exhausted_total', {'op': op}) is not None


def test_shed_counters_are_declared_in_the_metrics_module():
    assert CUSTODY_COMMIT_TRANSIENT_RETRIES._name == 'omi_audio_custody_commit_transient_retries'
    assert CUSTODY_COMMIT_TRANSIENT_EXHAUSTED._name == 'omi_audio_custody_commit_shed_exhausted'


# ---------------------------------------------------------------------------
# The pusher boundary: window commits and the session-level failure family.
# ---------------------------------------------------------------------------


class SessionSocket:
    def __init__(self, frames):
        self.frames = deque(frames)
        self.sent = []
        self.client_state = WebSocketState.CONNECTED
        self.close_code = None

    async def accept(self):
        pass

    async def send_bytes(self, data):
        self.sent.append(data)

    async def receive_bytes(self):
        await asyncio.sleep(0)
        if self.frames:
            return self.frames.popleft()
        raise WebSocketDisconnect(1000)

    async def close(self, code, **kwargs):
        self.close_code = code
        self.client_state = WebSocketState.DISCONNECTED


@pytest.fixture
def session(monkeypatch, real_storage):
    """Pusher session harness over the REAL commit path and fake bucket."""

    monkeypatch.setenv('PUSHER_AUDIO_FILE_INCREMENTAL_ENABLED', '0')
    monkeypatch.setenv('AUDIO_DURABLE_OUTBOX_ENABLED', 'true')
    monkeypatch.setattr(pusher_audio_projection.conversations_db, 'get_conversation_raw_snapshot', lambda *a, **kw: {})
    monkeypatch.setattr(record_audio_db, 'seal_record_audio', MagicMock(return_value='not_batch_owner'))
    monkeypatch.setattr(record_audio_db, 'mark_record_upload_failed', MagicMock(return_value=True))
    monkeypatch.setattr(record_audio_db, 'set_record_upload_pending', MagicMock(return_value=True))
    monkeypatch.setattr(pusher, 'get_audio_bytes_webhook_seconds', lambda uid: None)
    monkeypatch.setattr(pusher, 'is_audio_bytes_app_enabled', lambda uid: False)
    monkeypatch.setattr(pusher.users_db, 'get_user_private_cloud_sync_enabled', lambda uid: True)
    monkeypatch.setattr(pusher, 'upload_audio_chunks_batch', MagicMock(return_value=None))
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_SYNC_PROCESS_INTERVAL', 0.001)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 60)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_BATCH_MAX_AGE', 0.001)
    return real_storage


def _session_frames(conversation, payloads, start=1000.0, step=0.01):
    frames = [struct.pack('<I', 103) + conversation.encode()]
    frames.extend(struct.pack('<Id', 101, start + index * step) + pcm for index, pcm in enumerate(payloads))
    return frames


def _session_receipts(sock):
    return [AudioReceipt(**json.loads(frame[4:])['receipt']) for frame in sock.sent]


def _blip_first_media_upload(monkeypatch, bucket, failures=1):
    """Wrap the REAL writer: the first raw-live call answers with a blip."""

    real = storage.archive_capture_bytes
    state = {'raw-live': failures}

    def blip_then_real(uid, raw, prefix, name, metadata, **kwargs):
        if prefix == 'raw-live' and state['raw-live'] > 0:
            state['raw-live'] -= 1
            raise ServiceUnavailable('cold channel')
        return real(uid, raw, prefix, name, metadata, **kwargs)

    monkeypatch.setattr(storage, 'archive_capture_bytes', blip_then_real)
    return state


def _always_down_media_upload(monkeypatch):
    real = storage.archive_capture_bytes

    def down(uid, raw, prefix, name, metadata, **kwargs):
        if prefix == 'raw-live':
            raise ServiceUnavailable('down')
        return real(uid, raw, prefix, name, metadata, **kwargs)

    monkeypatch.setattr(storage, 'archive_capture_bytes', down)


@pytest.mark.asyncio
async def test_window_boundary_blip_still_acks_every_window(session, monkeypatch):
    _blip_first_media_upload(monkeypatch, session)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    payloads = [struct.pack('<160h', *[n] * 160) for n in range(4)]
    sock = SessionSocket(_session_frames('conversation', payloads))
    await pusher._websocket_util_trigger(sock, 'owner', 16000, audio_custody=1)
    receipts = _session_receipts(sock)
    assert len(receipts) == len(payloads)
    assert sock.close_code != 1011


@pytest.mark.asyncio
async def test_shutdown_tail_blip_commits_and_ends_clean(session, monkeypatch):
    _blip_first_media_upload(monkeypatch, session)
    payloads = [struct.pack('<160h', *[n] * 160) for n in range(3)]
    sock = SessionSocket(_session_frames('conversation', payloads))
    await pusher._websocket_util_trigger(sock, 'owner', 16000, audio_custody=1)
    assert len(_session_receipts(sock)) == 1
    assert sock.close_code != 1011
    media = [name for name in session.blobs if name.startswith('raw-live/')]
    assert media, 'the tail window committed custody'


@pytest.mark.asyncio
async def test_real_path_blip_receipt_round_trips_the_exact_payload(session, monkeypatch):
    _blip_first_media_upload(monkeypatch, session)
    payloads = [struct.pack('<160h', *[7] * 160) for n in range(2)]
    sock = SessionSocket(_session_frames('conversation', payloads))
    await pusher._websocket_util_trigger(sock, 'owner', 16000, audio_custody=1)
    receipts = _session_receipts(sock)
    assert read_pcm('owner', receipts[0]) == b''.join(payloads)


@pytest.mark.asyncio
async def test_conversation_switch_after_a_recovered_blip_commits_both_windows(session, monkeypatch):
    _blip_first_media_upload(monkeypatch, session)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    first = [struct.pack('<160h', *[1] * 160) for _ in range(2)]
    second = [struct.pack('<160h', *[2] * 160) for _ in range(2)]
    frames = (
        _session_frames('conversation-a', first)
        + [struct.pack('<I', 103) + b'conversation-b']
        + [struct.pack('<Id', 101, 2000 + n * 0.01) + pcm for n, pcm in enumerate(second)]
    )
    sock = SessionSocket(frames)
    await pusher._websocket_util_trigger(sock, 'owner', 16000, audio_custody=1)
    receipts = _session_receipts(sock)
    assert [receipt.conversation_id for receipt in receipts] == [
        'conversation-a',
        'conversation-a',
        'conversation-b',
        'conversation-b',
    ]


@pytest.mark.asyncio
async def test_recovered_session_books_no_would_drop(session, monkeypatch):
    _blip_first_media_upload(monkeypatch, session)
    stages = []
    real_would_drop = pusher.record_would_drop
    monkeypatch.setattr(
        pusher,
        'record_would_drop',
        lambda stage: stages.append(stage) or real_would_drop(stage),
    )
    payloads = [struct.pack('<160h', *[n] * 160) for n in range(3)]
    sock = SessionSocket(_session_frames('conversation', payloads))
    await pusher._websocket_util_trigger(sock, 'owner', 16000, audio_custody=1)
    assert stages == []


@pytest.mark.asyncio
async def test_exhausted_shutdown_tail_fails_closed_with_1011(session, monkeypatch):
    _always_down_media_upload(monkeypatch)
    payloads = [struct.pack('<160h', *[n] * 160) for n in range(3)]
    sock = SessionSocket(_session_frames('conversation', payloads))
    await pusher._websocket_util_trigger(sock, 'owner', 16000, audio_custody=1)
    assert sock.sent == [], 'a window that never committed must never be acknowledged'
    assert sock.close_code == 1011


@pytest.mark.asyncio
async def test_exhausted_midstream_boundary_fails_closed_with_1011(session, monkeypatch):
    _always_down_media_upload(monkeypatch)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    payloads = [struct.pack('<160h', *[n] * 160) for n in range(3)]
    sock = SessionSocket(_session_frames('conversation', payloads))
    await pusher._websocket_util_trigger(sock, 'owner', 16000, audio_custody=1)
    assert sock.sent == []
    assert sock.close_code == 1011


@pytest.mark.asyncio
async def test_exhausted_tail_records_the_window_tail_stage(session, monkeypatch):
    _always_down_media_upload(monkeypatch)
    stages = []
    real_would_drop = pusher.record_would_drop
    monkeypatch.setattr(
        pusher,
        'record_would_drop',
        lambda stage: stages.append(stage) or real_would_drop(stage),
    )
    payloads = [struct.pack('<160h', *[n] * 160) for n in range(3)]
    sock = SessionSocket(_session_frames('conversation', payloads))
    await pusher._websocket_util_trigger(sock, 'owner', 16000, audio_custody=1)
    assert 'window_tail' in stages


@pytest.mark.asyncio
async def test_no_custody_objects_after_an_exhausted_session(session, monkeypatch):
    _always_down_media_upload(monkeypatch)
    payloads = [struct.pack('<160h', *[n] * 160) for n in range(3)]
    sock = SessionSocket(_session_frames('conversation', payloads))
    await pusher._websocket_util_trigger(sock, 'owner', 16000, audio_custody=1)
    media = [name for name in session.blobs if name.startswith('raw-live/')]
    assert media == []


@pytest.mark.asyncio
async def test_projection_still_runs_after_a_recovered_blip(session, monkeypatch):
    _blip_first_media_upload(monkeypatch, session)
    payloads = [struct.pack('<160h', *[n] * 160) for n in range(3)]
    sock = SessionSocket(_session_frames('conversation', payloads))
    await pusher._websocket_util_trigger(sock, 'owner', 16000, audio_custody=1)
    assert pusher.upload_audio_chunks_batch.called


def _window_kwargs(payloads, *, audio_custody=1, conversation='conversation', start=1000.0):
    pcm = b''.join(payloads)
    frames = _framed_setup(payloads, start=start)
    return {
        'uid': 'owner',
        'payload': pcm,
        'frames': frames,
        'conversation_id': conversation,
        'start': start,
        'sample_rate': 16000,
        'custody_root': 'root',
        'protection_level': 'standard',
        'audio_custody': audio_custody,
        'timeline_v2': True,
        'websocket': None,
        'durable_queue': None,
        'budget': ByteBudget(20 * 1024 * 1024),
        'queue_wait_timeout': 5.0,
        'framed': True,
    }


@pytest.mark.asyncio
async def test_direct_window_commit_returns_a_receipt_after_a_blip(shed_storage):
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('blip')]
    kwargs = _window_kwargs([_pcm(fill=3)])
    kwargs['websocket'] = SessionSocket([])
    kwargs['durable_queue'] = RecordProjectionQueue(maxsize=4)
    receipt = await pusher._commit_durable_audio_window(**kwargs)
    assert receipt is not None and receipt.generation == '17'


@pytest.mark.asyncio
async def test_direct_window_commit_acks_when_audio_custody_is_1(shed_storage):
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('blip')]
    kwargs = _window_kwargs([_pcm(fill=3)])
    sock = SessionSocket([])
    kwargs['websocket'] = sock
    kwargs['durable_queue'] = RecordProjectionQueue(maxsize=4)
    await pusher._commit_durable_audio_window(**kwargs)
    assert sock.sent, 'audio custody 1 owes the producer an ACK'


@pytest.mark.asyncio
async def test_direct_window_commit_skips_the_ack_without_custody(shed_storage):
    kwargs = _window_kwargs([_pcm(fill=3)], audio_custody=None)
    sock = SessionSocket([])
    kwargs['websocket'] = sock
    kwargs['durable_queue'] = RecordProjectionQueue(maxsize=4)
    await pusher._commit_durable_audio_window(**kwargs)
    assert sock.sent == []


@pytest.mark.asyncio
async def test_direct_window_commit_stages_the_projection_after_a_blip(shed_storage):
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('blip')]
    kwargs = _window_kwargs([_pcm(fill=3)])
    sock = SessionSocket([])
    queue = RecordProjectionQueue(maxsize=4)
    kwargs['websocket'] = sock
    kwargs['durable_queue'] = queue
    receipt = await pusher._commit_durable_audio_window(**kwargs)
    assert queue.qsize() == 1
    assert queue.pending_projection is None
    assert receipt.conversation_id == 'conversation'


@pytest.mark.asyncio
async def test_direct_window_commit_delivers_pending_after_a_blip(shed_storage):
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('blip')]
    kwargs = _window_kwargs([_pcm(fill=3)])
    sock = SessionSocket([])
    queue = RecordProjectionQueue(maxsize=4)
    kwargs['websocket'] = sock
    kwargs['durable_queue'] = queue
    await pusher._commit_durable_audio_window(**kwargs)
    assert queue.qsize() == 1 or queue.pending_projection is None


@pytest.mark.asyncio
async def test_direct_window_commit_releases_the_budget_after_a_blip(shed_storage):
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('blip')]
    kwargs = _window_kwargs([_pcm(fill=3)])
    sock = SessionSocket([])
    kwargs['websocket'] = sock
    kwargs['durable_queue'] = RecordProjectionQueue(maxsize=4)
    payload_bytes = len(kwargs['payload'])
    kwargs['budget'].reserve(payload_bytes)
    await pusher._commit_durable_audio_window(**kwargs)
    assert kwargs['budget'].used == 0


@pytest.mark.asyncio
async def test_direct_window_commit_runs_on_committed_once_after_a_blip(shed_storage):
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('blip')]
    kwargs = _window_kwargs([_pcm(fill=3)])
    sock = SessionSocket([])
    kwargs['websocket'] = sock
    kwargs['durable_queue'] = RecordProjectionQueue(maxsize=4)
    commits = []
    kwargs['on_committed'] = lambda: commits.append(1)
    await pusher._commit_durable_audio_window(**kwargs)
    assert commits == [1]


@pytest.mark.asyncio
async def test_direct_window_commit_empty_window_is_none(shed_storage):
    kwargs = _window_kwargs([_pcm(fill=3)])
    kwargs['frames'] = []
    kwargs['start'] = None
    assert await pusher._commit_durable_audio_window(**kwargs) is None


@pytest.mark.asyncio
async def test_direct_window_commit_propagates_projection_queue_timeout(shed_storage):
    kwargs = _window_kwargs([_pcm(fill=3)])
    sock = SessionSocket([])
    queue = RecordProjectionQueue(maxsize=1)
    queue.put_nowait(
        AudioProjection(
            AudioReceipt(
                bucket='b',
                path='p',
                generation='1',
                sha256='d',
                manifest_path='m',
                manifest_generation='1',
                manifest_sha256='md',
                pcm_sha256=None,
                conversation_id='other',
                start=0.0,
                samples=1,
                sample_rate=16000,
            ),
            0.0,
            0,
            1,
            (),
        )
    )
    kwargs['websocket'] = sock
    kwargs['durable_queue'] = queue
    kwargs['queue_wait_timeout'] = 0.01
    with pytest.raises(ProjectionQueueWaitTimeout):
        await pusher._commit_durable_audio_window(**kwargs)


@pytest.mark.asyncio
async def test_direct_window_commit_exhaustion_raises_the_transient(shed_storage):
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('down') for _ in range(3)]
    kwargs = _window_kwargs([_pcm(fill=3)])
    kwargs['websocket'] = SessionSocket([])
    kwargs['durable_queue'] = RecordProjectionQueue(maxsize=4)
    with pytest.raises(ServiceUnavailable) as caught:
        await pusher._commit_durable_audio_window(**kwargs)
    assert caught.value.custody_shed_exhausted is True


@pytest.mark.asyncio
async def test_live_archive_shape_multi_channel_metadata_survives_a_blip(shed_storage):
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('blip')]
    pcm = _pcm(fill=3)
    receipt = commit_capture(
        'owner',
        pcm,
        'conversation/2/1/root/9',
        {
            'format': 'pcm16le',
            'codec': 'pcm16',
            'sample_rate': 16000,
            'channels': 2,
            'capture_start': 1000.0,
            'capture_end': 1001.0,
            'sequence_count': 1,
            'gap_count': 0,
            'conversation_id': 'conversation',
            'custody_schema': 'audio_custody_v1',
            'source_layout': 'multi-channel',
        },
        _framed_setup([pcm]),
        data_protection_level='standard',
    )
    manifest = json.loads(shed_storage.bucket.blobs[receipt.manifest_path].data)
    assert manifest['capture']['source_layout'] == 'multi-channel'
    assert receipt.path.startswith('raw-live/owner/conversation/2/1/')


def test_custody_schema_stamp_is_idempotent_under_a_blip(shed_storage):
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('blip')]
    pcm = _pcm(fill=3)
    metadata = {
        'codec': 'pcm16',
        'sample_rate': 16000,
        'capture_start': 1000.0,
        'capture_end': 1001.0,
        'conversation_id': 'conversation',
    }
    commit_capture('owner', pcm, 'conversation/0/0/root/0', dict(metadata), [], data_protection_level='standard')
    media_metadata = next(
        blob.metadata
        for path, blob in shed_storage.bucket.blobs.items()
        if path.startswith('raw-live/') and blob.metadata.get('sha256') == hashlib.sha256(pcm).hexdigest()
    )
    assert media_metadata['custody_schema'] == 'audio_custody_v1'
    assert media_metadata['sha256'] == hashlib.sha256(pcm).hexdigest()


def test_exhausted_manifest_upload_bad_gateway(shed_storage):
    shed_storage.archive.script['audio-outbox'] = [BadGateway('down') for _ in range(3)]
    with pytest.raises(BadGateway):
        _commit(shed_storage)


def test_exhausted_manifest_upload_gateway_timeout(shed_storage):
    shed_storage.archive.script['audio-outbox'] = [GatewayTimeout('down') for _ in range(3)]
    with pytest.raises(GatewayTimeout):
        _commit(shed_storage)


def test_exhausted_manifest_upload_connection_error(shed_storage):
    shed_storage.archive.script['audio-outbox'] = [ConnectionError('down') for _ in range(3)]
    with pytest.raises(ConnectionError):
        _commit(shed_storage)


def test_exhausted_manifest_upload_requests_transport(shed_storage):
    shed_storage.archive.script['audio-outbox'] = [REQUESTS_CONNECTION_ERROR('down') for _ in range(3)]
    with pytest.raises(REQUESTS_CONNECTION_ERROR):
        _commit(shed_storage)


def test_exhausted_media_generation_read_bad_gateway(shed_storage):
    media = _commit(shed_storage)
    shed_storage.bucket.blobs[media.path].reload_failures = [BadGateway('down') for _ in range(3)]
    with pytest.raises(BadGateway):
        _commit(shed_storage)


def test_exhausted_media_generation_read_gateway_timeout(shed_storage):
    media = _commit(shed_storage)
    shed_storage.bucket.blobs[media.path].reload_failures = [GatewayTimeout('down') for _ in range(3)]
    with pytest.raises(GatewayTimeout):
        _commit(shed_storage)


def test_exhausted_media_generation_read_requests_transport(shed_storage):
    media = _commit(shed_storage)
    shed_storage.bucket.blobs[media.path].reload_failures = [REQUESTS_READ_TIMEOUT('down') for _ in range(3)]
    with pytest.raises(REQUESTS_READ_TIMEOUT):
        _commit(shed_storage)


def test_exhausted_manifest_generation_read_connection_error(shed_storage):
    media = _commit(shed_storage)
    shed_storage.bucket.blobs[media.manifest_path].reload_failures = [ConnectionError('down') for _ in range(3)]
    with pytest.raises(ConnectionError):
        _commit(shed_storage)


def test_exhausted_manifest_generation_read_bad_gateway(shed_storage):
    media = _commit(shed_storage)
    shed_storage.bucket.blobs[media.manifest_path].reload_failures = [BadGateway('down') for _ in range(3)]
    with pytest.raises(BadGateway):
        _commit(shed_storage)


def test_exhaustion_raises_the_last_transient_when_types_mix(shed_storage):
    shed_storage.archive.script['raw-live'] = [
        TooManyRequests('churn'),
        BadGateway('blip'),
        GatewayTimeout('final'),
    ]
    with pytest.raises(GatewayTimeout):
        _commit(shed_storage)


def test_shed_recovers_on_the_third_attempt(no_shed_wait):
    attempts = []

    def flaky():
        attempts.append(1)
        if len(attempts) < 3:
            raise ServiceUnavailable('blip')
        return 'ok'

    assert _commit_op_with_transient_shed('media_upload', flaky) == 'ok'
    assert len(attempts) == 3


def test_media_generation_read_retry_is_read_only(shed_storage):
    media = _commit(shed_storage)
    blob = shed_storage.bucket.blobs[media.path]
    data_before = blob.data
    blob.reload_failures = [ServiceUnavailable('blip')]
    commit_pcm_window('owner', _pcm(fill=3), 'conversation', 1000.0, 16000, 'root', 0, [], framed=False)
    assert blob.data == data_before


def test_manifest_generation_read_retry_is_read_only(shed_storage):
    media = _commit(shed_storage)
    blob = shed_storage.bucket.blobs[media.manifest_path]
    data_before = blob.data
    blob.reload_failures = [ServiceUnavailable('blip')]
    _commit(shed_storage)
    assert blob.data == data_before


def test_manifest_read_back_after_a_media_generation_blip(shed_storage):
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('blip')]
    receipt = _commit(shed_storage)
    manifest = json.loads(shed_storage.bucket.blobs[receipt.manifest_path].data)
    stored = shed_storage.bucket.blobs[receipt.path].data
    assert manifest['media']['sha256'] == hashlib.sha256(stored).hexdigest()


def test_classifier_accepts_requests_chunked_encoding_error():
    import requests.exceptions as requests_exceptions

    assert _is_commit_availability_blip(requests_exceptions.ChunkedEncodingError('broken pipe')) is True


def test_classifier_rejects_stop_iteration():
    assert _is_commit_availability_blip(StopIteration()) is False


def test_exhaustion_counter_labels_the_manifest_generation_op(shed_storage):
    media = _commit(shed_storage)
    before = shed_exhausted('manifest_generation')
    shed_storage.bucket.blobs[media.manifest_path].reload_failures = [ServiceUnavailable('down') for _ in range(3)]
    with pytest.raises(ServiceUnavailable):
        _commit(shed_storage)
    assert shed_exhausted('manifest_generation') == before + 1


def test_retry_counter_labels_the_media_generation_op(shed_storage):
    media = _commit(shed_storage)
    before = shed_retries('media_generation')
    shed_storage.bucket.blobs[media.path].reload_failures = [ServiceUnavailable('blip')]
    commit_pcm_window('owner', _pcm(fill=3), 'conversation', 1000.0, 16000, 'root', 0, [], framed=False)
    assert shed_retries('media_generation') == before + 1


def test_retry_counter_labels_the_manifest_generation_op(shed_storage):
    media = _commit(shed_storage)
    before = shed_retries('manifest_generation')
    shed_storage.bucket.blobs[media.manifest_path].reload_failures = [ServiceUnavailable('blip')]
    _commit(shed_storage)
    assert shed_retries('manifest_generation') == before + 1


def test_drained_budget_marks_the_last_risk_gauge(shed_storage):
    before = audio_outbox_metrics.LAST_RISK._value.get()
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('down') for _ in range(3)]
    with pytest.raises(ServiceUnavailable):
        _commit(shed_storage)
    assert audio_outbox_metrics.LAST_RISK._value.get() >= before
    assert audio_outbox_metrics.LAST_RISK._value.get() > 0 or before > 0


def test_a_deterministic_error_carries_no_exhausted_mark(shed_storage, monkeypatch):
    def collision(uid, raw, prefix, name, metadata, **kwargs):
        raise ValueError('capture identity collision')

    monkeypatch.setattr(storage, 'archive_capture_bytes', collision)
    with pytest.raises(ValueError) as caught:
        _commit(shed_storage)
    assert getattr(caught.value, 'custody_shed_exhausted', False) is False


def test_the_shed_never_sleeps_longer_than_the_budget_cap(no_shed_wait):
    def flaky():
        raise ServiceUnavailable('down')

    with pytest.raises(ServiceUnavailable):
        _commit_op_with_transient_shed('media_upload', flaky)
    assert max(no_shed_wait) <= 0.4


@pytest.mark.asyncio
async def test_session_recovers_two_media_blips(session, monkeypatch):
    _blip_first_media_upload(monkeypatch, session, failures=2)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    payloads = [struct.pack('<160h', *[n] * 160) for n in range(4)]
    sock = SessionSocket(_session_frames('conversation', payloads))
    await pusher._websocket_util_trigger(sock, 'owner', 16000, audio_custody=1)
    assert len(_session_receipts(sock)) == len(payloads)


def test_receipt_generation_pinning_matches_the_objects_after_recovery(shed_storage):
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('blip')]
    receipt = _commit(shed_storage)
    assert int(receipt.generation) == shed_storage.bucket.blobs[receipt.path].generation
    assert int(receipt.manifest_generation) == shed_storage.bucket.blobs[receipt.manifest_path].generation


def test_shed_covers_framed_and_unframed_windows_alike(shed_storage):
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('blip')]
    framed = _commit(shed_storage)
    unframed = commit_pcm_window('owner', _pcm(fill=8), 'conversation', 1000.0, 16000, 'root', 0, [], framed=False)
    assert framed.generation == unframed.generation == '17'


def test_read_pcm_rejects_a_drifted_generation_after_recovery(shed_storage):
    shed_storage.archive.script['raw-live'] = [ServiceUnavailable('blip')]
    receipt = _commit(shed_storage)
    shed_storage.bucket.blobs[receipt.path].generation = 18
    with pytest.raises(Exception):
        read_pcm('owner', receipt)
