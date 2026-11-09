"""Decoded extent versus admitted capture is deterministic, so it is terminal.

The fetch_decode boundary raises ``decoded duration differs from admitted capture``
when the decoded PCM extent disagrees with the admitted capture metadata. The
stored bytes and the admitted metadata are both fixed per job, so every retry
decodes the same samples against the same admitted duration: the failure is
permanent. This pins the closed-reason classification, its stage scoping, the
tolerance boundary, and the scheduler/pump routing parity with the typed
retained-audio family.

Failure-Class: FC-permanent-retained-decode-failure-burns-retry-ladder
"""

import logging
import time
from dataclasses import replace
from unittest.mock import Mock

import pytest

from config.batch_pipeline_providers import ProviderConfig
from utils.batch_pipeline.contracts import FailedWork, ValidationFailureWork
from diarizer.batch_pipeline import DecodedDurationMismatch
from utils.batch_pipeline.pump import Pump
from utils.batch_pipeline.scheduler import Scheduler
from utils.batch_pipeline.word_validation import BatchValidationError, ValidationReason
from utils.observability.reasons import WorkerValidationReason
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from tests.unit.test_batch_pipeline_worker import Samples, item, setup_worker

DURATION = WorkerValidationReason.DECODED_DURATION_MISMATCH.value


def mismatched_decode(seconds):
    def decode(work):
        return Samples(seconds)

    return decode


# --- Classification -------------------------------------------------------------


@pytest.mark.parametrize('safety_net', ['false', 'true'])
def test_duration_mismatch_is_terminal(monkeypatch, safety_net):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', safety_net)
    worker, words, saved, *_ = setup_worker(decode=mismatched_decode(99))
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', DURATION)]
    assert not words.calls and not saved


def test_duration_mismatch_token_value():
    assert WorkerValidationReason.DECODED_DURATION_MISMATCH.value == 'decoded_duration_mismatch'


