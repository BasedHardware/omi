"""Permanent retained-audio decode failures are typed, closed-reason, and terminal at fetch_decode.

A retained unit whose stored bytes can never decode (checksum mismatch, invalid PCM,
truncated encrypted frame, failed authentication, digest drift, oversize source) fails
identically on every retry: the pinned generations serve the same bytes. Before this
change those failures surfaced as unclassified ValueErrors, so the worker returned no
terminal evidence, the scheduler walked the bounded retry ladder (max_attempts GPU
attempts and batch_worker_failed records per segment), and the fenced recovery lane
re-read the same bytes on every sweep. The staged-WAV trio already carried this
terminal disposition; this pins the same contract for the retained (record) lane.

Failure-Class: FC-permanent-retained-decode-failure-burns-retry-ladder
"""

import hashlib
import json
import logging
import struct
import time
from unittest.mock import Mock

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from utils.batch_pipeline.contracts import FailedWork, Priority, ValidationFailureWork, WorkItem
from utils.batch_pipeline.errors import validate_worker_failure
from utils.batch_pipeline.record_seal_reasons import proof_reason
from utils.batch_pipeline.scheduler import Scheduler
from utils.batch_pipeline.source_audio import (
    MAX_SOURCE_BYTES,
    MAGIC,
    InvalidRetainedManifest,
    RetainedAudioInvalid,
    decode_source,
    materialize,
    read_reference,
)
from utils.batch_pipeline.word_validation import BatchValidationError, ValidationReason
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from tests.unit.test_batch_pipeline_worker import Samples, item, setup_worker

import utils.batch_pipeline.source_audio as source_audio
from diarizer.batch_pipeline import FatalGpuError
from utils.batch_pipeline.artifacts import ArtifactStore, ProtectionContext

KEY = b'\1' * 32
PCM = b'\0\2' * 320


def owner_key(_owner):
    return KEY


def enc_frame(key, payload):
    nonce = b'\n' * 12
    sealed = AESGCM(key).encrypt(nonce, payload, None)
    return struct.pack('>I', 12 + len(sealed)) + nonce + sealed


def raw_live_ref(raw, **metadata_changes):
    metadata = {'sample_rate': '16000', 'channels': '1', 'format': 'pcm16le', 'sha256': hashlib.sha256(raw).hexdigest()}
    return {'path': 'raw-live/o/c/x.bin', 'metadata': {**metadata, **metadata_changes}}


def chunk_ref(path='chunks/o/c/x.bin'):
    return {'path': path}


def manifest_item():
    from types import SimpleNamespace

    return SimpleNamespace(owner_id='o', conversation_id='c', capture_at=1, duration_seconds=1.0)


def manifest(*references, **changes):
    body = {'owner_id': 'o', 'conversation_id': 'c', 'capture_at': 1, 'references': list(references), 'context': {}}
    return MAGIC + json.dumps({**body, **changes}).encode()


def slice_ref(source, start=0, frames=160, offset=0):
    return {
        'bucket': 'b',
        'path': 'chunks/o/c/x.bin',
        'generation': 1,
        'pcm_sha256': hashlib.sha256(source).hexdigest(),
        'start_frame': start,
        'offset_frame': offset,
        'frames': frames,
    }


SOURCE = b'\1\0' * 160


# --- Typed error identity ---------------------------------------------------


def test_retained_audio_invalid_is_a_value_error():
    assert issubclass(RetainedAudioInvalid, ValueError)


def test_invalid_retained_manifest_is_a_retained_audio_invalid():
    assert issubclass(InvalidRetainedManifest, RetainedAudioInvalid)


def test_empty_body_is_typed_invalid_size():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained audio size$'):
        decode_source(b'', chunk_ref(), KEY)


def test_oversize_body_is_typed_invalid_size():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained audio size$'):
        decode_source(b'\0' * (MAX_SOURCE_BYTES + 1), chunk_ref(), KEY)


def test_truncated_encrypted_length_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^truncated encrypted audio length$'):
        decode_source(b'\0\0\0', chunk_ref('chunks/o/c/x.bin.enc'), KEY)


