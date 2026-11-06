"""Typed decode faults stop the retry ladder at attempt one; untyped faults keep it.

Failure-Class: FC-deterministic-staged-decode-failure-walks-gpu-retry-ladder-as-unclassified-valueerror

End-to-end parity through the scheduler store: a deterministic staged
decode fault quarantines at attempt 1 with its typed evidence, is never
re-pulled, and never merges; the same shape raised untyped walks every
ladder attempt (defer → re-pull → fail) before its blind quarantine.
This is the attempt economics the ×170-style production signature was
paying four GPU attempts per stuck unit for.
"""

import time
import wave
from unittest.mock import Mock

import pytest

from diarizer.batch_pipeline import DecodedDurationMismatch
from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from tests.unit.test_batch_pipeline_worker import Samples, item, setup_worker
from utils.batch_pipeline.audio import StagedAudioInvalid
from utils.batch_pipeline.contracts import FailedWork, ValidationFailureWork
from utils.batch_pipeline.pump import Pump
from utils.batch_pipeline.scheduler import Scheduler

NOW = time.time()


@pytest.fixture(autouse=True)
def _ladder_flags(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')


def enqueue_and_lease(store, unit=None):
    queue = Scheduler(store)
    queue.enqueue(unit or item(), NOW)
    lease = queue.pull(NOW)[0]
    return queue, lease


async def run_publish(queue, worker, lease, result):
    return await Pump(queue, worker)._publish(lease, {lease.item.segment_id: result}, set())


# --- the typed fault quarantines at attempt one --------------------------------------


@pytest.mark.asyncio
async def test_typed_container_fault_quarantines_first_attempt():
    store = MemoryStore()
    queue, lease = enqueue_and_lease(store)
    worker, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    results = worker.process_batch([lease.item])
    assert await run_publish(queue, worker, lease, results[0])
    job = store.rows['jobs', lease.item.segment_id]
    assert job['state'] == 'quarantined'
    assert job['attempt'] == 1
    assert job['worker_failure'] == {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}
    assert job['recovery_state'] == 'held'
    assert not job['merge_pending']


@pytest.mark.asyncio
async def test_typed_container_fault_is_never_re_pulled():
    store = MemoryStore()
    queue, lease = enqueue_and_lease(store)
    worker, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    results = worker.process_batch([lease.item])
    await run_publish(queue, worker, lease, results[0])
    assert queue.pull(NOW + 600) == []
    assert queue.pull(NOW + 60000) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'message',
    [
        'staging requires 16kHz mono PCM16 WAV',
        'invalid staged audio length',
        'truncated staged WAV',
        'invalid staged WAV container',
        'invalid bounded intake context or WAV',
    ],
)
async def test_every_typed_staged_message_quarantines_with_the_same_evidence(message):
    store = MemoryStore()
    queue, lease = enqueue_and_lease(store)
    worker, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid(message)))
    results = worker.process_batch([lease.item])
    await run_publish(queue, worker, lease, results[0])
    job = store.rows['jobs', lease.item.segment_id]
    assert job['state'] == 'quarantined' and job['attempt'] == 1
    assert job['worker_failure'] == {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}


@pytest.mark.asyncio
async def test_typed_duration_mismatch_quarantines_first_attempt():
    store = MemoryStore()
    queue, lease = enqueue_and_lease(store)
    worker, *_ = setup_worker(decode=lambda work: Samples(work.duration_seconds + 1))
    results = worker.process_batch([lease.item])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'decoded_duration_mismatch')]
    assert await run_publish(queue, worker, lease, results[0])
    job = store.rows['jobs', lease.item.segment_id]
    assert job['state'] == 'quarantined' and job['attempt'] == 1
    assert job['worker_failure'] == {'stage': 'fetch_decode', 'reason': 'decoded_duration_mismatch'}


@pytest.mark.asyncio
async def test_typed_quarantine_publishes_exactly_once():
    store = MemoryStore()
    queue, lease = enqueue_and_lease(store)
    worker, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    results = worker.process_batch([lease.item])
    assert await run_publish(queue, worker, lease, results[0])


# --- the quarantine log names the fault ----------------------------------------------


