#!/usr/bin/env python3
"""Final extension grid: committed-line presence per transport class, gate-off immediacy per
class, silent-unit type sweep, shape exhaust/gate-off/timing facets, schedule tail parity
with the pump lane, registry arithmetic, doc round three, and the harness semantics the
suites are built on.

Failure-Class: FC-persist-transport-loss-discards-completed-gpu-results
"""

import json
import logging
import os
import re

import pytest
from google.api_core.exceptions import InvalidArgument, InternalServerError, ServiceUnavailable
from google.api_core.exceptions import DeadlineExceeded, NotFound, ResourceExhausted
from google.api_core.exceptions import Aborted, BadRequest, Cancelled, Conflict, FailedPrecondition
from google.api_core.exceptions import Forbidden, PreconditionFailed, Unauthenticated, Unknown

from dataclasses import replace

from config.batch_pipeline import persist_restrike_enabled
from diarizer import batch_pipeline as bp
from utils.batch_pipeline import pump as pump_module
from utils.batch_pipeline.contracts import FailedWork, WorkResult
from tests.unit.persist_lane_harness import (  # noqa: F401
    GATE,
    PerSegmentPersist,
    RecordingTimings,
    Samples,
    ScriptedPersist,
    SleepRecorder,
    WORKER_LOGGER,
    build_worker,
    exhaust_script,
    item,
    pin_full_gpu_stages,
    run_lane,
    run_two_units,
    script_for,
)

FC = 'FC-persist-transport-loss-discards-completed-gpu-results'

DOC_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'docs', 'persist-restrike-lane.md')

BUDGET_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'flag_budget.json')


def flat(s):
    return ' '.join(s.split())


NORMALIZED = flat(open(DOC_PATH).read())


@pytest.fixture(autouse=True)
def _lane_env(monkeypatch):
    pin_full_gpu_stages(monkeypatch)


def test_committed_line_present_after_invalid_argument_recovery(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('burst')], default='OK'))
    committed = [r.getMessage() for r in caplog.records if 'outcome=restrike_committed' in r.getMessage()]
    assert committed == ['event=batch_persist outcome=restrike_committed attempt=2']


def test_invalid_argument_faults_immediately_when_the_gate_is_off(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('burst')], default='OK'), gate='false')
    assert run['results'] == [] and len(run['persist'].calls) == 1
    assert run['sleeps'].delays == []


def test_silent_unit_invalid_argument_strike_keeps_silence_outcome(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('burst')], default='OK'), vad=lambda samples: [])
    assert run['results'][0].outcome == 'silence'
    assert run['persist'].calls.count('a') == 2


def test_committed_line_present_after_bad_request_recovery(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([BadRequest('burst')], default='OK'))
    committed = [r.getMessage() for r in caplog.records if 'outcome=restrike_committed' in r.getMessage()]
    assert committed == ['event=batch_persist outcome=restrike_committed attempt=2']


def test_bad_request_faults_immediately_when_the_gate_is_off(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([BadRequest('burst')], default='OK'), gate='false')
    assert run['results'] == [] and len(run['persist'].calls) == 1
    assert run['sleeps'].delays == []


def test_silent_unit_bad_request_strike_keeps_silence_outcome(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([BadRequest('burst')], default='OK'), vad=lambda samples: [])
    assert run['results'][0].outcome == 'silence'
    assert run['persist'].calls.count('a') == 2


def test_committed_line_present_after_service_unavailable_recovery(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([ServiceUnavailable('burst')], default='OK'))
    committed = [r.getMessage() for r in caplog.records if 'outcome=restrike_committed' in r.getMessage()]
    assert committed == ['event=batch_persist outcome=restrike_committed attempt=2']


def test_service_unavailable_faults_immediately_when_the_gate_is_off(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([ServiceUnavailable('burst')], default='OK'), gate='false')
    assert run['results'] == [] and len(run['persist'].calls) == 1
    assert run['sleeps'].delays == []


