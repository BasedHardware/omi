"""The retry ladder keeps its diagnosis: evidence transitions in the scheduler.

scheduler.fail() accepts the worker's evidence-only diagnosis
(``worker_failure_evidence``) without ever letting it decide a transition: an
ordinary failure still defers through the bounded ladder and quarantines at
the attempt ceiling, but every attempt re-records the latest evidence on the
job and the terminal quarantine log names the real stage and reason instead
of ``stage=unknown worker_reason=unclassified``. A structured
``worker_failure`` still wins the log, an evidence-less ladder still logs the
historical shape, completion clears the evidence, and nothing about the
quarantine decision, metrics, or operator-recovery custody changes.

Failure-Class: FC-batch-transient-worker-failure-quarantines-blind-without-stage-or-reason-evidence
"""

import json
import logging
import time
from unittest.mock import Mock

import pytest

from utils.batch_pipeline.contracts import WorkResult
from utils.batch_pipeline.scheduler import LEASE_SECONDS, Scheduler
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from tests.unit.test_batch_pipeline_worker import item

EVIDENCE = {'stage': 'fetch_decode', 'reason': 'unknown'}
CLOSED_EVIDENCE = {'stage': 'word_clocks', 'reason': 'word_clock'}


def _queue(store=None):
    return Scheduler(store if store is not None else MemoryStore())


def _ladder(store, segment='a', *, attempts, evidence=EVIDENCE, caplog=None):
    """Drive `attempts` worker failures; returns (queue, store, last_job)."""
    queue = _queue(store)
    queue.enqueue(item(segment), 0)
    job = None
    for attempt in range(1, attempts + 1):
        now = attempt * 1000
        queue.recover(now)
        lease = queue.pull(now)[0]
        kwargs = {}
        if evidence is not None:
            kwargs['worker_failure_evidence'] = evidence
        queue.fail(segment, lease.token, now + 1, **kwargs)
        job = store.rows['jobs', segment]
        if attempt < attempts and job['state'] != 'retry':
            raise AssertionError(f'expected retry at attempt {attempt}, got {job["state"]}')
    return queue, store, job


# --- Ladder shape with evidence ---------------------------------------------------


def test_first_evidenced_failure_defers_instead_of_quarantining():
    queue, store, job = _ladder(MemoryStore(), attempts=1)
    assert job['state'] == 'retry' and job['attempt'] == 1


def test_evidence_is_recorded_on_the_first_failure():
    _, store, job = _ladder(MemoryStore(), attempts=1)
    assert job['worker_failure_evidence'] == EVIDENCE


def test_every_ladder_attempt_defers_until_the_ceiling():
    _, store, job = _ladder(MemoryStore(), attempts=4)
    assert job['state'] == 'retry' and job['attempt'] == 4


def test_ladder_quarantines_at_the_default_ceiling():
    _, store, job = _ladder(MemoryStore(), attempts=5)
    assert job['state'] == 'quarantined' and job['attempt'] == 5


def test_evidence_survives_every_ladder_attempt():
    _, store, job = _ladder(MemoryStore(), attempts=5)
    assert job['worker_failure_evidence'] == EVIDENCE


def test_evidence_does_not_shorten_or_lengthen_the_ladder():
    store = MemoryStore()
    _ladder(store, attempts=5)
    plain = MemoryStore()
    _ladder(plain, attempts=5, evidence=None)
    evidenced_job = store.rows['jobs', 'a']
    plain_job = plain.rows['jobs', 'a']
    assert evidenced_job['state'] == plain_job['state'] == 'quarantined'
    assert evidenced_job['attempt'] == plain_job['attempt'] == 5
    assert evidenced_job['quarantined_at'] == plain_job['quarantined_at']


def test_evidence_backoff_matches_the_plain_ladder_backoff():
    store, plain = MemoryStore(), MemoryStore()
    _ladder(store, attempts=2)
    _ladder(plain, attempts=2, evidence=None)
    assert store.rows['jobs', 'a']['available_at'] == plain.rows['jobs', 'a']['available_at']


# --- Evidence persistence semantics ------------------------------------------------


