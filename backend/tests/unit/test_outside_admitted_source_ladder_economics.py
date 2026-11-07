"""Ladder economics for the named outside-admitted-source fault, end to end.

The named fault must behave exactly like the anonymous unclassified fault it
replaced at the transition level — defer, evidence preserved, backoff,
max-attempts quarantine — and must never gain the terminal chain-ender
disposition its bytes-family siblings carry. This suite walks the real
Scheduler ladder through the pump's publication seam.

Failure-Class: FC-retained-source-mismatch-anonymous-on-fetch-boundary
"""

import time
from unittest.mock import Mock

import pytest

from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from tests.unit.test_batch_pipeline_worker import item
from utils.batch_pipeline.contracts import FailedWork, ValidationFailureWork
from utils.batch_pipeline.pump import Pump
from utils.batch_pipeline.scheduler import Scheduler
from utils.batch_pipeline.source_audio import RetainedAudioOutsideAdmittedSource

NAMED = {'stage': 'fetch_decode', 'reason': 'outside_admitted_source'}


def fresh_queue():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    return store, queue


def pull_swept(queue, now, advance=10.0, limit=12):
    for _ in range(limit):
        leases = queue.pull(now)
        if leases:
            return leases[0], now
        now += advance
        queue.recover(now)
    raise AssertionError('no due lease appeared')


async def publish_named(queue, lease, now, evidence=NAMED):
    return await Pump(queue, None)._publish(lease, {'a': FailedWork('a', None, None, worker_failure=evidence)}, set())


# --- The pump publishes the named evidence to the scheduler ------------------------


@pytest.mark.asyncio
async def test_pump_publishes_the_named_evidence_on_failure():
    store, queue = fresh_queue()
    now = time.time()
    lease, now = pull_swept(queue, now)
    assert await publish_named(queue, lease, now) is True
    assert store.rows['jobs', 'a']['worker_failure_evidence'] == NAMED


@pytest.mark.asyncio
async def test_pump_published_named_failure_defers():
    store, queue = fresh_queue()
    now = time.time()
    lease, now = pull_swept(queue, now)
    await publish_named(queue, lease, now)
    assert store.rows['jobs', 'a']['state'] == 'retry'


@pytest.mark.asyncio
async def test_pump_published_named_failure_carries_no_structured_failure():
    store, queue = fresh_queue()
    now = time.time()
    lease, now = pull_swept(queue, now)
    await publish_named(queue, lease, now)
    assert 'worker_failure' not in store.rows['jobs', 'a']


@pytest.mark.asyncio
async def test_pump_published_named_failure_keeps_measured_vad_none():
    store, queue = fresh_queue()
    now = time.time()
    lease, now = pull_swept(queue, now)
    await publish_named(queue, lease, now)
    job = store.rows['jobs', 'a']
    assert job.get('measured_held_vad_speech_seconds') is None


@pytest.mark.asyncio
async def test_pump_publishes_evidence_less_failure_without_touching_the_diagnosis():
    store, queue = fresh_queue()
    now = time.time()
    lease, now = pull_swept(queue, now)
    await publish_named(queue, lease, now)
    later = store.rows['jobs', 'a']['available_at'] + 1
    lease2, later = pull_swept(queue, later)
    result = FailedWork('a', None, None, worker_failure=None)
    assert await Pump(queue, None)._publish(lease2, {'a': result}, set()) is True
    assert store.rows['jobs', 'a']['worker_failure_evidence'] == NAMED


@pytest.mark.asyncio
async def test_pump_named_failure_never_quarantines_via_the_publication_seam():
    store, queue = fresh_queue()
    now = time.time()
    lease, now = pull_swept(queue, now)
    await publish_named(queue, lease, now)
    assert store.rows['jobs', 'a']['state'] == 'retry'


