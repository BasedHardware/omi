"""The evidence chain holds across the pump, the ladder and the shadow lane.

Publication must forward the worker's evidence without changing any decision
the pump already makes per work type, the end-to-end ladder (worker failure ->
pump publish -> scheduler fail -> recover -> re-pull) must still quarantine at
the attempt ceiling while recording and logging the diagnosis, and the shadow
lane must keep treating an evidenced ordinary failure exactly like a plain
one: finish as an error, never authorize a new paid call.

Failure-Class: FC-batch-transient-worker-failure-quarantines-blind-without-stage-or-reason-evidence
"""

import asyncio
import logging
import time
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from utils.batch_pipeline.contracts import FailedWork, HeldWork, RecoveryWork, ValidationFailureWork, WorkResult
from utils.batch_pipeline.pump import Pump
from utils.batch_pipeline.scheduler import Scheduler
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from tests.unit.test_batch_pipeline_worker import item, setup_worker
from tests.unit.test_batch_pipeline_shadow import repository, running, row  # noqa: F401

EVIDENCE = {'stage': 'fetch_decode', 'reason': 'unknown'}


@pytest.fixture(autouse=True)
def _evidence_pipeline(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')


def _leased_queue(monkeypatch, segment='a'):
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(segment), time.time())
    lease = queue.pull(time.time())[0]
    fail = Mock(wraps=queue.fail)
    monkeypatch.setattr(queue, 'fail', fail)
    return queue, store, lease, fail


def _worker():
    worker, *_ = setup_worker()
    return worker


async def _published(queue, lease, result):
    return await Pump(queue, _worker())._publish(lease, {'a': result}, set())


# --- Pump routing: per-work-type contract -----------------------------------------


@pytest.mark.asyncio
async def test_pump_forwards_failed_work_evidence(monkeypatch):
    queue, _, lease, fail = _leased_queue(monkeypatch)
    assert await _published(queue, lease, FailedWork('a', None, None, EVIDENCE)) is True
    assert fail.call_args.kwargs['worker_failure_evidence'] == EVIDENCE
    assert 'worker_failure' not in fail.call_args.kwargs
    assert 'quarantine' not in fail.call_args.kwargs


@pytest.mark.asyncio
async def test_pump_forwards_none_evidence_for_a_plain_failed_work(monkeypatch):
    queue, _, lease, fail = _leased_queue(monkeypatch)
    assert await _published(queue, lease, FailedWork('a', None, None)) is True
    assert fail.call_args.kwargs['worker_failure_evidence'] is None


@pytest.mark.asyncio
async def test_pump_forwards_none_evidence_for_a_lost_worker_result(monkeypatch):
    queue, _, lease, fail = _leased_queue(monkeypatch)
    worker, *_ = setup_worker()
    assert await Pump(queue, worker)._publish(lease, {}, set()) is True
    assert fail.call_args.kwargs['worker_failure_evidence'] is None
    assert fail.call_args.args[0] == 'a'


@pytest.mark.asyncio
async def test_pump_evidence_publish_defers_the_unit(monkeypatch):
    queue, store, lease, _ = _leased_queue(monkeypatch)
    await _published(queue, lease, FailedWork('a', None, None, EVIDENCE))
    job = store.rows['jobs', 'a']
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == EVIDENCE


@pytest.mark.asyncio
async def test_pump_held_work_still_defers_without_evidence_kwargs(monkeypatch):
    queue, _, lease, fail = _leased_queue(monkeypatch)
    defer = Mock(wraps=queue.defer)
    monkeypatch.setattr(queue, 'defer', defer)
    worker, *_ = setup_worker()
    assert await Pump(queue, worker)._publish(lease, {'a': HeldWork('a', 60, 'capacity')}, set()) is False
    fail.assert_not_called()
    assert defer.call_args.kwargs['admission_refused'] is True
    assert defer.call_args.kwargs['held_reason'] == 'capacity'