def test_evidence_persists_across_recover_and_pull():
    store = MemoryStore()
    queue, _, _ = _ladder(store, attempts=1)
    queue.recover(store.rows['jobs', 'a']['available_at'])
    queue.pull(store.rows['jobs', 'a']['available_at'])
    assert store.rows['jobs', 'a']['worker_failure_evidence'] == EVIDENCE


def test_a_later_evidence_less_attempt_preserves_the_previous_diagnosis():
    store = MemoryStore()
    queue = _queue(store)
    queue.enqueue(item('a'), 0)
    now = 1000
    queue.recover(now)
    lease = queue.pull(now)[0]
    assert queue.fail('a', lease.token, now + 1, worker_failure_evidence=EVIDENCE)
    queue.recover(now + 2000)
    lease2 = queue.pull(now + 2000)[0]
    assert queue.fail('a', lease2.token, now + 2001)
    assert store.rows['jobs', 'a']['worker_failure_evidence'] == EVIDENCE


def test_a_later_evidenced_attempt_replaces_the_previous_diagnosis():
    store = MemoryStore()
    queue = _queue(store)
    queue.enqueue(item('a'), 0)
    now = 1000
    queue.recover(now)
    lease = queue.pull(now)[0]
    assert queue.fail('a', lease.token, now + 1, worker_failure_evidence=EVIDENCE)
    queue.recover(now + 2000)
    lease2 = queue.pull(now + 2000)[0]
    assert queue.fail('a', lease2.token, now + 2001, worker_failure_evidence=CLOSED_EVIDENCE)
    assert store.rows['jobs', 'a']['worker_failure_evidence'] == CLOSED_EVIDENCE


def test_mixed_evidence_sequence_keeps_the_last_diagnosis():
    store = MemoryStore()
    queue = _queue(store)
    queue.enqueue(item('a'), 0)
    now = 1000
    queue.recover(now)
    lease = queue.pull(now)[0]
    queue.fail('a', lease.token, now + 1, worker_failure_evidence=EVIDENCE)
    queue.recover(now + 2000)
    lease2 = queue.pull(now + 2000)[0]
    queue.fail('a', lease2.token, now + 2001)
    queue.recover(now + 4000)
    lease3 = queue.pull(now + 4000)[0]
    queue.fail('a', lease3.token, now + 4001, worker_failure_evidence=CLOSED_EVIDENCE)
    assert store.rows['jobs', 'a']['worker_failure_evidence'] == CLOSED_EVIDENCE


def test_typed_worker_failure_and_evidence_can_coexist_on_the_job():
    store = MemoryStore()
    queue = _queue(store)
    queue.enqueue(item('a'), 0)
    now = 1000
    queue.recover(now)
    lease = queue.pull(now)[0]
    typed = {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}
    queue.fail('a', lease.token, now + 1, worker_failure=typed, worker_failure_evidence=EVIDENCE)
    job = store.rows['jobs', 'a']
    assert job['worker_failure'] == typed
    assert job['worker_failure_evidence'] == EVIDENCE
    assert job['state'] == 'quarantined'  # typed failures quarantine immediately, as before


def test_completion_clears_the_evidence():
    store = MemoryStore()
    queue, _, _ = _ladder(store, attempts=1)
    due = store.rows['jobs', 'a']['available_at']
    queue.recover(due)
    lease = queue.pull(due)[0]
    assert queue.complete(WorkResult('a', 'gs://results/a'), lease.token, due + 1)
    assert 'worker_failure_evidence' not in store.rows['jobs', 'a']


def test_completion_without_prior_evidence_still_succeeds():
    store = MemoryStore()
    queue = _queue(store)
    queue.enqueue(item('a'), 0)
    lease = queue.pull(0)[0]
    assert queue.complete(WorkResult('a', 'gs://results/a'), lease.token, 1)
    assert store.rows['jobs', 'a']['state'] == 'result_ready'


def test_quarantine_keeps_the_evidence_for_operator_recovery():
    _, store, job = _ladder(MemoryStore(), attempts=5)
    assert job['worker_failure_evidence'] == EVIDENCE
    assert job['state'] == 'quarantined'


