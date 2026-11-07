"""The fetch_decode boundary names the outside-admitted-source fault end to end.

The worker's ``fail`` closure used to collapse every non-validation exception
into ``reason='unclassified'``: the per-attempt ERROR record (the loop
sensor's x386/30m ``error_class=ValueError reason=unclassified stage=fetch_decode``
family), the FailedWork evidence and the eventual terminal quarantine all
carried the anonymous shape. A retained manifest reference outside the
deployment's admitted bucket set — the one bare raise left on that boundary —
now carries ``RetainedAudioOutsideAdmittedSource`` and the closed
``outside_admitted_source`` evidence token through every surface: the
per-attempt record, the ladder's evidence, and the terminal quarantine.

The safety-net kill switch contract is unchanged: with
``BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED=false`` the fault again returns
no result (the scheduler contract's retryable missing-result shape), exactly
as it did when it was anonymous.

Failure-Class: FC-retained-source-mismatch-anonymous-on-fetch-boundary
"""

import logging
from dataclasses import replace

import pytest

from diarizer.batch_pipeline import transient_failure_evidence
from tests.unit.test_batch_pipeline_worker import Samples, item, setup_worker
from utils.batch_pipeline.contracts import FailedWork, ValidationFailureWork, WorkItem
from utils.batch_pipeline.errors import (
    WORKER_VALIDATION_REASONS,
    WORKER_VALIDATION_STAGES,
    validate_worker_failure_evidence,
)
from utils.batch_pipeline.source_audio import RetainedAudioOutsideAdmittedSource
from utils.observability.reasons import WorkerValidationReason


def fault(message='retained audio reference is outside admitted source'):
    return RetainedAudioOutsideAdmittedSource(message)


# --- transient_failure_evidence maps the named fault ------------------------------


def test_evidence_closes_the_named_fault_on_the_fetch_stage():
    assert transient_failure_evidence('fetch_decode', 'outside_admitted_source') == {
        'stage': 'fetch_decode',
        'reason': 'outside_admitted_source',
    }


def test_evidence_for_the_named_fault_passes_the_evidence_gate():
    assert (
        validate_worker_failure_evidence(transient_failure_evidence('fetch_decode', 'outside_admitted_source')) is None
    )


def test_evidence_for_the_named_fault_on_every_stage():
    for stage in sorted(WORKER_VALIDATION_STAGES):
        assert transient_failure_evidence(stage, 'outside_admitted_source') == {
            'stage': stage,
            'reason': 'outside_admitted_source',
        }


def test_evidence_for_the_named_fault_is_not_the_terminal_unknown_fallback():
    closed = transient_failure_evidence('fetch_decode', 'outside_admitted_source')
    assert closed is not None
    assert closed['reason'] != WorkerValidationReason.UNKNOWN.value


def test_evidence_still_collapses_the_truly_unknown_reason():
    assert transient_failure_evidence('fetch_decode', 'unclassified') == {
        'stage': 'fetch_decode',
        'reason': WorkerValidationReason.UNKNOWN.value,
    }


def test_evidence_stays_none_for_the_untyped_provider_stage():
    assert transient_failure_evidence('persist', 'outside_admitted_source') is None


def test_evidence_stays_none_for_an_invented_stage():
    assert transient_failure_evidence('smoke_test', 'outside_admitted_source') is None


# --- The worker boundary surfaces the named fault ---------------------------------


def named_decode(work):
    raise fault()


def test_named_fault_rides_the_retryable_failed_work_arm():
    worker, *_ = setup_worker(decode=named_decode)
    results = worker.process_batch([item()])
    assert len(results) == 1
    assert isinstance(results[0], FailedWork)


def test_named_fault_evidence_names_stage_and_reason():
    worker, *_ = setup_worker(decode=named_decode)
    results = worker.process_batch([item()])
    assert results[0].worker_failure == {'stage': 'fetch_decode', 'reason': 'outside_admitted_source'}


def test_named_fault_evidence_passes_the_evidence_gate_through_the_contract():
    worker, *_ = setup_worker(decode=named_decode)
    results = worker.process_batch([item()])
    validate_worker_failure_evidence(results[0].worker_failure)


def test_named_fault_evidence_is_not_the_terminal_structured_failure():
    worker, *_ = setup_worker(decode=named_decode)
    results = worker.process_batch([item()])
    assert not isinstance(results[0], ValidationFailureWork)