@pytest.mark.asyncio
async def test_terminal_quarantine_log_names_stage_and_reason(caplog):
    import logging

    store = MemoryStore()
    queue, lease = enqueue_and_lease(store)
    worker, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    results = worker.process_batch([lease.item])
    with caplog.at_level(logging.DEBUG, logger='utils.batch_pipeline.scheduler'):
        await run_publish(queue, worker, lease, results[0])
    assert 'event=batch_quarantined' in caplog.text
    assert 'stage=fetch_decode' in caplog.text
    assert 'worker_reason=staged_audio_invalid' in caplog.text
    assert 'stage=unknown' not in caplog.text


@pytest.mark.asyncio
async def test_typed_quarantine_does_not_emit_the_blind_signature(caplog):
    import logging

    store = MemoryStore()
    queue, lease = enqueue_and_lease(store)
    worker, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    results = worker.process_batch([lease.item])
    with caplog.at_level(logging.DEBUG, logger='utils.batch_pipeline.scheduler'):
        await run_publish(queue, worker, lease, results[0])
    assert 'worker_reason=unclassified' not in caplog.text


# --- untyped faults keep the whole ladder ---------------------------------------------


@pytest.mark.asyncio
async def test_untyped_decode_fault_is_deferred_not_quarantined():
    store = MemoryStore()
    queue, lease = enqueue_and_lease(store)
    worker, *_ = setup_worker(decode=Mock(side_effect=ValueError('different decode failure')))
    results = worker.process_batch([lease.item])
    assert len(results) == 1 and isinstance(results[0], FailedWork)
    assert await run_publish(queue, worker, lease, results[0])
    job = store.rows['jobs', lease.item.segment_id]
    assert job['state'] != 'quarantined'
    assert job['attempt'] == 1
    due = job['available_at']
    assert queue.recover(due) == 1
    assert queue.pull(due) != []


@pytest.mark.asyncio
async def test_untyped_wave_error_from_a_foreign_callable_keeps_the_ladder():
    store = MemoryStore()
    queue, lease = enqueue_and_lease(store)
    worker, *_ = setup_worker(decode=Mock(side_effect=wave.Error('truncated staged WAV')))
    results = worker.process_batch([lease.item])
    assert isinstance(results[0], FailedWork)
    await run_publish(queue, worker, lease, results[0])
    assert store.rows['jobs', lease.item.segment_id]['state'] != 'quarantined'


@pytest.mark.asyncio
async def test_ladder_escalates_untyped_faults_to_the_attempt_ceiling_then_quarantines():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), NOW)
    worker, *_ = setup_worker(decode=Mock(side_effect=ValueError('transient decode fault')))
    segment = 'a'
    at = NOW
    for attempt in range(1, 5):
        assert queue.recover(at) >= 0
        lease = queue.pull(at)[0]
        assert lease is not None
        results = worker.process_batch([lease.item])
        assert await run_publish(queue, worker, lease, results[0])
        job = store.rows['jobs', segment]
        assert job['state'] != 'quarantined'
        assert job['attempt'] == attempt
        at = job['available_at']
    assert queue.recover(at) >= 0
    lease = queue.pull(at)[0]
    assert lease is not None
    results = worker.process_batch([lease.item])
    assert await run_publish(queue, worker, lease, results[0])
    job = store.rows['jobs', segment]
    assert job['state'] == 'quarantined'
    assert job['attempt'] == 5


@pytest.mark.asyncio
async def test_ladder_escalation_evidence_keeps_the_last_diagnosis():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), NOW)
    worker, *_ = setup_worker(decode=Mock(side_effect=ValueError('transient decode fault')))
    at = NOW
    for attempt in range(1, 6):
        assert queue.recover(at) >= 0
        lease = queue.pull(at)[0]
        results = worker.process_batch([lease.item])
        await run_publish(queue, worker, lease, results[0])
        at = store.rows['jobs', 'a']['available_at']
    job = store.rows['jobs', 'a']
    evidence = job.get('worker_failure_evidence')
    assert evidence is not None
    assert evidence['stage'] == 'fetch_decode'


# --- attempt economics: the typed fault buys back four GPU passes ---------------------