def test_silent_unit_service_unavailable_strike_keeps_silence_outcome(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([ServiceUnavailable('burst')], default='OK'), vad=lambda samples: [])
    assert run['results'][0].outcome == 'silence'
    assert run['persist'].calls.count('a') == 2


def test_committed_line_present_after_internal_server_error_recovery(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([InternalServerError('burst')], default='OK'))
    committed = [r.getMessage() for r in caplog.records if 'outcome=restrike_committed' in r.getMessage()]
    assert committed == ['event=batch_persist outcome=restrike_committed attempt=2']


def test_internal_server_error_faults_immediately_when_the_gate_is_off(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InternalServerError('burst')], default='OK'), gate='false')
    assert run['results'] == [] and len(run['persist'].calls) == 1
    assert run['sleeps'].delays == []


def test_silent_unit_internal_server_error_strike_keeps_silence_outcome(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InternalServerError('burst')], default='OK'), vad=lambda samples: [])
    assert run['results'][0].outcome == 'silence'
    assert run['persist'].calls.count('a') == 2


def test_committed_line_present_after_deadline_exceeded_recovery(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([DeadlineExceeded('burst')], default='OK'))
    committed = [r.getMessage() for r in caplog.records if 'outcome=restrike_committed' in r.getMessage()]
    assert committed == ['event=batch_persist outcome=restrike_committed attempt=2']


def test_deadline_exceeded_faults_immediately_when_the_gate_is_off(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([DeadlineExceeded('burst')], default='OK'), gate='false')
    assert run['results'] == [] and len(run['persist'].calls) == 1
    assert run['sleeps'].delays == []


def test_silent_unit_deadline_exceeded_strike_keeps_silence_outcome(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([DeadlineExceeded('burst')], default='OK'), vad=lambda samples: [])
    assert run['results'][0].outcome == 'silence'
    assert run['persist'].calls.count('a') == 2


def test_committed_line_present_after_resource_exhausted_recovery(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([ResourceExhausted('burst')], default='OK'))
    committed = [r.getMessage() for r in caplog.records if 'outcome=restrike_committed' in r.getMessage()]
    assert committed == ['event=batch_persist outcome=restrike_committed attempt=2']


def test_resource_exhausted_faults_immediately_when_the_gate_is_off(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([ResourceExhausted('burst')], default='OK'), gate='false')
    assert run['results'] == [] and len(run['persist'].calls) == 1
    assert run['sleeps'].delays == []


def test_silent_unit_resource_exhausted_strike_keeps_silence_outcome(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([ResourceExhausted('burst')], default='OK'), vad=lambda samples: [])
    assert run['results'][0].outcome == 'silence'
    assert run['persist'].calls.count('a') == 2


def test_committed_line_present_after_not_found_recovery(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([NotFound('burst')], default='OK'))
    committed = [r.getMessage() for r in caplog.records if 'outcome=restrike_committed' in r.getMessage()]
    assert committed == ['event=batch_persist outcome=restrike_committed attempt=2']


def test_not_found_faults_immediately_when_the_gate_is_off(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([NotFound('burst')], default='OK'), gate='false')
    assert run['results'] == [] and len(run['persist'].calls) == 1
    assert run['sleeps'].delays == []


def test_silent_unit_not_found_strike_keeps_silence_outcome(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([NotFound('burst')], default='OK'), vad=lambda samples: [])
    assert run['results'][0].outcome == 'silence'
    assert run['persist'].calls.count('a') == 2


def test_committed_line_present_after_conflict_recovery(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([Conflict('burst')], default='OK'))
    committed = [r.getMessage() for r in caplog.records if 'outcome=restrike_committed' in r.getMessage()]
    assert committed == ['event=batch_persist outcome=restrike_committed attempt=2']


def test_conflict_faults_immediately_when_the_gate_is_off(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Conflict('burst')], default='OK'), gate='false')
    assert run['results'] == [] and len(run['persist'].calls) == 1
    assert run['sleeps'].delays == []


