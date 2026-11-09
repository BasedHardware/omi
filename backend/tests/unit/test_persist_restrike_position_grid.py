#!/usr/bin/env python3
"""Strike-position times fault-type permutation grid.

For every Google transport class the lane recovers when the fault lands at strike 1 or
strike 2, sleeping exactly the documented prefix and naming that class in the wait line;
mixed permutations and the three-distinct-type exhaustion pin the booking at the cap.

Failure-Class: FC-persist-transport-loss-discards-completed-gpu-results
"""

import datetime
import json
import logging
import os
import re

import pytest
from google.api_core.exceptions import InvalidArgument, InternalServerError, ServiceUnavailable
from google.api_core.exceptions import DeadlineExceeded, NotFound, ResourceExhausted, RetryError
from google.api_core.exceptions import Aborted, BadRequest, Cancelled, Conflict, FailedPrecondition
from google.api_core.exceptions import Forbidden, GoogleAPIError, PreconditionFailed
from google.api_core.exceptions import Unauthenticated, Unknown

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


def test_invalid_argument_at_strike_position_1_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('burst'), 'OK']))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['persist'].calls.count('a') == 2


def test_invalid_argument_at_strike_position_1_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('burst'), 'OK']))
    assert run['sleeps'].delays == [0.25]


def test_invalid_argument_at_strike_position_1_waits_log_the_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('burst'), 'OK']))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits[0] and 'exception_type=InvalidArgument' in waits[0]


def test_invalid_argument_at_strike_position_2_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), InvalidArgument('burst'), 'OK']))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['persist'].calls.count('a') == 3


def test_invalid_argument_at_strike_position_2_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), InvalidArgument('burst'), 'OK']))
    assert run['sleeps'].delays == [0.25, 0.5]


def test_invalid_argument_at_strike_position_2_waits_log_the_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), InvalidArgument('burst'), 'OK']))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits[1] and 'exception_type=InvalidArgument' in waits[1]


def test_bad_request_at_strike_position_1_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([BadRequest('burst'), 'OK']))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['persist'].calls.count('a') == 2


def test_bad_request_at_strike_position_1_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([BadRequest('burst'), 'OK']))
    assert run['sleeps'].delays == [0.25]


def test_bad_request_at_strike_position_1_waits_log_the_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([BadRequest('burst'), 'OK']))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits[0] and 'exception_type=BadRequest' in waits[0]


def test_bad_request_at_strike_position_2_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), BadRequest('burst'), 'OK']))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['persist'].calls.count('a') == 3


def test_bad_request_at_strike_position_2_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), BadRequest('burst'), 'OK']))
    assert run['sleeps'].delays == [0.25, 0.5]


def test_bad_request_at_strike_position_2_waits_log_the_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), BadRequest('burst'), 'OK']))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits[1] and 'exception_type=BadRequest' in waits[1]


def test_service_unavailable_at_strike_position_1_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([ServiceUnavailable('burst'), 'OK']))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['persist'].calls.count('a') == 2


def test_service_unavailable_at_strike_position_1_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([ServiceUnavailable('burst'), 'OK']))
    assert run['sleeps'].delays == [0.25]


def test_service_unavailable_at_strike_position_1_waits_log_the_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([ServiceUnavailable('burst'), 'OK']))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits[0] and 'exception_type=ServiceUnavailable' in waits[0]


def test_service_unavailable_at_strike_position_2_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), ServiceUnavailable('burst'), 'OK']))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['persist'].calls.count('a') == 3


def test_service_unavailable_at_strike_position_2_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), ServiceUnavailable('burst'), 'OK']))
    assert run['sleeps'].delays == [0.25, 0.5]


def test_service_unavailable_at_strike_position_2_waits_log_the_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), ServiceUnavailable('burst'), 'OK']))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits[1] and 'exception_type=ServiceUnavailable' in waits[1]


def test_internal_server_error_at_strike_position_1_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InternalServerError('burst'), 'OK']))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['persist'].calls.count('a') == 2


def test_internal_server_error_at_strike_position_1_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InternalServerError('burst'), 'OK']))
    assert run['sleeps'].delays == [0.25]