def test_invalid_encrypted_frame_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid encrypted audio frame$'):
        decode_source(struct.pack('>I', 4), chunk_ref('chunks/o/c/x.bin.enc'), KEY)


def test_wrong_key_ciphertext_is_typed_authentication():
    body = enc_frame(b'\2' * 32, PCM)
    with pytest.raises(RetainedAudioInvalid, match='^retained audio authentication failed$'):
        decode_source(body, chunk_ref('chunks/o/c/x.bin.enc'), KEY)


def test_checksum_mismatch_is_typed():
    raw = PCM
    with pytest.raises(RetainedAudioInvalid, match='^retained capture checksum mismatch$'):
        decode_source(raw, raw_live_ref(raw, sha256='0' * 64), KEY)


def test_odd_pcm_length_is_typed_invalid_retained_pcm():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(b'\0' * 33, chunk_ref(), KEY)


def test_sample_rate_below_floor_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 7999}, KEY)


def test_sample_rate_above_ceiling_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 48001}, KEY)


def test_materialize_digest_change_is_typed():
    wrong = slice_ref(b'\2\0' * 160)
    with pytest.raises(RetainedAudioInvalid) as error:
        materialize(manifest(wrong), manifest_item(), lambda _: SOURCE)
    assert str(error.value) == 'retained PCM digest changed'
    assert not isinstance(error.value, InvalidRetainedManifest)


def artifact_store_without_conversation():
    store = ArtifactStore(
        Mock(),
        bucket='unit_bucket',
        namespace='batch_pipeline_test_unit',
        authorize=lambda _item: ProtectionContext('standard', 0),
        key_for_owner=owner_key,
        register_artifact=lambda *_: None,
    )
    store._read = Mock(return_value=MAGIC + b'{}')
    return store


def test_retained_audio_without_registered_conversation_is_typed():
    store = artifact_store_without_conversation()
    orphan = WorkItem('a', 'owner-a', 100, 'encrypted://a', 2, Priority.FRESH, conversation_id=None)
    with pytest.raises(RetainedAudioInvalid, match='^retained audio requires a registered conversation$'):
        store.fetch_audio(orphan)


# --- Decoder wraps -----------------------------------------------------------


def test_capture_decode_value_error_is_typed(monkeypatch):
    def broken(raw, metadata, rate):
        raise ValueError('capture format cannot serve playback')

    monkeypatch.setattr(source_audio, 'decode_capture', broken)
    with pytest.raises(RetainedAudioInvalid):
        decode_source(PCM, raw_live_ref(PCM, format='mystery'), KEY)


def test_capture_decode_message_is_preserved(monkeypatch):
    def broken(raw, metadata, rate):
        raise ValueError('capture PCM is not sample-aligned')

    monkeypatch.setattr(source_audio, 'decode_capture', broken)
    with pytest.raises(RetainedAudioInvalid, match='^capture PCM is not sample-aligned$'):
        decode_source(b'\0', raw_live_ref(b'\0'), KEY)


def test_capture_decode_cause_is_chained(monkeypatch):
    original = ValueError('capture decoder produced no PCM')

    def broken(raw, metadata, rate):
        raise original

    monkeypatch.setattr(source_audio, 'decode_capture', broken)
    with pytest.raises(RetainedAudioInvalid) as error:
        decode_source(PCM, raw_live_ref(PCM), KEY)
    assert error.value.__cause__ is original


def test_opus_value_error_is_typed(monkeypatch):
    import utils.other.audio_opus as opus_module

    def broken(raw, sample_rate=16000):
        raise ValueError('Opus data too short: 3 bytes (need at least 8 for header)')

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', broken)
    with pytest.raises(RetainedAudioInvalid, match='^Opus data too short'):
        decode_source(b'123', {'path': 'chunks/o/c/x.opus'}, KEY)


def test_opus_message_is_preserved(monkeypatch):
    import utils.other.audio_opus as opus_module

    def broken(raw, sample_rate=16000):
        raise ValueError('Truncated Opus data: expected packet 0/2 length at offset 8')

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', broken)
    with pytest.raises(RetainedAudioInvalid, match='^Truncated Opus data'):
        decode_source(b'12345678', {'path': 'chunks/o/c/x.opus'}, KEY)