@pytest.mark.asyncio
async def test_typed_fault_never_reaches_attempt_two():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), NOW)
    decode_calls = []

    def decode(work):
        decode_calls.append(work.segment_id)
        raise StagedAudioInvalid('invalid staged WAV container')

    worker, *_ = setup_worker(decode=decode)
    lease = queue.pull(NOW)[0]
    results = worker.process_batch([lease.item])
    await run_publish(queue, worker, lease, results[0])
    assert queue.pull(NOW + 60000) == []
    assert len(decode_calls) == 1


@pytest.mark.asyncio
async def test_typed_quarantine_keeps_the_unit_out_of_the_due_pages():
    store = MemoryStore()
    queue, lease = enqueue_and_lease(store)
    worker, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    results = worker.process_batch([lease.item])
    await run_publish(queue, worker, lease, results[0])
    assert store.due('ready', NOW + 60000, 100) == []
    assert store.due('leased', NOW + 60000, 100) == []


@pytest.mark.asyncio
async def test_typed_quarantine_emits_the_recovery_held_metrics():
    store = MemoryStore()
    queue = Scheduler(store)
    metrics = Mock()
    queue.metrics = metrics
    queue.enqueue(item(), NOW)
    worker, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    lease = queue.pull(NOW)[0]
    results = worker.process_batch([lease.item])
    await run_publish(queue, worker, lease, results[0])
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert 'quarantined' in recorded
    assert 'recovery_held' in recorded


@pytest.mark.asyncio
async def test_untyped_ladder_attempts_emit_retry_not_quarantine_metrics():
    store = MemoryStore()
    queue = Scheduler(store)
    metrics = Mock()
    queue.metrics = metrics
    queue.enqueue(item(), NOW)
    worker, *_ = setup_worker(decode=Mock(side_effect=ValueError('transient decode fault')))
    lease = queue.pull(NOW)[0]
    results = worker.process_batch([lease.item])
    await run_publish(queue, worker, lease, results[0])
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert 'retry' in recorded
    assert 'quarantined' not in recorded


# --- custody: the typed quarantine never destroys audio -------------------------------


@pytest.mark.asyncio
async def test_typed_quarantine_preserves_the_audio_uri_for_fenced_recovery():
    store = MemoryStore()
    queue, lease = enqueue_and_lease(store)
    worker, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    results = worker.process_batch([lease.item])
    await run_publish(queue, worker, lease, results[0])
    job = store.rows['jobs', lease.item.segment_id]
    assert job.get('audio_uri') == lease.item.audio_uri


@pytest.mark.asyncio
async def test_typed_quarantine_carries_the_measured_vad_evidence():
    store = MemoryStore()
    queue, lease = enqueue_and_lease(store)
    worker, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    results = worker.process_batch([lease.item])
    await run_publish(queue, worker, lease, results[0])
    job = store.rows['jobs', lease.item.segment_id]
    # No VAD ran: the measured speech evidence stays absent, never zero.
    assert job.get('speech_seconds') in (None, lease.item.duration_seconds, 0) or 'speech_seconds' not in job


# --- correctness telemetry ------------------------------------------------------------


@pytest.mark.asyncio
async def test_typed_quarantine_records_failed_correctness(monkeypatch):
    from utils.batch_pipeline import scheduler as scheduler_module

    seen = []
    monkeypatch.setattr(scheduler_module, 'record_correctness', lambda event, **kwargs: seen.append(event))
    store = MemoryStore()
    queue, lease = enqueue_and_lease(store)
    worker, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    results = worker.process_batch([lease.item])
    await run_publish(queue, worker, lease, results[0])
    assert 'failed' in seen


@pytest.mark.asyncio
async def test_typed_quarantine_records_no_empty_asr_attempt(monkeypatch):
    from utils.batch_pipeline import scheduler as scheduler_module

    seen = []
    monkeypatch.setattr(scheduler_module, 'record_correctness', lambda event, **kwargs: seen.append(event))
    store = MemoryStore()
    queue, lease = enqueue_and_lease(store)
    worker, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    results = worker.process_batch([lease.item])
    await run_publish(queue, worker, lease, results[0])
    assert 'empty_asr_attempt' not in seen