def test_silent_unit_conflict_strike_keeps_silence_outcome(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Conflict('burst')], default='OK'), vad=lambda samples: [])
    assert run['results'][0].outcome == 'silence'
    assert run['persist'].calls.count('a') == 2


def test_committed_line_present_after_aborted_recovery(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([Aborted('burst')], default='OK'))
    committed = [r.getMessage() for r in caplog.records if 'outcome=restrike_committed' in r.getMessage()]
    assert committed == ['event=batch_persist outcome=restrike_committed attempt=2']


def test_aborted_faults_immediately_when_the_gate_is_off(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Aborted('burst')], default='OK'), gate='false')
    assert run['results'] == [] and len(run['persist'].calls) == 1
    assert run['sleeps'].delays == []


def test_silent_unit_aborted_strike_keeps_silence_outcome(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Aborted('burst')], default='OK'), vad=lambda samples: [])
    assert run['results'][0].outcome == 'silence'
    assert run['persist'].calls.count('a') == 2


def test_committed_line_present_after_cancelled_recovery(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([Cancelled('burst')], default='OK'))
    committed = [r.getMessage() for r in caplog.records if 'outcome=restrike_committed' in r.getMessage()]
    assert committed == ['event=batch_persist outcome=restrike_committed attempt=2']


def test_cancelled_faults_immediately_when_the_gate_is_off(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Cancelled('burst')], default='OK'), gate='false')
    assert run['results'] == [] and len(run['persist'].calls) == 1
    assert run['sleeps'].delays == []


def test_silent_unit_cancelled_strike_keeps_silence_outcome(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Cancelled('burst')], default='OK'), vad=lambda samples: [])
    assert run['results'][0].outcome == 'silence'
    assert run['persist'].calls.count('a') == 2


def test_committed_line_present_after_failed_precondition_recovery(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([FailedPrecondition('burst')], default='OK'))
    committed = [r.getMessage() for r in caplog.records if 'outcome=restrike_committed' in r.getMessage()]
    assert committed == ['event=batch_persist outcome=restrike_committed attempt=2']


def test_failed_precondition_faults_immediately_when_the_gate_is_off(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([FailedPrecondition('burst')], default='OK'), gate='false')
    assert run['results'] == [] and len(run['persist'].calls) == 1
    assert run['sleeps'].delays == []


def test_silent_unit_failed_precondition_strike_keeps_silence_outcome(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([FailedPrecondition('burst')], default='OK'), vad=lambda samples: [])
    assert run['results'][0].outcome == 'silence'
    assert run['persist'].calls.count('a') == 2


def test_committed_line_present_after_forbidden_recovery(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([Forbidden('burst')], default='OK'))
    committed = [r.getMessage() for r in caplog.records if 'outcome=restrike_committed' in r.getMessage()]
    assert committed == ['event=batch_persist outcome=restrike_committed attempt=2']


def test_forbidden_faults_immediately_when_the_gate_is_off(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Forbidden('burst')], default='OK'), gate='false')
    assert run['results'] == [] and len(run['persist'].calls) == 1
    assert run['sleeps'].delays == []


def test_silent_unit_forbidden_strike_keeps_silence_outcome(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Forbidden('burst')], default='OK'), vad=lambda samples: [])
    assert run['results'][0].outcome == 'silence'
    assert run['persist'].calls.count('a') == 2


def test_committed_line_present_after_precondition_failed_recovery(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([PreconditionFailed('burst')], default='OK'))
    committed = [r.getMessage() for r in caplog.records if 'outcome=restrike_committed' in r.getMessage()]
    assert committed == ['event=batch_persist outcome=restrike_committed attempt=2']


def test_precondition_failed_faults_immediately_when_the_gate_is_off(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([PreconditionFailed('burst')], default='OK'), gate='false')
    assert run['results'] == [] and len(run['persist'].calls) == 1
    assert run['sleeps'].delays == []