def test_internal_server_error_at_strike_position_1_waits_log_the_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([InternalServerError('burst'), 'OK']))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits[0] and 'exception_type=InternalServerError' in waits[0]


def test_internal_server_error_at_strike_position_2_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), InternalServerError('burst'), 'OK']))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['persist'].calls.count('a') == 3


def test_internal_server_error_at_strike_position_2_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), InternalServerError('burst'), 'OK']))
    assert run['sleeps'].delays == [0.25, 0.5]


def test_internal_server_error_at_strike_position_2_waits_log_the_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), InternalServerError('burst'), 'OK']))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits[1] and 'exception_type=InternalServerError' in waits[1]


def test_deadline_exceeded_at_strike_position_1_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([DeadlineExceeded('burst'), 'OK']))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['persist'].calls.count('a') == 2


def test_deadline_exceeded_at_strike_position_1_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([DeadlineExceeded('burst'), 'OK']))
    assert run['sleeps'].delays == [0.25]


def test_deadline_exceeded_at_strike_position_1_waits_log_the_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([DeadlineExceeded('burst'), 'OK']))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits[0] and 'exception_type=DeadlineExceeded' in waits[0]


def test_deadline_exceeded_at_strike_position_2_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), DeadlineExceeded('burst'), 'OK']))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['persist'].calls.count('a') == 3


def test_deadline_exceeded_at_strike_position_2_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), DeadlineExceeded('burst'), 'OK']))
    assert run['sleeps'].delays == [0.25, 0.5]


def test_deadline_exceeded_at_strike_position_2_waits_log_the_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), DeadlineExceeded('burst'), 'OK']))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits[1] and 'exception_type=DeadlineExceeded' in waits[1]


def test_resource_exhausted_at_strike_position_1_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([ResourceExhausted('burst'), 'OK']))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['persist'].calls.count('a') == 2


def test_resource_exhausted_at_strike_position_1_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([ResourceExhausted('burst'), 'OK']))
    assert run['sleeps'].delays == [0.25]


def test_resource_exhausted_at_strike_position_1_waits_log_the_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([ResourceExhausted('burst'), 'OK']))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits[0] and 'exception_type=ResourceExhausted' in waits[0]


def test_resource_exhausted_at_strike_position_2_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), ResourceExhausted('burst'), 'OK']))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['persist'].calls.count('a') == 3


def test_resource_exhausted_at_strike_position_2_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), ResourceExhausted('burst'), 'OK']))
    assert run['sleeps'].delays == [0.25, 0.5]


def test_resource_exhausted_at_strike_position_2_waits_log_the_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), ResourceExhausted('burst'), 'OK']))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits[1] and 'exception_type=ResourceExhausted' in waits[1]


def test_not_found_at_strike_position_1_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([NotFound('burst'), 'OK']))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['persist'].calls.count('a') == 2


def test_not_found_at_strike_position_1_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([NotFound('burst'), 'OK']))
    assert run['sleeps'].delays == [0.25]


def test_not_found_at_strike_position_1_waits_log_the_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([NotFound('burst'), 'OK']))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits[0] and 'exception_type=NotFound' in waits[0]


def test_not_found_at_strike_position_2_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), NotFound('burst'), 'OK']))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['persist'].calls.count('a') == 3


def test_not_found_at_strike_position_2_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), NotFound('burst'), 'OK']))
    assert run['sleeps'].delays == [0.25, 0.5]


def test_not_found_at_strike_position_2_waits_log_the_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), NotFound('burst'), 'OK']))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits[1] and 'exception_type=NotFound' in waits[1]


def test_conflict_at_strike_position_1_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Conflict('burst'), 'OK']))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['persist'].calls.count('a') == 2


def test_conflict_at_strike_position_1_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Conflict('burst'), 'OK']))
    assert run['sleeps'].delays == [0.25]


def test_conflict_at_strike_position_1_waits_log_the_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([Conflict('burst'), 'OK']))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits[0] and 'exception_type=Conflict' in waits[0]


def test_conflict_at_strike_position_2_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), Conflict('burst'), 'OK']))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['persist'].calls.count('a') == 3


def test_conflict_at_strike_position_2_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), Conflict('burst'), 'OK']))
    assert run['sleeps'].delays == [0.25, 0.5]