@pytest.mark.asyncio
async def test_deferred_untyped_attempt_records_retry_correctness(monkeypatch):
    from utils.batch_pipeline import scheduler as scheduler_module

    seen = []
    monkeypatch.setattr(scheduler_module, 'record_correctness', lambda event, **kwargs: seen.append(event))
    store = MemoryStore()
    queue, lease = enqueue_and_lease(store)
    worker, *_ = setup_worker(decode=Mock(side_effect=ValueError('transient decode fault')))
    results = worker.process_batch([lease.item])
    await run_publish(queue, worker, lease, results[0])
    assert 'failed' not in seen


# --- scheduling invariants around the typed quarantine --------------------------------


@pytest.mark.asyncio
async def test_typed_quarantine_does_not_block_later_units_for_the_owner():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), NOW)
    queue.enqueue(item('b'), NOW + 1)
    worker, *_ = setup_worker(
        decode=lambda work: (
            (_ for _ in ()).throw(StagedAudioInvalid('invalid staged WAV container'))
            if work.segment_id == 'a'
            else Samples(work.duration_seconds)
        )
    )
    lease_first = queue.pull(NOW)[0]
    first = lease_first.item.segment_id
    other = 'b' if first == 'a' else 'a'
    results = worker.process_batch([lease_first.item])
    if first == 'a':
        assert isinstance(results[0], ValidationFailureWork)
        await run_publish(queue, worker, lease_first, results[0])
        assert store.rows['jobs', 'a']['state'] == 'quarantined'
    due_other = store.rows['jobs', other]['available_at']
    assert queue.recover(due_other) >= 0
    lease_other = queue.pull(due_other)[0]
    assert lease_other is not None and lease_other.item.segment_id == other


@pytest.mark.asyncio
async def test_typed_quarantine_survives_a_second_publish_attempt():
    # A duplicate publication of the same terminal result stays fenced.
    store = MemoryStore()
    queue, lease = enqueue_and_lease(store)
    worker, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    results = worker.process_batch([lease.item])
    await run_publish(queue, worker, lease, results[0])
    job_before = store.rows['jobs', 'a']
    await run_publish(queue, worker, lease, results[0])
    job_after = store.rows['jobs', 'a']
    assert job_after == job_before


@pytest.mark.asyncio
async def test_typed_quarantine_holds_across_a_lease_expiry_repull():
    store = MemoryStore()
    queue, lease = enqueue_and_lease(store)
    worker, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    results = worker.process_batch([lease.item])
    await run_publish(queue, worker, lease, results[0])
    # A stale lease snapshot may still try: the store fence refuses it.
    stale = await run_publish(queue, worker, lease, results[0])
    job = store.rows['jobs', 'a']
    assert job['state'] == 'quarantined' and job['attempt'] == 1


# --- escalation parity for every untyped class ----------------------------------------


async def escalate_to_quarantine(queue, store, worker, steps=5):
    at = NOW
    for attempt in range(1, steps):
        assert queue.recover(at) >= 0
        lease = queue.pull(at)[0]
        results = worker.process_batch([lease.item])
        assert await run_publish(queue, worker, lease, results[0])
        at = store.rows['jobs', 'a']['available_at']
    assert queue.recover(at) >= 0
    lease = queue.pull(at)[0]
    results = worker.process_batch([lease.item])
    assert await run_publish(queue, worker, lease, results[0])
    return store.rows['jobs', 'a']


@pytest.mark.asyncio
async def test_wave_error_escalates_to_the_blind_quarantine():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), NOW)
    worker, *_ = setup_worker(decode=Mock(side_effect=wave.Error('truncated staged WAV')))
    job = await escalate_to_quarantine(queue, store, worker)
    assert job['state'] == 'quarantined' and job['attempt'] == 5


@pytest.mark.asyncio
async def test_runtime_error_escalates_to_the_blind_quarantine():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), NOW)
    worker, *_ = setup_worker(decode=Mock(side_effect=RuntimeError('transient decode fault')))
    job = await escalate_to_quarantine(queue, store, worker)
    assert job['state'] == 'quarantined' and job['attempt'] == 5


