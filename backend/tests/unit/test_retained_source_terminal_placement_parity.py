"""Terminal-record evidence placement and the retained decode roundtrip.

Where the diagnosis rides (attempt one, attempt three, every attempt) and
where it does not; the retained bytes decode roundtrip that the typed
families guard; and the storage-call defaults that keep the fetch budgeted.

Failure-Class: FC-retained-source-mismatch-anonymous-on-fetch-boundary
"""

import hashlib
import logging
import struct
import time
from unittest.mock import Mock

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from tests.unit.test_batch_pipeline_worker import item
from utils.batch_pipeline.scheduler import Scheduler
from utils.batch_pipeline.source_audio import (
    validate_reference,
    RetainedAudioOutsideAdmittedSource,
    MAX_SOURCE_BYTES,
    decode_source,
    read_reference,
)
from utils.observability.reasons import WorkerValidationReason, WorkerValidationStage

NAMED = {'stage': 'fetch_decode', 'reason': 'outside_admitted_source'}
KEY = bytes([3]) * 32
LOGGER = 'utils.batch_pipeline.scheduler'


def fresh_queue():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    return store, queue


def _sweep(queue, now, advance=30.0):
    lease = queue.pull(now)
    while not lease:
        now += advance
        queue.recover(now)
        lease = queue.pull(now)
    return lease[0], now


def _walk_until_terminal(queue, store, now, evidence_at=()):
    attempt = 0
    while attempt < 6:
        lease, now = _sweep(queue, now)
        now += 30
        attempt += 1
        queue.fail('a', lease.token, now, worker_failure_evidence=NAMED if attempt in evidence_at else None)
        if store.rows['jobs', 'a']['state'] == 'quarantined':
            return attempt, now
    raise AssertionError('no quarantine')


def quarantine_record(caplog):
    return [line for line in caplog.text.splitlines() if 'event=batch_quarantined' in line][-1]


# --- Evidence placement: the terminal record names the LATEST carried diagnosis -------


def test_evidence_on_attempt_one_only(caplog):
    store, queue = fresh_queue()
    now = time.time()
    with caplog.at_level(logging.ERROR, logger=LOGGER):
        _walk_until_terminal(queue, store, now, evidence_at=(1,))
    assert 'worker_reason=outside_admitted_source' in quarantine_record(caplog)


def test_evidence_on_attempt_two_only(caplog):
    store, queue = fresh_queue()
    now = time.time()
    with caplog.at_level(logging.ERROR, logger=LOGGER):
        _walk_until_terminal(queue, store, now, evidence_at=(2,))
    assert 'worker_reason=outside_admitted_source' in quarantine_record(caplog)


def test_evidence_on_attempt_three_only(caplog):
    store, queue = fresh_queue()
    now = time.time()
    with caplog.at_level(logging.ERROR, logger=LOGGER):
        _walk_until_terminal(queue, store, now, evidence_at=(3,))
    assert 'worker_reason=outside_admitted_source' in quarantine_record(caplog)


def test_evidence_on_attempt_four_only(caplog):
    store, queue = fresh_queue()
    now = time.time()
    with caplog.at_level(logging.ERROR, logger=LOGGER):
        _walk_until_terminal(queue, store, now, evidence_at=(4,))
    assert 'worker_reason=outside_admitted_source' in quarantine_record(caplog)


def test_evidence_on_every_attempt(caplog):
    store, queue = fresh_queue()
    now = time.time()
    with caplog.at_level(logging.ERROR, logger=LOGGER):
        _walk_until_terminal(queue, store, now, evidence_at=(1, 2, 3, 4, 5))
    assert 'worker_reason=outside_admitted_source' in quarantine_record(caplog)


def test_no_evidence_anywhere_stays_anonymous(caplog):
    store, queue = fresh_queue()
    now = time.time()
    with caplog.at_level(logging.ERROR, logger=LOGGER):
        _walk_until_terminal(queue, store, now)
    assert 'worker_reason=unclassified' in quarantine_record(caplog)


def test_job_row_keeps_the_last_carried_evidence_after_a_mixed_walk():
    store, queue = fresh_queue()
    now = time.time()
    _walk_until_terminal(queue, store, now, evidence_at=(3,))
    assert store.rows['jobs', 'a']['worker_failure_evidence'] == NAMED