@pytest.mark.asyncio
async def test_pump_named_failure_returns_true_for_the_owner_drain():
    store, queue = fresh_queue()
    now = time.time()
    lease, now = pull_swept(queue, now)
    assert await publish_named(queue, lease, now) is True


# --- The full named walk through the publication seam -------------------------------


@pytest.mark.asyncio
async def test_named_walk_quarantines_at_max_attempts():
    store, queue = fresh_queue()
    now = time.time()
    for attempt in range(1, 6):
        lease, now = pull_swept(queue, now)
        now += 10
        queue.fail('a', lease.token, now, worker_failure_evidence=NAMED)
    job = store.rows['jobs', 'a']
    assert job['state'] == 'quarantined'
    assert job['attempt'] == 5


@pytest.mark.asyncio
async def test_named_walk_attempt_five_is_the_terminal_record(monkeypatch, caplog):
    import logging

    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    store, queue = fresh_queue()
    now = time.time()
    for attempt in range(1, 6):
        lease, now = pull_swept(queue, now)
        now += 10
        queue.fail('a', lease.token, now, worker_failure_evidence=NAMED if attempt == 1 else None)
    with caplog.at_level(logging.ERROR, logger='utils.batch_pipeline.scheduler'):
        pass
    job = store.rows['jobs', 'a']
    assert job['worker_failure_evidence'] == NAMED
    assert job['quarantine_reason'] == 'worker_failed'


@pytest.mark.asyncio
async def test_named_walk_never_sets_the_structured_failure_field():
    store, queue = fresh_queue()
    now = time.time()
    for attempt in range(1, 6):
        lease, now = pull_swept(queue, now)
        now += 10
        queue.fail('a', lease.token, now, worker_failure_evidence=NAMED)
    assert 'worker_failure' not in store.rows['jobs', 'a']


@pytest.mark.asyncio
async def test_named_walk_recovery_state_is_held_at_the_end():
    store, queue = fresh_queue()
    now = time.time()
    for attempt in range(1, 6):
        lease, now = pull_swept(queue, now)
        now += 10
        queue.fail('a', lease.token, now, worker_failure_evidence=NAMED)
    assert store.rows['jobs', 'a']['recovery_state'] == 'held'


# --- The typed bytes family keeps its terminal disposition --------------------------


@pytest.mark.asyncio
async def test_bytes_family_still_quarantines_on_attempt_one():
    store, queue = fresh_queue()
    now = time.time()
    lease, now = pull_swept(queue, now)
    assert queue.fail(
        'a', lease.token, now, worker_failure={'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'}
    )
    assert store.rows['jobs', 'a']['state'] == 'quarantined'


@pytest.mark.asyncio
async def test_bytes_family_publishes_through_the_terminal_validation_work():
    store, queue = fresh_queue()
    now = time.time()
    lease, now = pull_swept(queue, now)
    result = ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')
    assert await Pump(queue, None)._publish(lease, {'a': result}, set()) is True
    job = store.rows['jobs', 'a']
    assert job['state'] == 'quarantined'
    assert job['worker_failure'] == {'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'}


@pytest.mark.asyncio
async def test_named_fault_is_not_confused_with_the_terminal_validation_work():
    store, queue = fresh_queue()
    now = time.time()
    lease, now = pull_swept(queue, now)
    result = FailedWork('a', None, None, worker_failure=NAMED)
    await Pump(queue, None)._publish(lease, {'a': result}, set())
    assert store.rows['jobs', 'a']['state'] == 'retry'


# --- Backoff economics for the named ladder ----------------------------------------


@pytest.mark.asyncio
async def test_named_backoff_doubles_from_five_seconds():
    store, queue = fresh_queue()
    now = time.time()
    lease, now = pull_swept(queue, now)
    queue.fail('a', lease.token, now, worker_failure_evidence=NAMED)
    assert round(store.rows['jobs', 'a']['available_at'] - now) == 5