@pytest.mark.asyncio
async def test_pump_validation_failure_keeps_the_typed_contract(monkeypatch):
    queue, _, lease, fail = _leased_queue(monkeypatch)
    typed = ValidationFailureWork('a', 'fetch_decode', 'staged_audio_invalid')
    assert await _published(queue, lease, typed) is True
    assert fail.call_args.kwargs['worker_failure'] == {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}
    assert 'worker_failure_evidence' not in fail.call_args.kwargs
    assert 'quarantine' not in fail.call_args.kwargs


@pytest.mark.asyncio
async def test_pump_recovery_work_keeps_the_quarantine_contract(monkeypatch):
    queue, _, lease, fail = _leased_queue(monkeypatch)
    assert await _published(queue, lease, RecoveryWork('a')) is True
    assert fail.call_args.kwargs['quarantine'] is True
    assert fail.call_args.kwargs['worker_failure'] == {'stage': 'assemble_words', 'reason': 'empty_asr'}
    assert 'worker_failure_evidence' not in fail.call_args.kwargs


@pytest.mark.asyncio
async def test_pump_work_result_still_completes(monkeypatch):
    queue, store, lease, fail = _leased_queue(monkeypatch)
    worker, *_ = setup_worker()
    assert await Pump(queue, worker)._publish(lease, {'a': WorkResult('a', 'gs://results/a')}, set()) is True
    fail.assert_not_called()
    assert store.rows['jobs', 'a']['state'] == 'result_ready'


@pytest.mark.asyncio
async def test_pump_publishes_the_evidenced_result_true_exactly_once(monkeypatch):
    queue, store, lease, _ = _leased_queue(monkeypatch)
    assert await _published(queue, lease, FailedWork('a', None, None, EVIDENCE)) is True
    due = store.rows['jobs', 'a']['available_at']
    queue.recover(due)
    lease2 = queue.pull(due)[0]
    assert await _published(queue, lease2, FailedWork('a', None, None, EVIDENCE)) is True


@pytest.mark.asyncio
async def test_pump_scheduler_failure_marks_the_segment_lost(monkeypatch):
    queue, _, lease, _ = _leased_queue(monkeypatch)
    monkeypatch.setattr(queue, 'fail', Mock(side_effect=RuntimeError('db down')))
    lost = set()
    worker, *_ = setup_worker()
    assert await Pump(queue, worker)._publish(lease, {'a': FailedWork('a', None, None, EVIDENCE)}, lost) is False
    assert lost == {'a'}


@pytest.mark.asyncio
async def test_pump_shadow_items_route_evidence_like_ordinary_items(monkeypatch):
    queue, store, lease, fail = _leased_queue(monkeypatch)
    await _published(queue, lease, FailedWork('a', 2.0, None, EVIDENCE))
    assert fail.call_args.kwargs['worker_failure_evidence'] == EVIDENCE
    assert fail.call_args.kwargs['measured_held_vad_speech_seconds'] == 2.0


@pytest.mark.asyncio
async def test_pump_evidence_publish_carries_the_vad_receipt(monkeypatch):
    from utils.batch_pipeline.contracts import vad_receipt

    queue, _, lease, fail = _leased_queue(monkeypatch)
    receipt = vad_receipt('encrypted://a', 32000, 1.5)
    await _published(queue, lease, FailedWork('a', 1.5, receipt, EVIDENCE))
    assert fail.call_args.kwargs['worker_vad_receipt'] == receipt
    assert fail.call_args.kwargs['worker_failure_evidence'] == EVIDENCE


# --- End-to-end ladder through the pump ---------------------------------------------


async def _pump_ladder(monkeypatch, work_factory, *, attempts, caplog=None):
    # The pump stamps scheduler.fail with wall-clock time itself, so this
    # ladder runs on wall clock too: pull times must stay inside the lease.
    store = MemoryStore()
    queue = Scheduler(store)
    start = time.time()
    queue.enqueue(item('a'), start)
    for attempt in range(1, attempts + 1):
        if attempt > 1:
            due = store.rows['jobs', 'a']['available_at']
            queue.recover(due)
        now = start if attempt == 1 else store.rows['jobs', 'a']['available_at']
        lease = queue.pull(now)[0]
        with caplog.at_level(logging.ERROR, logger='utils.batch_pipeline.scheduler') if caplog else _nulllevel():
            await Pump(queue, _worker())._publish(lease, {'a': work_factory(attempt)}, set())
    return queue, store


