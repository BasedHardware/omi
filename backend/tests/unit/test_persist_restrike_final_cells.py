#!/usr/bin/env python3
"""Last extension cells: committed-line absence per clean type, harness-site suffix per
exhausted type, two-strike recovery for the silent/shadow/receipt/capture shapes, gate-off
immediacy per shape, and the FC trailer presence across every lane file.

Failure-Class: FC-persist-transport-loss-discards-completed-gpu-results
"""

import logging
import os
import re

import pytest
from google.api_core.exceptions import InvalidArgument, InternalServerError, ServiceUnavailable
from google.api_core.exceptions import DeadlineExceeded, NotFound, ResourceExhausted
from google.api_core.exceptions import Aborted, BadRequest, Cancelled, Conflict, FailedPrecondition
from google.api_core.exceptions import Forbidden, PreconditionFailed, Unauthenticated, Unknown

from dataclasses import replace

from diarizer import batch_pipeline as bp
from utils.batch_pipeline.contracts import WorkResult
from tests.unit.persist_lane_harness import (  # noqa: F401
    GATE,
    RecordingTimings,
    ScriptedPersist,
    SleepRecorder,
    WORKER_LOGGER,
    build_worker,
    exhaust_script,
    item,
    pin_full_gpu_stages,
    run_lane,
    script_for,
)

FC = 'FC-persist-transport-loss-discards-completed-gpu-results'


@pytest.fixture(autouse=True)
def _lane_env(monkeypatch):
    pin_full_gpu_stages(monkeypatch)


def test_invalid_argument_clean_first_call_logs_no_committed_line(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist(['OK']))
    assert not [r for r in caplog.records if 'outcome=restrike_committed' in r.getMessage()]


def test_invalid_argument_exhaustion_demotes_to_the_designed_line_without_site(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('burst')] * 3, default=InvalidArgument('burst')))
    assert [type(r).__name__ for r in run['results']] == ['ValidationFailureWork']
    demoted = [r.getMessage() for r in caplog.records if 'event=batch_validation_disposition' in r.getMessage()]
    assert demoted and 'error_class=InvalidArgument stage=persist' in demoted[0]
    assert 'reason=persist_payload_invalid' in demoted[0]
    assert ' site=' not in demoted[0]
    assert not [r for r in caplog.records if 'event=batch_worker_failed' in r.getMessage()]


def test_bad_request_clean_first_call_logs_no_committed_line(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist(['OK']))
    assert not [r for r in caplog.records if 'outcome=restrike_committed' in r.getMessage()]


def test_bad_request_exhaustion_fault_line_carries_the_harness_site(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([BadRequest('burst')] * 3, default=BadRequest('burst')))
    errors = [r.getMessage() for r in caplog.records if 'event=batch_worker_failed' in r.getMessage()]
    assert errors and ' site=persist_lane_harness.py:' in errors[0]


def test_service_unavailable_clean_first_call_logs_no_committed_line(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist(['OK']))
    assert not [r for r in caplog.records if 'outcome=restrike_committed' in r.getMessage()]


def test_service_unavailable_exhaustion_fault_line_carries_the_harness_site(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([ServiceUnavailable('burst')] * 3, default=ServiceUnavailable('burst')))
    errors = [r.getMessage() for r in caplog.records if 'event=batch_worker_failed' in r.getMessage()]
    assert errors and ' site=persist_lane_harness.py:' in errors[0]


def test_internal_server_error_clean_first_call_logs_no_committed_line(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist(['OK']))
    assert not [r for r in caplog.records if 'outcome=restrike_committed' in r.getMessage()]