@pytest.mark.asyncio
async def test_named_backoff_is_never_negative():
    store, queue = fresh_queue()
    now = time.time()
    lease, now = pull_swept(queue, now)
    queue.fail('a', lease.token, now, worker_failure_evidence=NAMED)
    assert store.rows['jobs', 'a']['available_at'] >= now


@pytest.mark.asyncio
async def test_named_backoff_sets_retry_started_at_once():
    store, queue = fresh_queue()
    now = time.time()
    lease, now = pull_swept(queue, now)
    queue.fail('a', lease.token, now, worker_failure_evidence=NAMED)
    first = store.rows['jobs', 'a']['retry_started_at']
    now = store.rows['jobs', 'a']['available_at'] + 1
    lease, now = pull_swept(queue, now)
    queue.fail('a', lease.token, now, worker_failure_evidence=NAMED)
    assert store.rows['jobs', 'a']['retry_started_at'] == first


# --- Fault-class identity through the scheduler surfaces ----------------------------


def test_named_fault_class_is_exported_for_the_worker_boundary():
    from diarizer.batch_pipeline import RetainedAudioOutsideAdmittedSource as BoundaryName

    assert BoundaryName is RetainedAudioOutsideAdmittedSource


def test_named_fault_evidence_survives_a_dict_copy_roundtrip():
    import copy

    assert copy.deepcopy(NAMED) == NAMED
    assert dict(NAMED) == NAMED


def test_named_fault_evidence_matches_the_closed_token_string():
    from utils.observability.reasons import WorkerValidationReason

    assert NAMED['reason'] == WorkerValidationReason.OUTSIDE_ADMITTED_SOURCE.value


def test_named_fault_stage_matches_the_fetch_decode_stage_token():
    from utils.observability.reasons import WorkerValidationStage

    assert NAMED['stage'] == WorkerValidationStage.FETCH_DECODE.value


def test_named_fault_never_carries_a_message_like_field():
    assert set(NAMED) == {'stage', 'reason'}


# --- Quarantine row shape after the named walk ---------------------------------------


def test_named_walk_terminal_row_shape():
    store, queue = fresh_queue()
    now = time.time()
    for attempt in range(1, 6):
        lease, now = pull_swept(queue, now)
        now += 10
        queue.fail('a', lease.token, now, worker_failure_evidence=NAMED)
    job = store.rows['jobs', 'a']
    assert job['state'] == 'quarantined'
    assert job['token'] == ''
    assert job['lease_until'] == 0.0
    assert job['merge_pending'] is False
    assert job['recovery_state'] == 'held'
    assert job['quarantine_reason'] == 'worker_failed'
    assert job['quarantined_at'] > 0
    assert job['failure'] == 'worker_failed'


def test_named_walk_keeps_the_attempt_counter_monotonic():
    store, queue = fresh_queue()
    now = time.time()
    seen = []
    for attempt in range(1, 6):
        lease, now = pull_swept(queue, now)
        now += 10
        queue.fail('a', lease.token, now, worker_failure_evidence=NAMED)
        seen.append(store.rows['jobs', 'a']['attempt'])
    assert seen == [1, 2, 3, 4, 5]


def test_named_walk_quarantined_unit_is_not_re_admitted_by_enqueue():
    store, queue = fresh_queue()
    now = time.time()
    for attempt in range(1, 6):
        lease, now = pull_swept(queue, now)
        now += 10
        queue.fail('a', lease.token, now, worker_failure_evidence=NAMED)
    assert queue.enqueue(item(), time.time() + 3600) is False


def test_named_walk_survives_a_full_recover_sweep_without_requeue():
    store, queue = fresh_queue()
    now = time.time()
    for attempt in range(1, 6):
        lease, now = pull_swept(queue, now)
        now += 10
        queue.fail('a', lease.token, now, worker_failure_evidence=NAMED)
    assert queue.recover(now + 3600) == 0
    assert store.rows['jobs', 'a']['state'] == 'quarantined'
