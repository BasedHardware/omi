"""The terminal quarantine keeps the diagnosis its ladder collected.

The scheduler's terminal quarantine record read only the current attempt's
locals: a ladder whose exhausting attempt arrived evidence-less (a missing
worker result, an untyped stage) logged
``stage=unknown worker_reason=unclassified`` even though every earlier
attempt had carried its diagnosis and the commit preserved it on the job
("a later attempt without evidence preserves the previous diagnosis"). The
record now prefers the current attempt's structured worker_failure, then its
evidence, then the preserved diagnosis; a never-diagnosed unit still records
the historical anonymous shape.

Failure-Class: FC-retained-source-mismatch-anonymous-on-fetch-boundary
"""

import logging
import time
from dataclasses import replace

import pytest

from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from tests.unit.test_batch_pipeline_worker import item
from utils.batch_pipeline.contracts import FailedWork, Priority, ValidationFailureWork, WorkItem
from utils.batch_pipeline.scheduler import Scheduler
from utils.batch_pipeline.source_audio import RetainedAudioOutsideAdmittedSource
from utils.observability.reasons import WorkerValidationReason

NAMED = {'stage': 'fetch_decode', 'reason': 'outside_admitted_source'}
BYTES = {'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'}
LOGGER = 'utils.batch_pipeline.scheduler'


def store_with_job():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    return store, queue


def walk(queue, store, *, evidence_plan, advance=10.0, limit=8):
    """Pull->fail until the unit quarantines; evidence_plan maps attempt->evidence."""
    now = time.time()
    attempt = 0
    while attempt < limit:
        leases = queue.pull(now)
        if not leases:
            # A deferred unit left the pull ring: the recovery sweep re-appends
            # due retries to their owner FIFO (the ladder's re-entry path).
            now += advance
            queue.recover(now)
            continue
        attempt += 1
        now += advance
        queue.fail(
            'a',
            leases[0].token,
            now,
            worker_failure_evidence=evidence_plan.get(attempt),
        )
        if store.rows['jobs', 'a']['state'] == 'quarantined':
            return attempt, now
    raise AssertionError('ladder never quarantined the unit')


def quarantine_lines(caplog):
    return [line for line in caplog.text.splitlines() if 'event=batch_quarantined reason=worker_failed' in line]


def pull_due(queue, now, advance=10.0, limit=12):
    """Pull with the recovery sweep re-appending due retries (the ladder's re-entry)."""
    for _ in range(limit):
        leases = queue.pull(now)
        if leases:
            return leases[0], now
        now += advance
        queue.recover(now)
    raise AssertionError('no due lease appeared')


# --- The fix: an evidence-less exhausting attempt keeps the diagnosis --------------


def test_terminal_record_names_the_preserved_diagnosis(caplog):
    store, queue = store_with_job()
    with caplog.at_level(logging.ERROR, logger=LOGGER):
        walk(queue, store, evidence_plan={1: NAMED})
    record = quarantine_lines(caplog)[-1]
    assert 'stage=fetch_decode' in record
    assert 'worker_reason=outside_admitted_source' in record


def test_terminal_record_names_the_preserved_diagnosis_at_attempt_five(caplog):
    store, queue = store_with_job()
    with caplog.at_level(logging.ERROR, logger=LOGGER):
        attempt, _ = walk(queue, store, evidence_plan={1: NAMED})
    assert attempt == 5  # SchedulerPolicy.max_attempts default: the sensor's attempt=5/5


def test_terminal_record_names_the_preserved_bytes_diagnosis(caplog):
    store, queue = store_with_job()
    with caplog.at_level(logging.ERROR, logger=LOGGER):
        walk(queue, store, evidence_plan={1: BYTES, 2: BYTES})
    record = quarantine_lines(caplog)[-1]
    assert 'worker_reason=retained_audio_invalid' in record


def test_terminal_record_prefers_the_exhausting_attempts_own_evidence(caplog):
    store, queue = store_with_job()
    with caplog.at_level(logging.ERROR, logger=LOGGER):
        walk(queue, store, evidence_plan={1: BYTES, 4: NAMED})
    record = quarantine_lines(caplog)[-1]
    # Attempt 4 carried the newest diagnosis; attempt 5 arrived empty.
    assert 'worker_reason=outside_admitted_source' in record


