"""The fetch_decode boundary and demotion parity grid: every typed retained
fault class takes the same terminal custody route (ValidationFailureWork,
closed evidence, attempt-one quarantine) while untyped deploy faults keep the
legacy retry ladder, and the scheduler's demotion predicates route exactly the
designed handoffs away from the ERROR fault channels - nothing else.

Failure-Class: FC-non-value-decoder-fault-burns-retry-ladder
"""

import logging
import struct
import time

import pytest

import utils.batch_pipeline.source_audio as source_audio
from utils.batch_pipeline.contracts import FailedWork, ValidationFailureWork
from utils.batch_pipeline.source_audio import RetainedAudioInvalid
from utils.batch_pipeline.errors import (
    empty_ladder_recovery_failure,
    language_guard_redrive_failure,
    validate_worker_failure,
    validation_disposition_failure,
)
from utils.batch_pipeline.scheduler import Scheduler
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from tests.unit.test_batch_pipeline_worker import item, setup_worker

KEY = b"\4" * 32
PCM = b"\0\2" * 320


class FakeOpusError(Exception):
    """Stands in for opuslib.OpusError on hosts without the native binding."""


def extended_fault_types():
    return source_audio.decoder_fault_types() + (FakeOpusError,)


def decode_raises(stub):
    def decode(work):
        raise RetainedAudioInvalid(str(stub)) from stub

    return decode


def decode_raises_raw(stub):
    def decode(work):
        raise stub

    return decode


def quarantine_once(monkeypatch, evidence):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    now = time.time()
    lease = queue.pull(now)[0]
    assert queue.fail('a', lease.token, now, worker_failure=evidence)
    return store.rows['jobs', 'a']


def test_real_key_error_cell_reaches_terminal_custody(monkeypatch):
    raw = b'\x00\x02' * 160
    metadata = {'channels': '1', 'format': 'pcm16le', 'sha256': __import__('hashlib').sha256(raw).hexdigest()}
    ref = {'path': 'raw-live/o/c/x.bin', 'metadata': metadata}

    def decode(work):
        return source_audio.decode_source(raw, ref, KEY)

    worker, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_real_zero_channels_cell_reaches_terminal_custody(monkeypatch):
    raw = b'\x00\x02' * 160
    metadata = {
        'channels': '0',
        'format': 'pcm16le',
        'sample_rate': '16000',
        'sha256': __import__('hashlib').sha256(raw).hexdigest(),
    }
    ref = {'path': 'raw-live/o/c/x.bin', 'metadata': metadata}

    def decode(work):
        return source_audio.decode_source(raw, ref, KEY)

    worker, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_real_overflow_rate_cell_reaches_terminal_custody(monkeypatch):
    raw = b'\x00\x02' * 160
    metadata = {
        'channels': '1',
        'format': 'pcm16le',
        'sample_rate': '99999999999',
        'sha256': __import__('hashlib').sha256(raw).hexdigest(),
    }
    ref = {'path': 'raw-live/o/c/x.bin', 'metadata': metadata}

    def decode(work):
        return source_audio.decode_source(raw, ref, KEY)

    worker, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_stub_opus_error_cell_reaches_terminal_custody(monkeypatch):
    monkeypatch.setattr(source_audio, '_DECODER_FAULT_TYPES', extended_fault_types())
    import utils.other.audio_opus as opus_module

    def broken(raw, sample_rate=16000):
        raise FakeOpusError('corrupt packet')

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', broken)

    def decode(work):
        return source_audio.decode_source(PCM, {'path': 'chunks/o/c/x.opus'}, KEY)

    worker, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_runtime_error_cell_keeps_the_retry_ladder(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    worker, *_ = setup_worker(decode=decode_raises_raw(RuntimeError('binding missing')))
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)