def test_job_row_without_evidence_stays_clean_after_a_mixed_walk():
    store, queue = fresh_queue()
    now = time.time()
    _walk_until_terminal(queue, store, now)
    assert 'worker_failure_evidence' not in store.rows['jobs', 'a']


# --- The retained bytes decode roundtrip (the family the named fault is NOT) ----------


def _enc_frame(payload):
    nonce = b'\n' * 12
    sealed = AESGCM(KEY).encrypt(nonce, payload, None)
    return struct.pack('>I', 12 + len(sealed)) + nonce + sealed


def _chunk_ref(path='chunks/o/c/x.bin.enc'):
    return {'path': path}


def test_valid_encrypted_frame_decodes_to_the_payload():
    raw = b'\\1\\2' * 100
    out = decode_source(_enc_frame(raw), _chunk_ref(), KEY)
    assert out == raw


def test_two_encrypted_frames_concatenate_in_order():
    raw_a, raw_b = b'\\1' * 50, b'\\2' * 60
    body = _enc_frame(raw_a) + _enc_frame(raw_b)
    assert decode_source(body, _chunk_ref(), KEY) == raw_a + raw_b


def test_tampered_payload_is_the_typed_auth_fault():
    body = bytearray(_enc_frame(b'\\0' * 32))
    body[-1] ^= 0xFF
    from utils.batch_pipeline.source_audio import RetainedAudioInvalid

    with pytest.raises(RetainedAudioInvalid, match='retained audio authentication failed'):
        decode_source(bytes(body), _chunk_ref(), KEY)


def test_a_length_header_past_the_end_is_typed_truncated():
    body = struct.pack('>I', 10_000) + bytes(16)
    from utils.batch_pipeline.source_audio import RetainedAudioInvalid

    with pytest.raises(RetainedAudioInvalid, match='invalid encrypted audio frame'):
        decode_source(body, _chunk_ref(), KEY)


def test_a_three_byte_body_is_typed_truncated():
    from utils.batch_pipeline.source_audio import RetainedAudioInvalid

    with pytest.raises(RetainedAudioInvalid, match='truncated encrypted audio length'):
        decode_source(bytes([0, 0, 1]), _chunk_ref(), KEY)


def test_oversize_plaintext_is_typed():
    from utils.batch_pipeline.source_audio import RetainedAudioInvalid

    with pytest.raises(RetainedAudioInvalid, match='invalid retained audio size'):
        decode_source(b'\\0' * (MAX_SOURCE_BYTES + 1), {'path': 'chunks/o/c/x.bin'}, KEY)


def test_empty_plaintext_is_typed():
    from utils.batch_pipeline.source_audio import RetainedAudioInvalid

    with pytest.raises(RetainedAudioInvalid, match='invalid retained audio size'):
        decode_source(b'', {'path': 'chunks/o/c/x.bin'}, KEY)


def test_unchanged_plaintext_passes_through_for_plain_paths():
    assert decode_source(b'\\0\\1' * 8, {'path': 'chunks/o/c/x.bin'}, KEY) == b'\\0\\1' * 8


def test_the_named_fault_is_orthogonal_to_the_decode_roundtrip():
    from utils.batch_pipeline.source_audio import RetainedAudioInvalid

    raw = b'\\7' * 40
    assert decode_source(_enc_frame(raw), _chunk_ref(), KEY) == raw
    with pytest.raises(RetainedAudioOutsideAdmittedSource):
        validate_reference({'bucket': 'nope', 'path': 'chunks/o/c/x.bin', 'generation': 1}, 'o', 'c', {'b'})


# --- Storage-call defaults stay budgeted ------------------------------------------------


