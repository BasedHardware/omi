#!/usr/bin/env python3
"""Unit-shape matrix for the persist re-strike lane.

Recovery and exhaustion across the real unit mix the production family books: ordinary,
long, short, shadow, language-receipt and capture-kind units plus silent units, pinning
the recovered URI or the legacy booking and the payload identity per shape.

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


def test_two_second_unit_recovers_through_the_lane(monkeypatch):
    unit = item()
    run = run_lane(monkeypatch, script_for(1), unit=unit)
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['sleeps'].delays == [0.25]


def test_two_second_unit_exhaustion_books_the_typed_custody_handoff(monkeypatch):
    unit = item()
    run = run_lane(monkeypatch, exhaust_script(), unit=unit)
    assert [type(r).__name__ for r in run['results']] == ['ValidationFailureWork']
    assert run['results'][0].stage == 'persist' and run['results'][0].reason == 'persist_payload_invalid'
    assert run['meta']['failures'] == [('a', 'InvalidArgument')]


def test_thirty_second_unit_recovers_through_the_lane(monkeypatch):
    unit = item('a', 30)
    run = run_lane(monkeypatch, script_for(1), unit=unit)
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['sleeps'].delays == [0.25]


def test_thirty_second_unit_exhaustion_books_the_typed_custody_handoff(monkeypatch):
    unit = item('a', 30)
    run = run_lane(monkeypatch, exhaust_script(), unit=unit)
    assert [type(r).__name__ for r in run['results']] == ['ValidationFailureWork']
    assert run['results'][0].stage == 'persist' and run['results'][0].reason == 'persist_payload_invalid'
    assert run['meta']['failures'] == [('a', 'InvalidArgument')]


def test_short_capture_recovers_through_the_lane(monkeypatch):
    unit = item('a', 1)
    run = run_lane(monkeypatch, script_for(1), unit=unit)
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['sleeps'].delays == [0.25]


def test_short_capture_exhaustion_books_the_typed_custody_handoff(monkeypatch):
    unit = item('a', 1)
    run = run_lane(monkeypatch, exhaust_script(), unit=unit)
    assert [type(r).__name__ for r in run['results']] == ['ValidationFailureWork']
    assert run['results'][0].stage == 'persist' and run['results'][0].reason == 'persist_payload_invalid'
    assert run['meta']['failures'] == [('a', 'InvalidArgument')]


def test_shadow_unit_recovers_through_the_lane(monkeypatch):
    unit = replace(item(), shadow=True)
    run = run_lane(monkeypatch, script_for(1), unit=unit)
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['sleeps'].delays == [0.25]


def test_shadow_unit_exhaustion_books_the_typed_custody_handoff(monkeypatch):
    unit = replace(item(), shadow=True)
    run = run_lane(monkeypatch, exhaust_script(), unit=unit)
    assert [type(r).__name__ for r in run['results']] == ['ValidationFailureWork']
    assert run['results'][0].stage == 'persist' and run['results'][0].reason == 'persist_payload_invalid'
    assert run['meta']['failures'] == [('a', 'InvalidArgument')]


def test_receipt_unit_recovers_through_the_lane(monkeypatch):
    unit = replace(item(), language_receipt_enabled=True)
    run = run_lane(monkeypatch, script_for(1), unit=unit)
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['sleeps'].delays == [0.25]


def test_receipt_unit_exhaustion_books_the_typed_custody_handoff(monkeypatch):
    unit = replace(item(), language_receipt_enabled=True)
    run = run_lane(monkeypatch, exhaust_script(), unit=unit)
    assert [type(r).__name__ for r in run['results']] == ['ValidationFailureWork']
    assert run['results'][0].stage == 'persist' and run['results'][0].reason == 'persist_payload_invalid'
    assert run['meta']['failures'] == [('a', 'InvalidArgument')]


def test_capture_unit_recovers_through_the_lane(monkeypatch):
    unit = replace(item(), unit_kind='capture_span', conversation_id='conv-1')
    run = run_lane(monkeypatch, script_for(1), unit=unit)
    assert run['results'] and run['results'][0].result_uri == 'OK'
    assert run['sleeps'].delays == [0.25]


def test_capture_unit_exhaustion_books_the_typed_custody_handoff(monkeypatch):
    unit = replace(item(), unit_kind='capture_span', conversation_id='conv-1')
    run = run_lane(monkeypatch, exhaust_script(), unit=unit)
    assert [type(r).__name__ for r in run['results']] == ['ValidationFailureWork']
    assert run['results'][0].stage == 'persist' and run['results'][0].reason == 'persist_payload_invalid'
    assert run['meta']['failures'] == [('a', 'InvalidArgument')]


def test_silent_unit_recovers_through_the_lane(monkeypatch):
    run = run_lane(monkeypatch, script_for(1), vad=lambda samples: [])
    assert run['results'][0].outcome == 'silence'


def test_silent_unit_exhaustion_books_the_typed_custody_handoff(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), vad=lambda samples: [])
    assert [type(r).__name__ for r in run['results']] == ['ValidationFailureWork']
    assert run['results'][0].stage == 'persist' and run['results'][0].reason == 'persist_payload_invalid'
    assert run['meta']['failures'] == [('a', 'InvalidArgument')]


def test_silent_unit_payload_keeps_empty_words_across_strikes(monkeypatch):
    run = run_lane(monkeypatch, script_for(1), vad=lambda samples: [])
    payloads = run['persist'].payloads
    assert payloads[0]['words'] == [] == payloads[1]['words']


def test_wordful_payload_keeps_words_across_strikes(monkeypatch):
    run = run_lane(monkeypatch, script_for(1))
    payloads = run['persist'].payloads
    assert payloads[0]['words'] == payloads[1]['words']
