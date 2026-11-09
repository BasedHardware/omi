#!/usr/bin/env python3
"""IO-executor call-site matrix for the persist re-strike lane.

The overlap path (io_concurrency > 1) recovers with the same schedule, exhausts into the
same booking, keeps the GPU chain at one pass, and preserves payload and timing-span
identity; the serial rollback path is pinned as the no-executor comparator.

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


def test_io_path_recovers_after_0_strikes_with_the_documented_schedule(monkeypatch):
    run = run_lane(monkeypatch, script_for(0), io_concurrency=2)
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['worker']._io is not None
    assert run['sleeps'].delays == []


def test_io_path_recovers_after_1_strikes_with_the_documented_schedule(monkeypatch):
    run = run_lane(monkeypatch, script_for(1), io_concurrency=2)
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['worker']._io is not None
    assert run['sleeps'].delays == [0.25]


def test_io_path_recovers_after_2_strikes_with_the_documented_schedule(monkeypatch):
    run = run_lane(monkeypatch, script_for(2), io_concurrency=2)
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['worker']._io is not None
    assert run['sleeps'].delays == [0.25, 0.5]


def test_io_path_exhaustion_books_the_legacy_fault(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), io_concurrency=2)
    assert run['results'] == [] and run['meta']['failures'] == [('a', 'InvalidArgument')]


def test_io_path_keeps_the_gpu_chain_at_one_pass(monkeypatch):
    run = run_lane(monkeypatch, script_for(1), io_concurrency=2)
    assert run['meta']['decoded'] == ['a'] and run['meta']['diarized'] == [32000]


def test_io_path_payload_identity_across_strikes(monkeypatch):
    run = run_lane(monkeypatch, script_for(1), io_concurrency=2)
    payloads = run['persist'].payloads
    assert payloads[0] is payloads[1]


def test_io_path_timing_span_per_strike(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(monkeypatch, script_for(1), timings=timings, io_concurrency=2)
    assert timings.spans.count('persist') == 2


def test_io_concurrency_one_has_no_executor(monkeypatch):
    run = run_lane(monkeypatch, script_for(1), io_concurrency=1)
    assert run['worker']._io is None
