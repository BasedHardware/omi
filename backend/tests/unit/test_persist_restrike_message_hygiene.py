#!/usr/bin/env python3
"""The lane and the fault line never leak exception messages.

Every hostile message shape a storage fault could carry — owner keys, segment payload
shapes, gs:// URIs with generations, JSON word payloads, bearer tokens — is absent from
the restrike lines and the terminal fault line; the failure callback receives only the
closed type name.

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


def test_message_00_uid_abc123_capture_token_never_reaches_the_fault_line(monkeypatch):
    secret = 'uid-abc123-capture-token'
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument(secret)], default=InvalidArgument(secret)))
    assert [type(r).__name__ for r in run['results']] == ['ValidationFailureWork']
    import logging

    captured = []
    handler = logging.Handler()
    handler.emit = lambda record: captured.append(record.getMessage())
    logging.getLogger(WORKER_LOGGER).addHandler(handler)
    worker, meta = build_worker(ScriptedPersist([InvalidArgument(secret)], default=InvalidArgument(secret)))
    worker.process_batch([item()])
    for message in captured:
        assert secret not in message


def test_message_00_uid_abc123_capture_token_never_reaches_the_wait_line(monkeypatch):
    secret = 'uid-abc123-capture-token'
    import logging

    captured = []
    handler = logging.Handler()
    handler.emit = lambda record: captured.append(record.getMessage())
    logging.getLogger(WORKER_LOGGER).addHandler(handler)
    run_lane(monkeypatch, ScriptedPersist([InvalidArgument(secret)], default='OK'))
    for message in captured:
        assert secret not in message


def test_message_01_segment_9f8e8d_payload_s_never_reaches_the_fault_line(monkeypatch):
    secret = 'segment-9f8e8d-payload-shape'
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument(secret)], default=InvalidArgument(secret)))
    assert [type(r).__name__ for r in run['results']] == ['ValidationFailureWork']
    import logging

    captured = []
    handler = logging.Handler()
    handler.emit = lambda record: captured.append(record.getMessage())
    logging.getLogger(WORKER_LOGGER).addHandler(handler)
    worker, meta = build_worker(ScriptedPersist([InvalidArgument(secret)], default=InvalidArgument(secret)))
    worker.process_batch([item()])
    for message in captured:
        assert secret not in message


def test_message_01_segment_9f8e8d_payload_s_never_reaches_the_wait_line(monkeypatch):
    secret = 'segment-9f8e8d-payload-shape'
    import logging

    captured = []
    handler = logging.Handler()
    handler.emit = lambda record: captured.append(record.getMessage())
    logging.getLogger(WORKER_LOGGER).addHandler(handler)
    run_lane(monkeypatch, ScriptedPersist([InvalidArgument(secret)], default='OK'))
    for message in captured:
        assert secret not in message


def test_message_02_owner_key_material_leak_never_reaches_the_fault_line(monkeypatch):
    secret = 'owner-key-material-leak'
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument(secret)], default=InvalidArgument(secret)))
    assert [type(r).__name__ for r in run['results']] == ['ValidationFailureWork']
    import logging

    captured = []
    handler = logging.Handler()
    handler.emit = lambda record: captured.append(record.getMessage())
    logging.getLogger(WORKER_LOGGER).addHandler(handler)
    worker, meta = build_worker(ScriptedPersist([InvalidArgument(secret)], default=InvalidArgument(secret)))
    worker.process_batch([item()])
    for message in captured:
        assert secret not in message


def test_message_02_owner_key_material_leak_never_reaches_the_wait_line(monkeypatch):
    secret = 'owner-key-material-leak'
    import logging

    captured = []
    handler = logging.Handler()
    handler.emit = lambda record: captured.append(record.getMessage())
    logging.getLogger(WORKER_LOGGER).addHandler(handler)
    run_lane(monkeypatch, ScriptedPersist([InvalidArgument(secret)], default='OK'))
    for message in captured:
        assert secret not in message


def test_message_03_gs___bucket_private_path_never_reaches_the_fault_line(monkeypatch):
    secret = 'gs://bucket/private/path/object.enc#123'
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument(secret)], default=InvalidArgument(secret)))
    assert [type(r).__name__ for r in run['results']] == ['ValidationFailureWork']
    import logging

    captured = []
    handler = logging.Handler()
    handler.emit = lambda record: captured.append(record.getMessage())
    logging.getLogger(WORKER_LOGGER).addHandler(handler)
    worker, meta = build_worker(ScriptedPersist([InvalidArgument(secret)], default=InvalidArgument(secret)))
    worker.process_batch([item()])
    for message in captured:
        assert secret not in message


def test_message_03_gs___bucket_private_path_never_reaches_the_wait_line(monkeypatch):
    secret = 'gs://bucket/private/path/object.enc#123'
    import logging

    captured = []
    handler = logging.Handler()
    handler.emit = lambda record: captured.append(record.getMessage())
    logging.getLogger(WORKER_LOGGER).addHandler(handler)
    run_lane(monkeypatch, ScriptedPersist([InvalidArgument(secret)], default='OK'))
    for message in captured:
        assert secret not in message


def test_message_04___words_____secret____never_reaches_the_fault_line(monkeypatch):
    secret = '{"words": ["secret"]}'
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument(secret)], default=InvalidArgument(secret)))
    assert [type(r).__name__ for r in run['results']] == ['ValidationFailureWork']
    import logging

    captured = []
    handler = logging.Handler()
    handler.emit = lambda record: captured.append(record.getMessage())
    logging.getLogger(WORKER_LOGGER).addHandler(handler)
    worker, meta = build_worker(ScriptedPersist([InvalidArgument(secret)], default=InvalidArgument(secret)))
    worker.process_batch([item()])
    for message in captured:
        assert secret not in message


def test_message_04___words_____secret____never_reaches_the_wait_line(monkeypatch):
    secret = '{"words": ["secret"]}'
    import logging

    captured = []
    handler = logging.Handler()
    handler.emit = lambda record: captured.append(record.getMessage())
    logging.getLogger(WORKER_LOGGER).addHandler(handler)
    run_lane(monkeypatch, ScriptedPersist([InvalidArgument(secret)], default='OK'))
    for message in captured:
        assert secret not in message


def test_message_05_Bearer_eyJhbGciOi_payloa_never_reaches_the_fault_line(monkeypatch):
    secret = 'Bearer eyJhbGciOi.payload.sig'
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument(secret)], default=InvalidArgument(secret)))
    assert [type(r).__name__ for r in run['results']] == ['ValidationFailureWork']
    import logging

    captured = []
    handler = logging.Handler()
    handler.emit = lambda record: captured.append(record.getMessage())
    logging.getLogger(WORKER_LOGGER).addHandler(handler)
    worker, meta = build_worker(ScriptedPersist([InvalidArgument(secret)], default=InvalidArgument(secret)))
    worker.process_batch([item()])
    for message in captured:
        assert secret not in message


def test_message_05_Bearer_eyJhbGciOi_payloa_never_reaches_the_wait_line(monkeypatch):
    secret = 'Bearer eyJhbGciOi.payload.sig'
    import logging

    captured = []
    handler = logging.Handler()
    handler.emit = lambda record: captured.append(record.getMessage())
    logging.getLogger(WORKER_LOGGER).addHandler(handler)
    run_lane(monkeypatch, ScriptedPersist([InvalidArgument(secret)], default='OK'))
    for message in captured:
        assert secret not in message


def test_failure_callback_receives_only_the_type_name(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script())
    assert run['meta']['failures'][0][1] == 'InvalidArgument'