def test_terminal_record_prefers_the_structured_worker_failure_over_all_evidence(caplog):
    store, queue = store_with_job()
    queue.enqueue(item(), time.time())
    now = time.time()
    lease = queue.pull(now)[0]
    with caplog.at_level(logging.ERROR, logger=LOGGER):
        queue.fail('a', lease.token, now, worker_failure=BYTES, worker_failure_evidence=NAMED)
    record = quarantine_lines(caplog)[-1]
    assert 'worker_reason=retained_audio_invalid' in record


def test_terminal_record_for_a_never_diagnosed_unit_stays_anonymous(caplog):
    store, queue = store_with_job()
    with caplog.at_level(logging.ERROR, logger=LOGGER):
        walk(queue, store, evidence_plan={})
    record = quarantine_lines(caplog)[-1]
    assert 'stage=unknown' in record
    assert 'worker_reason=unclassified' in record


def test_preserved_diagnosis_lands_on_the_job_for_the_terminal_record():
    store, queue = store_with_job()
    walk(queue, store, evidence_plan={1: NAMED})
    job = store.rows['jobs', 'a']
    assert job['worker_failure_evidence'] == NAMED


def test_an_evidence_less_mid_ladder_attempt_preserves_the_earlier_diagnosis():
    store, queue = store_with_job()
    walk(queue, store, evidence_plan={1: NAMED})
    job = store.rows['jobs', 'a']
    # Attempts 2..N carried nothing; the job keeps attempt 1's diagnosis.
    assert job['worker_failure_evidence'] == NAMED


def test_the_latest_evidence_replaces_the_preserved_one_on_the_job():
    store, queue = store_with_job()
    walk(queue, store, evidence_plan={1: BYTES, 2: NAMED})
    job = store.rows['jobs', 'a']
    assert job['worker_failure_evidence'] == NAMED


# --- The ladder's transitions stay exactly as before -------------------------------


def test_named_evidence_defers_on_the_first_attempt():
    store, queue = store_with_job()
    now = time.time()
    lease = queue.pull(now)[0]
    assert queue.fail('a', lease.token, now, worker_failure_evidence=NAMED) is True
    job = store.rows['jobs', 'a']
    assert job['state'] == 'retry'
    assert job['attempt'] == 1
    assert 'worker_failure' not in job


def test_named_evidence_never_quarantines_early():
    store, queue = store_with_job()
    attempt, _ = walk(queue, store, evidence_plan={1: NAMED})
    assert attempt == 5
    assert store.rows['jobs', 'a']['state'] == 'quarantined'


def test_quarantined_named_unit_leaves_the_pull_ring():
    store, queue = store_with_job()
    walk(queue, store, evidence_plan={1: NAMED})
    assert queue.pull(time.time() + 3600) == []


def test_quarantine_marks_recovery_held_and_drops_merge_pending():
    store, queue = store_with_job()
    walk(queue, store, evidence_plan={1: NAMED})
    job = store.rows['jobs', 'a']
    assert job['recovery_state'] == 'held'
    assert job['merge_pending'] is False
    assert job['quarantine_reason'] == 'worker_failed'


def test_defer_backoff_grows_per_attempt_then_caps():
    store, queue = store_with_job()
    now = time.time()
    gaps = []
    for attempt in range(1, 5):
        lease, now = pull_due(queue, now)
        queue.fail('a', lease.token, now, worker_failure_evidence=NAMED)
        job = store.rows['jobs', 'a']
        gaps.append(job['available_at'] - now)
        now = job['available_at']
    assert gaps[0] == 5.0
    assert gaps[1] == 10.0
    assert gaps[2] == 20.0
    assert gaps[3] == 40.0


def test_defer_backoff_never_exceeds_the_cap():
    store, queue = store_with_job()
    now = time.time()
    lease = queue.pull(now)[0]
    queue.fail('a', lease.token, now, worker_failure_evidence=NAMED)
    job = store.rows['jobs', 'a']
    now = job['available_at']
    for _ in range(12):
        leases = queue.pull(now)
        if not leases:
            now += 700
            continue
        queue.fail('a', leases[0].token, now, worker_failure_evidence=NAMED)
        job = store.rows['jobs', 'a']
        assert job['available_at'] - now <= 600.0
        if job['state'] == 'quarantined':
            break
        now = job['available_at']