def test_quarantine_reason_stays_worker_failed():
    _, store, job = _ladder(MemoryStore(), attempts=5, evidence=CLOSED_EVIDENCE)
    assert job['quarantine_reason'] == 'worker_failed'
    assert job['failure'] == 'worker_failed'


def test_evidence_quarantine_retains_the_audio_for_fenced_recovery():
    _, store, job = _ladder(MemoryStore(), attempts=5)
    assert job['audio_uri'] == 'encrypted://a'
    assert job['recovery_state'] == 'held'


def test_measured_vad_is_still_recorded_alongside_evidence():
    store = MemoryStore()
    queue = _queue(store)
    queue.enqueue(item('a'), 0)
    now = 1000
    queue.recover(now)
    lease = queue.pull(now)[0]
    queue.fail('a', lease.token, now + 1, worker_failure_evidence=EVIDENCE, measured_held_vad_speech_seconds=1.5)
    job = store.rows['jobs', 'a']
    assert job['worker_failure_evidence'] == EVIDENCE
    assert job['measured_held_vad_speech_seconds'] == 1.5


def test_vad_receipt_is_still_recorded_alongside_evidence():
    from utils.batch_pipeline.contracts import vad_receipt

    store = MemoryStore()
    queue = _queue(store)
    queue.enqueue(item('a'), 0)
    now = 1000
    queue.recover(now)
    lease = queue.pull(now)[0]
    receipt = vad_receipt('encrypted://a', 32000, 1.5)
    queue.fail(
        'a',
        lease.token,
        now + 1,
        worker_failure_evidence=EVIDENCE,
        measured_held_vad_speech_seconds=1.5,
        worker_vad_receipt=receipt,
    )
    assert store.rows['jobs', 'a']['worker_vad_receipt'] == receipt


def test_recorded_evidence_is_a_copy_of_the_caller_dict():
    store = MemoryStore()
    queue = _queue(store)
    queue.enqueue(item('a'), 0)
    now = 1000
    queue.recover(now)
    lease = queue.pull(now)[0]
    evidence = dict(EVIDENCE)
    queue.fail('a', lease.token, now + 1, worker_failure_evidence=evidence)
    evidence['stage'] = 'mutated'
    assert store.rows['jobs', 'a']['worker_failure_evidence'] == EVIDENCE


def test_evidence_lands_under_its_exact_document_key():
    _, store, job = _ladder(MemoryStore(), attempts=1)
    assert 'worker_failure_evidence' in job


def test_evidence_only_path_writes_no_worker_failure_key():
    _, store, job = _ladder(MemoryStore(), attempts=5)
    assert 'worker_failure' not in job


def test_evidence_only_quarantine_writes_no_empty_retry_evidence():
    _, store, job = _ladder(MemoryStore(), attempts=5)
    assert 'worker_empty_evidence' not in job


# --- Terminal quarantine log precedence ---------------------------------------------


def _quarantine_records(caplog):
    return [r for r in caplog.records if 'event=batch_quarantined' in r.getMessage()]


def test_terminal_log_names_the_evidence_stage_and_reason(caplog):
    store = MemoryStore()
    with caplog.at_level(logging.ERROR, logger='utils.batch_pipeline.scheduler'):
        _ladder(store, attempts=5)
    lines = [_quarantine_records(caplog)[-1].getMessage() for _ in (0,)]
    assert lines[-1] == (
        'event=batch_quarantined reason=worker_failed attempt=5 recovery=held '
        'stage=fetch_decode worker_reason=unknown'
    )


def test_terminal_log_names_a_closed_evidence_reason(caplog):
    store = MemoryStore()
    with caplog.at_level(logging.ERROR, logger='utils.batch_pipeline.scheduler'):
        _ladder(store, attempts=5, evidence=CLOSED_EVIDENCE)
    assert _quarantine_records(caplog)[-1].getMessage().endswith('stage=word_clocks worker_reason=word_clock')