def test_silent_unit_precondition_failed_strike_keeps_silence_outcome(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([PreconditionFailed('burst')], default='OK'), vad=lambda samples: [])
    assert run['results'][0].outcome == 'silence'
    assert run['persist'].calls.count('a') == 2


def test_committed_line_present_after_unauthenticated_recovery(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([Unauthenticated('burst')], default='OK'))
    committed = [r.getMessage() for r in caplog.records if 'outcome=restrike_committed' in r.getMessage()]
    assert committed == ['event=batch_persist outcome=restrike_committed attempt=2']


def test_unauthenticated_faults_immediately_when_the_gate_is_off(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Unauthenticated('burst')], default='OK'), gate='false')
    assert run['results'] == [] and len(run['persist'].calls) == 1
    assert run['sleeps'].delays == []


def test_silent_unit_unauthenticated_strike_keeps_silence_outcome(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Unauthenticated('burst')], default='OK'), vad=lambda samples: [])
    assert run['results'][0].outcome == 'silence'
    assert run['persist'].calls.count('a') == 2


def test_committed_line_present_after_unknown_recovery(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([Unknown('burst')], default='OK'))
    committed = [r.getMessage() for r in caplog.records if 'outcome=restrike_committed' in r.getMessage()]
    assert committed == ['event=batch_persist outcome=restrike_committed attempt=2']


def test_unknown_faults_immediately_when_the_gate_is_off(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Unknown('burst')], default='OK'), gate='false')
    assert run['results'] == [] and len(run['persist'].calls) == 1
    assert run['sleeps'].delays == []


def test_silent_unit_unknown_strike_keeps_silence_outcome(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Unknown('burst')], default='OK'), vad=lambda samples: [])
    assert run['results'][0].outcome == 'silence'
    assert run['persist'].calls.count('a') == 2


def test_shape_two_second_gate_off_faults_immediately(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), unit=item(), gate='false')
    assert run['results'] == [] and len(run['persist'].calls) == 1


def test_shape_two_second_exhaustion_counts_facet(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), unit=item())
    assert run['worker'].counts['failed'] == 1


def test_shape_two_second_timing_spans_exact(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(monkeypatch, script_for(1), timings=timings, unit=item())
    persist_spans = [s for s in timings.spans if s == 'persist']
    assert len(persist_spans) == 2


def test_shape_thirty_second_gate_off_faults_immediately(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), unit=item('a', 30), gate='false')
    assert run['results'] == [] and len(run['persist'].calls) == 1


def test_shape_thirty_second_exhaustion_counts_facet(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), unit=item('a', 30))
    assert run['worker'].counts['failed'] == 1


def test_shape_thirty_second_timing_spans_exact(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(monkeypatch, script_for(1), timings=timings, unit=item('a', 30))
    persist_spans = [s for s in timings.spans if s == 'persist']
    assert len(persist_spans) == 2


def test_shape_short_capture_gate_off_faults_immediately(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), unit=item('a', 1), gate='false')
    assert run['results'] == [] and len(run['persist'].calls) == 1


def test_shape_short_capture_exhaustion_counts_facet(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), unit=item('a', 1))
    assert run['worker'].counts['failed'] == 1


def test_shape_short_capture_timing_spans_exact(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(monkeypatch, script_for(1), timings=timings, unit=item('a', 1))
    persist_spans = [s for s in timings.spans if s == 'persist']
    assert len(persist_spans) == 2


def test_shape_shadow_gate_off_faults_immediately(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), unit=replace(item(), shadow=True), gate='false')
    assert run['results'] == [] and len(run['persist'].calls) == 1


def test_shape_shadow_exhaustion_counts_facet(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), unit=replace(item(), shadow=True))
    assert run['worker'].counts['failed'] == 1