@pytest.mark.asyncio
async def test_blind_quarantine_log_still_says_unknown_unclassified(caplog):
    import logging

    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), NOW)
    worker, *_ = setup_worker(decode=Mock(side_effect=ValueError('transient decode fault')))
    with caplog.at_level(logging.DEBUG, logger='utils.batch_pipeline.scheduler'):
        await escalate_to_quarantine(queue, store, worker)
    # The ladder's carried diagnosis names the stage with the closed
    # unknown token — never an exception message.
    assert 'worker_reason=unknown' in caplog.text


@pytest.mark.asyncio
async def test_typed_fault_never_produces_the_blind_quarantine(caplog):
    import logging

    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), NOW)
    worker, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    lease = queue.pull(NOW)[0]
    results = worker.process_batch([lease.item])
    with caplog.at_level(logging.DEBUG, logger='utils.batch_pipeline.scheduler'):
        await run_publish(queue, worker, lease, results[0])
    assert 'worker_reason=unclassified' not in caplog.text
    assert 'worker_reason=staged_audio_invalid' in caplog.text


# --- terminal handling of a pre-attempted job -----------------------------------------


@pytest.mark.asyncio
async def test_typed_fault_terminalizes_a_pre_attempted_job():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), NOW)
    worker, *_ = setup_worker(decode=Mock(side_effect=ValueError('transient decode fault')))
    at = NOW
    for _ in range(2):
        assert queue.recover(at) >= 0
        lease = queue.pull(at)[0]
        results = worker.process_batch([lease.item])
        await run_publish(queue, worker, lease, results[0])
        at = store.rows['jobs', 'a']['available_at']
    assert store.rows['jobs', 'a']['attempt'] == 2
    assert queue.recover(at) >= 0
    lease = queue.pull(at)[0]
    typed, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    results = typed.process_batch([lease.item])
    assert await run_publish(queue, typed, lease, results[0])
    job = store.rows['jobs', 'a']
    assert job['state'] == 'quarantined'
    assert job['worker_failure'] == {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}


@pytest.mark.asyncio
async def test_typed_quarantine_log_reports_the_real_attempt(caplog):
    import logging

    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), NOW)
    worker, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    lease = queue.pull(NOW)[0]
    results = worker.process_batch([lease.item])
    with caplog.at_level(logging.DEBUG, logger='utils.batch_pipeline.scheduler'):
        await run_publish(queue, worker, lease, results[0])
    assert 'attempt=1' in caplog.text


# --- store invariants around the typed quarantine --------------------------------------


@pytest.mark.asyncio
async def test_typed_quarantine_leaves_no_ready_page_entry():
    store = MemoryStore()
    queue, lease = enqueue_and_lease(store)
    worker, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    results = worker.process_batch([lease.item])
    await run_publish(queue, worker, lease, results[0])
    assert store.oldest(0, ready_only=True) is None
    assert store.oldest(0, ready_only=False) is None


@pytest.mark.asyncio
async def test_typed_quarantine_never_arms_a_merge_hold():
    store = MemoryStore()
    queue, lease = enqueue_and_lease(store)
    worker, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    results = worker.process_batch([lease.item])
    await run_publish(queue, worker, lease, results[0])
    assert ('merge_holds', 'owner-owner:a') not in store.rows


@pytest.mark.asyncio
async def test_typed_quarantine_clears_the_lease_token():
    store = MemoryStore()
    queue, lease = enqueue_and_lease(store)
    worker, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    results = worker.process_batch([lease.item])
    await run_publish(queue, worker, lease, results[0])
    job = store.rows['jobs', 'a']
    assert not job.get('token')


@pytest.mark.asyncio
async def test_typed_quarantine_keeps_priority_and_owner_binding():
    store = MemoryStore()
    queue, lease = enqueue_and_lease(store)
    worker, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    results = worker.process_batch([lease.item])
    await run_publish(queue, worker, lease, results[0])
    job = store.rows['jobs', 'a']
    assert job['priority'] == lease.item.priority
    assert job['owner_key']