def test_terminal_log_prefers_the_typed_worker_failure_over_evidence(caplog):
    store = MemoryStore()
    queue = _queue(store)
    queue.enqueue(item('a'), 0)
    now = 1000
    queue.recover(now)
    lease = queue.pull(now)[0]
    with caplog.at_level(logging.ERROR, logger='utils.batch_pipeline.scheduler'):
        queue.fail(
            'a',
            lease.token,
            now + 1,
            worker_failure={'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'},
            worker_failure_evidence=CLOSED_EVIDENCE,
        )
    message = _quarantine_records(caplog)[-1].getMessage()
    assert 'stage=fetch_decode worker_reason=staged_audio_invalid' in message


def test_terminal_log_keeps_the_historical_shape_without_any_diagnosis(caplog):
    store = MemoryStore()
    with caplog.at_level(logging.ERROR, logger='utils.batch_pipeline.scheduler'):
        _ladder(store, attempts=5, evidence=None)
    assert _quarantine_records(caplog)[-1].getMessage() == (
        'event=batch_quarantined reason=worker_failed attempt=5 recovery=held '
        'stage=unknown worker_reason=unclassified'
    )


def test_terminal_log_attempt_value_matches_the_ceiling(caplog):
    store = MemoryStore()
    with caplog.at_level(logging.ERROR, logger='utils.batch_pipeline.scheduler'):
        _ladder(store, attempts=5)
    assert 'attempt=5' in _quarantine_records(caplog)[-1].getMessage()


def test_terminal_log_emits_exactly_one_quarantined_line(caplog):
    store = MemoryStore()
    with caplog.at_level(logging.ERROR, logger='utils.batch_pipeline.scheduler'):
        _ladder(store, attempts=5)
    assert len(_quarantine_records(caplog)) == 1


def test_recovery_held_line_accompanies_the_evidenced_quarantine(caplog):
    store = MemoryStore()
    with caplog.at_level(logging.WARNING, logger='utils.batch_pipeline.scheduler'):
        _ladder(store, attempts=5)
    held = [r for r in caplog.records if 'event=batch_recovery outcome=held' in r.getMessage()]
    assert len(held) == 1
    assert 'reason=awaiting_fenced_recovery' in held[0].getMessage()


def test_deferred_retry_log_keeps_its_parent_shape(caplog):
    store = MemoryStore()
    with caplog.at_level(logging.INFO, logger='utils.batch_pipeline.scheduler'):
        _ladder(store, attempts=1)
    retries = [r for r in caplog.records if 'event=batch_retry' in r.getMessage()]
    assert len(retries) == 1
    assert retries[0].getMessage() == 'event=batch_retry reason=worker_failed outcome=deferred attempt=1'


def test_custom_ceiling_quarantines_with_evidence_log(monkeypatch, caplog):
    store = MemoryStore()
    queue = _queue(store)
    queue.enqueue(item('a'), 0)
    lease = queue.pull(0)[0]
    # policy_parts exist only after the first pull resolved them.
    store.rows['jobs', 'a']['policy_parts']['scheduler']['max_attempts'] = 2
    with caplog.at_level(logging.ERROR, logger='utils.batch_pipeline.scheduler'):
        queue.fail('a', lease.token, 1, worker_failure_evidence=EVIDENCE)
    assert store.rows['jobs', 'a']['state'] == 'retry'
    due = store.rows['jobs', 'a']['available_at']
    queue.recover(due)
    lease2 = queue.pull(due)[0]
    with caplog.at_level(logging.ERROR, logger='utils.batch_pipeline.scheduler'):
        queue.fail('a', lease2.token, due + 1, worker_failure_evidence=EVIDENCE)
    assert store.rows['jobs', 'a']['state'] == 'quarantined'
    assert 'stage=fetch_decode worker_reason=unknown' in _quarantine_records(caplog)[-1].getMessage()


# --- Guards: evidence never decides or corrupts a transition ------------------------


def test_malformed_evidence_raises_and_leaves_the_job_leased():
    store = MemoryStore()
    queue = _queue(store)
    queue.enqueue(item('a'), 0)
    lease = queue.pull(0)[0]
    with pytest.raises(ValueError, match='closed worker failure evidence required'):
        queue.fail('a', lease.token, 1, worker_failure_evidence='fetch_decode/unknown')
    job = store.rows['jobs', 'a']
    assert job['state'] == 'leased' and 'worker_failure_evidence' not in job


