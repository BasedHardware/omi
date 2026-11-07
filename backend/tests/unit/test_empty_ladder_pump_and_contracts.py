# Failure-Class: FC-empty-ladder-gate-drift-misroutes-recovery-units-between-hold-retry-and-terminal-rungs
"""The pump's empty-ladder mapping and the Work-contract vocabulary.

The pump is the only translator between the worker's result objects and the
scheduler transition: ``RecoveryWork`` must arrive as a quarantine with the
padded-retry token and the assemble_words diagnosis, ``ValidationFailureWork``
as a terminal quarantine without empty evidence, ``FailedWork`` as an
ordinary ladder step that only retains evidence, and ``HeldWork`` as a
policy hold. This suite pins that mapping result-by-result, then pins the
closed dataclass contracts the mapping relies on.
"""

import asyncio
import time
from unittest.mock import Mock

import pytest

from tests.unit.test_batch_pipeline_pump import setup
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from tests.unit.test_batch_pipeline_worker import item
from utils.batch_pipeline.contracts import (
    EMPTY_WORKER_REASONS,
    FailedWork,
    HeldWork,
    RecoveryWork,
    ValidationFailureWork,
    WorkItem,
    WorkResult,
    validate_measured_vad,
    WorkerValidationReason,
)
from utils.batch_pipeline.errors import WORKER_VALIDATION_STAGES
from utils.batch_pipeline.pump import Pump, PoolCapacity
from utils.batch_pipeline.scheduler import Scheduler
from utils.observability.reasons import WorkerValidationStage


class StubWorker:
    def __init__(self, results):
        self.results = results
        self.calls = 0

    def process_batch(self, items):
        self.calls += 1
        return [self.results.get(v.segment_id) for v in items]


def run(results):
    worker = StubWorker(results)
    store, queue, pump = setup(worker)
    import asyncio

    asyncio.run(pump.run_once())
    return store, queue


# --- the RecoveryWork mapping ------------------------------------------------------------------


def test_recovery_work_quarantines_with_the_empty_token_and_diagnosis():
    store, _ = run({'first': RecoveryWork('first', padded_retry='empty', padded_retry_empty=True)})
    job = store.rows['jobs', 'first']
    assert job['state'] == 'quarantined' and job['recovery_state'] == 'held'
    assert job['worker_failure'] == {'stage': 'assemble_words', 'reason': 'empty_asr'}
    assert job['worker_empty_evidence'] == {'padded_retry': 'empty', 'version': 1}
    assert job['attempt'] == 1


def test_recovery_work_skipped_oversize_token_reaches_the_job():
    store, _ = run({'first': RecoveryWork('first', padded_retry='skipped_oversize', reason='empty_asr')})
    assert store.rows['jobs', 'first']['worker_empty_evidence'] == {'padded_retry': 'skipped_oversize', 'version': 1}


def test_recovery_work_skipped_long_speech_token_reaches_the_job():
    store, _ = run({'first': RecoveryWork('first', padded_retry='skipped_long_speech', reason='empty_asr')})
    assert store.rows['jobs', 'first']['worker_empty_evidence'] == {
        'padded_retry': 'skipped_long_speech',
        'version': 1,
    }


def test_recovery_work_without_a_token_quarantines_without_evidence():
    store, _ = run({'first': RecoveryWork('first')})
    job = store.rows['jobs', 'first']
    assert job['state'] == 'quarantined'
    assert 'worker_empty_evidence' not in job
    assert job['worker_failure'] == {'stage': 'assemble_words', 'reason': 'empty_asr'}


def test_recovery_work_no_owned_reason_keeps_its_diagnosis():
    store, _ = run(
        {'first': RecoveryWork('first', padded_retry='empty', padded_retry_empty=True, reason='no_owned_words')}
    )
    assert store.rows['jobs', 'first']['worker_failure'] == {
        'stage': 'assemble_words',
        'reason': 'no_owned_words',
    }


def test_recovery_work_carries_the_measured_vad_evidence_to_the_job():
    store, _ = run({'first': RecoveryWork('first', measured_held_vad_speech_seconds=0.6)})
    assert store.rows['jobs', 'first']['measured_held_vad_speech_seconds'] == pytest.approx(0.6)


def test_recovery_work_never_writes_a_result():
    store, _ = run({'first': RecoveryWork('first')})
    assert ('results', 'first') not in store.rows


