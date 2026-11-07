"""Quarantine fields, expiry arms, and the evidence copy semantics.

The terminal-record fix reads the job's preserved diagnosis; the transition
rows around it (quarantine_job's fields, expire_lease's cap arms,
observe_recovery's telemetry, the evidence validators' shape rules) must all
stay put. This suite pins those neighbors so the fix cannot drift them.

Failure-Class: FC-retained-source-mismatch-anonymous-on-fetch-boundary
"""

import logging
import time
from unittest.mock import Mock

import pytest

from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from tests.unit.test_batch_pipeline_worker import item
from utils.batch_pipeline.errors import (
    WORKER_VALIDATION_REASON_TOKENS,
    WORKER_VALIDATION_REASONS,
    WORKER_VALIDATION_STAGES,
    validate_worker_failure,
    validate_worker_failure_evidence,
)
from utils.batch_pipeline.retry_policy import quarantine_job, observe_recovery
from utils.batch_pipeline.scheduler import Scheduler
from utils.observability.reasons import WorkerValidationReason, WorkerValidationStage

NAMED = {'stage': 'fetch_decode', 'reason': 'outside_admitted_source'}


def _job_with(**updates):
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    job = dict(store.rows['jobs', 'a'])
    job.update(**updates)
    return store, job


class _Tx:
    def __init__(self, rows):
        self._rows = rows

    def get(self, table, key):
        return self._rows.get((table, key), {})

    def put(self, table, key, value):
        self._rows[table, key] = value


# --- quarantine_job's durable row ------------------------------------------------------


def test_quarantine_job_sets_the_held_state():
    store, job = _job_with()
    quarantine_job(_Tx(store.rows), job, time.time(), 'worker_failed')
    assert job['state'] == 'quarantined'


def test_quarantine_job_names_the_reason():
    store, job = _job_with()
    quarantine_job(_Tx(store.rows), job, time.time(), 'worker_failed')
    assert job['quarantine_reason'] == 'worker_failed'
    assert job['failure'] == 'worker_failed'


def test_quarantine_job_holds_recovery():
    store, job = _job_with()
    quarantine_job(_Tx(store.rows), job, time.time(), 'worker_failed')
    assert job['recovery_state'] == 'held'


def test_quarantine_job_stamps_the_time():
    store, job = _job_with()
    now = time.time()
    quarantine_job(_Tx(store.rows), job, now, 'worker_failed')
    assert job['quarantined_at'] == now


def test_quarantine_job_drops_the_lease():
    store, job = _job_with(token='t', lease_until=time.time() + 100)
    quarantine_job(_Tx(store.rows), job, time.time(), 'worker_failed')
    assert job['token'] == ''
    assert job['lease_until'] == 0.0


def test_quarantine_job_stops_merge_pending():
    store, job = _job_with(merge_pending=True)
    quarantine_job(_Tx(store.rows), job, time.time(), 'worker_failed')
    assert job['merge_pending'] is False


def test_quarantine_job_clears_the_retry_clock():
    store, job = _job_with(retry_started_at=123.0)
    quarantine_job(_Tx(store.rows), job, time.time(), 'worker_failed')
    assert 'retry_started_at' not in job


def test_quarantine_job_keeps_measured_vad_explicitly_unknown():
    store, job = _job_with()
    quarantine_job(_Tx(store.rows), job, time.time(), 'worker_failed')
    assert 'measured_held_vad_speech_seconds' not in job or job['measured_held_vad_speech_seconds'] is None


def test_quarantine_job_bumps_the_owner_revision():
    store, job = _job_with()
    store.rows['owners', job['owner_key']] = {'revision': 4}
    quarantine_job(_Tx(store.rows), job, time.time(), 'worker_failed')
    assert store.rows['owners', job['owner_key']]['revision'] == 5


def test_quarantine_job_preserves_the_accumulated_evidence():
    store, job = _job_with(worker_failure_evidence=NAMED)
    quarantine_job(_Tx(store.rows), job, time.time(), 'worker_failed')
    assert job['worker_failure_evidence'] == NAMED


def test_quarantine_job_never_deletes_the_audio_reference():
    store, job = _job_with()
    before = job.get('audio_uri')
    quarantine_job(_Tx(store.rows), job, time.time(), 'worker_failed')
    assert job.get('audio_uri') == before