class _nulllevel:
    def __enter__(self):
        return None

    def __exit__(self, *args):
        return None


@pytest.mark.asyncio
async def test_end_to_end_evidenced_ladder_defers_then_quarantines(monkeypatch):
    _, store = await _pump_ladder(monkeypatch, lambda a: FailedWork('a', None, None, EVIDENCE), attempts=5)
    job = store.rows['jobs', 'a']
    assert job['state'] == 'quarantined'
    assert job['worker_failure_evidence'] == EVIDENCE


@pytest.mark.asyncio
async def test_end_to_end_evidenced_ladder_logs_the_diagnosis(monkeypatch, caplog):
    with caplog.at_level(logging.ERROR, logger='utils.batch_pipeline.scheduler'):
        _, store = await _pump_ladder(monkeypatch, lambda a: FailedWork('a', None, None, EVIDENCE), attempts=5)
    quarantined = [r for r in caplog.records if 'event=batch_quarantined' in r.getMessage()]
    assert len(quarantined) == 1
    assert quarantined[-1].getMessage() == (
        'event=batch_quarantined reason=worker_failed attempt=5 recovery=held '
        'stage=fetch_decode worker_reason=unknown'
    )


@pytest.mark.asyncio
async def test_end_to_end_plain_ladder_keeps_the_historical_log(monkeypatch, caplog):
    with caplog.at_level(logging.ERROR, logger='utils.batch_pipeline.scheduler'):
        _, store = await _pump_ladder(monkeypatch, lambda a: FailedWork('a', None, None), attempts=5)
    quarantined = [r for r in caplog.records if 'event=batch_quarantined' in r.getMessage()]
    assert quarantined[-1].getMessage().endswith('stage=unknown worker_reason=unclassified')
    assert 'worker_failure_evidence' not in store.rows['jobs', 'a']


@pytest.mark.asyncio
async def test_end_to_end_crash_after_evidenced_attempts_keeps_the_diagnosis(monkeypatch, caplog):
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), time.time())
    lease = queue.pull(time.time())[0]
    await Pump(queue, _worker())._publish(lease, {'a': FailedWork('a', None, None, EVIDENCE)}, set())
    for _ in range(4):
        due = store.rows['jobs', 'a']['available_at']
        queue.recover(due)
        lease = queue.pull(due)[0]
        # The worker crashed: no entry for this segment at all.
        await Pump(queue, _worker())._publish(lease, {}, set())
    job = store.rows['jobs', 'a']
    assert job['state'] == 'quarantined'
    assert job['worker_failure_evidence'] == EVIDENCE


@pytest.mark.asyncio
async def test_end_to_end_decode_failure_stays_private(monkeypatch, caplog):
    marker = 'synthetic-private-provider-text'
    worker, *_ = setup_worker(decode=Mock(side_effect=RuntimeError(marker)))
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), time.time())
    for attempt in range(1, 6):
        if attempt > 1:
            due = store.rows['jobs', 'a']['available_at']
            queue.recover(due)
        lease = queue.pull(due if attempt > 1 else time.time())[0]
        result = worker.process_batch([item()])[0]
        with caplog.at_level(logging.ERROR, logger='utils.batch_pipeline.scheduler'):
            await Pump(queue, worker)._publish(lease, {'a': result}, set())
    assert marker not in caplog.text
    assert store.rows['jobs', 'a']['worker_failure_evidence'] == {'stage': 'fetch_decode', 'reason': 'unknown'}


@pytest.mark.asyncio
async def test_end_to_end_vad_failure_evidence_names_the_stage(monkeypatch):
    worker, *_ = setup_worker(vad=Mock(side_effect=RuntimeError('boom')))
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a', duration=60), time.time())
    lease = queue.pull(time.time())[0]
    result = worker.process_batch([item('a', duration=60)])[0]
    await Pump(queue, worker)._publish(lease, {'a': result}, set())
    assert store.rows['jobs', 'a']['worker_failure_evidence'] == {'stage': 'vad_windows', 'reason': 'unknown'}