def test_stale_token_recovery_mapping_is_a_no_op():
    worker = StubWorker({'first': RecoveryWork('first')})
    store, queue, pump = setup(worker)
    import asyncio

    queue.fail(
        'first',
        'other-token',
        time.time(),
        quarantine=True,
        worker_failure={'stage': 'assemble_words', 'reason': 'empty_asr'},
    )
    asyncio.run(pump.run_once())
    # The revoked lease leaves the earlier terminal state untouched.
    assert store.rows['jobs', 'first']['state'] == 'quarantined'


# --- the other result mappings ------------------------------------------------------------------


def test_validation_failure_quarantines_without_empty_evidence():
    store, _ = run({'first': ValidationFailureWork('first', 'assemble_words', 'empty_asr')})
    job = store.rows['jobs', 'first']
    assert job['state'] == 'quarantined'
    assert job['worker_failure'] == {'stage': 'assemble_words', 'reason': 'empty_asr'}
    assert 'worker_empty_evidence' not in job


def test_failed_work_defers_and_retains_evidence_only():
    store, _ = run(
        {'first': FailedWork('first', 0.6, None, worker_failure={'stage': 'assemble_words', 'reason': 'empty_asr'})}
    )
    job = store.rows['jobs', 'first']
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == {'stage': 'assemble_words', 'reason': 'empty_asr'}
    assert 'worker_empty_evidence' not in job


def test_held_work_defers_as_a_policy_hold_without_attempts():
    store, _ = run({'first': HeldWork('first', reason='allowance_exhausted')})
    job = store.rows['jobs', 'first']
    assert job['state'] == 'retry'
    assert job['attempt'] == 0


def test_held_work_default_reason_defers_without_a_named_hold():
    store, _ = run({'first': HeldWork('first')})
    assert store.rows['jobs', 'first']['state'] == 'retry'


def test_work_result_completes_the_unit():
    store, _ = run({'first': WorkResult('first', 'gs://results/first')})
    assert ('results', 'first') in store.rows


def test_mixed_results_settle_independently():
    results = {
        'first': RecoveryWork('first', padded_retry='empty', padded_retry_empty=True),
        'second': FailedWork('second'),
    }
    worker = StubWorker(results)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('first'), time.time())
    queue.enqueue(item('second', 2), time.time())
    pump = Pump(queue, worker, capacity=lambda: PoolCapacity(time.time(), 8))
    asyncio.run(pump.run_once())
    assert store.rows['jobs', 'first']['state'] == 'quarantined'
    # The unmapped unit took the ordinary ladder step instead of the terminal.
    assert store.rows['jobs', 'second']['state'] == 'retry'
    assert ('results', 'first') not in store.rows


def test_recovery_work_without_any_token_stays_unnormalized():
    work = RecoveryWork('a')
    assert work.padded_retry is None and work.padded_retry_empty is False


def test_scheduler_failure_logs_the_completion_retry_signature(caplog):
    import asyncio
    import logging

    worker = StubWorker({'first': RecoveryWork('first')})
    store, queue, pump = setup(worker)
    queue.fail = Mock(side_effect=ValueError('store down'))
    with caplog.at_level(logging.ERROR):
        asyncio.run(pump.run_once())
    record = next(r.getMessage() for r in caplog.records if 'event=batch_completion outcome=retry' in r.getMessage())
    assert 'exception_type=ValueError' in record


# --- RecoveryWork contract ------------------------------------------------------------------------


def test_recovery_work_default_reason_is_empty_asr():
    assert RecoveryWork('a').reason == 'empty_asr'


def test_recovery_work_rejects_non_empty_reasons():
    with pytest.raises(ValueError, match='closed empty worker reason required'):
        RecoveryWork('a', reason='word_clock')


def test_recovery_work_normalizes_a_bare_empty_flag_into_the_token():
    assert RecoveryWork('a', padded_retry_empty=True).padded_retry == 'empty'


def test_recovery_work_normalizes_the_empty_token_into_the_flag():
    work = RecoveryWork('a', padded_retry='empty')
    assert work.padded_retry_empty is True


def test_recovery_work_rejects_unknown_padded_tokens():
    with pytest.raises(ValueError, match='unsupported padded retry evidence'):
        RecoveryWork('a', padded_retry='identical')


def test_recovery_work_rejects_conflicting_empty_evidence():
    with pytest.raises(ValueError, match='conflicting padded retry evidence'):
        RecoveryWork('a', padded_retry='skipped_oversize', padded_retry_empty=True)