def test_conflict_at_strike_position_2_waits_log_the_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), Conflict('burst'), 'OK']))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits[1] and 'exception_type=Conflict' in waits[1]


def test_aborted_at_strike_position_1_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Aborted('burst'), 'OK']))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['persist'].calls.count('a') == 2


def test_aborted_at_strike_position_1_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Aborted('burst'), 'OK']))
    assert run['sleeps'].delays == [0.25]


def test_aborted_at_strike_position_1_waits_log_the_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([Aborted('burst'), 'OK']))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits[0] and 'exception_type=Aborted' in waits[0]


def test_aborted_at_strike_position_2_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), Aborted('burst'), 'OK']))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['persist'].calls.count('a') == 3


def test_aborted_at_strike_position_2_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), Aborted('burst'), 'OK']))
    assert run['sleeps'].delays == [0.25, 0.5]


def test_aborted_at_strike_position_2_waits_log_the_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), Aborted('burst'), 'OK']))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits[1] and 'exception_type=Aborted' in waits[1]


def test_cancelled_at_strike_position_1_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Cancelled('burst'), 'OK']))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['persist'].calls.count('a') == 2


def test_cancelled_at_strike_position_1_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Cancelled('burst'), 'OK']))
    assert run['sleeps'].delays == [0.25]


def test_cancelled_at_strike_position_1_waits_log_the_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([Cancelled('burst'), 'OK']))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits[0] and 'exception_type=Cancelled' in waits[0]


def test_cancelled_at_strike_position_2_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), Cancelled('burst'), 'OK']))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['persist'].calls.count('a') == 3


def test_cancelled_at_strike_position_2_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), Cancelled('burst'), 'OK']))
    assert run['sleeps'].delays == [0.25, 0.5]


def test_cancelled_at_strike_position_2_waits_log_the_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), Cancelled('burst'), 'OK']))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits[1] and 'exception_type=Cancelled' in waits[1]


def test_failed_precondition_at_strike_position_1_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([FailedPrecondition('burst'), 'OK']))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['persist'].calls.count('a') == 2


def test_failed_precondition_at_strike_position_1_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([FailedPrecondition('burst'), 'OK']))
    assert run['sleeps'].delays == [0.25]


def test_failed_precondition_at_strike_position_1_waits_log_the_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([FailedPrecondition('burst'), 'OK']))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits[0] and 'exception_type=FailedPrecondition' in waits[0]


def test_failed_precondition_at_strike_position_2_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), FailedPrecondition('burst'), 'OK']))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['persist'].calls.count('a') == 3


def test_failed_precondition_at_strike_position_2_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), FailedPrecondition('burst'), 'OK']))
    assert run['sleeps'].delays == [0.25, 0.5]


def test_failed_precondition_at_strike_position_2_waits_log_the_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), FailedPrecondition('burst'), 'OK']))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits[1] and 'exception_type=FailedPrecondition' in waits[1]


def test_forbidden_at_strike_position_1_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Forbidden('burst'), 'OK']))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['persist'].calls.count('a') == 2


def test_forbidden_at_strike_position_1_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Forbidden('burst'), 'OK']))
    assert run['sleeps'].delays == [0.25]


def test_forbidden_at_strike_position_1_waits_log_the_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([Forbidden('burst'), 'OK']))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits[0] and 'exception_type=Forbidden' in waits[0]


def test_forbidden_at_strike_position_2_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), Forbidden('burst'), 'OK']))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['persist'].calls.count('a') == 3


def test_forbidden_at_strike_position_2_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), Forbidden('burst'), 'OK']))
    assert run['sleeps'].delays == [0.25, 0.5]


def test_forbidden_at_strike_position_2_waits_log_the_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), Forbidden('burst'), 'OK']))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits[1] and 'exception_type=Forbidden' in waits[1]


def test_precondition_failed_at_strike_position_1_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([PreconditionFailed('burst'), 'OK']))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['persist'].calls.count('a') == 2


def test_precondition_failed_at_strike_position_1_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([PreconditionFailed('burst'), 'OK']))
    assert run['sleeps'].delays == [0.25]


def test_precondition_failed_at_strike_position_1_waits_log_the_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([PreconditionFailed('burst'), 'OK']))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits[0] and 'exception_type=PreconditionFailed' in waits[0]