@pytest.mark.asyncio
async def test_end_to_end_word_clock_failure_evidence_names_the_closed_reason(monkeypatch):
    class BrokenWords:
        def transcribe_batch(self, samples):
            return [[{'word': 'hi', 'timestamp': [-1, 0]}] for _ in samples]

    worker, *_ = setup_worker(words_providers={'parakeet': BrokenWords()})
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a', duration=60), time.time())
    lease = queue.pull(time.time())[0]
    result = worker.process_batch([item('a', duration=60)])[0]
    assert isinstance(result, FailedWork)
    await Pump(queue, worker)._publish(lease, {'a': result}, set())
    assert store.rows['jobs', 'a']['worker_failure_evidence'] == {'stage': 'word_clocks', 'reason': 'word_clock'}


@pytest.mark.asyncio
async def test_end_to_end_evidenced_and_plain_ladders_share_the_ceiling(monkeypatch):
    _, evidenced = await _pump_ladder(monkeypatch, lambda a: FailedWork('a', None, None, EVIDENCE), attempts=5)
    _, plain = await _pump_ladder(monkeypatch, lambda a: FailedWork('a', None, None), attempts=5)
    assert evidenced.rows['jobs', 'a']['attempt'] == plain.rows['jobs', 'a']['attempt'] == 5
    assert evidenced.rows['jobs', 'a']['state'] == plain.rows['jobs', 'a']['state'] == 'quarantined'


@pytest.mark.asyncio
async def test_end_to_end_evidenced_retry_keeps_merge_pending(monkeypatch):
    _, store = await _pump_ladder(monkeypatch, lambda a: FailedWork('a', None, None, EVIDENCE), attempts=2)
    assert store.rows['jobs', 'a']['merge_pending'] is True


@pytest.mark.asyncio
async def test_end_to_end_quarantined_evidenced_job_never_redrives(monkeypatch):
    queue, store = await _pump_ladder(monkeypatch, lambda a: FailedWork('a', None, None, EVIDENCE), attempts=5)
    job = store.rows['jobs', 'a']
    assert queue.recover(job['quarantined_at'] + 100000) == 0
    assert queue.pull(job['quarantined_at'] + 100000) == []
    assert not queue.redrive_dead('a', job['quarantined_at'] + 100000)


@pytest.mark.asyncio
async def test_end_to_end_safety_net_off_drop_publishes_a_none_result(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    worker, *_ = setup_worker(decode=Mock(side_effect=RuntimeError('boom')))
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), time.time())
    lease = queue.pull(time.time())[0]
    results = worker.process_batch([item()])
    assert results == []
    await Pump(queue, worker)._publish(lease, {}, set())
    job = store.rows['jobs', 'a']
    assert job['state'] == 'retry'
    assert 'worker_failure_evidence' not in job


# --- Shadow lane parity ---------------------------------------------------------------


async def _run_shadow(repository, work, result):
    from utils.batch_pipeline.capacity import PoolCapacity
    from utils.batch_pipeline.shadow_worker import ShadowRunner

    repository.take = lambda _: work
    recovery = Mock()
    runner = ShadowRunner(repository, recovery)
    worker = Mock()
    worker.process_batch.return_value = [result]
    pump = SimpleNamespace(_gpu=asyncio.Lock(), _normal_flights=0, worker=worker)
    capacity = PoolCapacity(time.time(), available_slots=1)
    assert await runner.run_once(pump, capacity=capacity) == 1
    return row(repository, work.segment_id), recovery


@pytest.mark.asyncio
async def test_shadow_evidenced_failure_finishes_as_an_error(repository):
    work = running(repository)
    result, _ = await _run_shadow(repository, work, FailedWork(work.segment_id, 2, None, EVIDENCE))
    assert result['outcome'] == 'error'
    assert result['speech_seconds'] == 2


