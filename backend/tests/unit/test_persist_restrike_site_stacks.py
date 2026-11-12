#!/usr/bin/env python3
"""The site= suffix across exception stack shapes.

Typed local faults, raised-and-reraised chains, timeout and permission faults all carry
the static raise-site suffix exactly once at the end of the line, while the demoted INFO
lane lines keep their site-free shapes.

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


def _line_for(monkeypatch, caplog, script):
    pin_full_gpu_stages(monkeypatch)
    monkeypatch.setenv(GATE, 'true')
    monkeypatch.setattr(bp.time, 'sleep', SleepRecorder())
    persist = (
        script
        if isinstance(script, (ScriptedPersist, PerSegmentPersist))
        else (script if callable(script) and not isinstance(script, (list, tuple)) else ScriptedPersist(script))
    )
    worker, meta = build_worker(persist)
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    worker.process_batch([item()])
    errors = [r for r in caplog.records if 'event=batch_worker_failed' in r.getMessage()]
    return errors[0].getMessage() if errors else ''


class LocalFault(ValueError):
    """A repo-local typed fault raised from the harness raise site."""


def test_site_field_survives_a_typed_local_fault(monkeypatch, caplog):
    line = _line_for(monkeypatch, caplog, ScriptedPersist([LocalFault('custody')]))
    assert 'error_class=LocalFault' in line
    assert ' site=persist_lane_harness.py:' in line


def test_site_field_survives_a_raised_and_reraised_chain(monkeypatch, caplog):
    inner = ScriptedPersist([InvalidArgument('burst')])

    def chained(work, payload):
        try:
            return inner(work, payload)
        except InvalidArgument as cause:
            raise LookupError('wrapped transport loss') from cause

    line = _line_for(monkeypatch, caplog, chained)
    # The site names the raise frame of the LAST exception raised through the boundary.
    assert 'error_class=LookupError' in line
    assert ' site=test_persist_restrike_site_stacks.py:' in line


def test_site_field_for_a_timeout_fault(monkeypatch, caplog):
    # A timeout now strikes, so the fail line requires the fault to exhaust
    # the lane budget; the surviving fail line keeps the static site suffix.
    fault = TimeoutError('deadline')
    line = _line_for(monkeypatch, caplog, ScriptedPersist([fault] * 3, default=fault))
    assert 'error_class=TimeoutError' in line
    assert ' site=persist_lane_harness.py:' in line


def test_site_field_for_a_permission_fault(monkeypatch, caplog):
    line = _line_for(monkeypatch, caplog, ScriptedPersist([PermissionError('fence')]))
    assert 'error_class=PermissionError' in line
    assert ' site=persist_lane_harness.py:' in line


def test_site_field_appears_exactly_once(monkeypatch, caplog):
    line = _line_for(monkeypatch, caplog, ScriptedPersist([InvalidArgument('burst')], default=InvalidArgument('burst')))
    assert line.count(' site=') == 1


def test_site_field_ends_the_line(monkeypatch, caplog):
    line = _line_for(monkeypatch, caplog, ScriptedPersist([InvalidArgument('burst')], default=InvalidArgument('burst')))
    assert re.search(r'site=[A-Za-z0-9_./-]+\.py:[0-9]+$', line)


def test_site_field_absent_from_info_demotion_lines(monkeypatch, caplog):
    pin_full_gpu_stages(monkeypatch)
    monkeypatch.setenv(GATE, 'true')
    monkeypatch.setattr(bp.time, 'sleep', SleepRecorder())
    persist = ScriptedPersist(script_for(1))
    worker, meta = build_worker(persist)
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    worker.process_batch([item()])
    info_lines = [r.getMessage() for r in caplog.records if 'event=batch_persist' in r.getMessage()]
    assert info_lines and all(' site=' not in m for m in info_lines)
