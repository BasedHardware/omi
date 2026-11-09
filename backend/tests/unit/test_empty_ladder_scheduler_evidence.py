# Failure-Class: FC-empty-ladder-gate-drift-misroutes-recovery-units-between-hold-retry-and-terminal-rungs
"""The scheduler half of the empty ladder: evidence, naming, and the ladder boundary.

The pump hands every empty-ladder unit to ``Scheduler.fail`` with
``quarantine=True``, the padded-retry token, and the closed
``worker_failure`` diagnosis. The transaction must write the bounded
``worker_empty_evidence`` the fenced recovery lane reads, name the terminal
record after the strongest diagnosis it holds, and otherwise leave the
bounded retry ladder untouched. These tests drive the real scheduler over
``MemoryStore`` and pin the evidence write conditions, the closed
vocabularies, the terminal/defer log naming, the metrics and correctness
telemetry, and custody semantics.
"""

import logging
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import utils.batch_pipeline.scheduler as scheduler_module
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from tests.unit.test_batch_pipeline_worker import item
from utils.batch_pipeline.scheduler import Scheduler


def leased(metric_record=None):
    store = MemoryStore()
    metrics = SimpleNamespace(record=metric_record) if metric_record is not None else None
    queue = Scheduler(store, metrics=metrics)
    queue.enqueue(item('a'), 0)
    lease = queue.pull(0)[0]
    return store, queue, lease


def terminal(store, queue, lease, **kwargs):
    kwargs.setdefault('quarantine', True)
    kwargs.setdefault('worker_failure', {'stage': 'assemble_words', 'reason': 'empty_asr'})
    return queue.fail('a', lease.token, 10.0, **kwargs)


# --- worker_empty_evidence write conditions ---------------------------------------------------


def test_quarantine_with_the_empty_token_writes_versioned_evidence():
    store, queue, lease = leased()
    assert terminal(store, queue, lease, padded_retry='empty', padded_retry_empty=True) is True
    assert store.rows['jobs', 'a']['worker_empty_evidence'] == {'padded_retry': 'empty', 'version': 1}


def test_quarantine_with_the_skipped_oversize_token_writes_the_evidence():
    store, queue, lease = leased()
    terminal(store, queue, lease, padded_retry='skipped_oversize')
    assert store.rows['jobs', 'a']['worker_empty_evidence'] == {'padded_retry': 'skipped_oversize', 'version': 1}


def test_quarantine_with_the_skipped_long_speech_token_writes_the_evidence():
    store, queue, lease = leased()
    terminal(store, queue, lease, padded_retry='skipped_long_speech')
    assert store.rows['jobs', 'a']['worker_empty_evidence'] == {'padded_retry': 'skipped_long_speech', 'version': 1}


def test_quarantine_without_a_padded_token_writes_no_evidence():
    store, queue, lease = leased()
    terminal(store, queue, lease, padded_retry=None, padded_retry_empty=False)
    assert 'worker_empty_evidence' not in store.rows['jobs', 'a']


def test_none_token_with_empty_flag_normalizes_to_the_empty_token():
    store, queue, lease = leased()
    terminal(store, queue, lease, padded_retry=None, padded_retry_empty=True)
    assert store.rows['jobs', 'a']['worker_empty_evidence'] == {'padded_retry': 'empty', 'version': 1}


def test_empty_token_without_the_empty_flag_normalizes_the_flag():
    store, queue, lease = leased()
    terminal(store, queue, lease, padded_retry='empty', padded_retry_empty=False)
    job = store.rows['jobs', 'a']
    assert job['worker_empty_evidence'] == {'padded_retry': 'empty', 'version': 1}
    assert job['worker_failure'] == {'stage': 'assemble_words', 'reason': 'empty_asr'}


def test_deferred_empty_failure_writes_no_evidence():
    store, queue, lease = leased()
    assert queue.fail('a', lease.token, 10.0, padded_retry='empty', padded_retry_empty=True) is True
    job = store.rows['jobs', 'a']
    assert job['state'] == 'retry'
    assert 'worker_empty_evidence' not in job


# --- closed vocabularies at the entry boundary -------------------------------------------------