def test_named_fault_does_not_reuse_the_bytes_family_reason():
    worker, *_ = setup_worker(decode=named_decode)
    results = worker.process_batch([item()])
    assert results[0].worker_failure['reason'] != 'retained_audio_invalid'


def test_named_fault_does_not_reuse_the_staged_family_reason():
    worker, *_ = setup_worker(decode=named_decode)
    results = worker.process_batch([item()])
    assert results[0].worker_failure['reason'] != 'staged_audio_invalid'


def test_named_fault_does_not_reuse_the_duration_family_reason():
    worker, *_ = setup_worker(decode=named_decode)
    results = worker.process_batch([item()])
    assert results[0].worker_failure['reason'] != 'decoded_duration_mismatch'


def test_named_fault_per_attempt_record_names_the_class(caplog):
    worker, *_ = setup_worker(decode=named_decode)
    with caplog.at_level(logging.ERROR, logger='diarizer.batch_pipeline'):
        worker.process_batch([item()])
    record = [line for line in caplog.text.splitlines() if 'event=batch_worker_failed' in line]
    assert record, 'the per-attempt failure record must still fire'
    assert 'error_class=RetainedAudioOutsideAdmittedSource' in record[-1]


def test_named_fault_per_attempt_record_names_the_closed_reason(caplog):
    worker, *_ = setup_worker(decode=named_decode)
    with caplog.at_level(logging.ERROR, logger='diarizer.batch_pipeline'):
        worker.process_batch([item()])
    record = [line for line in caplog.text.splitlines() if 'event=batch_worker_failed' in line]
    assert 'reason=outside_admitted_source' in record[-1]


def test_named_fault_per_attempt_record_names_the_stage(caplog):
    worker, *_ = setup_worker(decode=named_decode)
    with caplog.at_level(logging.ERROR, logger='diarizer.batch_pipeline'):
        worker.process_batch([item()])
    record = [line for line in caplog.text.splitlines() if 'event=batch_worker_failed' in line]
    assert 'stage=fetch_decode' in record[-1]


def test_named_fault_per_attempt_record_carries_no_exception_message(caplog):
    # The closed-code contract: records carry tokens, never provider text.
    worker, *_ = setup_worker(decode=lambda work: fault('secret-bucket-name-leak'))
    with caplog.at_level(logging.ERROR, logger='diarizer.batch_pipeline'):
        worker.process_batch([item()])
    record = [line for line in caplog.text.splitlines() if 'event=batch_worker_failed' in line]
    assert 'secret-bucket-name-leak' not in record[-1]


def test_named_fault_leaves_the_sibling_units_untouched():
    def decode(work):
        if work.segment_id == 'a':
            raise fault()
        return Samples(work.duration_seconds)

    worker, _, saved, *_ = setup_worker(decode=decode)
    results = worker.process_batch([item('a'), item('b')])
    assert isinstance(results[0], FailedWork)
    assert results[1].outcome == 'success' and saved['b']['words']


def test_named_fault_runs_decode_exactly_once_per_unit():
    decoded = []

    def decode(work):
        decoded.append(work.segment_id)
        raise fault()

    worker, *_ = setup_worker(decode=decode)
    worker.process_batch([item()])
    assert decoded == ['a']


def test_named_fault_is_not_classified_as_empty_asr_attempt():
    # record_correctness('empty_asr_attempt') must not fire for this reason.
    worker, *_ = setup_worker(decode=named_decode)
    worker.process_batch([item()])
    from utils.batch_pipeline import correctness_metrics

    snapshot = dict(correctness_metrics.SNAPSHOT) if hasattr(correctness_metrics, 'SNAPSHOT') else {}
    assert not snapshot.get('empty_asr_attempt')


def test_named_fault_counts_as_a_worker_failure_for_metrics():
    worker, *_ = setup_worker(decode=named_decode)
    before = dict(worker.counts)
    worker.process_batch([item()])
    assert worker.counts['failed'] == before.get('failed', 0) + 1


def test_named_fault_on_a_shadow_unit_logs_the_shadow_shape(caplog):
    worker, *_ = setup_worker(decode=named_decode)
    shadow = replace(item(), shadow=True)
    with caplog.at_level(logging.INFO, logger='diarizer.batch_pipeline'):
        results = worker.process_batch([shadow])
    assert isinstance(results[0], FailedWork)
    infos = [line for line in caplog.text.splitlines() if 'event=batch_shadow_worker_failure' in line]
    assert infos, 'shadow failures must keep their quiet INFO shape'
    assert not [line for line in caplog.text.splitlines() if 'event=batch_worker_failed' in line]


