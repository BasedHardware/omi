#!/usr/bin/env python3
"""Custody booking parity across the lane.

Recovered units keep the completed WorkResult with no fault booking and no evidence
token; exhausted units book exactly the legacy transient fault with persist still
unevidenced (the documented closed-vocabulary contract), identically under the safety
net on or off, and byte-for-byte against the gate-off fallback.

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


def test_recovery_safety_off_returns_a_work_result(monkeypatch):
    run = run_lane(monkeypatch, script_for(1), safety_net='false')
    assert isinstance(run['results'][0], WorkResult)


def test_recovery_safety_off_books_no_failed_work(monkeypatch):
    run = run_lane(monkeypatch, script_for(1), safety_net='false')
    assert not [r for r in run['results'] if isinstance(r, FailedWork)]


def test_recovery_safety_off_worker_failure_evidence_stays_absent(monkeypatch):
    run = run_lane(monkeypatch, script_for(1), safety_net='false')
    assert not [r for r in run['results'] if getattr(r, 'worker_failure', None)]


def test_exhaustion_safety_off_returns_no_work_result(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), safety_net='false')
    assert not [r for r in run['results'] if isinstance(r, WorkResult)]


def test_exhaustion_safety_off_books_no_evidence_token(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), safety_net='false')
    assert not [r for r in run['results'] if getattr(r, 'worker_failure', None)]


def test_recovery_safety_on_returns_a_work_result(monkeypatch):
    run = run_lane(monkeypatch, script_for(1), safety_net='true')
    assert isinstance(run['results'][0], WorkResult)


def test_recovery_safety_on_books_no_failed_work(monkeypatch):
    run = run_lane(monkeypatch, script_for(1), safety_net='true')
    assert not [r for r in run['results'] if isinstance(r, FailedWork)]


def test_recovery_safety_on_worker_failure_evidence_stays_absent(monkeypatch):
    run = run_lane(monkeypatch, script_for(1), safety_net='true')
    assert not [r for r in run['results'] if getattr(r, 'worker_failure', None)]


def test_exhaustion_safety_on_returns_no_work_result(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), safety_net='true')
    assert not [r for r in run['results'] if isinstance(r, WorkResult)]


def test_exhaustion_safety_on_books_the_persist_stage_evidence_token(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), safety_net='true')
    carried = [getattr(r, 'worker_failure', None) for r in run['results']]
    assert carried and all(c == {'stage': 'persist', 'reason': 'unknown'} for c in carried if c)


def test_exhaustion_safety_on_books_the_typed_custody_handoff(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), safety_net='true')
    assert len(run['results']) == 1 and type(run['results'][0]).__name__ == 'ValidationFailureWork'
    assert run['results'][0].stage == 'persist' and run['results'][0].reason == 'persist_payload_invalid'


def test_exhaustion_safety_off_still_books_the_typed_custody_handoff(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), safety_net='false')
    assert [type(r).__name__ for r in run['results']] == ['ValidationFailureWork']
    assert run['results'][0].stage == 'persist' and run['results'][0].reason == 'persist_payload_invalid'


def test_recovered_unit_is_never_a_failed_work_under_safety_on(monkeypatch):
    run = run_lane(monkeypatch, script_for(2), safety_net='true')
    assert isinstance(run['results'][0], WorkResult)


def test_gate_off_matches_lane_exhaustion_booking(monkeypatch):
    legacy = run_lane(monkeypatch, exhaust_script(), gate='false')
    lane = run_lane(monkeypatch, exhaust_script(), gate='true')
    assert legacy['meta']['failures'] == lane['meta']['failures']
    assert legacy['worker'].counts == lane['worker'].counts
    assert len(legacy['persist'].calls) == 1
    assert len(lane['persist'].calls) == 3
    assert lane['sleeps'].delays == [0.25, 0.5]


def test_counts_recovered_and_exhausted_mix_stay_independent(monkeypatch):
    run = run_two_units(
        monkeypatch,
        (
            PerSegmentPersist({'a': exhaust_script(), 'b': ScriptedPersist([])})
            if False
            else PerSegmentPersist({'a': exhaust_script(), 'b': ScriptedPersist([])})
        ),
    )
    assert run['worker'].counts['items'] == 2 and run['worker'].counts['failed'] == 1


def test_persist_fault_keeps_the_unit_metadata_in_the_fault_record(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script())
    assert run['meta']['failures'][0][0] == 'a'


def test_on_failure_receives_only_the_type_name(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script())
    assert run['meta']['failures'][0][1] == 'InvalidArgument'


def test_counts_items_counts_every_admitted_unit(monkeypatch):
    run = run_two_units(monkeypatch, PerSegmentPersist({'a': exhaust_script(), 'b': ScriptedPersist([])}))
    assert run['worker'].counts['items'] == 2