def test_internal_server_error_exhaustion_fault_line_carries_the_harness_site(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(
        monkeypatch, ScriptedPersist([InternalServerError('burst')] * 3, default=InternalServerError('burst'))
    )
    errors = [r.getMessage() for r in caplog.records if 'event=batch_worker_failed' in r.getMessage()]
    assert errors and ' site=persist_lane_harness.py:' in errors[0]


def test_deadline_exceeded_clean_first_call_logs_no_committed_line(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist(['OK']))
    assert not [r for r in caplog.records if 'outcome=restrike_committed' in r.getMessage()]


def test_deadline_exceeded_exhaustion_fault_line_carries_the_harness_site(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([DeadlineExceeded('burst')] * 3, default=DeadlineExceeded('burst')))
    errors = [r.getMessage() for r in caplog.records if 'event=batch_worker_failed' in r.getMessage()]
    assert errors and ' site=persist_lane_harness.py:' in errors[0]


def test_resource_exhausted_clean_first_call_logs_no_committed_line(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist(['OK']))
    assert not [r for r in caplog.records if 'outcome=restrike_committed' in r.getMessage()]


def test_resource_exhausted_exhaustion_fault_line_carries_the_harness_site(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([ResourceExhausted('burst')] * 3, default=ResourceExhausted('burst')))
    errors = [r.getMessage() for r in caplog.records if 'event=batch_worker_failed' in r.getMessage()]
    assert errors and ' site=persist_lane_harness.py:' in errors[0]


def test_not_found_clean_first_call_logs_no_committed_line(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist(['OK']))
    assert not [r for r in caplog.records if 'outcome=restrike_committed' in r.getMessage()]


def test_not_found_exhaustion_fault_line_carries_the_harness_site(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([NotFound('burst')] * 3, default=NotFound('burst')))
    errors = [r.getMessage() for r in caplog.records if 'event=batch_worker_failed' in r.getMessage()]
    assert errors and ' site=persist_lane_harness.py:' in errors[0]


def test_conflict_clean_first_call_logs_no_committed_line(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist(['OK']))
    assert not [r for r in caplog.records if 'outcome=restrike_committed' in r.getMessage()]


def test_conflict_exhaustion_fault_line_carries_the_harness_site(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([Conflict('burst')] * 3, default=Conflict('burst')))
    errors = [r.getMessage() for r in caplog.records if 'event=batch_worker_failed' in r.getMessage()]
    assert errors and ' site=persist_lane_harness.py:' in errors[0]


def test_aborted_clean_first_call_logs_no_committed_line(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist(['OK']))
    assert not [r for r in caplog.records if 'outcome=restrike_committed' in r.getMessage()]


def test_aborted_exhaustion_fault_line_carries_the_harness_site(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([Aborted('burst')] * 3, default=Aborted('burst')))
    errors = [r.getMessage() for r in caplog.records if 'event=batch_worker_failed' in r.getMessage()]
    assert errors and ' site=persist_lane_harness.py:' in errors[0]


def test_cancelled_clean_first_call_logs_no_committed_line(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist(['OK']))
    assert not [r for r in caplog.records if 'outcome=restrike_committed' in r.getMessage()]


def test_cancelled_exhaustion_fault_line_carries_the_harness_site(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([Cancelled('burst')] * 3, default=Cancelled('burst')))
    errors = [r.getMessage() for r in caplog.records if 'event=batch_worker_failed' in r.getMessage()]
    assert errors and ' site=persist_lane_harness.py:' in errors[0]


def test_failed_precondition_clean_first_call_logs_no_committed_line(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist(['OK']))
    assert not [r for r in caplog.records if 'outcome=restrike_committed' in r.getMessage()]


def test_failed_precondition_exhaustion_fault_line_carries_the_harness_site(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([FailedPrecondition('burst')] * 3, default=FailedPrecondition('burst')))
    errors = [r.getMessage() for r in caplog.records if 'event=batch_worker_failed' in r.getMessage()]
    assert errors and ' site=persist_lane_harness.py:' in errors[0]


def test_forbidden_clean_first_call_logs_no_committed_line(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist(['OK']))
    assert not [r for r in caplog.records if 'outcome=restrike_committed' in r.getMessage()]


def test_forbidden_exhaustion_fault_line_carries_the_harness_site(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([Forbidden('burst')] * 3, default=Forbidden('burst')))
    errors = [r.getMessage() for r in caplog.records if 'event=batch_worker_failed' in r.getMessage()]
    assert errors and ' site=persist_lane_harness.py:' in errors[0]


def test_precondition_failed_clean_first_call_logs_no_committed_line(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist(['OK']))
    assert not [r for r in caplog.records if 'outcome=restrike_committed' in r.getMessage()]


def test_precondition_failed_exhaustion_fault_line_carries_the_harness_site(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([PreconditionFailed('burst')] * 3, default=PreconditionFailed('burst')))
    errors = [r.getMessage() for r in caplog.records if 'event=batch_worker_failed' in r.getMessage()]
    assert errors and ' site=persist_lane_harness.py:' in errors[0]


def test_unauthenticated_clean_first_call_logs_no_committed_line(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist(['OK']))
    assert not [r for r in caplog.records if 'outcome=restrike_committed' in r.getMessage()]


def test_unauthenticated_exhaustion_fault_line_carries_the_harness_site(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([Unauthenticated('burst')] * 3, default=Unauthenticated('burst')))
    errors = [r.getMessage() for r in caplog.records if 'event=batch_worker_failed' in r.getMessage()]
    assert errors and ' site=persist_lane_harness.py:' in errors[0]


def test_unknown_clean_first_call_logs_no_committed_line(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist(['OK']))
    assert not [r for r in caplog.records if 'outcome=restrike_committed' in r.getMessage()]


def test_unknown_exhaustion_fault_line_carries_the_harness_site(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([Unknown('burst')] * 3, default=Unknown('burst')))
    errors = [r.getMessage() for r in caplog.records if 'event=batch_worker_failed' in r.getMessage()]
    assert errors and ' site=persist_lane_harness.py:' in errors[0]


def test_silent_unit_two_strike_recovery_uri(monkeypatch):
    run = run_lane(monkeypatch, script_for(2), vad=lambda samples: [])
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['sleeps'].delays == [0.25, 0.5]


def test_shadow_unit_two_strike_recovery_uri(monkeypatch):
    run = run_lane(monkeypatch, script_for(2), unit=replace(item(), shadow=True))
    assert run['results'] and run['results'][0].result_uri == 'OK'


def test_receipt_unit_two_strike_recovery_route(monkeypatch):
    run = run_lane(monkeypatch, script_for(2), unit=replace(item(), language_receipt_enabled=True))
    assert run['results'][0].language_receipt['route'] == 'parakeet'


def test_capture_span_unit_two_strike_recovery_uri(monkeypatch):
    run = run_lane(monkeypatch, script_for(2), unit=replace(item(), unit_kind='capture_span', conversation_id='c-1'))
    assert run['results'] and run['results'][0].result_uri == 'OK'


def test_thirty_second_unit_exhaustion_books_once(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), unit=item('a', 30))
    assert [type(r).__name__ for r in run['results']] == ['ValidationFailureWork']
    assert run['meta']['failures'] == [('a', 'InvalidArgument')]


def test_short_capture_unit_exhaustion_books_once(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), unit=item('a', 1))
    assert [type(r).__name__ for r in run['results']] == ['ValidationFailureWork']


def test_gate_off_silent_unit_faults_immediately(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), vad=lambda samples: [], gate='false')
    assert [type(r).__name__ for r in run['results']] == ['ValidationFailureWork']
    assert len(run['persist'].calls) == 1


def test_gate_off_shadow_unit_faults_immediately(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), unit=replace(item(), shadow=True), gate='false')
    assert [type(r).__name__ for r in run['results']] == ['ValidationFailureWork']
    assert len(run['persist'].calls) == 1


def test_every_lane_file_carries_the_failure_class_trailer():
    here = os.path.dirname(__file__)
    names = [
        n
        for n in sorted(os.listdir(here))
        if ('persist_restrike' in n or n == 'persist_lane_harness.py') and n.endswith('.py')
    ]
    assert len(names) >= 18
    for name in names:
        assert (
            'Failure-Class: FC-persist-transport-loss-discards-completed-gpu-results'
            in open(os.path.join(here, name)).read()
        ), name