def test_runtime_error_cell_without_safety_net_yields_no_work(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    worker, *_ = setup_worker(decode=decode_raises_raw(RuntimeError('binding missing')))
    assert worker.process_batch([item()]) == []


def test_typed_evidence_quarantines_once(monkeypatch):
    job = quarantine_once(monkeypatch, {'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'})
    assert job['state'] == 'quarantined'
    assert job['attempt'] == 1
    assert job['recovery_state'] == 'held'
    assert job['worker_failure'] == {'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'}


def test_typed_evidence_never_repulls(monkeypatch):
    quarantine_once(monkeypatch, {'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'})
    store = MemoryStore()
    queue = Scheduler(store)
    now = time.time() + 7200
    assert queue.pull(now) == []


def test_evidence_less_failure_keeps_the_ladder(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    now = time.time()
    lease = queue.pull(now)[0]
    assert queue.fail('a', lease.token, now)
    assert store.rows['jobs', 'a']['state'] == 'retry'


def test_disposition_fetch_decode_staged_audio_invalid_demotes_flag_False():
    assert validation_disposition_failure(
        {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'},
        disposition_enabled=False,
    )


def test_disposition_fetch_decode_retained_audio_invalid_demotes_flag_False():
    assert validation_disposition_failure(
        {'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'},
        disposition_enabled=False,
    )


def test_disposition_fetch_decode_decoded_duration_mismatch_demotes_flag_False():
    assert validation_disposition_failure(
        {'stage': 'fetch_decode', 'reason': 'decoded_duration_mismatch'},
        disposition_enabled=False,
    )


def test_disposition_fetch_decode_staged_audio_invalid_demotes_flag_True():
    assert validation_disposition_failure(
        {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'},
        disposition_enabled=True,
    )


def test_disposition_fetch_decode_retained_audio_invalid_demotes_flag_True():
    assert validation_disposition_failure(
        {'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'},
        disposition_enabled=True,
    )


def test_disposition_fetch_decode_decoded_duration_mismatch_demotes_flag_True():
    assert validation_disposition_failure(
        {'stage': 'fetch_decode', 'reason': 'decoded_duration_mismatch'},
        disposition_enabled=True,
    )


def test_disposition_unconditional_trio_never_demotes_off_stage():
    assert not validation_disposition_failure(
        {'stage': 'vad_windows', 'reason': 'retained_audio_invalid'},
        disposition_enabled=True,
    )


def test_disposition_unconditional_trio_never_demotes_unknown():
    assert not validation_disposition_failure(
        {'stage': 'fetch_decode', 'reason': 'unknown'},
        disposition_enabled=True,
    )


def test_disposition_unclassified_stays_on_the_fault_channel():
    assert not validation_disposition_failure(
        {'stage': 'fetch_decode', 'reason': 'unknown'},
        disposition_enabled=False,
    )


def test_disposition_flagged_vad_nonfinite_demotes_only_while_enabled():
    diagnosis = {'stage': 'vad_windows', 'reason': 'vad_nonfinite'}
    assert validation_disposition_failure(diagnosis, disposition_enabled=True)
    assert not validation_disposition_failure(diagnosis, disposition_enabled=False)


def test_disposition_flagged_vad_order_demotes_only_while_enabled():
    diagnosis = {'stage': 'vad_windows', 'reason': 'vad_order'}
    assert validation_disposition_failure(diagnosis, disposition_enabled=True)
    assert not validation_disposition_failure(diagnosis, disposition_enabled=False)


def test_disposition_flagged_vad_bounds_demotes_only_while_enabled():
    diagnosis = {'stage': 'vad_windows', 'reason': 'vad_bounds'}
    assert validation_disposition_failure(diagnosis, disposition_enabled=True)
    assert not validation_disposition_failure(diagnosis, disposition_enabled=False)


def test_disposition_flagged_word_shape_demotes_only_while_enabled():
    diagnosis = {'stage': 'vad_windows', 'reason': 'word_shape'}
    assert validation_disposition_failure(diagnosis, disposition_enabled=True)
    assert not validation_disposition_failure(diagnosis, disposition_enabled=False)


def test_disposition_flagged_word_clock_demotes_only_while_enabled():
    diagnosis = {'stage': 'vad_windows', 'reason': 'word_clock'}
    assert validation_disposition_failure(diagnosis, disposition_enabled=True)
    assert not validation_disposition_failure(diagnosis, disposition_enabled=False)


def test_disposition_flagged_word_sequence_demotes_only_while_enabled():
    diagnosis = {'stage': 'vad_windows', 'reason': 'word_sequence'}
    assert validation_disposition_failure(diagnosis, disposition_enabled=True)
    assert not validation_disposition_failure(diagnosis, disposition_enabled=False)


def test_disposition_flagged_reason_demotes_at_every_closed_stage():
    for stage in ('vad_windows', 'word_clocks', 'assemble_words', 'asr_recovery'):
        assert validation_disposition_failure(
            {'stage': stage, 'reason': 'vad_bounds'},
            disposition_enabled=True,
        )


def test_disposition_hostile_empty_dict_never_demotes():
    assert not validation_disposition_failure({}, disposition_enabled=True)


def test_disposition_hostile_extra_key_never_demotes():
    assert not validation_disposition_failure(
        {'stage': 'fetch_decode', 'reason': 'retained_audio_invalid', 'extra': 1}, disposition_enabled=True
    )


def test_disposition_hostile_missing_reason_never_demotes():
    assert not validation_disposition_failure({'stage': 'fetch_decode'}, disposition_enabled=True)


def test_disposition_hostile_missing_stage_never_demotes():
    assert not validation_disposition_failure({'reason': 'retained_audio_invalid'}, disposition_enabled=True)


def test_disposition_hostile_non_string_stage_never_demotes():
    assert not validation_disposition_failure(
        {'stage': 1, 'reason': 'retained_audio_invalid'}, disposition_enabled=True
    )


def test_disposition_hostile_non_string_reason_never_demotes():
    assert not validation_disposition_failure({'stage': 'fetch_decode', 'reason': 1}, disposition_enabled=True)


def test_disposition_hostile_list_shape_never_demotes():
    assert not validation_disposition_failure(['fetch_decode', 'retained_audio_invalid'], disposition_enabled=True)


def test_disposition_hostile_none_never_demotes():
    assert not validation_disposition_failure(None, disposition_enabled=True)


def test_disposition_hostile_string_never_demotes():
    assert not validation_disposition_failure('retained_audio_invalid', disposition_enabled=True)


def test_empty_ladder_predicate_accepts_only_the_assemble_words_handoff():
    assert empty_ladder_recovery_failure({'stage': 'assemble_words', 'reason': 'empty_asr'})
    assert empty_ladder_recovery_failure({'stage': 'assemble_words', 'reason': 'no_owned_words'})
    assert not empty_ladder_recovery_failure({'stage': 'fetch_decode', 'reason': 'empty_asr'})
    assert not empty_ladder_recovery_failure({'stage': 'assemble_words', 'reason': 'retained_audio_invalid'})
    assert not empty_ladder_recovery_failure({})
    assert not empty_ladder_recovery_failure(None)


def test_language_guard_predicate_routes_on_the_closed_reason():
    assert language_guard_redrive_failure({'stage': 'vad_windows', 'reason': 'unsupported_language'})
    assert language_guard_redrive_failure({'stage': 'assemble_words', 'reason': 'unsupported_language'})
    assert not language_guard_redrive_failure({'stage': 'vad_windows', 'reason': 'empty_asr'})
    assert not language_guard_redrive_failure({'stage': 'vad_windows', 'reason': 'retained_audio_invalid'})
    assert not language_guard_redrive_failure(None)


def test_terminal_gate_accepts_the_retained_family_token():
    validate_worker_failure({'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'})


def test_terminal_gate_rejects_unclassified():
    from utils.batch_pipeline.errors import validate_worker_failure as gate

    try:
        gate({'stage': 'fetch_decode', 'reason': 'unclassified'})
    except ValueError:
        pass
    else:
        raise AssertionError('unclassified must not satisfy the closed gate')


def test_terminal_gate_rejects_foreign_stage():
    try:
        validate_worker_failure({'stage': 'not_a_stage', 'reason': 'retained_audio_invalid'})
    except ValueError:
        pass
    else:
        raise AssertionError('foreign stage must not satisfy the closed gate')


def test_worker_failure_log_carries_the_closed_tokens(caplog):
    caplog.set_level(20)
    worker, *_ = setup_worker(decode=decode_raises(KeyError('leaky key name')))
    worker.process_batch([item()])
    assert 'error_class=RetainedAudioInvalid' in caplog.text
    assert 'stage=fetch_decode' in caplog.text
    assert 'reason=retained_audio_invalid' in caplog.text
    assert 'leaky key name' not in caplog.text
