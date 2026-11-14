#!/usr/bin/env python3
"""Every Google transport fault class recovers through the lane under the documented schedule.

One cell per class strikes once and pins the recovered URI plus the 0.25s first wait; one
cell per class exhausts at the cap and pins the booking after the budget (the typed custody
handoff for the deterministic refusal, the legacy fault for every other class); one cell per class pins
the restrike_wait log naming that exception type. Together they prove the classifier
verdicts translate into lane behavior class by class.

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


@pytest.fixture(autouse=True)
def _lane_env(monkeypatch):
    pin_full_gpu_stages(monkeypatch)


def test_invalid_argument_strike_recovers_with_the_documented_first_wait(monkeypatch):
    run = run_lane(
        monkeypatch,
        script_for(1, final='OK', fault=None) if False else ScriptedPersist([InvalidArgument('burst')], default='OK'),
    )
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['sleeps'].delays == [0.25]


def test_invalid_argument_exhaustion_books_the_typed_custody_handoff(monkeypatch):
    fault = InvalidArgument('burst')
    run = run_lane(monkeypatch, ScriptedPersist([fault] * 3, default=fault))
    assert [type(r).__name__ for r in run['results']] == ['ValidationFailureWork']
    assert run['results'][0].stage == 'persist' and run['results'][0].reason == 'persist_payload_invalid'
    assert run['meta']['failures'] == [('a', type(fault).__name__)]


def test_invalid_argument_strike_logs_its_exception_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('burst')], default='OK'))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits and 'exception_type=InvalidArgument' in waits[0]


def test_bad_request_strike_recovers_with_the_documented_first_wait(monkeypatch):
    run = run_lane(
        monkeypatch,
        script_for(1, final='OK', fault=None) if False else ScriptedPersist([BadRequest('burst')], default='OK'),
    )
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['sleeps'].delays == [0.25]


def test_bad_request_exhaustion_books_the_legacy_fault(monkeypatch):
    fault = BadRequest('burst')
    run = run_lane(monkeypatch, ScriptedPersist([fault] * 3, default=fault))
    assert run['results'] == [] and run['meta']['failures'] == [('a', type(fault).__name__)]


def test_bad_request_strike_logs_its_exception_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([BadRequest('burst')], default='OK'))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits and 'exception_type=BadRequest' in waits[0]


def test_service_unavailable_strike_recovers_with_the_documented_first_wait(monkeypatch):
    run = run_lane(
        monkeypatch,
        (
            script_for(1, final='OK', fault=None)
            if False
            else ScriptedPersist([ServiceUnavailable('burst')], default='OK')
        ),
    )
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['sleeps'].delays == [0.25]


def test_service_unavailable_exhaustion_books_the_legacy_fault(monkeypatch):
    fault = ServiceUnavailable('burst')
    run = run_lane(monkeypatch, ScriptedPersist([fault] * 3, default=fault))
    assert run['results'] == [] and run['meta']['failures'] == [('a', type(fault).__name__)]


def test_service_unavailable_strike_logs_its_exception_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([ServiceUnavailable('burst')], default='OK'))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits and 'exception_type=ServiceUnavailable' in waits[0]


def test_internal_server_error_strike_recovers_with_the_documented_first_wait(monkeypatch):
    run = run_lane(
        monkeypatch,
        (
            script_for(1, final='OK', fault=None)
            if False
            else ScriptedPersist([InternalServerError('burst')], default='OK')
        ),
    )
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['sleeps'].delays == [0.25]


def test_internal_server_error_exhaustion_books_the_legacy_fault(monkeypatch):
    fault = InternalServerError('burst')
    run = run_lane(monkeypatch, ScriptedPersist([fault] * 3, default=fault))
    assert run['results'] == [] and run['meta']['failures'] == [('a', type(fault).__name__)]


def test_internal_server_error_strike_logs_its_exception_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([InternalServerError('burst')], default='OK'))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits and 'exception_type=InternalServerError' in waits[0]


def test_deadline_exceeded_strike_recovers_with_the_documented_first_wait(monkeypatch):
    run = run_lane(
        monkeypatch,
        script_for(1, final='OK', fault=None) if False else ScriptedPersist([DeadlineExceeded('burst')], default='OK'),
    )
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['sleeps'].delays == [0.25]


def test_deadline_exceeded_exhaustion_books_the_legacy_fault(monkeypatch):
    fault = DeadlineExceeded('burst')
    run = run_lane(monkeypatch, ScriptedPersist([fault] * 3, default=fault))
    assert run['results'] == [] and run['meta']['failures'] == [('a', type(fault).__name__)]


def test_deadline_exceeded_strike_logs_its_exception_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([DeadlineExceeded('burst')], default='OK'))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits and 'exception_type=DeadlineExceeded' in waits[0]


def test_resource_exhausted_strike_recovers_with_the_documented_first_wait(monkeypatch):
    run = run_lane(
        monkeypatch,
        script_for(1, final='OK', fault=None) if False else ScriptedPersist([ResourceExhausted('burst')], default='OK'),
    )
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['sleeps'].delays == [0.25]


def test_resource_exhausted_exhaustion_books_the_legacy_fault(monkeypatch):
    fault = ResourceExhausted('burst')
    run = run_lane(monkeypatch, ScriptedPersist([fault] * 3, default=fault))
    assert run['results'] == [] and run['meta']['failures'] == [('a', type(fault).__name__)]


def test_resource_exhausted_strike_logs_its_exception_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([ResourceExhausted('burst')], default='OK'))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits and 'exception_type=ResourceExhausted' in waits[0]


def test_not_found_strike_recovers_with_the_documented_first_wait(monkeypatch):
    run = run_lane(
        monkeypatch,
        script_for(1, final='OK', fault=None) if False else ScriptedPersist([NotFound('burst')], default='OK'),
    )
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['sleeps'].delays == [0.25]


def test_not_found_exhaustion_books_the_legacy_fault(monkeypatch):
    fault = NotFound('burst')
    run = run_lane(monkeypatch, ScriptedPersist([fault] * 3, default=fault))
    assert run['results'] == [] and run['meta']['failures'] == [('a', type(fault).__name__)]


def test_not_found_strike_logs_its_exception_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([NotFound('burst')], default='OK'))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits and 'exception_type=NotFound' in waits[0]


def test_conflict_strike_recovers_with_the_documented_first_wait(monkeypatch):
    run = run_lane(
        monkeypatch,
        script_for(1, final='OK', fault=None) if False else ScriptedPersist([Conflict('burst')], default='OK'),
    )
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['sleeps'].delays == [0.25]


def test_conflict_exhaustion_books_the_legacy_fault(monkeypatch):
    fault = Conflict('burst')
    run = run_lane(monkeypatch, ScriptedPersist([fault] * 3, default=fault))
    assert run['results'] == [] and run['meta']['failures'] == [('a', type(fault).__name__)]


def test_conflict_strike_logs_its_exception_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([Conflict('burst')], default='OK'))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits and 'exception_type=Conflict' in waits[0]


def test_aborted_strike_recovers_with_the_documented_first_wait(monkeypatch):
    run = run_lane(
        monkeypatch,
        script_for(1, final='OK', fault=None) if False else ScriptedPersist([Aborted('burst')], default='OK'),
    )
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['sleeps'].delays == [0.25]


def test_aborted_exhaustion_books_the_legacy_fault(monkeypatch):
    fault = Aborted('burst')
    run = run_lane(monkeypatch, ScriptedPersist([fault] * 3, default=fault))
    assert run['results'] == [] and run['meta']['failures'] == [('a', type(fault).__name__)]


def test_aborted_strike_logs_its_exception_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([Aborted('burst')], default='OK'))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits and 'exception_type=Aborted' in waits[0]


def test_cancelled_strike_recovers_with_the_documented_first_wait(monkeypatch):
    run = run_lane(
        monkeypatch,
        script_for(1, final='OK', fault=None) if False else ScriptedPersist([Cancelled('burst')], default='OK'),
    )
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['sleeps'].delays == [0.25]


def test_cancelled_exhaustion_books_the_legacy_fault(monkeypatch):
    fault = Cancelled('burst')
    run = run_lane(monkeypatch, ScriptedPersist([fault] * 3, default=fault))
    assert run['results'] == [] and run['meta']['failures'] == [('a', type(fault).__name__)]


def test_cancelled_strike_logs_its_exception_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([Cancelled('burst')], default='OK'))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits and 'exception_type=Cancelled' in waits[0]


def test_failed_precondition_strike_recovers_with_the_documented_first_wait(monkeypatch):
    run = run_lane(
        monkeypatch,
        (
            script_for(1, final='OK', fault=None)
            if False
            else ScriptedPersist([FailedPrecondition('burst')], default='OK')
        ),
    )
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['sleeps'].delays == [0.25]


def test_failed_precondition_exhaustion_books_the_legacy_fault(monkeypatch):
    fault = FailedPrecondition('burst')
    run = run_lane(monkeypatch, ScriptedPersist([fault] * 3, default=fault))
    assert run['results'] == [] and run['meta']['failures'] == [('a', type(fault).__name__)]


def test_failed_precondition_strike_logs_its_exception_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([FailedPrecondition('burst')], default='OK'))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits and 'exception_type=FailedPrecondition' in waits[0]


def test_forbidden_strike_recovers_with_the_documented_first_wait(monkeypatch):
    run = run_lane(
        monkeypatch,
        script_for(1, final='OK', fault=None) if False else ScriptedPersist([Forbidden('burst')], default='OK'),
    )
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['sleeps'].delays == [0.25]


def test_forbidden_exhaustion_books_the_legacy_fault(monkeypatch):
    fault = Forbidden('burst')
    run = run_lane(monkeypatch, ScriptedPersist([fault] * 3, default=fault))
    assert run['results'] == [] and run['meta']['failures'] == [('a', type(fault).__name__)]


def test_forbidden_strike_logs_its_exception_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([Forbidden('burst')], default='OK'))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits and 'exception_type=Forbidden' in waits[0]


def test_precondition_failed_strike_recovers_with_the_documented_first_wait(monkeypatch):
    run = run_lane(
        monkeypatch,
        (
            script_for(1, final='OK', fault=None)
            if False
            else ScriptedPersist([PreconditionFailed('burst')], default='OK')
        ),
    )
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['sleeps'].delays == [0.25]


def test_precondition_failed_exhaustion_books_the_legacy_fault(monkeypatch):
    fault = PreconditionFailed('burst')
    run = run_lane(monkeypatch, ScriptedPersist([fault] * 3, default=fault))
    assert run['results'] == [] and run['meta']['failures'] == [('a', type(fault).__name__)]


def test_precondition_failed_strike_logs_its_exception_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([PreconditionFailed('burst')], default='OK'))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits and 'exception_type=PreconditionFailed' in waits[0]


def test_unauthenticated_strike_recovers_with_the_documented_first_wait(monkeypatch):
    run = run_lane(
        monkeypatch,
        script_for(1, final='OK', fault=None) if False else ScriptedPersist([Unauthenticated('burst')], default='OK'),
    )
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['sleeps'].delays == [0.25]


def test_unauthenticated_exhaustion_books_the_legacy_fault(monkeypatch):
    fault = Unauthenticated('burst')
    run = run_lane(monkeypatch, ScriptedPersist([fault] * 3, default=fault))
    assert run['results'] == [] and run['meta']['failures'] == [('a', type(fault).__name__)]


def test_unauthenticated_strike_logs_its_exception_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([Unauthenticated('burst')], default='OK'))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits and 'exception_type=Unauthenticated' in waits[0]


def test_unknown_strike_recovers_with_the_documented_first_wait(monkeypatch):
    run = run_lane(
        monkeypatch,
        script_for(1, final='OK', fault=None) if False else ScriptedPersist([Unknown('burst')], default='OK'),
    )
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['sleeps'].delays == [0.25]


def test_unknown_exhaustion_books_the_legacy_fault(monkeypatch):
    fault = Unknown('burst')
    run = run_lane(monkeypatch, ScriptedPersist([fault] * 3, default=fault))
    assert run['results'] == [] and run['meta']['failures'] == [('a', type(fault).__name__)]


def test_unknown_strike_logs_its_exception_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([Unknown('burst')], default='OK'))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits and 'exception_type=Unknown' in waits[0]


def test_retry_error_strike_recovers_with_the_documented_first_wait(monkeypatch):
    run = run_lane(
        monkeypatch,
        script_for(1, final='OK', fault=None) if False else ScriptedPersist([RetryError('burst', None)], default='OK'),
    )
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['sleeps'].delays == [0.25]


def test_retry_error_exhaustion_books_the_legacy_fault(monkeypatch):
    fault = RetryError('burst', None)
    run = run_lane(monkeypatch, ScriptedPersist([fault] * 3, default=fault))
    assert run['results'] == [] and run['meta']['failures'] == [('a', type(fault).__name__)]


def test_retry_error_strike_logs_its_exception_type(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([RetryError('burst', None)], default='OK'))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits and 'exception_type=RetryError' in waits[0]