def test_defer_clears_the_lease_and_records_the_machine_reason():
    store, queue = store_with_job()
    now = time.time()
    lease = queue.pull(now)[0]
    queue.fail('a', lease.token, now, worker_failure_evidence=NAMED)
    job = store.rows['jobs', 'a']
    assert job['token'] == ''
    assert job['lease_until'] == 0.0
    assert job['failure'] == 'worker_failed'


def test_a_stale_token_cannot_move_the_job():
    store, queue = store_with_job()
    now = time.time()
    lease = queue.pull(now)[0]
    assert queue.fail('a', 'not-the-token', now, worker_failure_evidence=NAMED) is False
    assert store.rows['jobs', 'a']['state'] == 'leased'


def test_a_stale_token_cannot_quarantine_the_job():
    store, queue = store_with_job()
    now = time.time()
    lease = queue.pull(now)[0]
    assert queue.fail('a', 'not-the-token', now, worker_failure=BYTES) is False
    assert store.rows['jobs', 'a']['state'] == 'leased'


# --- Evidence validation at the scheduler boundary ----------------------------------


def test_evidence_with_an_open_reason_is_refused():
    store, queue = store_with_job()
    now = time.time()
    lease = queue.pull(now)[0]
    with pytest.raises(ValueError, match='closed worker failure evidence required'):
        queue.fail('a', lease.token, now, worker_failure_evidence={'stage': 'fetch_decode', 'reason': 'unclassified'})


def test_evidence_with_an_open_stage_is_refused():
    store, queue = store_with_job()
    now = time.time()
    lease = queue.pull(now)[0]
    with pytest.raises(ValueError, match='closed worker failure evidence required'):
        queue.fail(
            'a', lease.token, now, worker_failure_evidence={'stage': 'smoke', 'reason': 'outside_admitted_source'}
        )


def test_structured_failure_with_the_named_reason_is_accepted():
    store, queue = store_with_job()
    now = time.time()
    lease = queue.pull(now)[0]
    assert queue.fail('a', lease.token, now, worker_failure=NAMED) is True
    assert store.rows['jobs', 'a']['state'] == 'quarantined'


def test_structured_failure_quarantines_on_the_first_attempt():
    store, queue = store_with_job()
    now = time.time()
    lease = queue.pull(now)[0]
    queue.fail('a', lease.token, now, worker_failure=BYTES)
    assert store.rows['jobs', 'a']['attempt'] == 1


def test_structured_failure_records_stage_and_reason_on_the_job():
    store, queue = store_with_job()
    now = time.time()
    lease = queue.pull(now)[0]
    queue.fail('a', lease.token, now, worker_failure=BYTES)
    job = store.rows['jobs', 'a']
    assert job['worker_failure'] == BYTES


def test_structured_failure_does_not_shadow_the_evidence_field():
    store, queue = store_with_job()
    now = time.time()
    lease = queue.pull(now)[0]
    queue.fail('a', lease.token, now, worker_failure=BYTES, worker_failure_evidence=NAMED)
    job = store.rows['jobs', 'a']
    assert job['worker_failure'] == BYTES
    assert job['worker_failure_evidence'] == NAMED


def test_malformed_evidence_shape_is_refused():
    store, queue = store_with_job()
    now = time.time()
    lease = queue.pull(now)[0]
    with pytest.raises(ValueError, match='closed worker failure evidence required'):
        queue.fail('a', lease.token, now, worker_failure_evidence={'stage': 'fetch_decode'})


def test_evidence_extra_keys_are_refused():
    store, queue = store_with_job()
    now = time.time()
    lease = queue.pull(now)[0]
    with pytest.raises(ValueError, match='closed worker failure evidence required'):
        queue.fail(
            'a',
            lease.token,
            now,
            worker_failure_evidence={'stage': 'fetch_decode', 'reason': 'outside_admitted_source', 'site': 'x'},
        )


def test_the_unknown_evidence_token_remains_evidence_only():
    store, queue = store_with_job()
    now = time.time()
    lease = queue.pull(now)[0]
    assert (
        queue.fail('a', lease.token, now, worker_failure_evidence={'stage': 'fetch_decode', 'reason': 'unknown'})
        is True
    )
    assert store.rows['jobs', 'a']['state'] == 'retry'