def test_precondition_failed_at_strike_position_2_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), PreconditionFailed('burst'), 'OK']))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['persist'].calls.count('a') == 3


def test_precondition_failed_at_strike_position_2_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), PreconditionFailed('burst'), 'OK']))
    assert run['sleeps'].delays == [0.25, 0.5]


def test_precondition_failed_at_strike_position_2_waits_log_the_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), PreconditionFailed('burst'), 'OK']))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits[1] and 'exception_type=PreconditionFailed' in waits[1]


def test_unauthenticated_at_strike_position_1_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Unauthenticated('burst'), 'OK']))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['persist'].calls.count('a') == 2


def test_unauthenticated_at_strike_position_1_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Unauthenticated('burst'), 'OK']))
    assert run['sleeps'].delays == [0.25]


def test_unauthenticated_at_strike_position_1_waits_log_the_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([Unauthenticated('burst'), 'OK']))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits[0] and 'exception_type=Unauthenticated' in waits[0]


def test_unauthenticated_at_strike_position_2_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), Unauthenticated('burst'), 'OK']))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['persist'].calls.count('a') == 3


def test_unauthenticated_at_strike_position_2_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), Unauthenticated('burst'), 'OK']))
    assert run['sleeps'].delays == [0.25, 0.5]


def test_unauthenticated_at_strike_position_2_waits_log_the_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), Unauthenticated('burst'), 'OK']))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits[1] and 'exception_type=Unauthenticated' in waits[1]


def test_unknown_at_strike_position_1_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Unknown('burst'), 'OK']))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['persist'].calls.count('a') == 2


def test_unknown_at_strike_position_1_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([Unknown('burst'), 'OK']))
    assert run['sleeps'].delays == [0.25]


def test_unknown_at_strike_position_1_waits_log_the_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([Unknown('burst'), 'OK']))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits[0] and 'exception_type=Unknown' in waits[0]


def test_unknown_at_strike_position_2_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), Unknown('burst'), 'OK']))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['persist'].calls.count('a') == 3


def test_unknown_at_strike_position_2_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), Unknown('burst'), 'OK']))
    assert run['sleeps'].delays == [0.25, 0.5]


def test_unknown_at_strike_position_2_waits_log_the_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), Unknown('burst'), 'OK']))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits[1] and 'exception_type=Unknown' in waits[1]


def test_retry_error_at_strike_position_1_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([RetryError('burst', None), 'OK']))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['persist'].calls.count('a') == 2


def test_retry_error_at_strike_position_1_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([RetryError('burst', None), 'OK']))
    assert run['sleeps'].delays == [0.25]


def test_retry_error_at_strike_position_1_waits_log_the_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([RetryError('burst', None), 'OK']))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits[0] and 'exception_type=RetryError' in waits[0]


def test_retry_error_at_strike_position_2_recovers(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), RetryError('burst', None), 'OK']))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['persist'].calls.count('a') == 3


def test_retry_error_at_strike_position_2_sleeps_the_documented_prefix(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), RetryError('burst', None), 'OK']))
    assert run['sleeps'].delays == [0.25, 0.5]


def test_retry_error_at_strike_position_2_waits_log_the_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('first'), RetryError('burst', None), 'OK']))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits[1] and 'exception_type=RetryError' in waits[1]


def test_mixed_type_permutation_recovers_across_positions(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([ServiceUnavailable('a'), InternalServerError('b'), 'OK']))
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['sleeps'].delays == [0.25, 0.5]


def test_exhaustion_with_three_distinct_types_books_the_final_raised_type(monkeypatch):
    run = run_lane(
        monkeypatch,
        ScriptedPersist(
            [InvalidArgument('a'), ServiceUnavailable('b'), DeadlineExceeded('c')], default=InvalidArgument('a')
        ),
    )
    assert run['results'] == [] and run['meta']['failures'] == [('a', 'DeadlineExceeded')]


def test_exhaustion_runs_exactly_the_cap_calls(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script())
    assert len(run['persist'].calls) == 3


def test_exhaustion_never_runs_a_fourth_call(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script())
    calls = run['persist'].calls
    assert calls == ['a', 'a', 'a']