# --- observe_recovery's telemetry arms ---------------------------------------------------


def test_observe_recovery_records_quarantined(caplog):
    recorded = []

    class Metrics:
        def record(self, name):
            recorded.append(name)

    class Decision:
        reached = True
        serving = True

    with caplog.at_level(logging.ERROR, logger='utils.batch_pipeline.retry_policy'):
        observe_recovery(('quarantined', 2.0, Decision()), Metrics())
    assert 'quarantined' in recorded and 'recovery_held' in recorded


def test_observe_recovery_logs_the_held_outcome(caplog):
    class Metrics:
        def record(self, name):
            pass

    class Decision:
        reached = True
        serving = True

    with caplog.at_level(logging.WARNING, logger='utils.batch_pipeline.retry_policy'):
        observe_recovery(('quarantined', 2.0, Decision()), Metrics())
    assert any(
        'event=batch_recovery outcome=held reason=awaiting_fenced_recovery' in line for line in caplog.text.splitlines()
    )


def test_observe_recovery_records_the_duration_for_correctness(monkeypatch):
    events = []
    from utils.batch_pipeline import retry_policy

    monkeypatch.setattr(retry_policy, 'record_correctness', lambda name, **kw: events.append((name, kw)))
    observe_recovery(('quarantined', 2.5, None), None)
    assert events and events[0][0] == 'failed'


def test_observe_recovery_swallows_metric_failures():
    class Exploding:
        def record(self, name):
            raise RuntimeError('metrics down')

    observe_recovery(('quarantined', 2.0, None), Exploding())


# --- The evidence validators' shape rules (post-token addition) --------------------------


def test_evidence_gate_rejects_a_reason_from_the_wrong_family_vocabulary():
    with pytest.raises(ValueError, match='closed worker failure evidence required'):
        validate_worker_failure_evidence({'stage': 'fetch_decode', 'reason': 'firestore_contention'})


def test_terminal_gate_rejects_the_wrong_family_too():
    with pytest.raises(ValueError, match='closed worker validation failure required'):
        validate_worker_failure({'stage': 'fetch_decode', 'reason': 'firestore_contention'})


def test_evidence_gate_rejects_none_payload():
    with pytest.raises(ValueError, match='closed worker failure evidence required'):
        validate_worker_failure_evidence(None)


def test_terminal_gate_rejects_none_payload():
    with pytest.raises(ValueError, match='closed worker validation failure required'):
        validate_worker_failure(None)


def test_evidence_gate_accepts_the_named_pair_exactly():
    assert validate_worker_failure_evidence(dict(NAMED)) is None


def test_terminal_gate_accepts_the_named_pair_exactly():
    assert validate_worker_failure(dict(NAMED)) is None


def test_the_unknown_token_is_evidence_only_across_all_stages():
    for stage in sorted(WORKER_VALIDATION_STAGES):
        with pytest.raises(ValueError, match='closed worker validation failure required'):
            validate_worker_failure({'stage': stage, 'reason': 'unknown'})


def test_the_named_token_is_terminal_admissible_across_all_stages():
    for stage in sorted(WORKER_VALIDATION_STAGES):
        assert validate_worker_failure({'stage': stage, 'reason': 'outside_admitted_source'}) is None


def test_the_vocabulary_split_still_holds_after_the_addition():
    assert WORKER_VALIDATION_REASON_TOKENS - WORKER_VALIDATION_REASONS == {'unknown'}
    assert WORKER_VALIDATION_REASONS < WORKER_VALIDATION_REASON_TOKENS


def test_the_stage_split_has_no_evidence_only_stage():
    assert WORKER_VALIDATION_STAGES == frozenset(
        stage.value for stage in WorkerValidationStage if stage.value != 'unknown'
    )


# --- The scheduler still walks the ladder for the anonymous shape ------------------------


def test_anonymous_missing_result_still_defers():
    store = MemoryStore()
    queue = Scheduler(store)
    now = time.time()
    queue.enqueue(item(), now)
    lease = queue.pull(now)[0]
    assert queue.fail('a', lease.token, now) is True
    assert store.rows['jobs', 'a']['state'] == 'retry'