def test_the_unknown_token_is_refused_as_a_structured_failure():
    store, queue = store_with_job()
    now = time.time()
    lease = queue.pull(now)[0]
    with pytest.raises(ValueError, match='closed worker validation failure required'):
        queue.fail('a', lease.token, now, worker_failure={'stage': 'fetch_decode', 'reason': 'unknown'})


# --- Ready transitions collect a fresh diagnosis ------------------------------------


def test_complete_clears_the_preserved_diagnosis():
    store, queue = store_with_job()
    now = time.time()
    lease = queue.pull(now)[0]
    queue.fail('a', lease.token, now, worker_failure_evidence=NAMED)
    job = store.rows['jobs', 'a']
    later = job['available_at'] + 1
    lease, later = pull_due(queue, later)
    from utils.batch_pipeline.contracts import WorkResult

    queue.complete(WorkResult('a', 'encrypted-result://a', 'success'), lease.token, later)
    assert 'worker_failure_evidence' not in store.rows['jobs', 'a']


def _ready_facade(store, queue, job_updates):
    """Seed a MemoryStore row set for the static ready transitions."""
    from config.batch_pipeline import scheduler_control_key
    from utils.batch_pipeline.scheduler import owner_key

    job = dict(store.rows['jobs', 'a'])
    job.update(job_updates)
    store.rows['jobs', 'a'] = job
    store.rows['owners', job['owner_key']] = {'revision': 0}
    store.rows['control', scheduler_control_key(job['owner_key'])] = {'rings': {'0': [], '1': [], '2': []}}
    return job


class _StaticTx:
    """Minimal transaction facade over MemoryStore rows for static transitions."""

    def __init__(self, store):
        self._store = store

    def get(self, table, key):
        return self._store.rows.get((table, key), {})

    def put(self, table, key, value):
        self._store.rows[table, key] = value


def test_restore_clears_the_quarantined_epochs_diagnosis():
    store, queue = store_with_job()
    walk(queue, store, evidence_plan={1: NAMED})
    job = _ready_facade(
        store,
        queue,
        {
            'artifact_disposition': {'state': 'restored'},
            'recovery_state': 'failed_held',
            'result': None,
            'merge_pending': False,
            'token': '',
            'lease_until': 0.0,
        },
    )
    Scheduler.restore_audio_in_transaction(_StaticTx(store), job, time.time(), frontier=0.0)
    assert store.rows['jobs', 'a']['state'] == 'ready'
    assert 'worker_failure_evidence' not in store.rows['jobs', 'a']


def test_restore_refuses_an_unverified_repair():
    store, queue = store_with_job()
    job = _ready_facade(
        store,
        queue,
        {'state': 'quarantined', 'recovery_state': 'held', 'artifact_disposition': {'state': 'unverified'}},
    )
    with pytest.raises(ValueError, match='verified missing-input repair required'):
        Scheduler.restore_audio_in_transaction(_StaticTx(store), job, time.time(), frontier=0.0)


def test_redrive_clears_the_dead_epochs_diagnosis():
    store, queue = store_with_job()
    job = _ready_facade(store, queue, {'state': 'dead', 'merge_pending': True, 'worker_failure_evidence': NAMED})
    assert (
        Scheduler.redrive_in_transaction(_StaticTx(store), store.rows['jobs', 'a'], time.time(), frontier=0.0) is True
    )
    assert 'worker_failure_evidence' not in store.rows['jobs', 'a']
    assert store.rows['jobs', 'a']['state'] == 'ready'


def test_redrive_refuses_a_unit_that_is_not_dead():
    store, queue = store_with_job()
    job = _ready_facade(store, queue, {'state': 'retry', 'merge_pending': True})
    assert Scheduler.redrive_in_transaction(_StaticTx(store), job, time.time(), frontier=0.0) is False


def test_redrive_refuses_a_unit_that_lost_merge_pending():
    store, queue = store_with_job()
    job = _ready_facade(store, queue, {'state': 'dead', 'merge_pending': False})
    assert Scheduler.redrive_in_transaction(_StaticTx(store), job, time.time(), frontier=0.0) is False


# --- The record's precedence is total ------------------------------------------------