def test_reload_uses_the_thirty_second_default_without_a_budget():
    client = Mock()
    blob = client.bucket.return_value.blob.return_value
    blob.size = 8
    blob.metadata = {}
    blob.download_as_bytes.return_value = b'\\0' * 8
    try:
        read_reference(client, {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': 3}, 'o', 'c', {'b'}, KEY)
    except Exception:
        pass
    assert blob.reload.call_args.kwargs.get('timeout') == 30


def test_download_uses_the_sixty_second_default_without_a_budget():
    client = Mock()
    blob = client.bucket.return_value.blob.return_value
    blob.size = 8
    blob.metadata = {}
    blob.download_as_bytes.return_value = b'\\0' * 8
    try:
        read_reference(client, {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': 3}, 'o', 'c', {'b'}, KEY)
    except Exception:
        pass
    assert blob.download_as_bytes.call_args.kwargs.get('timeout') == 60


def test_download_pins_the_admitted_generation():
    client = Mock()
    blob = client.bucket.return_value.blob.return_value
    blob.size = 8
    blob.metadata = {}
    blob.download_as_bytes.return_value = b'\\0' * 8
    try:
        read_reference(client, {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': 41}, 'o', 'c', {'b'}, KEY)
    except Exception:
        pass
    assert blob.download_as_bytes.call_args.kwargs.get('if_generation_match') == 41


def test_reload_pins_the_admitted_generation():
    client = Mock()
    blob = client.bucket.return_value.blob.return_value
    blob.size = 8
    blob.metadata = {}
    blob.download_as_bytes.return_value = b'\\0' * 8
    try:
        read_reference(client, {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': 41}, 'o', 'c', {'b'}, KEY)
    except Exception:
        pass
    assert blob.reload.call_args.kwargs.get('if_generation_match') == 41


def test_a_zero_size_source_is_typed_oversize_family():
    client = Mock()
    blob = client.bucket.return_value.blob.return_value
    blob.size = 0
    blob.metadata = {}
    from utils.batch_pipeline.source_audio import RetainedAudioInvalid

    with pytest.raises(RetainedAudioInvalid, match='retained audio source exceeds size budget'):
        read_reference(client, {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': 3}, 'o', 'c', {'b'}, KEY)


def test_the_blob_is_read_with_retry_disabled():
    client = Mock()
    blob = client.bucket.return_value.blob.return_value
    blob.size = 8
    blob.metadata = {}
    blob.download_as_bytes.return_value = b'\\0' * 8
    try:
        read_reference(client, {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': 3}, 'o', 'c', {'b'}, KEY)
    except Exception:
        pass
    assert blob.reload.call_args.kwargs.get('retry') is None
    assert blob.download_as_bytes.call_args.kwargs.get('retry') is None


# --- The five stage members are exactly the GPU chain -------------------------------------


def test_stage_vocabulary_has_exactly_six_members():
    from utils.observability.reasons import WorkerValidationStage

    assert len({stage.value for stage in WorkerValidationStage}) == 7  # six + unknown


def test_fetch_decode_is_a_stage_member():
    from utils.observability.reasons import WorkerValidationStage

    assert WorkerValidationStage.FETCH_DECODE.value == 'fetch_decode'


def test_vad_windows_is_a_stage_member():
    from utils.observability.reasons import WorkerValidationStage

    assert WorkerValidationStage.VAD_WINDOWS.value == 'vad_windows'


def test_word_clocks_is_a_stage_member():
    from utils.observability.reasons import WorkerValidationStage

    assert WorkerValidationStage.WORD_CLOCKS.value == 'word_clocks'


def test_assemble_words_is_a_stage_member():
    from utils.observability.reasons import WorkerValidationStage

    assert WorkerValidationStage.ASSEMBLE_WORDS.value == 'assemble_words'


def test_asr_recovery_is_a_stage_member():
    from utils.observability.reasons import WorkerValidationStage

    assert WorkerValidationStage.ASR_RECOVERY.value == 'asr_recovery'


def test_the_named_reason_member_is_not_a_stage_member():
    assert 'outside_admitted_source' not in {stage.value for stage in WorkerValidationStage}


def test_the_named_reason_member_is_not_the_unknown_reason():
    assert WorkerValidationReason.OUTSIDE_ADMITTED_SOURCE.value != WorkerValidationReason.UNKNOWN.value


def test_the_scheduler_deferred_state_is_retriable_not_terminal():
    store, queue = fresh_queue()
    now = time.time()
    lease = queue.pull(now)[0]
    queue.fail('a', lease.token, now, worker_failure_evidence=NAMED)
    job = store.rows['jobs', 'a']
    assert job['state'] == 'retry'
    assert job.get('quarantine_reason') != 'worker_failed'


def test_the_named_evidence_does_not_change_the_deferred_state_name():
    store, queue = fresh_queue()
    now = time.time()
    lease = queue.pull(now)[0]
    queue.fail('a', lease.token, now, worker_failure_evidence=NAMED)
    assert store.rows['jobs', 'a']['state'] == 'retry'


def test_time_budget_probe_reaches_the_named_terminal():
    store, queue = fresh_queue()
    now = time.time()
    attempts, _ = _walk_until_terminal(queue, store, now, evidence_at=(1,))
    assert attempts == 5
