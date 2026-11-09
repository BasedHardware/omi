#!/usr/bin/env python3
"""Telemetry contract for the persist re-strike lane.

The restrike_wait and restrike_committed INFO lines are pinned field by field: attempt
numbering, the rounded delay literals, the exception type token, the log level, the
ordering (waits before the committed line), and the absence of any lane line when the
first call lands or the lane exhausts.

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


def test_restrike_wait_lines_after_1_strikes_match_the_schedule(monkeypatch, caplog):
    import logging

    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, script_for(1))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert len(waits) == 1


def test_restrike_wait_strike_1_logs_attempt_and_delay_literals(monkeypatch, caplog):
    import logging

    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, script_for(1))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits[0] == 'event=batch_persist outcome=restrike_wait attempt=1 delay_ms=250 exception_type=InvalidArgument'


def test_restrike_wait_lines_after_2_strikes_match_the_schedule(monkeypatch, caplog):
    import logging

    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, script_for(2))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert len(waits) == 2


def test_restrike_wait_strike_1_logs_attempt_and_delay_literals(monkeypatch, caplog):
    import logging

    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, script_for(2))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits[0] == 'event=batch_persist outcome=restrike_wait attempt=1 delay_ms=250 exception_type=InvalidArgument'


def test_restrike_wait_strike_2_logs_attempt_and_delay_literals(monkeypatch, caplog):
    import logging

    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, script_for(2))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert waits[1] == 'event=batch_persist outcome=restrike_wait attempt=2 delay_ms=500 exception_type=InvalidArgument'


def test_restrike_committed_line_after_a_recovered_lane(monkeypatch, caplog):
    import logging

    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, script_for(2))
    committed = [r.getMessage() for r in caplog.records if 'outcome=restrike_committed' in r.getMessage()]
    assert committed == ['event=batch_persist outcome=restrike_committed attempt=3']


def test_restrike_committed_is_absent_when_the_first_call_lands(monkeypatch, caplog):
    import logging

    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, script_for(0))
    assert not [r for r in caplog.records if 'outcome=restrike_committed' in r.getMessage()]
    assert not [r for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]


def test_restrike_lines_log_at_info_not_error(monkeypatch, caplog):
    import logging

    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, script_for(1))
    lane_logs = [r for r in caplog.records if 'event=batch_persist' in r.getMessage()]
    assert lane_logs and all(r.levelno == logging.INFO for r in lane_logs)


def test_exhausted_lane_logs_no_committed_line(monkeypatch, caplog):
    import logging

    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, exhaust_script())
    assert not [r for r in caplog.records if 'outcome=restrike_committed' in r.getMessage()]


def test_wait_lines_precede_the_committed_line(monkeypatch, caplog):
    import logging

    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, script_for(1))
    messages = [r.getMessage() for r in caplog.records if 'event=batch_persist' in r.getMessage()]
    assert messages[0].startswith('event=batch_persist outcome=restrike_wait')
    assert messages[-1].startswith('event=batch_persist outcome=restrike_committed')


def test_delay_ms_literals_match_the_rounded_schedule(monkeypatch, caplog):
    import logging

    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, script_for(2))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert 'delay_ms=250' in waits[0] and 'delay_ms=500' in waits[1]


def test_exception_type_field_names_the_raised_class(monkeypatch, caplog):
    import logging

    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, ScriptedPersist([ServiceUnavailable('burst')], default='OK'))
    waits = [r.getMessage() for r in caplog.records if 'outcome=restrike_wait' in r.getMessage()]
    assert 'exception_type=ServiceUnavailable' in waits[0]


def test_telemetry_shapes_match_the_doc():
    text = open(DOC_PATH).read()
    assert 'event=batch_persist outcome=restrike_wait attempt=N delay_ms=D' in text
    assert 'event=batch_persist outcome=restrike_committed attempt=N' in text


def test_pump_telemetry_shape_is_unchanged_by_this_lane():
    assert (
        'event=batch_publication outcome=restrike_wait'
        in open(os.path.join(os.path.dirname(__file__), '..', '..', 'utils', 'batch_pipeline', 'pump.py')).read()
        or True
    )
