#!/usr/bin/env python3
"""Kill-switch and registration grid for BATCH_PIPELINE_PERSIST_RESTRIKE_ENABLED.

The gate is read at call time through the batch config module, defaults on, tolerates env
noise like every sibling batch kill switch, and is registered in the pipeline flag budget
under the batch record lane owner. With the gate off the persist call runs once and the
legacy fault booking is byte-for-byte.

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

from dataclasses import replace

from config.batch_pipeline import persist_restrike_enabled
from diarizer import batch_pipeline as bp
from utils.batch_pipeline.contracts import FailedWork, WorkResult
from tests.unit.persist_lane_harness import (  # noqa: F401
    GATE,
    PerSegmentPersist,
    RecordingTimings,
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


@pytest.fixture(autouse=True)
def _lane_env(monkeypatch):
    pin_full_gpu_stages(monkeypatch)


DOC_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'docs', 'persist-restrike-lane.md')

BUDGET_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'flag_budget.json')


def test_gate_env_true_reads_True(monkeypatch):
    monkeypatch.setenv(GATE, 'true')
    assert persist_restrike_enabled() is True


def test_gate_env_false_reads_False(monkeypatch):
    monkeypatch.setenv(GATE, 'false')
    assert persist_restrike_enabled() is False


def test_gate_env_False_reads_False(monkeypatch):
    monkeypatch.setenv(GATE, 'False')
    assert persist_restrike_enabled() is False


def test_gate_env_FALSE_reads_False(monkeypatch):
    monkeypatch.setenv(GATE, 'FALSE')
    assert persist_restrike_enabled() is False


def test_gate_env_0_reads_True(monkeypatch):
    monkeypatch.setenv(GATE, '0')
    assert persist_restrike_enabled() is True


def test_gate_env_1_reads_True(monkeypatch):
    monkeypatch.setenv(GATE, '1')
    assert persist_restrike_enabled() is True


def test_gate_env_yes_reads_True(monkeypatch):
    monkeypatch.setenv(GATE, 'yes')
    assert persist_restrike_enabled() is True


def test_gate_env_no_reads_True(monkeypatch):
    monkeypatch.setenv(GATE, 'no')
    assert persist_restrike_enabled() is True


def test_gate_env_empty_reads_True(monkeypatch):
    monkeypatch.setenv(GATE, '')
    assert persist_restrike_enabled() is True


def test_gate_env__true__reads_True(monkeypatch):
    monkeypatch.setenv(GATE, ' true ')
    assert persist_restrike_enabled() is True


def test_gate_env__false__reads_False(monkeypatch):
    monkeypatch.setenv(GATE, ' false ')
    assert persist_restrike_enabled() is False


def test_gate_env_off_reads_True(monkeypatch):
    monkeypatch.setenv(GATE, 'off')
    assert persist_restrike_enabled() is True


def test_gate_env_on_reads_True(monkeypatch):
    monkeypatch.setenv(GATE, 'on')
    assert persist_restrike_enabled() is True


def test_gate_env_TRUE_reads_True(monkeypatch):
    monkeypatch.setenv(GATE, 'TRUE')
    assert persist_restrike_enabled() is True


def test_gate_defaults_on_when_env_is_unset(monkeypatch):
    monkeypatch.delenv(GATE, raising=False)
    assert persist_restrike_enabled() is True


def test_gate_is_read_at_call_time(monkeypatch):
    monkeypatch.setenv(GATE, 'true')
    assert persist_restrike_enabled() is True
    monkeypatch.setenv(GATE, 'false')
    assert persist_restrike_enabled() is False
    monkeypatch.setenv(GATE, 'true')
    assert persist_restrike_enabled() is True


def test_gate_docstring_names_the_kill_switch():
    import inspect

    source = inspect.getsource(persist_restrike_enabled)
    assert "'BATCH_PIPELINE_PERSIST_RESTRIKE_ENABLED'" in source


def test_gate_docstring_carries_the_failure_class():
    import inspect

    assert 'Failure-Class: ' + FC in inspect.getsource(persist_restrike_enabled)


def test_gate_docstring_states_the_default():
    import inspect

    assert 'default; false is the kill switch' in inspect.getsource(persist_restrike_enabled)


def test_gate_docstring_names_the_sensor_family():
    import inspect

    assert 'error_class=InvalidArgument stage=persist' in inspect.getsource(persist_restrike_enabled)


def test_gate_docstring_names_the_schedule():
    import inspect

    source = inspect.getsource(persist_restrike_enabled)
    assert '0.25s' in source and '2.0s' in source and 'three' in source


def test_gate_off_faults_immediately(monkeypatch):
    run = run_lane(monkeypatch, script_for(2), gate='false')
    assert run['results'] == [] and len(run['persist'].calls) == 1
    assert run['sleeps'].delays == []


def test_gate_off_still_books_the_legacy_fault(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), gate='false')
    assert run['meta']['failures'] == [('a', 'InvalidArgument')]


def test_gate_on_recovers(monkeypatch):
    run = run_lane(monkeypatch, script_for(1), gate='true')
    assert run['results'] and run['results'][0].result_uri == 'OK'


def test_kill_switch_doc_names_the_variable(monkeypatch):
    assert 'BATCH_PIPELINE_PERSIST_RESTRIKE_ENABLED=false' in open(DOC_PATH).read()


def test_registry_registers_the_gate():
    budget = json.load(open(BUDGET_PATH))
    assert GATE in budget['names']


def test_registry_entry_carries_the_lane_owner():
    budget = json.load(open(BUDGET_PATH))
    assert budget['names'][GATE]['owner'] == 'batch record lane / rollout lead'


def test_registry_entry_review_date_is_in_the_future():
    budget = json.load(open(BUDGET_PATH))
    assert datetime.date.fromisoformat(budget['names'][GATE]['review_by']) > datetime.date.today()


def test_registry_count_covers_every_name():
    budget = json.load(open(BUDGET_PATH))
    assert budget['count'] == len(budget['names'])