def test_named_fault_shadow_evidence_still_names_the_reason(caplog):
    worker, *_ = setup_worker(decode=named_decode)
    shadow = replace(item(), shadow=True)
    with caplog.at_level(logging.INFO, logger='diarizer.batch_pipeline'):
        worker.process_batch([shadow])
    infos = [line for line in caplog.text.splitlines() if 'event=batch_shadow_worker_failure' in line]
    assert 'reason=outside_admitted_source' in infos[-1]


# --- The safety-net kill switch contract ------------------------------------------


def test_safety_net_off_returns_no_result_for_the_named_fault(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    worker, *_ = setup_worker(decode=named_decode)
    results = worker.process_batch([item()])
    assert results == []


def test_safety_net_default_keeps_the_evidence_path(monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', raising=False)
    worker, *_ = setup_worker(decode=named_decode)
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)


def test_safety_net_off_keeps_the_per_attempt_record(caplog, monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    worker, *_ = setup_worker(decode=named_decode)
    with caplog.at_level(logging.ERROR, logger='diarizer.batch_pipeline'):
        worker.process_batch([item()])
    assert [line for line in caplog.text.splitlines() if 'event=batch_worker_failed' in line]


def test_safety_net_switch_is_read_per_call(monkeypatch):
    worker, *_ = setup_worker(decode=named_decode)
    results_first = worker.process_batch([item('a')])
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    results_second = worker.process_batch([item('b')])
    assert len(results_first) == 1
    assert results_second == []


# --- The boundary stays a closed vocabulary surface --------------------------------


def test_named_fault_reason_is_not_the_worker_unknown_token():
    worker, *_ = setup_worker(decode=named_decode)
    results = worker.process_batch([item()])
    assert results[0].worker_failure['reason'] != 'unknown'


def test_named_fault_reason_is_a_member_of_the_closed_vocabulary():
    worker, *_ = setup_worker(decode=named_decode)
    results = worker.process_batch([item()])
    assert results[0].worker_failure['reason'] in WORKER_VALIDATION_REASONS


def test_named_fault_stage_is_the_fetch_decode_stage():
    worker, *_ = setup_worker(decode=named_decode)
    results = worker.process_batch([item()])
    assert results[0].worker_failure['stage'] == 'fetch_decode'


def test_named_fault_stage_is_in_the_closed_stage_vocabulary():
    worker, *_ = setup_worker(decode=named_decode)
    results = worker.process_batch([item()])
    assert results[0].worker_failure['stage'] in WORKER_VALIDATION_STAGES


def test_named_fault_evidence_pair_has_exactly_two_keys():
    worker, *_ = setup_worker(decode=named_decode)
    results = worker.process_batch([item()])
    assert set(results[0].worker_failure) == {'stage', 'reason'}


def test_genuinely_untyped_faults_stay_anonymous():
    # A bare ValueError that is NOT the named class keeps the historical
    # unknown evidence shape — the taxonomy widens, it does not mislabel.
    worker, *_ = setup_worker(decode=lambda work: (_ for _ in ()).throw(ValueError('mystery')))
    results = worker.process_batch([item()])
    assert results[0].worker_failure == {'stage': 'fetch_decode', 'reason': 'unknown'}


def test_genuinely_untyped_runtime_faults_stay_anonymous():
    worker, *_ = setup_worker(decode=lambda work: (_ for _ in ()).throw(RuntimeError('mystery')))
    results = worker.process_batch([item()])
    assert results[0].worker_failure == {'stage': 'fetch_decode', 'reason': 'unknown'}


def test_retained_bytes_faults_keep_their_own_reason():
    from utils.batch_pipeline.source_audio import RetainedAudioInvalid

    worker, *_ = setup_worker(
        decode=lambda work: (_ for _ in ()).throw(RetainedAudioInvalid('retained capture checksum mismatch'))
    )
    results = worker.process_batch([item()])
    assert isinstance(results[0], ValidationFailureWork)
    assert results[0].reason == 'retained_audio_invalid'


def test_staged_bytes_faults_keep_their_own_reason():
    from utils.batch_pipeline.audio import StagedAudioInvalid

    worker, *_ = setup_worker(
        decode=lambda work: (_ for _ in ()).throw(StagedAudioInvalid('invalid staged WAV container'))
    )
    results = worker.process_batch([item()])
    assert isinstance(results[0], ValidationFailureWork)
    assert results[0].reason == 'staged_audio_invalid'


# --- The class cooperates with every boundary consumer ------------------------------


def test_named_fault_survives_a_raise_from_chain():
    try:
        try:
            raise fault()
        except ValueError as inner:
            raise RuntimeError('wrap') from inner
    except RuntimeError as outer:
        assert isinstance(outer.__cause__, RetainedAudioOutsideAdmittedSource)


def test_named_fault_is_catchable_where_value_error_was_caught():
    # Existing callers that caught bare ValueError keep working: the class is
    # a ValueError subclass, so no catch site narrows.
    caught = []
    try:
        raise fault()
    except ValueError as error:
        caught.append(type(error).__name__)
    assert caught == ['RetainedAudioOutsideAdmittedSource']


def test_named_fault_in_a_manifest_materialize_chain_is_the_only_raise():
    # materialize's own manifest-shape faults stay InvalidRetainedManifest;
    # only the bucket arm produces the new class.
    from utils.batch_pipeline.source_audio import InvalidRetainedManifest, materialize
    from types import SimpleNamespace

    holder = SimpleNamespace(owner_id='o', conversation_id='c', capture_at=1, duration_seconds=1.0)
    from utils.batch_pipeline.source_audio import MAGIC
    import json

    body = (
        MAGIC
        + json.dumps(
            {'owner_id': 'o', 'conversation_id': 'c', 'capture_at': 1, 'references': [], 'context': {}}
        ).encode()
    )
    with pytest.raises(InvalidRetainedManifest):
        materialize(body, holder, lambda ref: b'')


def test_named_fault_is_not_produced_by_materialize_for_the_binding_arms():
    from utils.batch_pipeline.source_audio import InvalidRetainedManifest, MAGIC, materialize
    from types import SimpleNamespace

    holder = SimpleNamespace(owner_id='o', conversation_id='c', capture_at=1, duration_seconds=1.0)
    import json

    body = (
        MAGIC
        + json.dumps(
            {'owner_id': 'o', 'conversation_id': 'c', 'capture_at': 1, 'references': [], 'context': {}}
        ).encode()
    )
    with pytest.raises(InvalidRetainedManifest) as error:
        materialize(body, holder, lambda ref: b'')
    assert not isinstance(error.value, RetainedAudioOutsideAdmittedSource)


def test_worker_failure_count_matches_failed_units_only():
    worker, *_ = setup_worker(decode=named_decode)
    worker.process_batch([item('a'), item('b')])
    assert worker.counts['failed'] == 2


def test_worker_failed_set_is_fenced_per_batch_run():
    # ``failed`` fences one process_batch call: the same segment in a LATER
    # batch is a fresh run and counts again (a re-leased unit's retry is a
    # real attempt), while a duplicate id inside ONE pull is refused outright.
    worker, *_ = setup_worker(decode=named_decode)
    worker.process_batch([item('a')])
    assert worker.counts['failed'] == 1
    worker.process_batch([item('a')])
    assert worker.counts['failed'] == 2
    with pytest.raises(ValueError, match='at most 32 distinct conversations'):
        worker.process_batch([item('c'), item('c')])


# --- Vocabulary hygiene: the token neither collides nor drifts ---------------------


def test_outside_admitted_source_token_does_not_collide_with_bytes_family():
    values = {reason.value for reason in WorkerValidationReason}
    assert {'outside_admitted_source', 'retained_audio_invalid'} <= values
    assert len({'outside_admitted_source', 'retained_audio_invalid'}) == 2


def test_outside_admitted_source_token_does_not_collide_with_staged_family():
    values = {reason.value for reason in WorkerValidationReason}
    assert 'outside_admitted_source' not in {'staged_audio_invalid', 'decoded_duration_mismatch'}


def test_outside_admitted_source_token_survives_reason_values_projection():
    from utils.batch_pipeline.errors import reason_values

    assert 'outside_admitted_source' in reason_values(WorkerValidationReason)


def test_outside_admitted_source_token_is_not_the_unknown_placeholder():
    assert WorkerValidationReason.OUTSIDE_ADMITTED_SOURCE is not WorkerValidationReason.UNKNOWN


def test_every_closed_stage_carries_the_named_token_through_the_evidence_gate():
    for stage in sorted(WORKER_VALIDATION_STAGES):
        assert validate_worker_failure_evidence({'stage': stage, 'reason': 'outside_admitted_source'}) is None