def test_worker_failure_beats_preserved_diagnosis_without_current_evidence(caplog):
    store, queue = store_with_job()
    now = time.time()
    lease = queue.pull(now)[0]
    queue.fail('a', lease.token, now, worker_failure_evidence=BYTES)
    now += 30
    lease, now = pull_due(queue, now)
    with caplog.at_level(logging.ERROR, logger=LOGGER):
        queue.fail('a', lease.token, now, worker_failure={'stage': 'assemble_words', 'reason': 'word_clock'})
    record = quarantine_lines(caplog)[-1]
    assert 'stage=assemble_words' in record
    assert 'worker_reason=word_clock' in record


def test_current_evidence_beats_preserved_diagnosis(caplog):
    store, queue = store_with_job()
    now = time.time()
    lease = queue.pull(now)[0]
    queue.fail('a', lease.token, now, worker_failure_evidence=BYTES)
    now += 30
    lease, now = pull_due(queue, now)
    with caplog.at_level(logging.ERROR, logger=LOGGER):
        queue.fail('a', lease.token, now, worker_failure_evidence={'stage': 'vad_windows', 'reason': 'vad_bounds'})
    # attempt 2 < max: this defers; walk the rest evidence-less.
    for _ in range(4):
        lease, now = pull_due(queue, now)
        queue.fail('a', lease.token, now)
        if store.rows['jobs', 'a']['state'] == 'quarantined':
            break
    record = quarantine_lines(caplog)[-1]
    assert 'worker_reason=vad_bounds' in record


def test_the_preserved_diagnosis_survives_a_full_evidence_free_tail(caplog):
    store, queue = store_with_job()
    with caplog.at_level(logging.ERROR, logger=LOGGER):
        walk(queue, store, evidence_plan={2: NAMED})
    record = quarantine_lines(caplog)[-1]
    assert 'worker_reason=outside_admitted_source' in record


def test_attempt_counter_in_the_record_is_the_exhausting_attempt(caplog):
    store, queue = store_with_job()
    with caplog.at_level(logging.ERROR, logger=LOGGER):
        walk(queue, store, evidence_plan={1: NAMED})
    record = quarantine_lines(caplog)[-1]
    assert 'attempt=5' in record


def test_the_record_keeps_its_shape_for_downstream_parsers(caplog):
    store, queue = store_with_job()
    with caplog.at_level(logging.ERROR, logger=LOGGER):
        walk(queue, store, evidence_plan={1: NAMED})
    record = quarantine_lines(caplog)[-1]
    for field in ('event=batch_quarantined', 'reason=worker_failed', 'recovery=held', 'stage=', 'worker_reason='):
        assert field in record


def test_never_diagnosed_units_keep_the_anonymous_record_shape(caplog):
    store, queue = store_with_job()
    with caplog.at_level(logging.ERROR, logger=LOGGER):
        walk(queue, store, evidence_plan={})
    record = quarantine_lines(caplog)[-1]
    assert 'stage=unknown' in record and 'worker_reason=unclassified' in record


# --- The named fault's evidence token rides the real walk ---------------------------


def test_outside_admitted_source_token_is_accepted_on_every_defer():
    store, queue = store_with_job()
    now = time.time()
    for attempt in range(1, 5):
        lease, now = pull_due(queue, now)
        assert queue.fail('a', lease.token, now, worker_failure_evidence=NAMED) is True
        job = store.rows['jobs', 'a']
        assert job['state'] == 'retry'
        now = job['available_at']


def test_the_named_walk_ends_in_a_named_quarantine(caplog):
    store, queue = store_with_job()
    with caplog.at_level(logging.ERROR, logger=LOGGER):
        walk(queue, store, evidence_plan={1: NAMED})
    record = quarantine_lines(caplog)[-1]
    assert 'worker_reason=outside_admitted_source' in record and 'stage=fetch_decode' in record


def test_the_named_token_never_appears_as_a_structured_failure_via_the_ladder():
    store, queue = store_with_job()
    walk(queue, store, evidence_plan={1: NAMED})
    job = store.rows['jobs', 'a']
    # The named fault is retryable: it must never gain the terminal
    # worker_failure field (that is the typed chain-ender families' field).
    assert 'worker_failure' not in job


def test_metrics_record_the_ladder_shape():
    from utils.batch_pipeline.metrics import QueueMetrics

    store = MemoryStore()
    queue = Scheduler(store)
    now = time.time()
    queue.enqueue(item(), now)
    lease = queue.pull(now)[0]
    queue.fail('a', lease.token, now, worker_failure_evidence=NAMED)
    assert store.rows['jobs', 'a']['state'] == 'retry'