def test_open_stage_evidence_raises_and_leaves_the_job_leased():
    store = MemoryStore()
    queue = _queue(store)
    queue.enqueue(item('a'), 0)
    lease = queue.pull(0)[0]
    with pytest.raises(ValueError, match='closed worker failure evidence required'):
        queue.fail('a', lease.token, 1, worker_failure_evidence={'stage': 'persist', 'reason': 'unknown'})
    assert store.rows['jobs', 'a']['state'] == 'leased'


def test_open_reason_evidence_raises_and_leaves_the_job_leased():
    store = MemoryStore()
    queue = _queue(store)
    queue.enqueue(item('a'), 0)
    lease = queue.pull(0)[0]
    with pytest.raises(ValueError, match='closed worker failure evidence required'):
        queue.fail('a', lease.token, 1, worker_failure_evidence={'stage': 'fetch_decode', 'reason': 'unclassified'})
    assert store.rows['jobs', 'a']['state'] == 'leased'


def test_extra_key_evidence_raises_and_leaves_the_job_leased():
    store = MemoryStore()
    queue = _queue(store)
    queue.enqueue(item('a'), 0)
    lease = queue.pull(0)[0]
    with pytest.raises(ValueError, match='closed worker failure evidence required'):
        queue.fail('a', lease.token, 1, worker_failure_evidence={**EVIDENCE, 'note': 'x'})
    assert store.rows['jobs', 'a']['state'] == 'leased'


def test_validation_failure_does_not_consume_an_attempt():
    store = MemoryStore()
    queue = _queue(store)
    queue.enqueue(item('a'), 0)
    lease = queue.pull(0)[0]
    with pytest.raises(ValueError):
        queue.fail('a', lease.token, 1, worker_failure_evidence={**EVIDENCE, 'note': 'x'})
    job = store.rows['jobs', 'a']
    assert job['attempt'] == 1 and job['state'] == 'leased'
    assert 'worker_failure_evidence' not in job
    # The lease stays usable: the same token still owns the job afterwards.
    assert queue.heartbeat('a', lease.token, 2) is True


def test_evidence_for_a_missing_segment_is_rejected_at_the_gate():
    with pytest.raises(ValueError, match='closed worker failure evidence required'):
        _queue().fail('missing', 'token', 0, worker_failure_evidence={'stage': 'nope', 'reason': 'unknown'})


def test_revoked_lease_rejects_the_evidenced_failure():
    store = MemoryStore()
    queue = _queue(store)
    queue.enqueue(item('a'), 0)
    queue.pull(0)
    assert queue.fail('a', 'stale-token', LEASE_SECONDS + 2, worker_failure_evidence=EVIDENCE) is False
    job = store.rows['jobs', 'a']
    assert 'worker_failure_evidence' not in job


def test_second_fail_on_the_same_lease_is_refused():
    store = MemoryStore()
    queue, _, _ = _ladder(store, attempts=1)
    due = store.rows['jobs', 'a']['available_at']
    queue.recover(due)
    lease = queue.pull(due)[0]
    assert queue.fail('a', lease.token, due + 1, worker_failure_evidence=EVIDENCE) is True
    assert queue.fail('a', lease.token, due + 1, worker_failure_evidence=EVIDENCE) is False


def test_quarantined_job_refuses_further_evidenced_failures():
    store = MemoryStore()
    queue, _, job = _ladder(store, attempts=5)
    assert queue.fail('a', 'token', 99999, worker_failure_evidence=EVIDENCE) is False
    assert store.rows['jobs', 'a'] is job or store.rows['jobs', 'a']['state'] == 'quarantined'


def test_evidenced_failure_reports_the_transition_once():
    store = MemoryStore()
    queue, _, _ = _ladder(store, attempts=1)
    now = store.rows['jobs', 'a']['available_at']
    queue.recover(now)
    lease = queue.pull(now)[0]
    assert queue.fail('a', lease.token, now + 1, worker_failure_evidence=EVIDENCE) is True