def test_unsupported_padded_token_is_refused_before_any_write():
    store, queue, lease = leased()
    with pytest.raises(ValueError, match='invalid padded retry evidence'):
        queue.fail('a', lease.token, 10.0, quarantine=True, padded_retry='identical')
    assert store.rows['jobs', 'a']['state'] == 'leased'


def test_conflicting_empty_flag_with_a_non_empty_token_is_refused():
    store, queue, lease = leased()
    with pytest.raises(ValueError, match='invalid padded retry evidence'):
        queue.fail('a', lease.token, 10.0, quarantine=True, padded_retry='skipped_oversize', padded_retry_empty=True)


def test_terminal_worker_failure_accepts_closed_codes_only():
    store, queue, lease = leased()
    with pytest.raises(ValueError, match='closed worker validation failure required'):
        queue.fail(
            'a', lease.token, 10.0, quarantine=True, worker_failure={'stage': 'assemble_words', 'reason': 'mystery'}
        )


def test_terminal_worker_failure_stage_is_closed():
    store, queue, lease = leased()
    with pytest.raises(ValueError, match='closed worker validation failure required'):
        queue.fail(
            'a', lease.token, 10.0, quarantine=True, worker_failure={'stage': 'elsewhere', 'reason': 'empty_asr'}
        )


def test_evidence_stage_is_closed_and_reasons_allow_unknown():
    store, queue, lease = leased()
    with pytest.raises(ValueError, match='closed worker failure evidence required'):
        queue.fail(
            'a',
            lease.token,
            10.0,
            worker_failure_evidence={'stage': 'elsewhere', 'reason': 'empty_asr'},
        )
    assert (
        queue.fail(
            'a',
            lease.token,
            10.0,
            worker_failure_evidence={'stage': 'assemble_words', 'reason': 'unknown'},
        )
        is True
    )


# --- terminal record naming ---------------------------------------------------------------------


def test_quarantine_log_names_the_worker_failure_diagnosis(caplog):
    store, queue, lease = leased()
    with caplog.at_level(logging.INFO):
        terminal(store, queue, lease, padded_retry='empty', padded_retry_empty=True)
    held = [r.getMessage() for r in caplog.records if 'event=batch_empty_ladder' in r.getMessage()]
    assert len(held) == 1
    assert 'attempt=1 recovery=held' in held[0]
    assert 'stage=assemble_words worker_reason=empty_asr' in held[0]


def test_no_owned_diagnosis_names_itself_in_the_terminal_record(caplog):
    store, queue, lease = leased()
    with caplog.at_level(logging.INFO):
        terminal(store, queue, lease, worker_failure={'stage': 'assemble_words', 'reason': 'no_owned_words'})
    assert 'worker_reason=no_owned_words' in caplog.text
    assert not [r for r in caplog.records if 'event=batch_quarantined' in r.getMessage()]


def test_terminal_record_names_the_preserved_diagnosis_when_the_call_has_none(caplog):
    store, queue, lease = leased()
    queue.fail('a', lease.token, 10.0, worker_failure_evidence={'stage': 'vad_windows', 'reason': 'vad_bounds'})
    store.rows['jobs', 'a'].update(state='leased', token='t2', lease_until=100.0, attempt=99)
    with caplog.at_level(logging.ERROR):
        queue.fail('a', 't2', 60.0)
    record = next(r.getMessage() for r in caplog.records if 'event=batch_quarantined' in r.getMessage())
    # The terminal naming prefers the current call's diagnosis, then the
    # diagnosis earlier ladder attempts preserved on the job (an exhausting
    # attempt may arrive evidence-less), and only a never-diagnosed unit
    # records the historical anonymous shape. The job row keeps the retained
    # ladder evidence for the fenced recovery lane either way.
    assert 'stage=vad_windows worker_reason=vad_bounds' in record
    assert store.rows['jobs', 'a']['worker_failure_evidence'] == {
        'stage': 'vad_windows',
        'reason': 'vad_bounds',
    }


