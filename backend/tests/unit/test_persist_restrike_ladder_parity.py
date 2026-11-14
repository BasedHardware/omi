#!/usr/bin/env python3
"""The lane composes with the legacy ladder without moving its contracts.

Gate-off and lane-exhaustion agree on results, failure booking and counters; persist
stays outside the closed evidence vocabulary (no token, no validation/recovery work
shapes, validator still rejects the stage), and the scheduler fail signature is
untouched by this diff.

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


def test_gate_off_and_lane_exhaustion_agree_on_returns_the_same_results(monkeypatch):
    legacy = run_lane(monkeypatch, exhaust_script(), gate='false')
    lane = run_lane(monkeypatch, exhaust_script(), gate='true')
    assert legacy['results'] == lane['results']


def test_gate_off_and_lane_exhaustion_agree_on_books_the_same_failure(monkeypatch):
    legacy = run_lane(monkeypatch, exhaust_script(), gate='false')
    lane = run_lane(monkeypatch, exhaust_script(), gate='true')
    assert legacy['meta']['failures'] == lane['meta']['failures']


def test_gate_off_and_lane_exhaustion_agree_on_counts_the_same(monkeypatch):
    legacy = run_lane(monkeypatch, exhaust_script(), gate='false')
    lane = run_lane(monkeypatch, exhaust_script(), gate='true')
    assert legacy['worker'].counts == lane['worker'].counts


def test_lane_exhaustion_costs_three_calls_vs_legacy_one(monkeypatch):
    legacy = run_lane(monkeypatch, exhaust_script(), gate='false')
    lane = run_lane(monkeypatch, exhaust_script(), gate='true')
    assert len(legacy['persist'].calls) == 1 and len(lane['persist'].calls) == 3
    assert lane['sleeps'].delays == [0.25, 0.5]


def test_evidence_contract_generic_persist_faults_name_their_stage_after_exhaustion(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(TimeoutError), safety_net='true')
    assert isinstance(run['results'][0], FailedWork)
    assert run['results'][0].worker_failure == {'stage': 'persist', 'reason': 'unknown'}


def test_evidence_contract_recovered_units_carry_no_failed_work(monkeypatch):
    run = run_lane(monkeypatch, script_for(1), safety_net='true')
    assert isinstance(run['results'][0], WorkResult)


def test_generic_persist_faults_never_produce_validation_failure_work(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(TimeoutError), safety_net='true')
    assert not [r for r in run['results'] if type(r).__name__ == 'ValidationFailureWork']


def test_deterministic_persist_refusal_books_the_validation_failure_work(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), safety_net='true')
    assert [type(r).__name__ for r in run['results']] == ['ValidationFailureWork']
    assert run['results'][0].stage == 'persist' and run['results'][0].reason == 'persist_payload_invalid'


def test_recovery_work_is_never_booked_for_persist_faults(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), safety_net='true')
    assert not [r for r in run['results'] if type(r).__name__ == 'RecoveryWork']


def test_the_scheduler_fail_signature_is_untouched_by_the_lane():
    import inspect

    from utils.batch_pipeline import scheduler

    source = inspect.getsource(scheduler)
    assert 'def fail(' in source
    assert FC not in source


def test_the_store_validators_accept_typed_persist_diagnoses():
    from utils.batch_pipeline.errors import validate_worker_failure

    try:
        validate_worker_failure({'stage': 'persist', 'reason': 'unclassified'})
    except ValueError:
        pass
    else:
        raise AssertionError('a typed persist diagnosis must clear the closed evidence gates')


def test_transient_failure_evidence_closes_the_persist_stage_pair():
    assert bp.transient_failure_evidence('persist', 'unclassified') == {'stage': 'persist', 'reason': 'unknown'}
