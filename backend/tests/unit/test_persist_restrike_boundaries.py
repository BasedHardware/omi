#!/usr/bin/env python3
"""Lane boundary grid.

The cap-1 recovery, cap exhaustion, attempt numbering, delay literals, landing-strike
committed line and the worker counters are pinned at their exact boundary values.

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


def test_cap_minus_one_strikes_recover(monkeypatch):
    run = run_lane(monkeypatch, script_for(2))
    assert run['results'] and run['results'][0].result_uri == 'OK'


def test_cap_strikes_exactly_exhaust(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script())
    assert run['results'] == [] and run['sleeps'].delays == [0.25, 0.5]


def test_strike_delays_never_exceed_the_cap(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script())
    assert all(delay <= bp.PERSIST_RESTRIKE_MAX_SECONDS for delay in run['sleeps'].delays)


def test_attempt_numbering_is_one_based_in_the_wait_lines(monkeypatch, caplog):
    import logging

    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, script_for(2))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert 'attempt=1' in waits[0] and 'attempt=2' in waits[1]


def test_committed_line_numbers_the_landing_strike(monkeypatch, caplog):
    import logging

    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, script_for(2))
    committed = [r.getMessage() for r in caplog.records if 'outcome=restrike_committed' in r.getMessage()]
    assert committed == ['event=batch_persist outcome=restrike_committed attempt=3']


def test_two_faults_then_success_is_the_last_recoverable_shape(monkeypatch):
    run = run_lane(monkeypatch, script_for(2))
    assert run['results'] and len(run['persist'].calls) == 3


def test_serial_sleep_records_exact_delays(monkeypatch):
    run = run_lane(monkeypatch, script_for(2))
    assert run['sleeps'].delays == [0.25, 0.5]


def test_worker_counts_items_stays_one_after_recovery(monkeypatch):
    run = run_lane(monkeypatch, script_for(1))
    assert run['worker'].counts == dict(items=1, reused_live=0, silence=0, failed=0, left_context=0)


def test_worker_counts_failed_is_one_after_exhaustion(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script())
    assert run['worker'].counts['failed'] == 1


def test_lane_constants_are_importable_and_typed():
    assert isinstance(bp.PERSIST_RESTRIKE_BASE_SECONDS, float)
    assert isinstance(bp.PERSIST_RESTRIKE_MAX_SECONDS, float)
    assert bp.PERSIST_RESTRIKE_MAX_ATTEMPTS == 3


def test_classifier_accepts_base_exception_subclass_boundary():
    assert bp.persist_loss_is_restrikeable(InvalidArgument('x')) is True
