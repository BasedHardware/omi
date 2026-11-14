#!/usr/bin/env python3
"""The worker fault line carries the static raise-site field.

Every unclassified event=batch_worker_failed line now ends with the site= suffix computed
by error_site_field: the closest non-site-packages source file and line, never an
exception message and never payload content. This pins the suffix format, the
message-never-leaks property, and the unchanged shapes of the demoted INFO lines and the
sensor substring prefix.

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


def _fault_line(monkeypatch, caplog, script):
    pin_full_gpu_stages(monkeypatch)
    monkeypatch.setenv(GATE, 'true')
    monkeypatch.setattr(bp.time, 'sleep', SleepRecorder())
    persist = script if isinstance(script, ScriptedPersist) else ScriptedPersist(script)
    worker, meta = build_worker(persist)
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    worker.process_batch([item()])
    errors = [r for r in caplog.records if 'event=batch_worker_failed' in r.getMessage()]
    return errors[0].getMessage() if errors else ''


def _demoted_line(monkeypatch, caplog, script):
    pin_full_gpu_stages(monkeypatch)
    monkeypatch.setenv(GATE, 'true')
    monkeypatch.setattr(bp.time, 'sleep', SleepRecorder())
    persist = script if isinstance(script, ScriptedPersist) else ScriptedPersist(script)
    worker, meta = build_worker(persist)
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    worker.process_batch([item()])
    demoted = [r for r in caplog.records if 'event=batch_validation_disposition' in r.getMessage()]
    return demoted[0].getMessage() if demoted else ''


def test_persist_fault_line_carries_the_site_suffix(monkeypatch, caplog):
    line = _fault_line(monkeypatch, caplog, ScriptedPersist([TimeoutError('burst')], default=TimeoutError('burst')))
    assert 'event=batch_worker_failed error_class=TimeoutError stage=persist' in line
    assert ' site=persist_lane_harness.py:' in line


def test_persist_fault_line_site_is_file_colon_line_only(monkeypatch, caplog):
    line = _fault_line(monkeypatch, caplog, ScriptedPersist([TimeoutError('burst')], default=TimeoutError('burst')))
    site = line.rsplit(' site=', 1)[1]
    assert re.fullmatch(r'[A-Za-z0-9_./-]+\.py:[0-9]+', site)


def test_persist_fault_line_never_carries_the_exception_message(monkeypatch, caplog):
    secret = 'burst-with-uid-abc123-and-payload'
    line = _fault_line(monkeypatch, caplog, ScriptedPersist([InvalidArgument(secret)], default=InvalidArgument(secret)))
    assert secret not in line


def test_fault_line_prefix_stays_sensor_compatible(monkeypatch, caplog):
    line = _fault_line(monkeypatch, caplog, ScriptedPersist([TimeoutError('burst')], default=TimeoutError('burst')))
    assert line.startswith('event=batch_worker_failed error_class=TimeoutError stage=persist segment_id=')


def test_fault_line_reason_stays_unclassified_for_generic_persist_faults(monkeypatch, caplog):
    line = _fault_line(monkeypatch, caplog, ScriptedPersist([TimeoutError('burst')], default=TimeoutError('burst')))
    assert 'reason=unclassified' in line


def test_deterministic_refusal_demotes_to_the_designed_line_without_site(monkeypatch, caplog):
    line = _demoted_line(
        monkeypatch, caplog, ScriptedPersist([InvalidArgument('burst')], default=InvalidArgument('burst'))
    )
    assert (
        'event=batch_validation_disposition outcome=recovery_handoff error_class=InvalidArgument stage=persist' in line
    )
    assert 'reason=persist_payload_invalid' in line
    assert ' site=' not in line


def test_demoted_info_lines_keep_their_exact_shape_without_site(monkeypatch, caplog):
    pin_full_gpu_stages(monkeypatch)
    monkeypatch.setenv(GATE, 'true')
    monkeypatch.setattr(bp.time, 'sleep', SleepRecorder())
    persist = ScriptedPersist([InvalidArgument('burst')], default=InvalidArgument('burst'))
    worker, meta = build_worker(persist)
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    worker.process_batch([replace(item(), shadow=True)])
    shadow_lines = [r.getMessage() for r in caplog.records if 'event=batch_shadow_worker_failure' in r.getMessage()]
    assert shadow_lines == ['event=batch_shadow_worker_failure stage=persist reason=persist_payload_invalid']


def test_recovered_lane_logs_no_worker_failed_line(monkeypatch, caplog):
    pin_full_gpu_stages(monkeypatch)
    monkeypatch.setenv(GATE, 'true')
    monkeypatch.setattr(bp.time, 'sleep', SleepRecorder())
    persist = ScriptedPersist(script_for(1))
    worker, meta = build_worker(persist)
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    worker.process_batch([item()])
    assert not [r for r in caplog.records if 'event=batch_worker_failed' in r.getMessage()]


def test_site_field_is_present_on_valueerror_faults_too(monkeypatch, caplog):
    line = _fault_line(monkeypatch, caplog, ScriptedPersist([ValueError('custody')]))
    assert ' site=persist_lane_harness.py:' in line


def test_error_site_field_names_the_closest_repo_frame():
    try:
        raise InvalidArgument('x')
    except InvalidArgument as error:
        site = bp.error_site_field(error)
    assert site.startswith(' site=test_persist_restrike_site_field.py:')


def test_error_site_field_is_empty_without_a_traceback():
    assert bp.error_site_field(InvalidArgument('x')) == ''


def test_error_site_field_skips_site_packages_frames():
    import yaml

    try:
        yaml.safe_load('\t- x')
    except yaml.YAMLError as error:
        site = bp.error_site_field(error)
    assert site == '' or 'site-packages' not in site


def test_error_site_field_names_the_stdlib_frame_without_site_packages():
    import json

    try:
        json.loads('{')
    except ValueError as error:
        site = bp.error_site_field(error)
    assert site.startswith(' site=') and '.py:' in site


def test_error_site_field_never_carries_the_message():
    secret = 'uid-abc-capture'
    try:
        raise InvalidArgument(secret)
    except InvalidArgument as error:
        site = bp.error_site_field(error)
    assert secret not in site