def test_over_ceiling_duration_is_terminal(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    config = ProviderConfig(pool_kind='dedicated_batch', max_unit_seconds=120, max_padded_seconds=120)
    worker, *_ = setup_worker(config=config, decode=mismatched_decode(121))
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', DURATION)]


def test_zero_length_decode_is_terminal(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    worker, words, saved, *_ = setup_worker(decode=mismatched_decode(0))
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', DURATION)]
    assert not words.calls and not saved


def test_one_frame_under_tolerance_is_accepted(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    worker, words, *_ = setup_worker(decode=mismatched_decode(2.1 - 1 / 16000))
    results = worker.process_batch([item()])
    assert not isinstance(results[0], ValidationFailureWork)
    assert words.calls


def test_sample_count_rounding_at_the_boundary_is_terminal(monkeypatch):
    """int(2.1 * 16000) samples decode to 2.1000000000000001s: past the tolerance."""
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    worker, words, saved, *_ = setup_worker(decode=mismatched_decode(2.1))
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', DURATION)]
    assert not words.calls and not saved


def test_one_frame_over_tolerance_is_terminal(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    worker, words, saved, *_ = setup_worker(decode=mismatched_decode(2.1 + 1 / 16000))
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', DURATION)]
    assert not words.calls and not saved


def test_half_frame_drift_is_accepted(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    worker, words, *_ = setup_worker(decode=mismatched_decode(2.05))
    results = worker.process_batch([item()])
    assert not isinstance(results[0], ValidationFailureWork)
    assert words.calls


def test_typed_errors_keep_their_own_reason(monkeypatch):
    """A typed retained failure never falls into the duration classification."""
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    from utils.batch_pipeline.source_audio import RetainedAudioInvalid

    def decode(work):
        raise RetainedAudioInvalid('retained capture checksum mismatch')

    worker, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_duration_message_at_vad_stage_stays_unclassified(monkeypatch):
    """Stage scoping: the same deterministic fault from a later stage keeps the legacy path."""
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')

    def vad(_samples):
        raise DecodedDurationMismatch('decoded duration differs from admitted capture')

    worker, words, saved, *_ = setup_worker(vad=vad)
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)


def test_batch_validation_error_is_never_duration_mismatch(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def decode(work):
        raise BatchValidationError(ValidationReason.WORD_CLOCK)

    worker, *_ = setup_worker(decode=decode)
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)


# --- Telemetry -------------------------------------------------------------------


def test_samples_are_recorded_in_the_failure_log(caplog):
    caplog.set_level(logging.INFO)
    worker, *_ = setup_worker(decode=mismatched_decode(99))
    worker.process_batch([item()])
    assert 'event=batch_validation_disposition outcome=recovery_handoff' in caplog.text
    assert 'reason=decoded_duration_mismatch' in caplog.text
    assert 'samples=1584000' in caplog.text


def test_duration_mismatch_log_never_leaks_admission_text(caplog):
    caplog.set_level(logging.ERROR)
    worker, *_ = setup_worker(decode=mismatched_decode(99))
    worker.process_batch([item()])
    assert 'decoded duration differs from admitted capture' not in caplog.text


def test_duration_mismatch_counts_one_failure_and_notifies_once():
    worker, _, _, _, _, failures = setup_worker(decode=mismatched_decode(99))
    worker.process_batch([item()])
    assert worker.counts['failed'] == 1
    assert failures == [('a', 'DecodedDurationMismatch')]


def test_duration_mismatch_makes_no_model_calls():
    worker, words, saved, _, diarized, _ = setup_worker(decode=mismatched_decode(99))
    worker.process_batch([item()])
    assert not words.calls and not saved and not diarized


def test_duration_mismatch_sibling_survives():
    def decode(work):
        if work.segment_id == 'bad':
            return Samples(99)
        return Samples(2)

    worker, _, saved, _, _, _ = setup_worker(decode=decode)
    results = worker.process_batch([item('bad'), item('ok')])
    assert [r.segment_id for r in results] == ['bad', 'ok']
    assert isinstance(results[0], ValidationFailureWork)
    assert results[1].outcome == 'success' and saved['ok']['words']


def test_shadow_duration_mismatch_is_terminal_without_error_log(caplog):
    caplog.set_level(logging.INFO)
    worker, *_ = setup_worker(decode=mismatched_decode(99))
    results = worker.process_batch([replace(item(), shadow=True)])
    assert results == [ValidationFailureWork('a', 'fetch_decode', DURATION)]
    assert 'event=batch_shadow_worker_failure stage=fetch_decode reason=decoded_duration_mismatch' in caplog.text
    assert 'event=batch_worker_failed' not in caplog.text


# --- Scheduler/pump parity --------------------------------------------------------


@pytest.mark.asyncio
async def test_duration_mismatch_quarantines_on_first_attempt(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    fail = Mock(wraps=queue.fail)
    monkeypatch.setattr(queue, 'fail', fail)
    worker, *_ = setup_worker()
    assert await Pump(queue, worker)._publish(lease, {'a': ValidationFailureWork('a', 'fetch_decode', DURATION)}, set())
    assert fail.call_args.kwargs['worker_failure'] == {'stage': 'fetch_decode', 'reason': DURATION}
    assert 'quarantine' not in fail.call_args.kwargs
    job = store.rows['jobs', 'a']
    assert job['state'] == 'quarantined' and job['attempt'] == 1
    assert job['recovery_state'] == 'held'
    assert queue.pull(time.time() + 600) == []


def test_duration_mismatch_never_reenters_the_pull_ring(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    now = time.time()
    lease = queue.pull(now)[0]
    assert queue.fail('a', lease.token, now, worker_failure={'stage': 'fetch_decode', 'reason': DURATION})
    now += 3600
    assert queue.recover(now) == 0
    assert queue.pull(now) == []


def test_both_new_reasons_share_the_fetch_decode_stage_token():
    retained = ValidationFailureWork('a', 'fetch_decode', WorkerValidationReason.RETAINED_AUDIO_INVALID.value)
    duration = ValidationFailureWork('a', 'fetch_decode', DURATION)
    assert retained.stage == duration.stage == 'fetch_decode'


def test_typed_batch_logs_one_record_per_failing_item(caplog):
    caplog.set_level(logging.INFO)

    def decode(work):
        return Samples(99) if work.segment_id == 'bad' else Samples(2)

    worker, *_ = setup_worker(decode=decode)
    worker.process_batch([item('bad'), item('ok')])
    records = {r.getMessage() for r in caplog.records if 'event=batch_validation_disposition' in r.message}
    assert len(records) == 1
    assert 'segment_id=bad' in next(iter(records))


def test_admitted_duration_is_never_rewritten_by_the_worker(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    admitted = item(duration=2)
    worker, *_ = setup_worker(decode=mismatched_decode(99))
    results = worker.process_batch([admitted])
    assert results == [ValidationFailureWork('a', 'fetch_decode', DURATION)]
    assert admitted.duration_seconds == 2