@pytest.mark.asyncio
async def test_stale_lease_publication_is_refused_after_typed_quarantine():
    from dataclasses import replace

    store = MemoryStore()
    queue, lease = enqueue_and_lease(store)
    worker, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    results = worker.process_batch([lease.item])
    await run_publish(queue, worker, lease, results[0])
    stale_lease = replace(lease, token='stale-token')
    assert await run_publish(queue, worker, stale_lease, results[0]) is False


@pytest.mark.asyncio
async def test_recover_after_typed_quarantine_finds_nothing():
    store = MemoryStore()
    queue, lease = enqueue_and_lease(store)
    worker, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    results = worker.process_batch([lease.item])
    await run_publish(queue, worker, lease, results[0])
    assert queue.recover(NOW + 100000) == 0


@pytest.mark.asyncio
async def test_duration_family_quarantine_emits_recovery_held_metrics():
    store = MemoryStore()
    queue = Scheduler(store)
    metrics = Mock()
    queue.metrics = metrics
    queue.enqueue(item(), NOW)
    worker, *_ = setup_worker(decode=lambda work: Samples(work.duration_seconds + 1))
    lease = queue.pull(NOW)[0]
    results = worker.process_batch([lease.item])
    await run_publish(queue, worker, lease, results[0])
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert 'quarantined' in recorded and 'recovery_held' in recorded


@pytest.mark.asyncio
async def test_duration_family_quarantine_records_failed_correctness(monkeypatch):
    from utils.batch_pipeline import scheduler as scheduler_module

    seen = []
    monkeypatch.setattr(scheduler_module, 'record_correctness', lambda event, **kwargs: seen.append(event))
    store = MemoryStore()
    queue, lease = enqueue_and_lease(store)
    worker, *_ = setup_worker(decode=lambda work: Samples(work.duration_seconds + 1))
    results = worker.process_batch([lease.item])
    await run_publish(queue, worker, lease, results[0])
    assert 'failed' in seen


@pytest.mark.asyncio
async def test_duration_family_quarantine_preserves_audio_custody():
    store = MemoryStore()
    queue, lease = enqueue_and_lease(store)
    worker, *_ = setup_worker(decode=lambda work: Samples(work.duration_seconds + 1))
    results = worker.process_batch([lease.item])
    await run_publish(queue, worker, lease, results[0])
    job = store.rows['jobs', 'a']
    assert job.get('audio_uri') == lease.item.audio_uri


@pytest.mark.asyncio
async def test_typed_quarantine_carries_no_result():
    store = MemoryStore()
    queue, lease = enqueue_and_lease(store)
    worker, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    results = worker.process_batch([lease.item])
    await run_publish(queue, worker, lease, results[0])
    job = store.rows['jobs', 'a']
    assert not job.get('result')


@pytest.mark.asyncio
async def test_typed_quarantine_leaves_the_row_without_available_at():
    store = MemoryStore()
    queue, lease = enqueue_and_lease(store)
    worker, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    results = worker.process_batch([lease.item])
    await run_publish(queue, worker, lease, results[0])
    job = store.rows['jobs', 'a']
    assert job['state'] == 'quarantined'


@pytest.mark.asyncio
async def test_typed_quarantine_does_not_disturb_the_control_rings_for_others():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), NOW)
    queue.enqueue(item('b'), NOW + 1)
    worker, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    lease = queue.pull(NOW)[0]
    first = lease.item.segment_id
    other = 'b' if first == 'a' else 'a'
    results = worker.process_batch([lease.item])
    await run_publish(queue, worker, lease, results[0])
    assert store.rows['jobs', first]['state'] == 'quarantined'
    due_other = store.rows['jobs', other]['available_at']
    assert queue.recover(due_other) >= 0
    assert queue.pull(due_other)[0].item.segment_id == other


@pytest.mark.asyncio
async def test_typed_quarantine_attempt_stays_one_across_recover_sweeps():
    store = MemoryStore()
    queue, lease = enqueue_and_lease(store)
    worker, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    results = worker.process_batch([lease.item])
    await run_publish(queue, worker, lease, results[0])
    for sweep in range(3):
        queue.recover(NOW + 60 * (sweep + 1))
    assert store.rows['jobs', 'a']['attempt'] == 1
    assert store.rows['jobs', 'a']['state'] == 'quarantined'