@pytest.mark.asyncio
async def test_shadow_plain_failure_finishes_as_an_error(repository):
    work = running(repository)
    result, _ = await _run_shadow(repository, work, FailedWork(work.segment_id, 2, None))
    assert result['outcome'] == 'error'
    assert result['speech_seconds'] == 2


@pytest.mark.asyncio
async def test_shadow_evidence_never_authorizes_a_paid_recovery_call(repository):
    work = running(repository)
    _, recovery = await _run_shadow(repository, work, FailedWork(work.segment_id, 2, None, EVIDENCE))
    recovery.assert_not_called()


@pytest.mark.asyncio
async def test_shadow_evidenced_error_record_carries_no_evidence_fields(repository):
    work = running(repository)
    result, _ = await _run_shadow(repository, work, FailedWork(work.segment_id, 2, None, EVIDENCE))
    assert 'worker_failure' not in result
    assert 'worker_failure_evidence' not in result


@pytest.mark.asyncio
async def test_shadow_validation_failure_routes_to_handoff_not_finish(repository):
    from utils.batch_pipeline.capacity import PoolCapacity
    from utils.batch_pipeline.shadow_worker import ShadowRunner

    work = running(repository)
    repository.take = lambda _: work
    handoff = Mock(wraps=repository.handoff)
    finish = Mock(wraps=repository.finish)
    repository.handoff = handoff
    repository.finish = finish
    runner = ShadowRunner(repository, Mock())
    worker = Mock()
    worker.process_batch.return_value = [ValidationFailureWork(work.segment_id, 'fetch_decode', 'staged_audio_invalid')]
    pump = SimpleNamespace(_gpu=asyncio.Lock(), _normal_flights=0, worker=worker)
    assert await runner.run_once(pump, capacity=PoolCapacity(time.time(), available_slots=1)) == 1
    assert handoff.call_args.args[1].reason == 'staged_audio_invalid'
    finish.assert_not_called()


@pytest.mark.asyncio
async def test_shadow_recovery_work_routes_to_handoff_not_finish(repository):
    from utils.batch_pipeline.capacity import PoolCapacity
    from utils.batch_pipeline.shadow_worker import ShadowRunner

    work = running(repository)
    repository.take = lambda _: work
    handoff = Mock(wraps=repository.handoff)
    finish = Mock(wraps=repository.finish)
    repository.handoff = handoff
    repository.finish = finish
    runner = ShadowRunner(repository, Mock())
    worker = Mock()
    worker.process_batch.return_value = [RecoveryWork(work.segment_id)]
    pump = SimpleNamespace(_gpu=asyncio.Lock(), _normal_flights=0, worker=worker)
    assert await runner.run_once(pump, capacity=PoolCapacity(time.time(), available_slots=1)) == 1
    assert handoff.call_args.args[1].reason == 'empty_asr'
    finish.assert_not_called()


# --- Cross-cutting regression guards -------------------------------------------------


@pytest.mark.asyncio
async def test_sched_fail_signature_still_accepts_the_parent_shaped_call(monkeypatch):
    queue, store, lease, _ = _leased_queue(monkeypatch)
    assert await _published(queue, lease, FailedWork('a', None, None)) is True
    assert store.rows['jobs', 'a']['state'] == 'retry'


@pytest.mark.asyncio
async def test_evidenced_ladder_writes_no_result_row(monkeypatch):
    _, store = await _pump_ladder(monkeypatch, lambda a: FailedWork('a', None, None, EVIDENCE), attempts=5)
    assert ('results', 'a') not in store.rows


@pytest.mark.asyncio
async def test_evidenced_retry_job_has_no_result_and_no_worker_failure(monkeypatch):
    _, store = await _pump_ladder(monkeypatch, lambda a: FailedWork('a', None, None, EVIDENCE), attempts=1)
    job = store.rows['jobs', 'a']
    assert 'result' not in job
    assert 'worker_failure' not in job
    assert job['worker_failure_evidence'] == EVIDENCE