# --- Metrics and serialization parity ------------------------------------------------


def test_evidenced_ladder_records_the_same_metrics_as_the_plain_ladder():
    store, plain = MemoryStore(), MemoryStore()
    metrics, plain_metrics = Mock(), Mock()
    queue = Scheduler(store, metrics=metrics)
    queue.enqueue(item('a'), 0)
    for attempt in range(1, 6):
        now = attempt * 1000
        queue.recover(now)
        lease = queue.pull(now)[0]
        queue.fail('a', lease.token, now + 1, worker_failure_evidence=EVIDENCE)
    plain_queue = Scheduler(plain, metrics=plain_metrics)
    plain_queue.enqueue(item('a'), 0)
    for attempt in range(1, 6):
        now = attempt * 1000
        plain_queue.recover(now)
        lease = plain_queue.pull(now)[0]
        plain_queue.fail('a', lease.token, now + 1)
    assert [c.args for c in metrics.record.call_args_list] == [c.args for c in plain_metrics.record.call_args_list]
    assert ('quarantined',) in [c.args for c in metrics.record.call_args_list]
    assert ('recovery_held',) in [c.args for c in metrics.record.call_args_list]


def test_evidence_is_json_serializable_in_the_job_document():
    _, store, job = _ladder(MemoryStore(), attempts=5)
    restored = json.loads(json.dumps(job))
    assert restored['worker_failure_evidence'] == EVIDENCE


def test_evidence_values_are_plain_strings():
    _, store, job = _ladder(MemoryStore(), attempts=1)
    evidence = job['worker_failure_evidence']
    assert set(evidence) == {'stage', 'reason'}
    assert all(isinstance(value, str) for value in evidence.values())


# --- Evidence stage matrix at the scheduler ------------------------------------------


def _evidenced_queue(store, evidence):
    queue = _queue(store)
    queue.enqueue(item('a'), 0)
    lease = queue.pull(0)[0]
    assert queue.fail('a', lease.token, 1, worker_failure_evidence=evidence)
    return queue, store.rows['jobs', 'a']


def test_every_closed_stage_defers_with_unknown_reason_evidence():
    for stage in ['fetch_decode', 'vad_windows', 'word_clocks', 'assemble_words', 'asr_recovery']:
        store = MemoryStore()
        _, job = _evidenced_queue(store, {'stage': stage, 'reason': 'unknown'})
        assert job['state'] == 'retry'
        assert job['worker_failure_evidence'] == {'stage': stage, 'reason': 'unknown'}


def test_every_closed_stage_quarantines_logging_its_own_stage(caplog):
    for stage in ['fetch_decode', 'vad_windows', 'word_clocks', 'assemble_words', 'asr_recovery']:
        store = MemoryStore()
        with caplog.at_level(logging.ERROR, logger='utils.batch_pipeline.scheduler'):
            queue, _ = _evidenced_queue(store, {'stage': stage, 'reason': 'unknown'})
            for attempt in range(2, 6):
                now = attempt * 1000
                queue.recover(now)
                lease = queue.pull(now)[0]
                queue.fail('a', lease.token, now + 1, worker_failure_evidence={'stage': stage, 'reason': 'unknown'})
        assert store.rows['jobs', 'a']['state'] == 'quarantined'
        assert f'stage={stage} worker_reason=unknown' in _quarantine_records(caplog)[-1].getMessage()
        caplog.clear()


# --- Lease-expiry family with evidence ------------------------------------------------


def _serving_store(monkeypatch):
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'serve')
    return MemoryStore()


def test_lease_expiry_at_the_cap_quarantines_with_evidence_kept(monkeypatch):
    store = _serving_store(monkeypatch)
    queue, _, job = _ladder(store, attempts=5)
    assert job['state'] == 'quarantined'
    assert job['worker_failure_evidence'] == EVIDENCE


def test_lease_expiry_mid_ladder_preserves_the_recorded_evidence(monkeypatch):
    store = _serving_store(monkeypatch)
    queue = _queue(store)
    queue.enqueue(item('a'), 0)
    queue.pull(0)
    store.rows['jobs', 'a']['worker_failure_evidence'] = dict(EVIDENCE)
    queue.recover(LEASE_SECONDS + 1)
    job = store.rows['jobs', 'a']
    assert job['state'] in {'retry', 'ready', 'leased'}
    assert job.get('worker_failure_evidence') == EVIDENCE