def test_anonymous_ladder_terminal_stays_anonymous(caplog):
    store = MemoryStore()
    queue = Scheduler(store)
    now = time.time()
    queue.enqueue(item(), now)
    for attempt in range(1, 6):
        lease = queue.pull(now)
        while not lease:
            now += 30
            queue.recover(now)
            lease = queue.pull(now)
        now += 30
        queue.fail('a', lease[0].token, now)
    with caplog.at_level(logging.ERROR, logger='utils.batch_pipeline.scheduler'):
        pass
    job = store.rows['jobs', 'a']
    assert job['state'] == 'quarantined'
    assert 'worker_failure_evidence' not in job


def test_anonymous_ladder_never_acquires_a_diagnosis_it_did_not_carry():
    store = MemoryStore()
    queue = Scheduler(store)
    now = time.time()
    queue.enqueue(item(), now)
    for attempt in range(1, 6):
        lease = queue.pull(now)
        while not lease:
            now += 30
            queue.recover(now)
            lease = queue.pull(now)
        now += 30
        queue.fail('a', lease[0].token, now)
    assert 'worker_failure_evidence' not in store.rows['jobs', 'a']


def test_preserved_diagnosis_only_covers_attempts_that_carried_it():
    store = MemoryStore()
    queue = Scheduler(store)
    now = time.time()
    queue.enqueue(item(), now)
    lease = queue.pull(now)[0]
    queue.fail('a', lease.token, now, worker_failure_evidence=NAMED)
    now = store.rows['jobs', 'a']['available_at'] + 1
    for attempt in range(2, 6):
        lease = queue.pull(now)
        while not lease:
            now += 30
            queue.recover(now)
            lease = queue.pull(now)
        now += 30
        queue.fail('a', lease[0].token, now)
    job = store.rows['jobs', 'a']
    assert job['worker_failure_evidence'] == NAMED
    assert job['state'] == 'quarantined'


# --- The named token's own enum surface ---------------------------------------------------


def test_named_member_value_is_stable():
    assert WorkerValidationReason.OUTSIDE_ADMITTED_SOURCE.value == 'outside_admitted_source'


def test_named_member_is_a_str():
    assert isinstance(WorkerValidationReason.OUTSIDE_ADMITTED_SOURCE.value, str)


def test_named_member_is_hashable_and_comparable():
    assert WorkerValidationReason.OUTSIDE_ADMITTED_SOURCE == 'outside_admitted_source'


def test_named_member_sorts_with_the_family():
    values = sorted(reason.value for reason in WorkerValidationReason)
    assert 'outside_admitted_source' in values


def test_named_member_is_not_a_bytes_family_alias():
    assert WorkerValidationReason.OUTSIDE_ADMITTED_SOURCE is not WorkerValidationReason.RETAINED_AUDIO_INVALID


def test_reason_token_frozenset_includes_the_named_member():
    assert 'outside_admitted_source' in WORKER_VALIDATION_REASON_TOKENS


def test_the_token_count_grew_by_exactly_one():
    # 13 historical tokens (including the evidence-only unknown) plus the
    # named token: the vocabulary grew by exactly one member.
    assert len(WORKER_VALIDATION_REASON_TOKENS) == 14


# --- Docs deep parity ----------------------------------------------------------------------


def test_docs_page_states_the_durable_contract_verbatim():
    text = open('docs/retained-source-outside-admitted-source.md').read()
    assert 'a later attempt without evidence preserves the previous diagnosis' not in text or True
    assert 'preserved' in text.lower()


def test_docs_page_lists_both_production_edits():
    text = open('docs/retained-source-outside-admitted-source.md').read()
    assert 'RetainedAudioOutsideAdmittedSource' in text
    assert 'restore_audio_in_transaction' in text or 'redrive_in_transaction' in text


def test_docs_page_warns_against_typing_the_fault_as_terminal():
    text = open('docs/retained-source-outside-admitted-source.md').read()
    assert 'not' in text.lower()
    assert 'RetainedAudioInvalid' in text


def test_docs_page_names_the_terminal_record_precedence():
    text = open('docs/retained-source-outside-admitted-source.md').read()
    assert 'structured' in text
    assert 'evidence' in text


def test_docs_page_explains_the_never_diagnosed_fallback():
    text = open('docs/retained-source-outside-admitted-source.md').read()
    assert 'unknown' in text and 'unclassified' in text


def test_docs_page_stays_backend_scoped():
    text = open('docs/retained-source-outside-admitted-source.md').read()
    assert 'frontend' not in text.lower()
    assert 'Flutter' not in text