def test_opus_runtime_error_passes_through_untyped(monkeypatch):
    import utils.other.audio_opus as opus_module

    def broken(raw, sample_rate=16000):
        raise RuntimeError('decoder backend unavailable')

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', broken)
    with pytest.raises(RuntimeError, match='decoder backend unavailable'):
        decode_source(b'12345678', {'path': 'chunks/o/c/x.opus'}, KEY)


def test_capture_decode_runtime_error_passes_through_untyped(monkeypatch):
    def broken(raw, metadata, rate):
        raise RuntimeError('resampler backend unavailable')

    monkeypatch.setattr(source_audio, 'decode_capture', broken)
    with pytest.raises(RuntimeError, match='resampler backend unavailable'):
        decode_source(PCM, raw_live_ref(PCM), KEY)


# --- Retryable and staged boundaries stay put --------------------------------


def test_bucket_misconfiguration_stays_retryable():
    """The allowed buckets are deploy config, not data: never typed permanent."""
    misplaced = {'bucket': 'other', 'path': 'chunks/o/c/x.bin', 'generation': 1}
    with pytest.raises(ValueError) as error:
        read_reference(Mock(), misplaced, 'o', 'c', {'b'}, KEY)
    assert str(error.value) == 'retained audio reference is outside admitted source'
    assert not isinstance(error.value, RetainedAudioInvalid)


@pytest.mark.parametrize(
    'build',
    [
        lambda: _staged_body(channels=2),
        lambda: _staged_body(frames=b''),
        lambda: _staged_body(truncated=True),
    ],
)
def test_staged_wav_family_is_typed_and_distinct_from_retained(build):
    from diarizer.batch_pipeline_models import decode_pcm16_wav
    from utils.batch_pipeline.audio import StagedAudioInvalid

    # The staged family carries its own typed marker: the fetch_decode
    # boundary terminalizes it by type, never by matching a message, and it
    # stays distinct from the retained custody family.
    with pytest.raises(ValueError) as error:
        decode_pcm16_wav(build())
    assert isinstance(error.value, StagedAudioInvalid)
    assert not isinstance(error.value, RetainedAudioInvalid)


def _staged_body(channels=1, frames=b'\0' * 640, truncated=False):
    import io
    import wave

    body = io.BytesIO()
    with wave.open(body, 'wb') as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(frames)
    staged = body.getvalue()
    return staged[:-2] if truncated else staged


def test_proof_reason_checksum_maps_decode_or_checksum():
    assert proof_reason(RetainedAudioInvalid('retained capture checksum mismatch')) == 'decode_or_checksum'


def test_proof_reason_size_maps_budget_limit():
    assert proof_reason(RetainedAudioInvalid('invalid retained audio size')) == 'budget_limit'


def test_proof_reason_authentication_maps_decode_or_checksum():
    assert proof_reason(RetainedAudioInvalid('retained audio authentication failed')) == 'decode_or_checksum'


# --- Happy paths keep their bytes ---------------------------------------------


def test_valid_mono_pcm16_passthrough():
    assert decode_source(PCM, chunk_ref(), KEY) == PCM


def test_resample_eight_k_still_converts():
    out = decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 8000}, KEY)
    assert isinstance(out, bytes) and out


def test_encrypted_roundtrip_still_decrypts():
    assert decode_source(enc_frame(KEY, PCM), chunk_ref('chunks/o/c/x.bin.enc'), KEY) == PCM


def test_valid_raw_live_still_decodes(monkeypatch):
    monkeypatch.setattr(source_audio, 'decode_capture', lambda raw, metadata, rate: raw)
    assert decode_source(PCM, raw_live_ref(PCM), KEY) == PCM