def test_recovery_work_tokens_oversize_and_long_speech_carry_no_empty_flag():
    assert RecoveryWork('a', padded_retry='skipped_oversize').padded_retry_empty is False
    assert RecoveryWork('a', padded_retry='skipped_long_speech').padded_retry_empty is False


# --- the other Work contracts ---------------------------------------------------------------------


def test_validation_failure_accepts_the_empty_family_for_terminal_routing():
    assert ValidationFailureWork('a', 'assemble_words', 'empty_asr').reason == 'empty_asr'
    assert ValidationFailureWork('a', 'assemble_words', 'no_owned_words').reason == 'no_owned_words'


def test_validation_failure_rejects_unclosed_reasons():
    with pytest.raises(ValueError):
        ValidationFailureWork('a', 'assemble_words', 'mystery')


def test_validation_failure_rejects_unclosed_stages():
    with pytest.raises(ValueError):
        ValidationFailureWork('a', 'elsewhere', 'empty_asr')


def test_failed_work_rejects_evidence_outside_the_closed_stage_vocabulary():
    with pytest.raises(ValueError, match='closed worker failure evidence required'):
        FailedWork('a', 0.6, None, worker_failure={'stage': 'elsewhere', 'reason': 'empty_asr'})


def test_failed_work_evidence_may_name_unknown_reasons():
    work = FailedWork('a', 0.6, None, worker_failure={'stage': 'asr_recovery', 'reason': 'unknown'})
    assert work.worker_failure['reason'] == 'unknown'


def test_measured_vad_rejects_negative_and_nonfinite_seconds():
    with pytest.raises(ValueError):
        validate_measured_vad(-0.5)
    with pytest.raises(ValueError):
        validate_measured_vad(float('nan'))


def test_measured_vad_accepts_none_and_nonnegative_seconds():
    assert validate_measured_vad(None) is None
    assert validate_measured_vad(0.0) == 0.0


def test_held_work_defaults():
    work = HeldWork('a')
    assert work.reason == '' and work.retry_after == 60


# --- the closed vocabulary the mapping depends on --------------------------------------------------


def test_empty_worker_reasons_are_exactly_the_two_family_tokens():
    assert EMPTY_WORKER_REASONS == {'empty_asr', 'no_owned_words'}


def test_worker_validation_stage_vocabulary_covers_the_worker_stages():
    from utils.observability.reasons import reason_values

    assert WORKER_VALIDATION_STAGES == reason_values(WorkerValidationStage)


def test_worker_validation_reason_tokens_cover_the_enum():
    tokens = {reason.value for reason in WorkerValidationReason}
    assert {'empty_asr', 'no_owned_words', 'word_clock', 'word_shape', 'word_sequence'} <= tokens


def test_work_items_carry_the_shadow_flag_the_gate_ignores():
    unit = item('a')
    assert isinstance(unit, WorkItem)
    assert hasattr(unit, 'shadow')


# --- additional mapping cells -------------------------------------------------------------------


def test_recovery_work_with_no_owned_reason_and_oversize_token_maps_fully():
    store, _ = run({'first': RecoveryWork('first', padded_retry='skipped_oversize', reason='no_owned_words')})
    job = store.rows['jobs', 'first']
    assert job['worker_failure'] == {'stage': 'assemble_words', 'reason': 'no_owned_words'}
    assert job['worker_empty_evidence'] == {'padded_retry': 'skipped_oversize', 'version': 1}


def test_validation_failure_with_the_word_clocks_stage_maps_verbatim():
    store, _ = run({'first': ValidationFailureWork('first', 'word_clocks', 'word_clock')})
    assert store.rows['jobs', 'first']['worker_failure'] == {'stage': 'word_clocks', 'reason': 'word_clock'}


def test_failed_work_measured_vad_lands_on_the_job():
    store, _ = run({'first': FailedWork('first', 0.6)})
    assert store.rows['jobs', 'first']['measured_held_vad_speech_seconds'] == pytest.approx(0.6)


def test_held_work_defer_keeps_the_job_out_of_the_results():
    store, _ = run({'first': HeldWork('first', reason='allowance_exhausted')})
    assert ('results', 'first') not in store.rows


# --- additional contract cells -------------------------------------------------------------------


def test_work_result_rejects_path_like_segment_ids():
    with pytest.raises(ValueError):
        WorkResult('a/b', 'gs://results/a')


def test_work_result_rejects_oversized_segment_ids():
    with pytest.raises(ValueError):
        WorkResult('a' * 129, 'gs://results/a')