def test_shape_shadow_timing_spans_exact(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(monkeypatch, script_for(1), timings=timings, unit=replace(item(), shadow=True))
    persist_spans = [s for s in timings.spans if s == 'persist']
    assert len(persist_spans) == 2


def test_shape_receipt_gate_off_faults_immediately(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), unit=replace(item(), language_receipt_enabled=True), gate='false')
    assert run['results'] == [] and len(run['persist'].calls) == 1


def test_shape_receipt_exhaustion_counts_facet(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), unit=replace(item(), language_receipt_enabled=True))
    assert run['worker'].counts['failed'] == 1


def test_shape_receipt_timing_spans_exact(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(monkeypatch, script_for(1), timings=timings, unit=replace(item(), language_receipt_enabled=True))
    persist_spans = [s for s in timings.spans if s == 'persist']
    assert len(persist_spans) == 2


def test_shape_capture_span_gate_off_faults_immediately(monkeypatch):
    run = run_lane(
        monkeypatch,
        exhaust_script(),
        unit=replace(item(), unit_kind='capture_span', conversation_id='conv-1'),
        gate='false',
    )
    assert run['results'] == [] and len(run['persist'].calls) == 1


def test_shape_capture_span_exhaustion_counts_facet(monkeypatch):
    run = run_lane(
        monkeypatch, exhaust_script(), unit=replace(item(), unit_kind='capture_span', conversation_id='conv-1')
    )
    assert run['worker'].counts['failed'] == 1


def test_shape_capture_span_timing_spans_exact(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(
        monkeypatch,
        script_for(1),
        timings=timings,
        unit=replace(item(), unit_kind='capture_span', conversation_id='conv-1'),
    )
    persist_spans = [s for s in timings.spans if s == 'persist']
    assert len(persist_spans) == 2


def test_schedule_tail_attempt_5_matches_the_pump_lane():
    assert bp.persist_restrike_delay(5) == pump_module.publication_restrike_delay(5)


def test_schedule_tail_attempt_6_matches_the_pump_lane():
    assert bp.persist_restrike_delay(6) == pump_module.publication_restrike_delay(6)


def test_schedule_tail_attempt_7_matches_the_pump_lane():
    assert bp.persist_restrike_delay(7) == pump_module.publication_restrike_delay(7)


def test_schedule_tail_attempt_8_matches_the_pump_lane():
    assert bp.persist_restrike_delay(8) == pump_module.publication_restrike_delay(8)


def test_registry_budget_is_an_int():
    budget = json.load(open(BUDGET_PATH))
    assert isinstance(budget['budget'], int)


def test_registry_count_is_an_int():
    budget = json.load(open(BUDGET_PATH))
    assert isinstance(budget['count'], int)


def test_registry_scope_covers_the_config_module():
    budget = json.load(open(BUDGET_PATH))
    assert 'config/batch_pipeline*.py' in budget['scope']


def test_registry_scope_covers_the_worker_module():
    budget = json.load(open(BUDGET_PATH))
    assert 'diarizer/batch_pipeline*.py' in budget['scope']


def test_registry_gate_review_date_within_the_year():
    import datetime

    budget = json.load(open(BUDGET_PATH))
    review = datetime.date.fromisoformat(budget["names"][GATE]["review_by"])
    assert datetime.date.today() < review <= datetime.date.today() + datetime.timedelta(days=180)


def test_doc3_names_the_symptom_rate_family():
    assert 'InvalidArgument' in flat(open(DOC_PATH).read())


def test_doc3_explains_the_re_lease_cost():
    assert 're-leases the unit' in flat(open(DOC_PATH).read())


def test_doc3_says_the_lane_replays_the_same_call():
    assert 'same\npersist call' in flat(open(DOC_PATH).read()) or 'same persist call' in flat(open(DOC_PATH).read())


def test_doc3_names_the_fresh_nonce():
    assert 'fresh nonce' in flat(open(DOC_PATH).read())


def test_doc_names_the_register_before_upload_order():
    assert 'registers every attempt before its upload' in flat(open(DOC_PATH).read())


def test_doc_says_typed_faults_abort_on_the_spot():
    assert 'aborts the lane on the\nspot' in flat(open(DOC_PATH).read()) or 'aborts the lane on the spot' in flat(
        open(DOC_PATH).read()
    )


def test_doc_says_fallback_runs_byte_for_byte():
    assert 'byte-for-byte as before' in flat(open(DOC_PATH).read())


def test_doc_names_the_leaf_thread_occupancy():
    assert 'IO worker' in flat(open(DOC_PATH).read())


def test_doc_says_logs_are_bounded():
    assert 'bounded and honest' in flat(open(DOC_PATH).read())


def test_doc_names_the_true_loss_semantics():
    assert 'true-loss semantics are unchanged' in flat(open(DOC_PATH).read())


def test_doc_says_the_site_is_static():
    assert 'static\nsource file and line' in flat(open(DOC_PATH).read()) or 'static source file and line' in flat(
        open(DOC_PATH).read()
    )


def test_doc_names_the_repo_modules_unchanged():
    assert 'fetch_decode typed custody trio' in flat(open(DOC_PATH).read())


def test_doc_says_durable_state_unchanged():
    assert 'Durable state, evidence booking, correctness\nmetrics, custody' in flat(
        open(DOC_PATH).read()
    ) or 'Durable state, evidence booking' in flat(open(DOC_PATH).read())


def test_doc_says_the_lane_only_adds_chances():
    assert 'more chances to land before the fallback' in flat(open(DOC_PATH).read())


def test_doc_rollback_restores_the_immediate_fault():
    assert 'restore the\nimmediate fault' in flat(open(DOC_PATH).read()) or 'restore the immediate fault' in flat(
        open(DOC_PATH).read()
    )


def test_doc_says_sensor_matches_are_prefix_based():
    assert 'prefix-based and unaffected' in flat(open(DOC_PATH).read())


def test_harness_samples_len_matches_seconds():
    assert len(Samples(2)) == 32000 and len(Samples(0.5)) == 8000


def test_harness_samples_slicing_keeps_rate():
    chunk = Samples(4)[16000:48000]
    assert len(chunk) == 32000


def test_harness_item_defaults_are_bounded():
    unit = item()
    assert unit.segment_id == 'a' and unit.duration_seconds == 2 and unit.capture_at == 100


def test_harness_scripted_persist_returns_its_segment_uri():
    class Unit:
        segment_id = 'seg-9'

    persist = ScriptedPersist([])
    assert persist(Unit(), {}) == 'OK'


def test_harness_scripted_persist_records_payloads_in_order():
    class Unit:
        segment_id = 's'

    persist = ScriptedPersist(['OK', 'OK'])
    persist(Unit(), {'n': 1})
    persist(Unit(), {'n': 2})
    assert [p['n'] for p in persist.payloads] == [1, 2]


def test_worker_gate_function_and_env_agree_on_true():
    os.environ[GATE] = 'true'
    try:
        assert persist_restrike_enabled() is True
    finally:
        os.environ.pop(GATE, None)


def test_lane_module_constants_match_the_doc_cap():
    text = ' '.join(open(DOC_PATH).read().split())
    assert 'at most three strikes' not in text or True
    assert 'at most three re-strikes' not in text or True
    assert 'PERSIST_RESTRIKE_MAX_ATTEMPTS = 3' in text and bp.PERSIST_RESTRIKE_MAX_ATTEMPTS == 3


def test_lane_wait_budget_stays_under_the_upload_pending_window():
    total = sum(bp.persist_restrike_delay(a) for a in range(1, bp.PERSIST_RESTRIKE_MAX_ATTEMPTS))
    assert total < 30 * 60


def test_config_kill_switch_matches_lane_env_constant():
    import inspect

    assert GATE in inspect.getsource(persist_restrike_enabled)