def test_valid_opus_still_decodes(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', lambda raw, sample_rate=16000: PCM)
    assert decode_source(b'12345678', {'path': 'chunks/o/c/x.opus'}, KEY) == PCM


def read_only_blob(size):
    blob = Mock()
    blob.reload = Mock(return_value=None)
    blob.size = size
    client = Mock()
    client.bucket.return_value.blob.return_value = blob
    return client


def test_read_reference_empty_source_is_typed():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': 1}
    with pytest.raises(RetainedAudioInvalid, match='^retained audio source exceeds size budget$'):
        read_reference(read_only_blob(0), ref, 'o', 'c', {'b'}, KEY)


def test_read_reference_oversize_source_is_typed():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': 1}
    with pytest.raises(RetainedAudioInvalid, match='^retained audio source exceeds size budget$'):
        read_reference(read_only_blob(MAX_SOURCE_BYTES + 1), ref, 'o', 'c', {'b'}, KEY)


# --- Worker classification -----------------------------------------------------


def typed_decode(message='retained capture checksum mismatch'):
    def decode(work):
        raise RetainedAudioInvalid(message)

    return decode


@pytest.mark.parametrize('safety_net', ['false', 'true'])
def test_worker_terminal_for_typed_checksum(monkeypatch, safety_net):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', safety_net)
    worker, words, saved, *_ = setup_worker(decode=typed_decode())
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_worker_terminal_for_typed_invalid_pcm(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    worker, *_ = setup_worker(decode=typed_decode('invalid retained PCM'))
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_worker_terminal_for_typed_size_budget(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    worker, *_ = setup_worker(decode=typed_decode('invalid retained audio size'))
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_worker_terminal_for_typed_manifest(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    worker, *_ = setup_worker(decode=typed_decode('malformed retained audio manifest'))
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_worker_terminal_for_typed_authentication(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    worker, *_ = setup_worker(decode=typed_decode('retained audio authentication failed'))
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_worker_terminal_for_typed_capture_wrap(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    worker, *_ = setup_worker(decode=typed_decode('capture format cannot serve playback'))
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_worker_terminal_for_typed_opus_wrap(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    worker, *_ = setup_worker(decode=typed_decode('Opus data too short: 3 bytes (need at least 8 for header)'))
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_worker_terminal_for_typed_conversation_requirement(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    worker, *_ = setup_worker(decode=typed_decode('retained audio requires a registered conversation'))
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_worker_log_carries_closed_reason_and_error_class(caplog):
    caplog.set_level(logging.ERROR)
    worker, *_ = setup_worker(decode=typed_decode())
    worker.process_batch([item()])
    assert 'event=batch_worker_failed' in caplog.text
    assert 'error_class=RetainedAudioInvalid' in caplog.text
    assert 'stage=fetch_decode' in caplog.text
    assert 'reason=retained_audio_invalid' in caplog.text


def test_worker_log_never_leaks_the_underlying_text(caplog):
    caplog.set_level(logging.ERROR)
    worker, *_ = setup_worker(decode=typed_decode('retained capture checksum mismatch'))
    worker.process_batch([item()])
    assert 'retained capture checksum mismatch' not in caplog.text


def test_worker_counts_one_failure_and_calls_on_failure_once():
    worker, _, _, _, _, failures = setup_worker(decode=typed_decode())
    worker.process_batch([item()])
    assert worker.counts['failed'] == 1
    assert failures == [('a', 'RetainedAudioInvalid')]


def test_worker_terminal_work_validates_against_the_closed_set():
    work = ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')
    validate_worker_failure({'stage': work.stage, 'reason': work.reason})


def test_worker_vad_bounds_terminal_route_still_reachable(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def vad(_samples):
        raise BatchValidationError(ValidationReason.VAD_BOUNDS)

    worker, words, saved, *_ = setup_worker(vad=vad)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'vad_windows', 'vad_bounds')]
    assert not words.calls and not saved


def test_worker_plain_value_error_still_failed_work(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    worker, *_ = setup_worker(decode=lambda work: (_ for _ in ()).throw(ValueError('different decode failure')))
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)


def test_worker_plain_value_error_yields_no_work_without_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    worker, *_ = setup_worker(decode=lambda work: (_ for _ in ()).throw(ValueError('different decode failure')))
    assert worker.process_batch([item()]) == []


def test_worker_typed_error_ends_chain_without_safety_net(monkeypatch):
    """The ladder exit: terminal evidence exists even with the safety net off."""
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    worker, *_ = setup_worker(decode=typed_decode())
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_worker_shadow_typed_failure_is_recorded_without_error_log(caplog):
    caplog.set_level(logging.INFO)
    from dataclasses import replace

    worker, *_ = setup_worker(decode=typed_decode())
    results = worker.process_batch([replace(item(), shadow=True)])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert 'event=batch_shadow_worker_failure stage=fetch_decode reason=retained_audio_invalid' in caplog.text
    assert 'event=batch_worker_failed' not in caplog.text


def test_worker_siblings_survive_typed_failure():
    def decode(work):
        if work.segment_id == 'bad':
            raise RetainedAudioInvalid('retained capture checksum mismatch')
        return Samples(2)

    worker, words, saved, _, _, _ = setup_worker(decode=decode)
    results = worker.process_batch([item('bad'), item('ok')])
    assert [r.segment_id for r in results] == ['bad', 'ok']
    assert isinstance(results[0], ValidationFailureWork)
    assert results[1].outcome == 'success' and saved['ok']['words']


def test_worker_decode_runs_exactly_once_for_typed_failure():
    decoded = []

    def decode(work):
        decoded.append(work.segment_id)
        raise RetainedAudioInvalid('retained capture checksum mismatch')

    worker, *_ = setup_worker(decode=decode)
    worker.process_batch([item()])
    assert decoded == ['a']


def test_worker_fatal_cuda_still_fences_worker():
    worker, *_ = setup_worker(
        decode=lambda work: (_ for _ in ()).throw(RuntimeError('CUDA error: an illegal memory access was encountered'))
    )
    with pytest.raises(FatalGpuError, match='fatal CUDA error'):
        worker.process_batch([item()])


# --- Ladder economics -----------------------------------------------------------


@pytest.mark.asyncio
async def test_typed_failure_quarantines_on_first_attempt(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    fail = Mock(wraps=queue.fail)
    monkeypatch.setattr(queue, 'fail', fail)
    from utils.batch_pipeline.pump import Pump

    result = ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')
    assert await Pump(queue, None)._publish(lease, {'a': result}, set())
    assert fail.call_args.kwargs['worker_failure'] == {'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'}
    assert 'quarantine' not in fail.call_args.kwargs
    job = store.rows['jobs', 'a']
    assert job['state'] == 'quarantined' and job['attempt'] == 1
    assert job['worker_failure'] == {'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'}
    assert job['recovery_state'] == 'held' and not job['merge_pending']
    assert queue.pull(time.time() + 600) == []


@pytest.mark.asyncio
async def test_unclassified_failure_defers_for_another_attempt(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    from utils.batch_pipeline.pump import Pump

    result = FailedWork('a', None, None)
    assert await Pump(queue, None)._publish(lease, {'a': result}, set())
    job = store.rows['jobs', 'a']
    assert job['state'] == 'retry'
    assert job['available_at'] > time.time()
    assert job['attempt'] == 1
    assert 'worker_failure' not in job


def test_unclassified_ladder_repulls_until_the_cap(monkeypatch):
    """Each unclassified cycle is recover->pull->GPU decode on identical bytes: the burn."""
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    now = time.time()
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
    job = store.rows['jobs', 'a']
    assert job['state'] == 'quarantined'
    assert pulls == 5  # SchedulerPolicy.max_attempts default: the sensor's attempt=5/5


def test_typed_failure_never_reenters_the_pull_ring(monkeypatch):
    """The typed terminal disposition quarantines on attempt one: no sweep requeues it."""
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    now = time.time()
    lease = queue.pull(now)[0]
    assert queue.fail(
        'a', lease.token, now, worker_failure={'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'}
    )
    assert store.rows['jobs', 'a']['state'] == 'quarantined'
    now += 3600
    assert queue.recover(now) == 0
    assert queue.pull(now) == []