@pytest.mark.asyncio
async def test_evidenced_ladder_records_the_retry_metric(monkeypatch):
    store = MemoryStore()
    metrics = Mock()
    queue = Scheduler(store, metrics=metrics)
    queue.enqueue(item('a'), time.time())
    lease = queue.pull(time.time())[0]
    await Pump(queue, _worker())._publish(lease, {'a': FailedWork('a', None, None, EVIDENCE)}, set())
    assert ('retry',) in [c.args for c in metrics.record.call_args_list]


@pytest.mark.asyncio
async def test_completed_evidenced_job_publishes_clean_metadata(monkeypatch):
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), time.time())
    lease = queue.pull(time.time())[0]
    await Pump(queue, _worker())._publish(lease, {'a': FailedWork('a', None, None, EVIDENCE)}, set())
    due = store.rows['jobs', 'a']['available_at']
    queue.recover(due)
    lease2 = queue.pull(due)[0]
    assert await Pump(queue, _worker())._publish(lease2, {'a': WorkResult('a', 'gs://results/a')}, set()) is True
    job = store.rows['jobs', 'a']
    assert job['state'] == 'result_ready'
    assert 'worker_failure_evidence' not in job


# --- Typed terminal families keep their contracts through the pump -------------------


@pytest.mark.asyncio
async def test_pump_typed_failure_quarantines_and_writes_no_evidence_key(monkeypatch, caplog):
    queue, store, lease, _ = _leased_queue(monkeypatch)
    with caplog.at_level(logging.ERROR, logger='utils.batch_pipeline.scheduler'):
        assert (
            await _published(queue, lease, ValidationFailureWork('a', 'fetch_decode', 'staged_audio_invalid')) is True
        )
    job = store.rows['jobs', 'a']
    assert job['state'] == 'quarantined' and job['attempt'] == 1
    assert job['worker_failure'] == {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}
    assert 'worker_failure_evidence' not in job
    quarantined = [r for r in caplog.records if 'event=batch_quarantined' in r.getMessage()]
    assert quarantined[-1].getMessage().endswith('stage=fetch_decode worker_reason=staged_audio_invalid')


@pytest.mark.asyncio
async def test_pump_typed_duration_mismatch_quarantine_log_keeps_its_reason(monkeypatch, caplog):
    queue, store, lease, _ = _leased_queue(monkeypatch)
    with caplog.at_level(logging.ERROR, logger='utils.batch_pipeline.scheduler'):
        await _published(queue, lease, ValidationFailureWork('a', 'fetch_decode', 'decoded_duration_mismatch'))
    quarantined = [r for r in caplog.records if 'event=batch_quarantined' in r.getMessage()]
    assert quarantined[-1].getMessage().endswith('worker_reason=decoded_duration_mismatch')
    assert 'worker_failure_evidence' not in store.rows['jobs', 'a']


@pytest.mark.asyncio
async def test_pump_recovery_work_records_the_padded_retry_evidence(monkeypatch):
    queue, store, lease, _ = _leased_queue(monkeypatch)
    assert await _published(queue, lease, RecoveryWork('a', padded_retry='empty')) is True
    job = store.rows['jobs', 'a']
    assert job['state'] == 'quarantined'
    assert job['worker_empty_evidence'] == {'padded_retry': 'empty', 'version': 1}
    assert 'worker_failure_evidence' not in job


@pytest.mark.asyncio
async def test_pump_evidence_forwarding_is_reference_faithful(monkeypatch):
    queue, _, lease, fail = _leased_queue(monkeypatch)
    evidence = {'stage': 'asr_recovery', 'reason': 'unknown'}
    await _published(queue, lease, FailedWork('a', None, None, evidence))
    assert fail.call_args.kwargs['worker_failure_evidence'] is evidence


@pytest.mark.asyncio
async def test_pump_evidenced_publish_on_a_revoked_lease_is_lost(monkeypatch):
    queue, store, lease, _ = _leased_queue(monkeypatch)
    store.rows['jobs', 'a']['token'] = 'revoked'
    lost = set()
    assert await _published_into(queue, lease, FailedWork('a', None, None, EVIDENCE), lost) is False
    assert lost == set()  # a refused (not failing) RPC is a clean False, not a lost segment