def test_terminal_record_prefers_the_current_call_diagnosis_over_the_preserved_one(caplog):
    store, queue, lease = leased()
    queue.fail('a', lease.token, 10.0, worker_failure_evidence={'stage': 'vad_windows', 'reason': 'vad_bounds'})
    store.rows['jobs', 'a'].update(state='leased', token='t2', lease_until=100.0, attempt=99)
    with caplog.at_level(logging.ERROR):
        queue.fail('a', 't2', 60.0, worker_failure_evidence={'stage': 'fetch_decode', 'reason': 'word_clock'})
    record = next(r.getMessage() for r in caplog.records if 'event=batch_quarantined' in r.getMessage())
    assert 'stage=fetch_decode worker_reason=word_clock' in record


def test_never_diagnosed_units_keep_the_historical_unknown_shape(caplog):
    store, queue, lease = leased()
    with caplog.at_level(logging.ERROR):
        terminal(store, queue, lease, worker_failure=None)
    record = next(r.getMessage() for r in caplog.records if 'event=batch_quarantined' in r.getMessage())
    assert 'stage=unknown worker_reason=unclassified' in record


def test_quarantine_logs_the_fenced_recovery_hold(caplog):
    store, queue, lease = leased()
    with caplog.at_level(logging.WARNING):
        terminal(store, queue, lease)
    assert 'event=batch_recovery outcome=held reason=awaiting_fenced_recovery' in caplog.text


def test_defer_logs_the_ladder_rung(caplog):
    store, queue, lease = leased()
    with caplog.at_level(logging.INFO):
        queue.fail('a', lease.token, 10.0)
    assert 'event=batch_retry reason=worker_failed outcome=deferred' in caplog.text


# --- the bounded ladder boundary -----------------------------------------------------------------


def test_ordinary_failure_defers_instead_of_quarantining():
    store, queue, lease = leased()
    assert queue.fail('a', lease.token, 10.0) is True
    job = store.rows['jobs', 'a']
    assert job['state'] == 'retry'
    assert job['attempt'] == 1


def test_exhausted_attempt_quarantines_the_unit():
    store, queue, lease = leased()
    store.rows['jobs', 'a']['attempt'] = 5
    assert queue.fail('a', lease.token, 10.0) is True
    assert store.rows['jobs', 'a']['state'] == 'quarantined'


def test_explicit_quarantine_at_first_attempt_matches_the_empty_signature():
    store, queue, lease = leased()
    assert queue.fail('a', lease.token, 10.0, quarantine=True, padded_retry='empty', padded_retry_empty=True)
    job = store.rows['jobs', 'a']
    assert job['state'] == 'quarantined'
    assert job['attempt'] == 1
    assert job['recovery_state'] == 'held'
    assert job['quarantine_reason'] == 'worker_failed'


def test_quarantine_never_deletes_the_durable_audio_or_invents_a_result():
    store, queue, lease = leased()
    terminal(store, queue, lease, padded_retry='empty', padded_retry_empty=True)
    job = store.rows['jobs', 'a']
    assert ('results', 'a') not in store.rows
    assert job['audio_uri'] == item('a').audio_uri


# --- telemetry ------------------------------------------------------------------------------------


def test_quarantine_records_the_quarantined_and_recovery_held_metrics():
    records = []
    store, queue, lease = leased(metric_record=records.append)
    terminal(store, queue, lease)
    assert records == ['quarantined', 'recovery_held']


def test_defer_records_the_retry_metric():
    records = []
    store, queue, lease = leased(metric_record=records.append)
    queue.fail('a', lease.token, 10.0)
    assert records == ['retry']


def test_metrics_failures_never_fail_the_transition():
    store, queue, lease = leased(metric_record=Mock(side_effect=RuntimeError('registry down')))
    assert terminal(store, queue, lease) is True


def test_quarantine_records_failed_correctness_with_the_duration(monkeypatch):
    recorded = []
    monkeypatch.setattr(scheduler_module, 'record_correctness', lambda *a, **k: recorded.append((a, k)))
    store, queue, lease = leased()
    terminal(store, queue, lease)
    assert recorded == [(('failed',), {'seconds': item('a').duration_seconds})]


def test_defer_records_no_failed_correctness(monkeypatch):
    recorded = []
    monkeypatch.setattr(scheduler_module, 'record_correctness', lambda *a, **k: recorded.append((a, k)))
    store, queue, lease = leased()
    queue.fail('a', lease.token, 10.0)
    assert recorded == []


# --- custody ---------------------------------------------------------------------------------------