def test_work_result_allows_the_silence_outcome():
    assert WorkResult('a', 'gs://results/a', outcome='silence').outcome == 'silence'


def test_recovery_work_measured_vad_is_validated_too():
    with pytest.raises(ValueError):
        RecoveryWork('a', measured_held_vad_speech_seconds=-1.0)


def test_validation_failure_measured_vad_is_validated_too():
    with pytest.raises(ValueError):
        ValidationFailureWork('a', 'assemble_words', 'empty_asr', measured_held_vad_speech_seconds=-1.0)


def test_failed_work_defaults_to_no_terminal_diagnosis():
    assert FailedWork('a').worker_failure is None


def test_held_work_accepts_a_custom_retry_after():
    assert HeldWork('a', retry_after=120).retry_after == 120


def test_validate_measured_vad_rejects_seconds_past_the_duration():
    with pytest.raises(ValueError):
        validate_measured_vad(3.0, 2.0)


def test_validate_measured_vad_allows_the_sub_frame_tolerance():
    assert validate_measured_vad(2.0, 2.0) == 2.0


def test_failed_work_takes_the_diagnosis_only_from_the_closed_vocabulary():
    FailedWork('a', 0.6, None, worker_failure={'stage': 'vad_windows', 'reason': 'vad_nonfinite'})
    with pytest.raises(ValueError):
        FailedWork('a', 0.6, None, worker_failure={'stage': 'vad_windows', 'reason': 'boom'})


def test_the_empty_family_tokens_are_the_only_recovery_reasons():
    for reason in sorted(EMPTY_WORKER_REASONS):
        assert RecoveryWork('a', reason=reason).reason == reason


# --- more pump-mapping cells ---------------------------------------------------------------------


def run_manual(results):
    worker = StubWorker(results)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('first'), time.time())
    pump = Pump(queue, worker, capacity=lambda: PoolCapacity(time.time(), 8))
    asyncio.run(pump.run_once())
    return store


def test_recovery_work_receipt_lands_on_the_job():
    from utils.batch_pipeline.contracts import vad_receipt

    unit = item('first')
    receipt = vad_receipt(unit.audio_uri, int(unit.duration_seconds * 16000), 0.6)
    store = run_manual(
        {'first': RecoveryWork('first', measured_held_vad_speech_seconds=0.6, worker_vad_receipt=receipt)}
    )
    assert store.rows['jobs', 'first']['worker_vad_receipt'] == receipt


def test_validation_failure_measured_vad_lands_on_the_job():
    store, _ = run({'first': ValidationFailureWork('first', 'assemble_words', 'empty_asr', 0.6)})
    assert store.rows['jobs', 'first']['measured_held_vad_speech_seconds'] == pytest.approx(0.6)


def test_failed_work_receipt_lands_on_the_job():
    from utils.batch_pipeline.contracts import vad_receipt

    unit = item('first')
    receipt = vad_receipt(unit.audio_uri, int(unit.duration_seconds * 16000), 0.6)
    store = run_manual({'first': FailedWork('first', 0.6, receipt)})
    assert store.rows['jobs', 'first']['worker_vad_receipt'] == receipt


def test_held_work_defer_records_no_empty_evidence():
    store, _ = run({'first': HeldWork('first')})
    assert 'worker_empty_evidence' not in store.rows['jobs', 'first']


# --- more contract cells --------------------------------------------------------------------------


def test_recovery_work_excludes_the_vad_fields_from_identity():
    plain = RecoveryWork('a', padded_retry='empty', padded_retry_empty=True)
    evidenced = RecoveryWork('a', padded_retry='empty', padded_retry_empty=True, measured_held_vad_speech_seconds=0.6)
    assert plain == evidenced


def test_failed_work_keeps_measured_vad_in_its_identity():
    # Unlike the handoff results, the ladder result's measured VAD is part of
    # its identity: two attempts with different measurements are different.
    assert FailedWork('a', 0.6) != FailedWork('a', 0.9)


def test_work_result_defaults_to_the_success_outcome():
    assert WorkResult('a', 'gs://results/a').outcome == 'success'


def test_the_padded_retry_token_vocabulary_is_exactly_four_values():
    valid = {None, 'empty', 'skipped_oversize', 'skipped_long_speech'}
    for token in valid:
        kwargs = {'padded_retry': token}
        if token == 'empty':
            kwargs['padded_retry_empty'] = True
        assert RecoveryWork('a', **kwargs).padded_retry == token