def test_lease_expiry_of_an_evidence_less_job_stays_evidence_less(monkeypatch):
    store = _serving_store(monkeypatch)
    queue = _queue(store)
    queue.enqueue(item('a'), 0)
    queue.pull(0)
    queue.recover(LEASE_SECONDS + 1)
    job = store.rows['jobs', 'a']
    assert 'worker_failure_evidence' not in job


def test_lease_expiry_ceiling_decision_is_evidence_blind(monkeypatch):
    # The retry-cap decision reads attempt counts, never evidence: both
    # ladders reach the same terminal at the same attempt.
    store, plain = _serving_store(monkeypatch), MemoryStore()
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'serve')
    _ladder(store, attempts=5)
    plain_store = MemoryStore()
    _ladder(plain_store, attempts=5, evidence=None)
    assert store.rows['jobs', 'a']['attempt'] == plain_store.rows['jobs', 'a']['attempt']
    assert store.rows['jobs', 'a']['state'] == plain_store.rows['jobs', 'a']['state'] == 'quarantined'


# --- Completion and control-surface parity --------------------------------------------


def test_evidenced_defer_records_the_retry_metric_once():
    store = MemoryStore()
    metrics = Mock()
    queue = Scheduler(store, metrics=metrics)
    queue.enqueue(item('a'), 0)
    lease = queue.pull(0)[0]
    queue.fail('a', lease.token, 1, worker_failure_evidence=EVIDENCE)
    assert [c.args for c in metrics.record.call_args_list] == [('leased',), ('retry',)]


def test_evidenced_ceiling_records_quarantined_and_recovery_held_once():
    store = MemoryStore()
    metrics = Mock()
    queue = Scheduler(store, metrics=metrics)
    queue.enqueue(item('a'), 0)
    for attempt in range(1, 6):
        now = attempt * 1000
        queue.recover(now)
        lease = queue.pull(now)[0]
        queue.fail('a', lease.token, now + 1, worker_failure_evidence=EVIDENCE)
    counts = [c.args for c in metrics.record.call_args_list]
    assert counts.count(('quarantined',)) == 1
    assert counts.count(('recovery_held',)) == 1
    assert counts.count(('retry',)) == 4


def test_result_ready_recomplete_is_idempotent_after_evidence_was_cleared():
    store = MemoryStore()
    queue, _, _ = _ladder(store, attempts=1)
    due = store.rows['jobs', 'a']['available_at']
    queue.recover(due)
    lease = queue.pull(due)[0]
    assert queue.complete(WorkResult('a', 'gs://results/a'), lease.token, due + 1)
    assert queue.complete(WorkResult('a', 'gs://results/a'), lease.token, due + 2)
    assert 'worker_failure_evidence' not in store.rows['jobs', 'a']


def test_typed_failure_keeps_its_document_key_and_clears_no_evidence():
    store = MemoryStore()
    queue = _queue(store)
    queue.enqueue(item('a'), 0)
    lease = queue.pull(0)[0]
    queue.fail('a', lease.token, 1, worker_failure={'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'})
    job = store.rows['jobs', 'a']
    assert job['worker_failure'] == {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}
    assert 'worker_failure_evidence' not in job


def test_evidenced_quarantine_then_redrive_refusal_leaves_evidence_intact():
    _, store, job = _ladder(MemoryStore(), attempts=5)
    assert not queue_redrive(store, 'a', 99999)
    assert store.rows['jobs', 'a']['worker_failure_evidence'] == EVIDENCE


def queue_redrive(store, segment, now):
    from utils.batch_pipeline.scheduler import Scheduler

    return Scheduler(store).redrive_dead(segment, now)


def test_evidence_only_ladder_leaves_merge_results_table_untouched():
    _, store, _ = _ladder(MemoryStore(), attempts=4)
    assert not any(table == 'results' for table, _ in store.rows)