def test_stale_token_cannot_fail_the_lease():
    store, queue, lease = leased()
    assert queue.fail('a', 'stale-token', 10.0, quarantine=True, worker_failure=None) is False
    assert store.rows['jobs', 'a']['state'] == 'leased'
    assert 'worker_empty_evidence' not in store.rows['jobs', 'a']


def test_lease_expiry_cannot_fail_the_unit():
    store, queue, lease = leased()
    assert queue.fail('a', lease.token, 10_000.0, quarantine=True, worker_failure=None) is False
    assert store.rows['jobs', 'a']['state'] == 'leased'


def test_evidence_diagnosis_rides_the_job_across_defers():
    store, queue, lease = leased()
    queue.fail('a', lease.token, 10.0, worker_failure_evidence={'stage': 'assemble_words', 'reason': 'empty_asr'})
    assert store.rows['jobs', 'a']['worker_failure_evidence'] == {
        'stage': 'assemble_words',
        'reason': 'empty_asr',
    }
    # The next lease of the same unit re-fails without evidence: the previous
    # diagnosis must survive rather than being erased.
    store.rows['jobs', 'a'].update(state='leased', token='t2', lease_until=100.0)
    queue.fail('a', 't2', 60.0)
    assert store.rows['jobs', 'a']['worker_failure_evidence'] == {
        'stage': 'assemble_words',
        'reason': 'empty_asr',
    }


def test_ladder_evidence_retention_never_replaces_the_terminal_diagnosis(caplog):
    store, queue, lease = leased()
    queue.fail('a', lease.token, 10.0, worker_failure_evidence={'stage': 'asr_recovery', 'reason': 'unknown'})
    store.rows['jobs', 'a'].update(state='leased', token='t2', lease_until=100.0)
    with caplog.at_level(logging.ERROR):
        queue.fail('a', 't2', 60.0, quarantine=True, padded_retry='empty', padded_retry_empty=True)
    record = next(r.getMessage() for r in caplog.records if 'event=batch_quarantined' in r.getMessage())
    # Without a same-call worker_failure the record names the diagnosis the
    # ladder preserved (asr_recovery/unknown here) instead of collapsing to
    # the historical anonymous shape; the job row retains the evidence for
    # the fenced recovery lane either way.
    assert 'stage=asr_recovery worker_reason=unknown' in record
    job = store.rows['jobs', 'a']
    assert job['worker_failure_evidence'] == {'stage': 'asr_recovery', 'reason': 'unknown'}
    assert 'worker_failure' not in job


# --- held VAD evidence ------------------------------------------------------------------------------


def test_measured_held_vad_seconds_land_on_the_job():
    store, queue, lease = leased()
    terminal(store, queue, lease, measured_held_vad_speech_seconds=0.6)
    assert store.rows['jobs', 'a']['measured_held_vad_speech_seconds'] == pytest.approx(0.6)


def test_negative_measured_vad_is_refused():
    store, queue, lease = leased()
    with pytest.raises(ValueError):
        terminal(store, queue, lease, measured_held_vad_speech_seconds=-1.0)


def test_receipt_requires_a_matching_measured_vad():
    store, queue, lease = leased()
    receipt = {'version': 1, 'speech_samples': 16000}
    with pytest.raises(ValueError, match='invalid bound VAD receipt'):
        terminal(store, queue, lease, measured_held_vad_speech_seconds=0.6, worker_vad_receipt=receipt)


def test_bound_receipt_lands_on_the_job():
    from utils.batch_pipeline.contracts import vad_receipt

    unit = item('a')
    receipt = vad_receipt(unit.audio_uri, 32000, 0.6)
    store, queue, lease = leased()
    terminal(store, queue, lease, measured_held_vad_speech_seconds=0.6, worker_vad_receipt=receipt)
    assert store.rows['jobs', 'a']['worker_vad_receipt'] == receipt


def test_vad_receipt_requires_the_measured_seconds_to_match_the_samples():
    from utils.batch_pipeline.contracts import vad_receipt

    unit = item('a')
    receipt = vad_receipt(unit.audio_uri, 32000, 0.6)
    store, queue, lease = leased()
    with pytest.raises(ValueError, match='invalid bound VAD receipt'):
        terminal(store, queue, lease, measured_held_vad_speech_seconds=0.5, worker_vad_receipt=receipt)