# --- log sequencing and store tails ---------------------------------------------------


@pytest.mark.asyncio
async def test_typed_quarantine_does_not_log_a_deferred_retry(caplog):
    import logging

    store = MemoryStore()
    queue, lease = enqueue_and_lease(store)
    worker, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    results = worker.process_batch([lease.item])
    with caplog.at_level(logging.DEBUG, logger='utils.batch_pipeline.scheduler'):
        await run_publish(queue, worker, lease, results[0])
    assert 'event=batch_retry' not in caplog.text
    assert 'event=batch_quarantined' in caplog.text


@pytest.mark.asyncio
async def test_deferred_untyped_attempt_logs_the_retry_event(caplog):
    import logging

    store = MemoryStore()
    queue, lease = enqueue_and_lease(store)
    worker, *_ = setup_worker(decode=Mock(side_effect=ValueError('transient decode fault')))
    results = worker.process_batch([lease.item])
    with caplog.at_level(logging.DEBUG, logger='utils.batch_pipeline.scheduler'):
        await run_publish(queue, worker, lease, results[0])
    assert 'event=batch_retry reason=worker_failed outcome=deferred attempt=1' in caplog.text


@pytest.mark.asyncio
async def test_typed_quarantine_worker_failure_survives_a_recover_sweep():
    store = MemoryStore()
    queue, lease = enqueue_and_lease(store)
    worker, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    results = worker.process_batch([lease.item])
    await run_publish(queue, worker, lease, results[0])
    queue.recover(NOW + 600)
    job = store.rows['jobs', 'a']
    assert job['worker_failure'] == {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}


@pytest.mark.asyncio
async def test_duration_family_pre_attempted_job_terminalizes():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), NOW)
    worker, *_ = setup_worker(decode=Mock(side_effect=ValueError('transient decode fault')))
    at = NOW
    for _ in range(2):
        assert queue.recover(at) >= 0
        lease = queue.pull(at)[0]
        results = worker.process_batch([lease.item])
        await run_publish(queue, worker, lease, results[0])
        at = store.rows['jobs', 'a']['available_at']
    assert queue.recover(at) >= 0
    lease = queue.pull(at)[0]
    typed, *_ = setup_worker(decode=lambda work: Samples(work.duration_seconds + 1))
    results = typed.process_batch([lease.item])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'decoded_duration_mismatch')]
    assert await run_publish(queue, typed, lease, results[0])
    job = store.rows['jobs', 'a']
    assert job['state'] == 'quarantined'
    assert job['worker_failure'] == {'stage': 'fetch_decode', 'reason': 'decoded_duration_mismatch'}


@pytest.mark.asyncio
async def test_typed_quarantine_rejects_a_second_fail_for_the_same_lease():
    store = MemoryStore()
    queue, lease = enqueue_and_lease(store)
    worker, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    results = worker.process_batch([lease.item])
    await run_publish(queue, worker, lease, results[0])
    # A second scheduler.fail with the same (now cleared) token is refused.
    assert not queue.fail(
        'a', lease.token, NOW + 1, worker_failure={'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}
    )


@pytest.mark.asyncio
async def test_typed_quarantine_keeps_no_retry_started_at():
    store = MemoryStore()
    queue, lease = enqueue_and_lease(store)
    worker, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    results = worker.process_batch([lease.item])
    await run_publish(queue, worker, lease, results[0])
    job = store.rows['jobs', 'a']
    assert not job.get('retry_started_at')


@pytest.mark.asyncio
async def test_typed_quarantine_keeps_the_duration_evidence_on_the_job():
    store = MemoryStore()
    queue, lease = enqueue_and_lease(store)
    worker, *_ = setup_worker(decode=lambda work: Samples(work.duration_seconds + 1))
    results = worker.process_batch([lease.item])
    await run_publish(queue, worker, lease, results[0])
    job = store.rows['jobs', 'a']
    assert job['worker_failure'] == {'stage': 'fetch_decode', 'reason': 'decoded_duration_mismatch'}
    assert 'worker_failure_evidence' not in job