async def _published_into(queue, lease, result, lost):
    return await Pump(queue, _worker())._publish(lease, {'a': result}, lost)


@pytest.mark.asyncio
async def test_pump_evidenced_failed_work_with_default_evidence_fields(monkeypatch):
    queue, _, lease, fail = _leased_queue(monkeypatch)
    await _published(queue, lease, FailedWork('a'))
    assert fail.call_args.kwargs['worker_failure_evidence'] is None
    assert fail.call_args.kwargs['measured_held_vad_speech_seconds'] is None
    assert fail.call_args.kwargs['worker_vad_receipt'] is None


@pytest.mark.asyncio
async def test_evidenced_ladder_separates_worker_and_scheduler_logs(monkeypatch, caplog):
    with caplog.at_level(0):
        await _pump_ladder(monkeypatch, lambda a: FailedWork('a', None, None, EVIDENCE), attempts=5, caplog=caplog)
    assert not any('event=batch_worker_failed' in r.getMessage() for r in caplog.records)
    assert any('event=batch_quarantined' in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_evidenced_ladder_replaces_the_diagnosis_on_the_final_attempt(monkeypatch):
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), time.time())
    work = FailedWork('a', None, None, EVIDENCE)
    for attempt in range(1, 6):
        if attempt > 1:
            due = store.rows['jobs', 'a']['available_at']
            queue.recover(due)
        lease = queue.pull(due if attempt > 1 else time.time())[0]
        final = FailedWork('a', None, None, {'stage': 'word_clocks', 'reason': 'word_shape'}) if attempt == 5 else work
        await Pump(queue, _worker())._publish(lease, {'a': final}, set())
    job = store.rows['jobs', 'a']
    assert job['state'] == 'quarantined'
    assert job['worker_failure_evidence'] == {'stage': 'word_clocks', 'reason': 'word_shape'}


@pytest.mark.asyncio
async def test_shadow_evidenced_failure_without_measured_speech_records_unknown_vad(repository):
    work = running(repository)
    result, _ = await _run_shadow(repository, work, FailedWork(work.segment_id, None, None, EVIDENCE))
    assert result['outcome'] == 'error'
    assert result['vad'] == 'unknown'
    assert result['speech_seconds'] == 0


@pytest.mark.asyncio
async def test_shadow_evidenced_row_keys_match_the_plain_row_keys(repository):
    work = running(repository)
    evidenced, _ = await _run_shadow(repository, work, FailedWork(work.segment_id, 2, None, EVIDENCE))
    assert evidenced['outcome'] == 'error'
    assert 'worker_failure' not in evidenced
    assert 'worker_failure_evidence' not in evidenced
    assert 'stage' not in evidenced and 'reason' not in evidenced


@pytest.mark.asyncio
async def test_evidenced_failed_work_stays_usable_as_a_map_value(monkeypatch):
    queue, store, lease, _ = _leased_queue(monkeypatch)
    result_map = {'a': FailedWork('a', None, None, EVIDENCE)}
    assert await Pump(queue, _worker())._publish(lease, result_map, set()) is True
    assert store.rows['jobs', 'a']['worker_failure_evidence'] == EVIDENCE


@pytest.mark.asyncio
async def test_two_evidenced_segments_in_one_flight_publish_independently(monkeypatch):
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), time.time())
    queue.enqueue(item('b'), time.time())
    leases = {lease.item.segment_id: lease for lease in [queue.pull(time.time())[0], queue.pull(time.time())[0]]}
    worker = _worker()
    pump = Pump(queue, worker)
    assert (
        await pump._publish(
            leases['a'], {'a': FailedWork('a', None, None, {'stage': 'fetch_decode', 'reason': 'unknown'})}, set()
        )
        is True
    )
    assert (
        await pump._publish(
            leases['b'], {'b': FailedWork('b', None, None, {'stage': 'vad_windows', 'reason': 'unknown'})}, set()
        )
        is True
    )
    assert store.rows['jobs', 'a']['worker_failure_evidence']['stage'] == 'fetch_decode'
    assert store.rows['jobs', 'b']['worker_failure_evidence']['stage'] == 'vad_windows'