def test_quarantine_pins_the_held_vad_even_without_a_measurement():
    store, queue, lease = leased()
    terminal(store, queue, lease, measured_held_vad_speech_seconds=None)
    assert store.rows['jobs', 'a']['measured_held_vad_speech_seconds'] is None


# --- the whole rung, end to end ----------------------------------------------------------------------


def test_padded_retry_shape_survives_the_full_empty_path():
    store, queue, lease = leased()
    assert terminal(store, queue, lease, padded_retry='empty', padded_retry_empty=True) is True
    job = store.rows['jobs', 'a']
    assert job['state'] == 'quarantined'
    assert job['recovery_state'] == 'held'
    assert job['worker_empty_evidence']['padded_retry'] == 'empty'
    assert job['worker_failure'] == {'stage': 'assemble_words', 'reason': 'empty_asr'}
    assert job['token'] == '' and job['lease_until'] == 0.0


# --- quarantine state hygiene --------------------------------------------------------------------


def test_quarantine_clears_the_retry_timer_and_merges_nothing():
    store, queue, lease = leased()
    queue.fail('a', lease.token, 10.0)  # one ladder step leaves a retry timer
    store.rows['jobs', 'a'].update(state='leased', token='t2', lease_until=100.0)
    queue.fail('a', 't2', 60.0, quarantine=True, padded_retry='empty', padded_retry_empty=True)
    job = store.rows['jobs', 'a']
    assert 'retry_started_at' not in job
    assert job['merge_pending'] is False


def test_quarantine_bumps_the_owner_revision():
    store, queue, lease = leased()
    owner_key = store.rows['jobs', 'a']['owner_key']
    before = store.rows['owners', owner_key]['revision']
    terminal(store, queue, lease)
    assert store.rows['owners', owner_key]['revision'] == before + 1


def test_quarantine_names_the_worker_failed_reason_on_the_job():
    store, queue, lease = leased()
    terminal(store, queue, lease)
    job = store.rows['jobs', 'a']
    assert job['failure'] == 'worker_failed'
    assert job['quarantine_reason'] == 'worker_failed'


def test_the_ladder_backoff_grows_across_defers():
    store, queue, lease = leased()
    queue.fail('a', lease.token, 10.0)
    first_available = store.rows['jobs', 'a']['available_at']
    store.rows['jobs', 'a'].update(state='leased', token='t2', lease_until=2000.0, attempt=2)
    queue.fail('a', 't2', 1500.0)
    second_available = store.rows['jobs', 'a']['available_at']
    assert second_available - 1500.0 > first_available - 10.0


def test_the_log_names_the_ladder_attempt_number(caplog):
    store, queue, lease = leased()
    with caplog.at_level(logging.INFO):
        queue.fail('a', lease.token, 10.0)
    record = next(r.getMessage() for r in caplog.records if 'event=batch_retry' in r.getMessage())
    assert 'attempt=1' in record


def test_terminal_log_names_the_attempt_that_quarantined(caplog):
    store, queue, lease = leased()
    store.rows['jobs', 'a'].update(state='leased', token='t2', lease_until=100.0, attempt=3)
    with caplog.at_level(logging.ERROR):
        queue.fail('a', 't2', 60.0, quarantine=True, padded_retry='empty', padded_retry_empty=True)
    record = next(r.getMessage() for r in caplog.records if 'event=batch_quarantined' in r.getMessage())
    assert 'attempt=3 recovery=held' in record


def test_a_scheduler_without_metrics_skips_the_telemetry_branch():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    lease = queue.pull(0)[0]
    assert terminal(store, queue, lease) is True


def test_ladder_terminal_at_max_attempts_writes_no_empty_evidence():
    store, queue, lease = leased()
    store.rows['jobs', 'a']['attempt'] = 99
    assert queue.fail('a', lease.token, 10.0) is True
    job = store.rows['jobs', 'a']
    assert job['state'] == 'quarantined'
    assert 'worker_empty_evidence' not in job


def test_fail_reports_the_outcome_triple_only_on_success():
    store, queue, lease = leased()
    assert terminal(store, queue, lease) is True
    assert queue.fail('a', 'stale', 10.0, quarantine=True, worker_failure=None) is False
